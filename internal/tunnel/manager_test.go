package tunnel

import (
	"context"
	"fmt"
	"io"
	"log/slog"
	"net"
	"os"
	"testing"
	"time"

	"github.com/denniswalker/tunnelgraf/internal/profile"
	tgssh "github.com/denniswalker/tunnelgraf/internal/ssh"
	"github.com/denniswalker/tunnelgraf/internal/testssh"
)

// TestManagerForwardsThroughSSH stands up an in-process SSH server and
// a TCP echo backend, then asks the Manager to tunnel from a local
// port to the backend through the SSH server. If bytes round-trip end
// to end, the tree walker + forwarder are wired correctly.
func TestManagerForwardsThroughSSH(t *testing.T) {
	echoAddr, stopEcho := startEchoServer(t)
	defer stopEcho()

	srv := testssh.Start(t, "test", "hunter2")
	sshHost, sshPort := splitHostPort(t, srv.Addr())
	echoHost, echoPort := splitHostPort(t, echoAddr)

	bindPort := freePort(t)

	root := &profile.Node{
		ID:      "server",
		Host:    sshHost,
		Port:    sshPort,
		SSHUser: "test",
		SSHPass: "hunter2",
		Nexthop: &profile.Node{
			ID:               "echo",
			Host:             echoHost,
			Port:             echoPort,
			LocalBindAddress: "127.0.0.1",
			LocalBindPort:    bindPort,
			Protocol:         "tcp",
		},
	}

	log := slog.New(slog.NewTextHandler(io.Discard, nil))
	hk, err := tgssh.HostKeyCallback("", tgssh.PolicyInsecure, log)
	if err != nil {
		t.Fatalf("host key cb: %v", err)
	}

	mgr := New(root, Options{
		Dialer: &tgssh.Dialer{HostKey: hk, Timeout: 3 * time.Second},
		Log:    log,
	})

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := mgr.Start(ctx); err != nil {
		t.Fatalf("Start: %v", err)
	}
	defer mgr.Stop()

	if got := mgr.TunnelCount(); got != 1 {
		t.Errorf("TunnelCount = %d, want 1", got)
	}

	conn, err := net.Dial("tcp", fmt.Sprintf("127.0.0.1:%d", bindPort))
	if err != nil {
		t.Fatalf("dial local bind: %v", err)
	}
	defer func() { _ = conn.Close() }()
	if _, err := conn.Write([]byte("hello\n")); err != nil {
		t.Fatalf("write: %v", err)
	}
	buf := make([]byte, 6)
	if err := conn.SetReadDeadline(time.Now().Add(2 * time.Second)); err != nil {
		t.Fatalf("deadline: %v", err)
	}
	if _, err := io.ReadFull(conn, buf); err != nil {
		t.Fatalf("read: %v", err)
	}
	if string(buf) != "hello\n" {
		t.Errorf("round-trip = %q, want %q", buf, "hello\n")
	}
}

// TestManagerTOFUAppendsHostKey verifies that the accept-new host-key
// policy writes the server's key to known_hosts on first connect.
func TestManagerTOFUAppendsHostKey(t *testing.T) {
	_, stopEcho := startEchoServer(t)
	defer stopEcho()

	srv := testssh.Start(t, "u", "p")
	sshHost, sshPort := splitHostPort(t, srv.Addr())

	root := &profile.Node{
		ID: "server", Host: sshHost, Port: sshPort,
		SSHUser: "u", SSHPass: "p",
		Nexthop: &profile.Node{
			ID: "leaf", Host: "127.0.0.1", Port: 1,
			LocalBindAddress: "127.0.0.1", LocalBindPort: freePort(t),
		},
	}
	khPath := t.TempDir() + "/known_hosts"

	log := slog.New(slog.NewTextHandler(io.Discard, nil))
	hk, err := tgssh.HostKeyCallback(khPath, tgssh.PolicyAcceptNew, log)
	if err != nil {
		t.Fatalf("host key cb: %v", err)
	}

	mgr := New(root, Options{Dialer: &tgssh.Dialer{HostKey: hk}, Log: log})
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	if err := mgr.Start(ctx); err != nil {
		t.Fatalf("Start: %v", err)
	}
	defer mgr.Stop()

	b, err := os.ReadFile(khPath)
	if err != nil {
		t.Fatalf("read known_hosts: %v", err)
	}
	if len(b) == 0 {
		t.Fatalf("known_hosts is empty; TOFU did not write")
	}
}

// --- shared helpers ------------------------------------------------

func startEchoServer(t *testing.T) (string, func()) {
	t.Helper()
	lis, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	go func() {
		for {
			c, err := lis.Accept()
			if err != nil {
				return
			}
			go func(c net.Conn) {
				defer func() { _ = c.Close() }()
				_, _ = io.Copy(c, c)
			}(c)
		}
	}()
	return lis.Addr().String(), func() { _ = lis.Close() }
}

func splitHostPort(t *testing.T, addr string) (string, int) {
	t.Helper()
	host, portStr, err := net.SplitHostPort(addr)
	if err != nil {
		t.Fatalf("split %s: %v", addr, err)
	}
	var port int
	if _, err := fmt.Sscanf(portStr, "%d", &port); err != nil {
		t.Fatalf("parse port %s: %v", portStr, err)
	}
	return host, port
}

func freePort(t *testing.T) int {
	t.Helper()
	lis, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("reserve port: %v", err)
	}
	port := lis.Addr().(*net.TCPAddr).Port
	_ = lis.Close()
	return port
}
