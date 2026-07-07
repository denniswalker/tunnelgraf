package tunnel

import (
	"bytes"
	"context"
	"errors"
	"io"
	"log/slog"
	"testing"
	"time"

	xssh "golang.org/x/crypto/ssh"

	"github.com/denniswalker/tunnelgraf/internal/profile"
	tgssh "github.com/denniswalker/tunnelgraf/internal/ssh"
	"github.com/denniswalker/tunnelgraf/internal/testssh"
)

func TestConnectPathDirectTarget(t *testing.T) {
	srv := testssh.Start(t, "u", "p")
	host, port := splitHostPort(t, srv.Addr())

	root := &profile.Node{ID: "target", Host: host, Port: port, SSHUser: "u", SSHPass: "p"}

	log := slog.New(slog.NewTextHandler(io.Discard, nil))
	hk, err := tgssh.HostKeyCallback("", tgssh.PolicyInsecure, log)
	if err != nil {
		t.Fatalf("hk: %v", err)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	h, err := ConnectPath(ctx, root, "target", &tgssh.Dialer{HostKey: hk})
	if err != nil {
		t.Fatalf("ConnectPath: %v", err)
	}
	defer h.Close()

	if out := runExec(t, h.Target, "hello world"); out != "hello world\n" {
		t.Errorf("exec output = %q, want %q", out, "hello world\n")
	}
}

func TestConnectPathThroughBastion(t *testing.T) {
	leaf := testssh.Start(t, "u", "p")
	leafHost, leafPort := splitHostPort(t, leaf.Addr())

	bastion := testssh.Start(t, "u", "p")
	bastionHost, bastionPort := splitHostPort(t, bastion.Addr())

	root := &profile.Node{
		ID: "bastion", Host: bastionHost, Port: bastionPort, SSHUser: "u", SSHPass: "p",
		Nexthop: &profile.Node{
			ID: "leaf", Host: leafHost, Port: leafPort, SSHUser: "u", SSHPass: "p",
			LocalBindAddress: "127.0.0.1", LocalBindPort: freePort(t),
		},
	}

	log := slog.New(slog.NewTextHandler(io.Discard, nil))
	hk, err := tgssh.HostKeyCallback("", tgssh.PolicyInsecure, log)
	if err != nil {
		t.Fatalf("hk: %v", err)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	h, err := ConnectPath(ctx, root, "leaf", &tgssh.Dialer{HostKey: hk})
	if err != nil {
		t.Fatalf("ConnectPath: %v", err)
	}
	defer h.Close()

	if out := runExec(t, h.Target, "marker"); out != "marker\n" {
		t.Errorf("output = %q", out)
	}
}

func TestConnectPathExitStatusPropagates(t *testing.T) {
	srv := testssh.Start(t, "u", "p")
	host, port := splitHostPort(t, srv.Addr())

	root := &profile.Node{ID: "t", Host: host, Port: port, SSHUser: "u", SSHPass: "p"}

	log := slog.New(slog.NewTextHandler(io.Discard, nil))
	hk, err := tgssh.HostKeyCallback("", tgssh.PolicyInsecure, log)
	if err != nil {
		t.Fatalf("hk: %v", err)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	h, err := ConnectPath(ctx, root, "t", &tgssh.Dialer{HostKey: hk})
	if err != nil {
		t.Fatalf("ConnectPath: %v", err)
	}
	defer h.Close()

	session, err := h.Target.NewSession()
	if err != nil {
		t.Fatalf("session: %v", err)
	}
	defer func() { _ = session.Close() }()

	err = session.Run("false")
	var exitErr *xssh.ExitError
	if !errors.As(err, &exitErr) {
		t.Fatalf("expected ExitError, got %v", err)
	}
	if exitErr.ExitStatus() != 1 {
		t.Errorf("exit status = %d, want 1", exitErr.ExitStatus())
	}
}

func TestConnectPathTargetNotFound(t *testing.T) {
	root := &profile.Node{ID: "root", Host: "127.0.0.1", Port: 1}
	_, err := ConnectPath(context.Background(), root, "missing", &tgssh.Dialer{})
	if err == nil {
		t.Fatal("expected error for missing target")
	}
}

func runExec(t *testing.T, client *xssh.Client, cmdline string) string {
	t.Helper()
	session, err := client.NewSession()
	if err != nil {
		t.Fatalf("session: %v", err)
	}
	defer func() { _ = session.Close() }()
	var out bytes.Buffer
	session.Stdout = &out
	if err := session.Run(cmdline); err != nil {
		t.Fatalf("run %q: %v", cmdline, err)
	}
	return out.String()
}
