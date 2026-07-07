package transfer

import (
	"context"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"os"
	"path"
	"path/filepath"
	"time"

	"github.com/pkg/sftp"
	xssh "golang.org/x/crypto/ssh"
)

// Execute opens an SFTP client over conn and performs the transfer
// described by spec. Progress is written to progress (may be nil).
func Execute(ctx context.Context, conn *xssh.Client, spec Spec, progress io.Writer) error {
	sc, err := sftp.NewClient(conn)
	if err != nil {
		return fmt.Errorf("open sftp: %w", err)
	}
	defer func() { _ = sc.Close() }()

	start := time.Now()
	var (
		bytes int64
		label string
	)
	switch spec.Direction {
	case Upload:
		bytes, err = doUpload(ctx, sc, spec.Local, spec.Remote)
		label = fmt.Sprintf("uploaded %s -> %s:%s", spec.Local, spec.TunnelID, spec.Remote)
	case Download:
		bytes, err = doDownload(ctx, sc, spec.Remote, spec.Local)
		label = fmt.Sprintf("downloaded %s:%s -> %s", spec.TunnelID, spec.Remote, spec.Local)
	default:
		return fmt.Errorf("unknown direction: %v", spec.Direction)
	}
	if err != nil {
		return err
	}
	if progress != nil {
		_, _ = fmt.Fprintf(progress, "%s (%d bytes in %s)\n", label, bytes, time.Since(start).Round(time.Millisecond))
	}
	return nil
}

// --- upload ---------------------------------------------------------

func doUpload(ctx context.Context, sc *sftp.Client, local, remote string) (int64, error) {
	info, err := os.Stat(local)
	if err != nil {
		return 0, fmt.Errorf("stat %s: %w", local, err)
	}
	if info.IsDir() {
		return uploadDir(ctx, sc, local, remote)
	}
	// If `remote` exists and is a directory, scp convention is to put
	// the file inside it under its local basename.
	target := resolveRemoteTarget(sc, remote, filepath.Base(local))
	return uploadFile(ctx, sc, local, target, info)
}

func uploadDir(ctx context.Context, sc *sftp.Client, localDir, remoteDir string) (int64, error) {
	// When the user gives an existing remote directory we drop the
	// local directory's basename inside it (scp -r convention).
	if st, err := sc.Stat(remoteDir); err == nil && st.IsDir() {
		remoteDir = path.Join(remoteDir, filepath.Base(localDir))
	}
	if err := sc.MkdirAll(remoteDir); err != nil {
		return 0, fmt.Errorf("mkdir %s: %w", remoteDir, err)
	}

	var total int64
	err := filepath.Walk(localDir, func(p string, info fs.FileInfo, err error) error {
		if err != nil {
			return err
		}
		if ctx.Err() != nil {
			return ctx.Err()
		}
		rel, err := filepath.Rel(localDir, p)
		if err != nil {
			return err
		}
		if rel == "." {
			return nil
		}
		rp := path.Join(remoteDir, filepath.ToSlash(rel))
		if info.IsDir() {
			if err := sc.MkdirAll(rp); err != nil {
				return fmt.Errorf("mkdir %s: %w", rp, err)
			}
			_ = sc.Chmod(rp, info.Mode().Perm())
			return nil
		}
		n, err := uploadFile(ctx, sc, p, rp, info)
		total += n
		return err
	})
	return total, err
}

func uploadFile(ctx context.Context, sc *sftp.Client, local, remote string, info fs.FileInfo) (int64, error) {
	src, err := os.Open(local)
	if err != nil {
		return 0, fmt.Errorf("open %s: %w", local, err)
	}
	defer func() { _ = src.Close() }()

	if parent := path.Dir(remote); parent != "." && parent != "/" {
		_ = sc.MkdirAll(parent)
	}
	dst, err := sc.OpenFile(remote, os.O_WRONLY|os.O_CREATE|os.O_TRUNC)
	if err != nil {
		return 0, fmt.Errorf("create %s: %w", remote, err)
	}
	n, copyErr := copyWithCtx(ctx, dst, src)
	if closeErr := dst.Close(); copyErr == nil && closeErr != nil {
		copyErr = closeErr
	}
	if copyErr != nil {
		return n, fmt.Errorf("write %s: %w", remote, copyErr)
	}
	// Best-effort preservation — fail silently; some SFTP servers
	// reject chtimes / chmod for the authenticated user but we've
	// still moved the bytes successfully.
	_ = sc.Chtimes(remote, info.ModTime(), info.ModTime())
	_ = sc.Chmod(remote, info.Mode().Perm())
	return n, nil
}

// --- download -------------------------------------------------------

func doDownload(ctx context.Context, sc *sftp.Client, remote, local string) (int64, error) {
	info, err := sc.Stat(remote)
	if err != nil {
		return 0, fmt.Errorf("stat %s: %w", remote, err)
	}
	if info.IsDir() {
		return downloadDir(ctx, sc, remote, local)
	}
	target := resolveLocalTarget(local, path.Base(remote))
	return downloadFile(ctx, sc, remote, target, info)
}

func downloadDir(ctx context.Context, sc *sftp.Client, remoteDir, localDir string) (int64, error) {
	if st, err := os.Stat(localDir); err == nil && st.IsDir() {
		localDir = filepath.Join(localDir, path.Base(remoteDir))
	}
	if err := os.MkdirAll(localDir, 0o755); err != nil {
		return 0, fmt.Errorf("mkdir %s: %w", localDir, err)
	}

	var total int64
	w := sc.Walk(remoteDir)
	for w.Step() {
		if err := w.Err(); err != nil {
			return total, fmt.Errorf("walk %s: %w", w.Path(), err)
		}
		if ctx.Err() != nil {
			return total, ctx.Err()
		}
		rp := w.Path()
		rel, err := relPosix(remoteDir, rp)
		if err != nil {
			return total, err
		}
		if rel == "." {
			continue
		}
		lp := filepath.Join(localDir, filepath.FromSlash(rel))
		info := w.Stat()
		if info.IsDir() {
			if err := os.MkdirAll(lp, info.Mode().Perm()); err != nil {
				return total, err
			}
			continue
		}
		n, err := downloadFile(ctx, sc, rp, lp, info)
		total += n
		if err != nil {
			return total, err
		}
	}
	return total, nil
}

func downloadFile(ctx context.Context, sc *sftp.Client, remote, local string, info fs.FileInfo) (int64, error) {
	src, err := sc.Open(remote)
	if err != nil {
		return 0, fmt.Errorf("open %s: %w", remote, err)
	}
	defer func() { _ = src.Close() }()

	if parent := filepath.Dir(local); parent != "." && parent != "/" {
		_ = os.MkdirAll(parent, 0o755)
	}
	dst, err := os.OpenFile(local, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, info.Mode().Perm())
	if err != nil {
		return 0, fmt.Errorf("create %s: %w", local, err)
	}
	n, copyErr := copyWithCtx(ctx, dst, src)
	if closeErr := dst.Close(); copyErr == nil && closeErr != nil {
		copyErr = closeErr
	}
	if copyErr != nil {
		return n, fmt.Errorf("write %s: %w", local, copyErr)
	}
	_ = os.Chtimes(local, info.ModTime(), info.ModTime())
	return n, nil
}

// --- helpers --------------------------------------------------------

// resolveRemoteTarget mirrors scp's "if remote exists and is a dir,
// append basename" rule.
func resolveRemoteTarget(sc *sftp.Client, remote, basename string) string {
	if st, err := sc.Stat(remote); err == nil && st.IsDir() {
		return path.Join(remote, basename)
	}
	return remote
}

// resolveLocalTarget is the mirror of resolveRemoteTarget for the
// local side.
func resolveLocalTarget(local, basename string) string {
	if st, err := os.Stat(local); err == nil && st.IsDir() {
		return filepath.Join(local, basename)
	}
	return local
}

// copyWithCtx is io.Copy that yields periodically to honour ctx.
func copyWithCtx(ctx context.Context, dst io.Writer, src io.Reader) (int64, error) {
	buf := make([]byte, 64*1024)
	var total int64
	for {
		if err := ctx.Err(); err != nil {
			return total, err
		}
		n, err := src.Read(buf)
		if n > 0 {
			w, werr := dst.Write(buf[:n])
			total += int64(w)
			if werr != nil {
				return total, werr
			}
			if w != n {
				return total, io.ErrShortWrite
			}
		}
		if err != nil {
			if errors.Is(err, io.EOF) {
				return total, nil
			}
			return total, err
		}
	}
}

// relPosix returns the POSIX-slash relative path of target under base.
func relPosix(base, target string) (string, error) {
	if target == base {
		return ".", nil
	}
	b := base
	if b == "" || b[len(b)-1] != '/' {
		b += "/"
	}
	if len(target) < len(b) || target[:len(b)] != b {
		return "", fmt.Errorf("%s is not under %s", target, base)
	}
	return target[len(b):], nil
}
