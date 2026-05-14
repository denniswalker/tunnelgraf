//go:build integration

package integration

import (
	"bytes"
	"context"
	"fmt"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// TestSCP runs end-to-end SCP scenarios against the live docker-compose
// stack. Each sub-test does a roundtrip: upload, then download, then
// byte-compare. Uses fresh local paths under t.TempDir() and unique
// remote paths so sub-tests don't collide on shared container fs.
//
// Unlike the Python suite, these tests don't require `tunnelgraf
// connect` to be running — Go's `scp` opens its own ssh chain via
// ConnectPath, independent of the manager's listeners.
func TestSCP(t *testing.T) {
	t.Run("UploadDownloadFile_Bastion", func(t *testing.T) {
		dir := t.TempDir()
		src := filepath.Join(dir, "upload.txt")
		writeFile(t, src, []byte("scp roundtrip\nline 2\nline 3\n"))

		remote := uniqueRemote(t, "bastion", "upload.txt")
		runSCP(t, src, remote)

		dst := filepath.Join(dir, "downloaded.txt")
		runSCP(t, remote, dst)
		assertSameFile(t, src, dst)
	})

	t.Run("UploadDownloadDirectory_SSHD1", func(t *testing.T) {
		dir := t.TempDir()
		srcDir := filepath.Join(dir, "tree")
		writeFile(t, filepath.Join(srcDir, "file1.txt"), []byte("one"))
		writeFile(t, filepath.Join(srcDir, "file2.txt"), []byte("two"))
		writeFile(t, filepath.Join(srcDir, "sub", "file3.txt"), []byte("three"))
		writeFile(t, filepath.Join(srcDir, "sub", "file4.txt"), []byte("four"))

		remote := uniqueRemote(t, "sshd1", "tree")
		runSCP(t, srcDir, remote)

		dstDir := filepath.Join(dir, "downloaded_tree")
		runSCP(t, remote, dstDir)
		assertSameTree(t, srcDir, dstDir)
	})

	t.Run("BinaryFile_SSHD2", func(t *testing.T) {
		dir := t.TempDir()
		src := filepath.Join(dir, "blob.bin")
		// 8KB of pseudo-binary including all byte values.
		buf := make([]byte, 8*1024)
		for i := range buf {
			buf[i] = byte(i % 256)
		}
		writeFile(t, src, buf)

		remote := uniqueRemote(t, "sshd2", "blob.bin")
		runSCP(t, src, remote)

		dst := filepath.Join(dir, "downloaded.bin")
		runSCP(t, remote, dst)
		assertSameFile(t, src, dst)
	})

	t.Run("LargeFile_Bastion", func(t *testing.T) {
		dir := t.TempDir()
		src := filepath.Join(dir, "big.txt")
		// ~1 MB so we exercise the streaming copy paths but stay quick.
		line := []byte("Large file content used for SCP transfer testing.\n")
		var big bytes.Buffer
		big.Grow(1 << 20)
		for big.Len() < 1<<20 {
			big.Write(line)
		}
		writeFile(t, src, big.Bytes())

		remote := uniqueRemote(t, "bastion", "big.txt")
		runSCP(t, src, remote)

		dst := filepath.Join(dir, "downloaded_big.txt")
		runSCP(t, remote, dst)
		assertSameFile(t, src, dst)
	})

	t.Run("EmptyFile_SSHD1", func(t *testing.T) {
		dir := t.TempDir()
		src := filepath.Join(dir, "empty.txt")
		writeFile(t, src, nil)

		remote := uniqueRemote(t, "sshd1", "empty.txt")
		runSCP(t, src, remote)

		dst := filepath.Join(dir, "downloaded_empty.txt")
		runSCP(t, remote, dst)
		assertSameFile(t, src, dst)
	})

	t.Run("MultiContainer", func(t *testing.T) {
		dir := t.TempDir()
		src := filepath.Join(dir, "multi.txt")
		writeFile(t, src, []byte("the same payload to every hop\n"))

		for _, container := range []string{"bastion", "sshd1", "sshd2"} {
			container := container
			t.Run(container, func(t *testing.T) {
				remote := uniqueRemote(t, container, "multi.txt")
				runSCP(t, src, remote)
				dst := filepath.Join(dir, "downloaded_"+container+".txt")
				runSCP(t, remote, dst)
				assertSameFile(t, src, dst)
			})
		}
	})

	t.Run("Error_LocalPathDoesNotExist", func(t *testing.T) {
		out, err := scpExec(t, "/no/such/file.txt", "bastion:/tmp/should_never_arrive.txt", "")
		if err == nil {
			t.Fatalf("expected error for missing local file; got success\n%s", out)
		}
	})

	t.Run("Error_InvalidTunnelID", func(t *testing.T) {
		dir := t.TempDir()
		src := filepath.Join(dir, "x.txt")
		writeFile(t, src, []byte("payload"))

		out, err := scpExec(t, src, "ghosts:/tmp/x.txt", "")
		if err == nil {
			t.Fatalf("expected error for invalid tunnel id; got success\n%s", out)
		}
		if !strings.Contains(out, "ghosts") && !strings.Contains(out, "not found") {
			t.Errorf("expected error to mention bad id or 'not found'; got: %s", out)
		}
	})
}

// uniqueRemote returns a "<container>:/tmp/<basename>-<nano>" path so
// parallel sub-tests (or repeated runs against a long-lived container)
// don't collide on the shared remote fs.
func uniqueRemote(t *testing.T, container, basename string) string {
	t.Helper()
	stamp := time.Now().UnixNano()
	return fmt.Sprintf("%s:/tmp/tg-itest-%d-%s", container, stamp, basename)
}

// runSCP executes `tunnelgraf scp <source> <destination>` and fails the
// test if it errors. Output is logged so failures are diagnosable.
func runSCP(t *testing.T, source, destination string) {
	t.Helper()
	out, err := scpExec(t, source, destination, "")
	if err != nil {
		t.Fatalf("scp %s -> %s failed: %v\n%s", source, destination, err, out)
	}
}

// scpExec is the side-effect-free form of runSCP — returns the error
// instead of failing the test, so error-path tests can assert on it.
func scpExec(t *testing.T, source, destination, tunnelID string) (string, error) {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()

	args := []string{"-p", profilePath}
	if tunnelID != "" {
		args = append(args, "-t", tunnelID)
	}
	args = append(args, "scp", "--insecure-host-keys", source, destination)

	cmd := exec.CommandContext(ctx, binaryPath, args...)
	cmd.Dir = repoRoot
	out, err := cmd.CombinedOutput()
	t.Logf("scp %s -> %s\n%s", source, destination, out)
	return string(out), err
}

// writeFile writes data to path, creating parent dirs as needed.
func writeFile(t *testing.T, path string, data []byte) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatalf("mkdir %s: %v", filepath.Dir(path), err)
	}
	if err := os.WriteFile(path, data, 0o644); err != nil {
		t.Fatalf("write %s: %v", path, err)
	}
}

// assertSameFile byte-compares two local files.
func assertSameFile(t *testing.T, a, b string) {
	t.Helper()
	ad, err := os.ReadFile(a)
	if err != nil {
		t.Fatalf("read %s: %v", a, err)
	}
	bd, err := os.ReadFile(b)
	if err != nil {
		t.Fatalf("read %s: %v", b, err)
	}
	if !bytes.Equal(ad, bd) {
		t.Fatalf("file content mismatch: %s (%d bytes) != %s (%d bytes)", a, len(ad), b, len(bd))
	}
}

// assertSameTree compares two local directory trees by relative path
// and content. Symlinks and special files are out of scope — we only
// generate regular files in these tests.
func assertSameTree(t *testing.T, want, got string) {
	t.Helper()
	wantFiles := walkFiles(t, want)
	gotFiles := walkFiles(t, got)
	if len(wantFiles) != len(gotFiles) {
		t.Fatalf("file count mismatch: want %d under %s, got %d under %s\nwant=%v\ngot=%v",
			len(wantFiles), want, len(gotFiles), got, sortedKeys(wantFiles), sortedKeys(gotFiles))
	}
	for rel, wantData := range wantFiles {
		gotData, ok := gotFiles[rel]
		if !ok {
			t.Fatalf("missing file in transfer: %s", rel)
		}
		if !bytes.Equal(wantData, gotData) {
			t.Fatalf("content mismatch at %s: want %d bytes, got %d", rel, len(wantData), len(gotData))
		}
	}
}

func walkFiles(t *testing.T, root string) map[string][]byte {
	t.Helper()
	out := map[string][]byte{}
	err := filepath.WalkDir(root, func(p string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() {
			return nil
		}
		rel, err := filepath.Rel(root, p)
		if err != nil {
			return err
		}
		data, err := os.ReadFile(p)
		if err != nil {
			return err
		}
		out[filepath.ToSlash(rel)] = data
		return nil
	})
	if err != nil {
		t.Fatalf("walk %s: %v", root, err)
	}
	return out
}

func sortedKeys(m map[string][]byte) []string {
	out := make([]string, 0, len(m))
	for k := range m {
		out = append(out, k)
	}
	// Tiny stable sort without importing sort just for diagnostics.
	for i := 1; i < len(out); i++ {
		for j := i; j > 0 && out[j-1] > out[j]; j-- {
			out[j-1], out[j] = out[j], out[j-1]
		}
	}
	return out
}
