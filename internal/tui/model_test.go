package tui

import (
	"strings"
	"testing"
	"time"

	"github.com/denniswalker/tunnelgraf/internal/profile"
	"github.com/denniswalker/tunnelgraf/internal/tunnel"
)

func TestModelSeedsInteriorNodesAsConnecting(t *testing.T) {
	root := &profile.Node{
		ID:   "root",
		Host: "127.0.0.1", Port: 22,
		Nexthop: &profile.Node{
			ID: "leaf", Host: "127.0.0.1", Port: 80,
			LocalBindAddress: "127.0.0.1", LocalBindPort: 8080,
		},
	}
	m := newModel(root)
	if _, ok := m.states["root"]; !ok {
		t.Errorf("root not seeded")
	}
	if _, ok := m.states["leaf"]; ok {
		t.Errorf("leaf should not have its own state (it has no children)")
	}
}

func TestModelUpdatesOnEvent(t *testing.T) {
	root := &profile.Node{ID: "root", Nexthop: &profile.Node{ID: "leaf", LocalBindPort: 1}}
	m := newModel(root)

	newModel, _ := m.Update(eventMsg{Kind: tunnel.EventConnected, NodeID: "root", At: time.Now()})
	m2 := newModel.(model)
	if m2.states["root"].kind != tunnel.EventConnected {
		t.Errorf("state not updated: %v", m2.states["root"])
	}
}

func TestModelRetryIncrementsCount(t *testing.T) {
	root := &profile.Node{ID: "root", Nexthop: &profile.Node{ID: "leaf", LocalBindPort: 1}}
	m := newModel(root)

	mi, _ := m.Update(eventMsg{Kind: tunnel.EventRetry, NodeID: "root", At: time.Now()})
	mi, _ = mi.(model).Update(eventMsg{Kind: tunnel.EventRetry, NodeID: "root", At: time.Now()})
	if mi.(model).states["root"].retries != 2 {
		t.Errorf("retries = %d, want 2", mi.(model).states["root"].retries)
	}
}

func TestModelViewRendersTree(t *testing.T) {
	root := &profile.Node{
		ID:   "bastion",
		Host: "jump.example.com", Port: 22,
		Nexthop: &profile.Node{
			ID: "web", Host: "10.0.0.1", Port: 443,
			LocalBindAddress: "127.0.0.1", LocalBindPort: 8443,
		},
	}
	m := newModel(root)
	// Simulate successful connect on bastion.
	mi, _ := m.Update(eventMsg{Kind: tunnel.EventConnected, NodeID: "bastion", At: time.Now()})
	out := mi.(model).View()

	if !strings.Contains(out, "bastion") {
		t.Errorf("view missing root id:\n%s", out)
	}
	if !strings.Contains(out, "web") {
		t.Errorf("view missing leaf id:\n%s", out)
	}
	// Leaf inherits parent's "connected" state, rendered as forward.
	if !strings.Contains(out, "fwd") {
		t.Errorf("view missing leaf forward glyph:\n%s", out)
	}
}
