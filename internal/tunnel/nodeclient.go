package tunnel

import (
	"context"
	"errors"
	"log/slog"
	"sync"
	"time"

	"github.com/denniswalker/tunnelgraf/internal/profile"
	tgssh "github.com/denniswalker/tunnelgraf/internal/ssh"
)

// nodeClient owns a supervised *ssh.Client for one interior node.
// On drop, it reconnects with exponential backoff. Concurrent readers
// of the current client are handled by a RWMutex + a re-created ready
// channel so waiters don't busy-loop.
type nodeClient struct {
	node   *profile.Node
	parent *nodeClient // nil for the root node
	dialer *tgssh.Dialer
	log    *slog.Logger
	events chan<- Event

	mu      sync.RWMutex
	current *tgssh.Client
	ready   chan struct{} // open while current==nil; closed while current!=nil
}

func newNodeClient(node *profile.Node, parent *nodeClient, dialer *tgssh.Dialer, events chan<- Event, log *slog.Logger) *nodeClient {
	return &nodeClient{
		node:   node,
		parent: parent,
		dialer: dialer,
		log:    log,
		events: events,
		ready:  make(chan struct{}),
	}
}

// Current returns the live *ssh.Client, or nil if this node is
// currently disconnected (reconnecting).
func (nc *nodeClient) Current() *tgssh.Client {
	nc.mu.RLock()
	defer nc.mu.RUnlock()
	return nc.current
}

func (nc *nodeClient) setCurrent(c *tgssh.Client) {
	nc.mu.Lock()
	defer nc.mu.Unlock()
	if c != nil && nc.current == nil {
		close(nc.ready)
	} else if c == nil && nc.current != nil {
		nc.ready = make(chan struct{})
	}
	nc.current = c
}

// waitReady blocks until Current() is non-nil or ctx is done. Returns
// false on cancellation.
func (nc *nodeClient) waitReady(ctx context.Context) bool {
	for {
		nc.mu.RLock()
		c := nc.current
		ch := nc.ready
		nc.mu.RUnlock()
		if c != nil {
			return true
		}
		select {
		case <-ch:
			// Either current became non-nil, or we transitioned
			// through another cycle — loop and re-check.
		case <-ctx.Done():
			return false
		}
	}
}

// connect opens the initial ssh.Client synchronously. Errors bubble
// up so Start can fail fast when the user's config is wrong.
func (nc *nodeClient) connect(ctx context.Context) error {
	nc.emit(EventConnecting, nil)
	client, err := nc.dial(ctx)
	if err != nil {
		nc.emit(EventRetry, err)
		return err
	}
	nc.setCurrent(client)
	nc.emit(EventConnected, nil)
	return nil
}

// supervise watches the current client. When it drops, reconnect with
// exponential backoff until ctx is done.
func (nc *nodeClient) supervise(ctx context.Context) {
	const (
		initialBackoff = 1 * time.Second
		maxBackoff     = 60 * time.Second
	)

	for {
		client := nc.Current()
		if client == nil {
			// setCurrent was concurrently called with nil — likely a
			// shutdown happened. Exit if ctx done, else wait for a
			// reconnect attempt to complete elsewhere.
			if ctx.Err() != nil {
				return
			}
			if !nc.waitReady(ctx) {
				return
			}
			continue
		}

		// Block until this client dies or we're told to stop.
		waitErr := make(chan error, 1)
		go func() { waitErr <- client.Wait() }()
		select {
		case <-ctx.Done():
			_ = client.Close()
			<-waitErr
			return
		case <-waitErr:
		}

		nc.setCurrent(nil)
		nc.emit(EventDown, nil)
		nc.log.Warn("ssh client dropped; reconnecting", "node", nc.node.ID)

		// Reconnect loop.
		backoff := initialBackoff
		for {
			select {
			case <-ctx.Done():
				return
			case <-time.After(backoff):
			}
			nc.emit(EventConnecting, nil)
			c, err := nc.dial(ctx)
			if err == nil {
				nc.setCurrent(c)
				nc.emit(EventConnected, nil)
				break
			}
			nc.emit(EventRetry, err)
			backoff *= 2
			if backoff > maxBackoff {
				backoff = maxBackoff
			}
		}
	}
}

// dial resolves parent.Current() (waiting if the parent is currently
// reconnecting) and opens an ssh.Client either directly or via it.
func (nc *nodeClient) dial(ctx context.Context) (*tgssh.Client, error) {
	if nc.parent == nil {
		return nc.dialer.Dial(ctx, nc.node)
	}
	if !nc.parent.waitReady(ctx) {
		return nil, errors.New("parent not available")
	}
	pc := nc.parent.Current()
	if pc == nil {
		return nil, errors.New("parent dropped during dial")
	}
	return nc.dialer.DialThrough(ctx, pc, nc.node)
}

func (nc *nodeClient) close() {
	nc.mu.Lock()
	c := nc.current
	nc.current = nil
	nc.mu.Unlock()
	if c != nil {
		_ = c.Close()
	}
}

func (nc *nodeClient) emit(kind EventKind, err error) {
	if nc.events == nil {
		return
	}
	select {
	case nc.events <- Event{Kind: kind, NodeID: nc.node.ID, Err: err, At: time.Now()}:
	default:
		// Drop the event if the subscriber is slow. Status is
		// eventually-consistent from snapshots, not event history.
	}
}
