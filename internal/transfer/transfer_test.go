package transfer

import (
	"bytes"
	"context"
	"io"
	"log/slog"
	"net"
	"os"
	"path/filepath"
	"strconv"
	"testing"
	"time"

	xssh "golang.org/x/crypto/ssh"

	"github.com/denniswalker/tunnelgraf/internal/profile"
	tgssh "github.com/denniswalker/tunnelgraf/internal/ssh"
	"github.com/denniswalker/tunnelgraf/internal/testssh"
)

func TestExecuteUploadDownloadFile(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	client := dialTestServer(t)
	dir := t.TempDir()

	// Upload
	srcPath := filepath.Join(dir, "hello.txt")
	want := []byte("hello over sftp\n")
	if err := os.WriteFile(srcPath, want, 0o644); err != nil {
		t.Fatalf("write src: %v", err)
	}
	dstPath := filepath.Join(dir, "remote.txt")

	var buf bytes.Buffer
	err := Execute(ctx, client, Spec{
		TunnelID:  "test",
		Local:     srcPath,
		Remote:    dstPath,
		Direction: Upload,
	}, &buf)
	if err != nil {
		t.Fatalf("upload: %v", err)
	}
	got, err := os.ReadFile(dstPath)
	if err != nil {
		t.Fatalf("read dst: %v", err)
	}
	if !bytes.Equal(got, want) {
		t.Errorf("uploaded contents = %q, want %q", got, want)
	}

	// Download back into a fresh path
	roundTripPath := filepath.Join(dir, "round_trip.txt")
	if err := Execute(ctx, client, Spec{
		TunnelID:  "test",
		Remote:    dstPath,
		Local:     roundTripPath,
		Direction: Download,
	}, io.Discard); err != nil {
		t.Fatalf("download: %v", err)
	}
	got, err = os.ReadFile(roundTripPath)
	if err != nil {
		t.Fatalf("read round-trip: %v", err)
	}
	if !bytes.Equal(got, want) {
		t.Errorf("downloaded contents = %q, want %q", got, want)
	}
}

func TestExecuteUploadDirectoryRecursive(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	client := dialTestServer(t)
	root := t.TempDir()

	// Build a small tree: src/a.txt, src/sub/b.txt, src/sub/c.bin
	src := filepath.Join(root, "src")
	mustMkdirAll(t, filepath.Join(src, "sub"))
	mustWriteFile(t, filepath.Join(src, "a.txt"), "alpha")
	mustWriteFile(t, filepath.Join(src, "sub", "b.txt"), "bravo")
	mustWriteFile(t, filepath.Join(src, "sub", "c.bin"), "charlie")

	dst := filepath.Join(root, "dst")

	if err := Execute(ctx, client, Spec{
		TunnelID:  "test",
		Local:     src,
		Remote:    dst,
		Direction: Upload,
	}, io.Discard); err != nil {
		t.Fatalf("upload dir: %v", err)
	}

	// All three files should show up under dst/ with matching contents.
	checkFile(t, filepath.Join(dst, "a.txt"), "alpha")
	checkFile(t, filepath.Join(dst, "sub", "b.txt"), "bravo")
	checkFile(t, filepath.Join(dst, "sub", "c.bin"), "charlie")
}

func TestExecuteDownloadDirectoryRecursive(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	client := dialTestServer(t)
	root := t.TempDir()

	remote := filepath.Join(root, "remote")
	mustMkdirAll(t, filepath.Join(remote, "nested"))
	mustWriteFile(t, filepath.Join(remote, "top.txt"), "top")
	mustWriteFile(t, filepath.Join(remote, "nested", "inner.txt"), "inner")

	local := filepath.Join(root, "local")

	if err := Execute(ctx, client, Spec{
		TunnelID:  "test",
		Remote:    remote,
		Local:     local,
		Direction: Download,
	}, io.Discard); err != nil {
		t.Fatalf("download dir: %v", err)
	}
	checkFile(t, filepath.Join(local, "top.txt"), "top")
	checkFile(t, filepath.Join(local, "nested", "inner.txt"), "inner")
}

func TestExecutePreservesMode(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	client := dialTestServer(t)
	dir := t.TempDir()
	src := filepath.Join(dir, "exec.sh")
	if err := os.WriteFile(src, []byte("#!/bin/sh\necho hi\n"), 0o755); err != nil {
		t.Fatalf("write: %v", err)
	}
	dst := filepath.Join(dir, "exec_dst.sh")

	if err := Execute(ctx, client, Spec{
		TunnelID:  "test",
		Local:     src,
		Remote:    dst,
		Direction: Upload,
	}, io.Discard); err != nil {
		t.Fatalf("upload: %v", err)
	}
	info, err := os.Stat(dst)
	if err != nil {
		t.Fatalf("stat dst: %v", err)
	}
	if got := info.Mode().Perm() & 0o111; got == 0 {
		t.Errorf("execute bit dropped: mode=%o", info.Mode().Perm())
	}
}

// --- helpers -------------------------------------------------------

func dialTestServer(t *testing.T) *xssh.Client {
	t.Helper()
	srv := testssh.Start(t, "u", "p")
	log := slog.New(slog.NewTextHandler(io.Discard, nil))
	hk, err := tgssh.HostKeyCallback("", tgssh.PolicyInsecure, log)
	if err != nil {
		t.Fatalf("hostkey cb: %v", err)
	}

	host, port := splitHostPort(t, srv.Addr())
	node := &profile.Node{
		ID: "test", Host: host, Port: port,
		SSHUser: "u", SSHPass: "p",
	}
	dialer := &tgssh.Dialer{HostKey: hk, Timeout: 3 * time.Second}
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	c, err := dialer.Dial(ctx, node)
	if err != nil {
		t.Fatalf("dial: %v", err)
	}
	t.Cleanup(func() { _ = c.Close() })
	return c
}

func splitHostPort(t *testing.T, addr string) (string, int) {
	t.Helper()
	host, portStr, err := net.SplitHostPort(addr)
	if err != nil {
		t.Fatalf("split %s: %v", addr, err)
	}
	port, err := strconv.Atoi(portStr)
	if err != nil {
		t.Fatalf("parse port %s: %v", portStr, err)
	}
	return host, port
}

func mustMkdirAll(t *testing.T, p string) {
	t.Helper()
	if err := os.MkdirAll(p, 0o755); err != nil {
		t.Fatalf("mkdir %s: %v", p, err)
	}
}

func mustWriteFile(t *testing.T, p, content string) {
	t.Helper()
	if err := os.WriteFile(p, []byte(content), 0o644); err != nil {
		t.Fatalf("write %s: %v", p, err)
	}
}

func checkFile(t *testing.T, p, want string) {
	t.Helper()
	b, err := os.ReadFile(p)
	if err != nil {
		t.Fatalf("read %s: %v", p, err)
	}
	if string(b) != want {
		t.Errorf("%s = %q, want %q", p, b, want)
	}
}
