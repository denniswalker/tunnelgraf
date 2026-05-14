package tunnel

import (
	"context"
	"fmt"
	"io"
	"log/slog"
	"net"
	"testing"
	"time"

	"github.com/denniswalker/tunnelgraf/internal/profile"
	tgssh "github.com/denniswalker/tunnelgraf/internal/ssh"
	"github.com/denniswalker/tunnelgraf/internal/testssh"
)

// TestManagerReconnectsAfterServerRestart brings a tunnel up, kills
// the SSH server hard (drops all connections), and verifies the
// Manager emits the correct event sequence and resumes forwarding
// once the server comes back on the same port.
func TestManagerReconnectsAfterServerRestart(t *testing.T) {
	echoAddr, stopEcho := startEchoServer(t)
	defer stopEcho()
	echoHost, echoPort := splitHostPort(t, echoAddr)

	// Reserve a port, then bind the server to it so we can restart.
	sshPort := freePort(t)
	sshAddr := fmt.Sprintf("127.0.0.1:%d", sshPort)
	srv := testssh.StartAt(t, sshAddr, "u", "p")

	bindPort := freePort(t)
	root := &profile.Node{
		ID: "server", Host: "127.0.0.1", Port: sshPort,
		SSHUser: "u", SSHPass: "p",
		Nexthop: &profile.Node{
			ID: "echo", Host: echoHost, Port: echoPort,
			LocalBindAddress: "127.0.0.1", LocalBindPort: bindPort,
		},
	}

	events := make(chan Event, 32)
	log := slog.New(slog.NewTextHandler(io.Discard, nil))
	hk, err := tgssh.HostKeyCallback("", tgssh.PolicyInsecure, log)
	if err != nil {
		t.Fatalf("hk: %v", err)
	}
	mgr := New(root, Options{
		Dialer: &tgssh.Dialer{HostKey: hk, Timeout: 2 * time.Second},
		Log:    log,
		Events: events,
	})
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	if err := mgr.Start(ctx); err != nil {
		t.Fatalf("Start: %v", err)
	}
	defer mgr.Stop()

	// Initial forward should work.
	if err := echoRoundTrip(bindPort, "first\n"); err != nil {
		t.Fatalf("initial round-trip: %v", err)
	}

	// Drain events received so far so we only observe post-kill ones.
	drain(events)

	// Kill the SSH server hard. Existing client's Wait() should
	// return, triggering EventDown and a reconnect loop.
	srv.Close()

	if !waitForEvent(t, events, EventDown, 3*time.Second) {
		t.Fatal("never saw EventDown after server kill")
	}

	// Bring the server back on the same port. Expect reconnect.
	testssh.StartAt(t, sshAddr, "u", "p")

	if !waitForEvent(t, events, EventConnected, 10*time.Second) {
		t.Fatal("never saw EventConnected after server restart")
	}

	// New connections through the tunnel should work again. Retry
	// briefly — the reconnect event fires a hair before the listener
	// is ready to pipe through the new client.
	var lastErr error
	deadline := time.Now().Add(3 * time.Second)
	for time.Now().Before(deadline) {
		if err := echoRoundTrip(bindPort, "second\n"); err == nil {
			lastErr = nil
			break
		} else {
			lastErr = err
		}
		time.Sleep(100 * time.Millisecond)
	}
	if lastErr != nil {
		t.Fatalf("forwarding did not recover: %v", lastErr)
	}
}

func echoRoundTrip(port int, msg string) error {
	conn, err := net.DialTimeout("tcp", fmt.Sprintf("127.0.0.1:%d", port), 2*time.Second)
	if err != nil {
		return err
	}
	defer func() { _ = conn.Close() }()
	if err := conn.SetDeadline(time.Now().Add(2 * time.Second)); err != nil {
		return err
	}
	if _, err := conn.Write([]byte(msg)); err != nil {
		return err
	}
	buf := make([]byte, len(msg))
	if _, err := io.ReadFull(conn, buf); err != nil {
		return err
	}
	if string(buf) != msg {
		return fmt.Errorf("echo mismatch: got %q, want %q", buf, msg)
	}
	return nil
}

func drain(events chan Event) {
	for {
		select {
		case <-events:
		default:
			return
		}
	}
}

func waitForEvent(t *testing.T, events chan Event, want EventKind, timeout time.Duration) bool {
	t.Helper()
	deadline := time.After(timeout)
	for {
		select {
		case e := <-events:
			if e.Kind == want {
				return true
			}
		case <-deadline:
			return false
		}
	}
}
