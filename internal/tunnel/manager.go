// Package tunnel walks a profile tree, opens an SSH client for every
// interior node, and runs a local forwarder per child so the whole
// graph is reachable from localhost. When an SSH client drops, the
// per-node supervisor reconnects with exponential backoff; existing
// listeners stay up across drops and serve the new client once it's
// back.
package tunnel

import (
	"context"
	"fmt"
	"log/slog"
	"net"
	"strconv"
	"sync"

	"github.com/denniswalker/tunnelgraf/internal/profile"
	tgssh "github.com/denniswalker/tunnelgraf/internal/ssh"
)

// Options configures a Manager.
type Options struct {
	Dialer *tgssh.Dialer
	Log    *slog.Logger
	// Events, if non-nil, receives state transitions for each node.
	// Emits are non-blocking and drop when the subscriber is slow.
	Events chan<- Event
}

// Manager owns the set of nodeClients and local listeners spun up
// from a profile. Concurrency-safe: Start may run on one goroutine
// while Stop runs on another (the signal handler).
type Manager struct {
	root *profile.Node
	opts Options

	ctx    context.Context
	cancel context.CancelFunc

	mu        sync.Mutex
	clients   []*nodeClient // tree-walk order; parents before children
	listeners []net.Listener
	closed    bool
	wg        sync.WaitGroup
}

// New returns a Manager ready to Start.
func New(root *profile.Node, opts Options) *Manager {
	if opts.Log == nil {
		opts.Log = slog.Default()
	}
	return &Manager{root: root, opts: opts}
}

// Start brings up the entire tunnel tree. Each interior node dials
// once synchronously — any failure aborts Start (and tears down what
// it already built). After Start returns, supervisors keep the
// clients alive in background goroutines; Stop ends them.
func (m *Manager) Start(ctx context.Context) error {
	// Derive our own context so Stop can cancel supervisors even if
	// the caller's context is still alive.
	m.ctx, m.cancel = context.WithCancel(context.Background())

	// Build nodeClients and connect them in tree order so each child
	// finds its parent already connected.
	if err := m.build(ctx, m.root, nil); err != nil {
		m.Stop()
		return err
	}

	// Kick off supervisors.
	for _, nc := range m.clients {
		nc := nc
		m.wg.Add(1)
		go func() {
			defer m.wg.Done()
			nc.supervise(m.ctx)
		}()
	}

	// Open local listeners for every child of every interior node.
	if err := m.startAllListeners(ctx); err != nil {
		m.Stop()
		return err
	}
	return nil
}

// build recurses through the tree, creating nodeClients for every
// interior node and performing the initial handshake.
func (m *Manager) build(ctx context.Context, node *profile.Node, parent *nodeClient) error {
	if len(node.Children()) == 0 {
		return nil // leaves need no client
	}
	nc := newNodeClient(node, parent, m.opts.Dialer, m.opts.Events, m.opts.Log)
	m.opts.Log.Info("dialing", "node", node.ID, "host", node.Host, "port", node.Port)
	if err := nc.connect(ctx); err != nil {
		return fmt.Errorf("connect %s: %w", node.ID, err)
	}

	m.mu.Lock()
	m.clients = append(m.clients, nc)
	m.mu.Unlock()

	for _, child := range node.Children() {
		if err := m.build(ctx, child, nc); err != nil {
			return err
		}
	}
	return nil
}

// startAllListeners opens a local listener for every child of every
// interior node. Listeners are independent of ssh.Clients — they
// survive reconnects.
func (m *Manager) startAllListeners(ctx context.Context) error {
	for _, nc := range m.clients {
		for _, child := range nc.node.Children() {
			if err := m.startForward(ctx, nc, child); err != nil {
				return err
			}
		}
	}
	return nil
}

func (m *Manager) startForward(ctx context.Context, parent *nodeClient, child *profile.Node) error {
	local := net.JoinHostPort(child.LocalBindAddress, strconv.Itoa(child.LocalBindPort))
	remote := net.JoinHostPort(child.Host, strconv.Itoa(child.Port))

	lc := net.ListenConfig{}
	lis, err := lc.Listen(ctx, "tcp", local)
	if err != nil {
		return fmt.Errorf("listen %s: %w", local, err)
	}

	m.mu.Lock()
	m.listeners = append(m.listeners, lis)
	m.mu.Unlock()

	m.opts.Log.Info("tunnel up", "id", child.ID, "local", local, "remote", remote)

	m.wg.Add(1)
	go func() {
		defer m.wg.Done()
		m.acceptLoop(lis, parent, remote, child.ID)
	}()
	return nil
}

func (m *Manager) acceptLoop(lis net.Listener, parent *nodeClient, remote, id string) {
	for {
		local, err := lis.Accept()
		if err != nil {
			if m.isClosed() {
				return
			}
			m.opts.Log.Error("accept failed", "id", id, "err", err)
			return
		}
		m.wg.Add(1)
		go func() {
			defer m.wg.Done()
			m.pipe(local, parent, remote, id)
		}()
	}
}

// pipe reads parent.Current() at dial time so reconnects are
// transparent: each new accepted connection runs through whichever
// ssh.Client is currently up.
func (m *Manager) pipe(local net.Conn, parent *nodeClient, remote, id string) {
	defer func() { _ = local.Close() }()
	via := parent.Current()
	if via == nil {
		m.opts.Log.Warn("upstream not connected; dropping accept", "child", id)
		return
	}
	upstream, err := via.Dial("tcp", remote)
	if err != nil {
		m.opts.Log.Warn("upstream dial failed", "id", id, "err", err)
		return
	}
	defer func() { _ = upstream.Close() }()
	proxyBoth(local, upstream)
}

// Stop closes listeners (ending new accepts), cancels supervisors
// (ending reconnect loops), closes current clients (ending in-flight
// pipes), and waits for everything to drain. Idempotent.
func (m *Manager) Stop() {
	m.mu.Lock()
	if m.closed {
		m.mu.Unlock()
		return
	}
	m.closed = true
	listeners := m.listeners
	clients := m.clients
	m.mu.Unlock()

	if m.cancel != nil {
		m.cancel()
	}
	for _, lis := range listeners {
		_ = lis.Close()
	}
	for _, nc := range clients {
		nc.close()
	}
	m.wg.Wait()
}

func (m *Manager) isClosed() bool {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.closed
}

// TunnelCount returns the number of live local forwarders. Useful for
// status output and tests.
func (m *Manager) TunnelCount() int {
	m.mu.Lock()
	defer m.mu.Unlock()
	return len(m.listeners)
}
