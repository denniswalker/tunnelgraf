// Package testssh is a tiny in-process SSH server used by tests in
// other packages. It's regular (non-test) code so it can be imported;
// it takes a *testing.T so setup failures are reported at the call
// site. The server accepts password auth for a single user/pass pair
// and serves:
//
//   - direct-tcpip channels (for tunnel forwarding tests)
//   - session channels with exec requests (for command tests)
//   - session channels with the "sftp" subsystem (for transfer tests)
package testssh

import (
	"crypto/rand"
	"crypto/rsa"
	"errors"
	"fmt"
	"io"
	"net"
	"sync"
	"testing"
	"time"

	"github.com/pkg/sftp"
	xssh "golang.org/x/crypto/ssh"
)

// Server is a running SSH server bound to a local port.
type Server struct {
	listener net.Listener
	cfg      *xssh.ServerConfig

	mu     sync.Mutex
	conns  []net.Conn
	closed bool
}

// Addr returns the host:port the server is listening on.
func (s *Server) Addr() string { return s.listener.Addr().String() }

// Close stops accepting new connections and forcibly drops every
// in-flight connection. Useful for simulating a server outage in
// reconnect tests.
func (s *Server) Close() {
	s.mu.Lock()
	if s.closed {
		s.mu.Unlock()
		return
	}
	s.closed = true
	conns := s.conns
	s.conns = nil
	s.mu.Unlock()
	_ = s.listener.Close()
	for _, c := range conns {
		_ = c.Close()
	}
}

// Start starts an SSH server on an ephemeral port. The returned
// server is auto-closed when the test finishes via t.Cleanup.
func Start(t *testing.T, user, password string) *Server {
	return StartAt(t, "127.0.0.1:0", user, password)
}

// StartAt is Start with a caller-chosen bind address. Pass
// "127.0.0.1:<port>" to bind a specific port — useful for reconnect
// tests that need to bring the same endpoint back up after a shutdown.
func StartAt(t *testing.T, addr, user, password string) *Server {
	t.Helper()

	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("rsa.GenerateKey: %v", err)
	}
	signer, err := xssh.NewSignerFromKey(key)
	if err != nil {
		t.Fatalf("ssh signer: %v", err)
	}

	cfg := &xssh.ServerConfig{
		PasswordCallback: func(meta xssh.ConnMetadata, pw []byte) (*xssh.Permissions, error) {
			if meta.User() == user && string(pw) == password {
				return &xssh.Permissions{}, nil
			}
			return nil, errors.New("bad credentials")
		},
	}
	cfg.AddHostKey(signer)

	lis, err := net.Listen("tcp", addr)
	if err != nil {
		t.Fatalf("listen %s: %v", addr, err)
	}

	s := &Server{listener: lis, cfg: cfg}
	t.Cleanup(s.Close)
	go s.acceptLoop()
	return s
}

func (s *Server) acceptLoop() {
	for {
		conn, err := s.listener.Accept()
		if err != nil {
			return
		}
		s.mu.Lock()
		if s.closed {
			s.mu.Unlock()
			_ = conn.Close()
			return
		}
		s.conns = append(s.conns, conn)
		s.mu.Unlock()
		go s.handleConn(conn)
	}
}

func (s *Server) handleConn(raw net.Conn) {
	defer func() { _ = raw.Close() }()
	sc, chans, reqs, err := xssh.NewServerConn(raw, s.cfg)
	if err != nil {
		return
	}
	defer func() { _ = sc.Close() }()
	go xssh.DiscardRequests(reqs)
	for nc := range chans {
		switch nc.ChannelType() {
		case "direct-tcpip":
			go handleDirectTCPIP(nc)
		case "session":
			go handleSession(nc)
		default:
			_ = nc.Reject(xssh.UnknownChannelType, "unsupported")
		}
	}
}

// --- direct-tcpip (port forwarding tests) --------------------------

func handleDirectTCPIP(nc xssh.NewChannel) {
	var payload struct {
		Host       string
		Port       uint32
		Origin     string
		OriginPort uint32
	}
	if err := xssh.Unmarshal(nc.ExtraData(), &payload); err != nil {
		_ = nc.Reject(xssh.ConnectionFailed, "bad payload")
		return
	}
	ch, reqs, err := nc.Accept()
	if err != nil {
		return
	}
	go xssh.DiscardRequests(reqs)
	defer func() { _ = ch.Close() }()

	target := net.JoinHostPort(payload.Host, fmt.Sprint(payload.Port))
	upstream, err := net.DialTimeout("tcp", target, 2*time.Second)
	if err != nil {
		return
	}
	defer func() { _ = upstream.Close() }()

	done := make(chan struct{}, 2)
	go func() { _, _ = io.Copy(upstream, ch); done <- struct{}{} }()
	go func() { _, _ = io.Copy(ch, upstream); done <- struct{}{} }()
	<-done
}

// --- session (exec + sftp subsystem) -------------------------------

func handleSession(nc xssh.NewChannel) {
	ch, reqs, err := nc.Accept()
	if err != nil {
		return
	}
	defer func() { _ = ch.Close() }()

	for req := range reqs {
		switch req.Type {
		case "exec":
			var p struct{ Command string }
			if err := xssh.Unmarshal(req.Payload, &p); err != nil {
				_ = req.Reply(false, nil)
				continue
			}
			_ = req.Reply(true, nil)
			runFakeExec(ch, p.Command)
			return
		case "subsystem":
			var p struct{ Name string }
			if err := xssh.Unmarshal(req.Payload, &p); err != nil || p.Name != "sftp" {
				_ = req.Reply(false, nil)
				continue
			}
			_ = req.Reply(true, nil)
			serveSFTP(ch)
			return
		case "pty-req", "env", "shell", "window-change":
			_ = req.Reply(true, nil)
		default:
			_ = req.Reply(false, nil)
		}
	}
}

// runFakeExec implements a minimal set of pretend commands so tests
// can cover exit-code propagation:
//
//   - "true"  -> exit 0, no output
//   - "false" -> exit 1, no output
//   - anything else -> writes the command line + "\n" to stdout, exit 0
func runFakeExec(ch xssh.Channel, cmdline string) {
	status := uint32(0)
	switch cmdline {
	case "true":
	case "false":
		status = 1
	default:
		_, _ = io.WriteString(ch, cmdline+"\n")
	}
	var buf [4]byte
	buf[0] = byte(status >> 24)
	buf[1] = byte(status >> 16)
	buf[2] = byte(status >> 8)
	buf[3] = byte(status)
	_, _ = ch.SendRequest("exit-status", false, buf[:])
}

// serveSFTP runs a real pkg/sftp server on the channel. Uses the
// process's actual filesystem, which is fine in tests because callers
// target t.TempDir() locations.
func serveSFTP(ch xssh.Channel) {
	srv, err := sftp.NewServer(ch)
	if err != nil {
		return
	}
	_ = srv.Serve()
	_ = srv.Close()
}
