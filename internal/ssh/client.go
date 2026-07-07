package ssh

import (
	"context"
	"fmt"
	"net"
	"strconv"
	"time"

	xssh "golang.org/x/crypto/ssh"

	"github.com/denniswalker/tunnelgraf/internal/profile"
)

// Client is an ssh.Client opened against a specific profile.Node.
type Client = xssh.Client

// Dialer opens ssh.Clients, either directly or tunneled through a
// parent client. Passing the same HostKeyCallback into every dial keeps
// known_hosts state consistent across the tree.
type Dialer struct {
	HostKey xssh.HostKeyCallback
	Timeout time.Duration
}

// Dial opens a direct connection to the node's host:port and returns
// an authenticated ssh.Client.
func (d *Dialer) Dial(ctx context.Context, node *profile.Node) (*Client, error) {
	cfg, err := d.clientConfig(node)
	if err != nil {
		return nil, err
	}
	addr := net.JoinHostPort(node.Host, strconv.Itoa(node.Port))

	var nd net.Dialer
	nd.Timeout = d.timeout()
	conn, err := nd.DialContext(ctx, "tcp", addr)
	if err != nil {
		return nil, fmt.Errorf("tcp dial %s: %w", addr, err)
	}
	return newClientOnConn(conn, addr, cfg)
}

// DialThrough opens a connection to node.Host:node.Port by first
// opening a channel inside parent's existing ssh.Client, then running
// the ssh handshake on top. This is equivalent to ProxyJump / nested
// tunnels without re-exposing a listener on the local side.
func (d *Dialer) DialThrough(ctx context.Context, parent *Client, node *profile.Node) (*Client, error) {
	cfg, err := d.clientConfig(node)
	if err != nil {
		return nil, err
	}
	addr := net.JoinHostPort(node.Host, strconv.Itoa(node.Port))

	// parent.DialContext requires Go 1.22+ x/crypto/ssh; fall back to
	// Dial since we don't need cancellation inside the handshake yet.
	conn, err := parent.Dial("tcp", addr)
	if err != nil {
		return nil, fmt.Errorf("dial %s through parent: %w", addr, err)
	}
	return newClientOnConn(conn, addr, cfg)
}

func (d *Dialer) timeout() time.Duration {
	if d.Timeout == 0 {
		return 15 * time.Second
	}
	return d.Timeout
}

func (d *Dialer) clientConfig(node *profile.Node) (*xssh.ClientConfig, error) {
	methods, err := authMethods(node)
	if err != nil {
		return nil, err
	}
	if d.HostKey == nil {
		return nil, fmt.Errorf("host-key callback required")
	}
	return &xssh.ClientConfig{
		User:            node.SSHUser,
		Auth:            methods,
		HostKeyCallback: d.HostKey,
		Timeout:         d.timeout(),
	}, nil
}

func newClientOnConn(conn net.Conn, addr string, cfg *xssh.ClientConfig) (*Client, error) {
	c, chans, reqs, err := xssh.NewClientConn(conn, addr, cfg)
	if err != nil {
		_ = conn.Close()
		return nil, fmt.Errorf("ssh handshake %s: %w", addr, err)
	}
	return xssh.NewClient(c, chans, reqs), nil
}
