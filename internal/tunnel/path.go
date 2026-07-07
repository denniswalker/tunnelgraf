package tunnel

import (
	"context"
	"fmt"

	"github.com/denniswalker/tunnelgraf/internal/profile"
	tgssh "github.com/denniswalker/tunnelgraf/internal/ssh"
)

// PathHandle is the result of ConnectPath: an ssh.Client authenticated
// to the target node plus a Close that tears down every ssh.Client
// opened along the way, parent-last.
type PathHandle struct {
	Target *tgssh.Client
	closes []func() error
}

// Close shuts the target client down first, then each parent up to the
// root. Safe to call multiple times.
func (p *PathHandle) Close() {
	for i := len(p.closes) - 1; i >= 0; i-- {
		_ = p.closes[i]()
	}
	p.closes = nil
}

// ConnectPath walks from root to the node whose ID matches target,
// opening an ssh.Client at each hop. Returns a handle holding the
// target's client. Unlike Manager, no local listeners are created —
// this is for one-shot uses like `command` and `shell`.
func ConnectPath(ctx context.Context, root *profile.Node, target string, dialer *tgssh.Dialer) (*PathHandle, error) {
	chain := findPath(root, target)
	if chain == nil {
		return nil, fmt.Errorf("tunnel id %q not found in profile", target)
	}

	h := &PathHandle{}
	var parent *tgssh.Client
	for i, n := range chain {
		var (
			c   *tgssh.Client
			err error
		)
		if i == 0 {
			c, err = dialer.Dial(ctx, n)
		} else {
			c, err = dialer.DialThrough(ctx, parent, n)
		}
		if err != nil {
			h.Close()
			return nil, fmt.Errorf("connect %s: %w", n.ID, err)
		}
		h.closes = append(h.closes, c.Close)
		parent = c
	}
	h.Target = parent
	return h, nil
}

// findPath returns the root→target node chain (inclusive of both ends)
// or nil if the target isn't in the tree.
func findPath(n *profile.Node, target string) []*profile.Node {
	if n == nil {
		return nil
	}
	if n.ID == target {
		return []*profile.Node{n}
	}
	for _, c := range n.Children() {
		if sub := findPath(c, target); sub != nil {
			return append([]*profile.Node{n}, sub...)
		}
	}
	return nil
}
