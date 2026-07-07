package tui

import (
	"strings"
	"testing"
	"time"

	tea "github.com/charmbracelet/bubbletea"

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

func TestModelCursorMovesWithArrowKeys(t *testing.T) {
	root := &profile.Node{
		ID: "bastion", Host: "jump.example.com", Port: 22,
		Nexthop: &profile.Node{
			ID: "web", Host: "10.0.0.1", Port: 443, Protocol: "https",
			LocalBindAddress: "127.0.0.1", LocalBindPort: 8443,
		},
	}
	m := newModel(root)
	if m.cursor != 0 {
		t.Fatalf("initial cursor = %d, want 0", m.cursor)
	}

	mi, _ := m.Update(tea.KeyMsg{Type: tea.KeyDown})
	m = mi.(model)
	if m.cursor != 1 {
		t.Errorf("cursor after down = %d, want 1", m.cursor)
	}

	// Downing past the end should clamp, not wrap or panic.
	mi, _ = m.Update(tea.KeyMsg{Type: tea.KeyDown})
	m = mi.(model)
	if m.cursor != 1 {
		t.Errorf("cursor after extra down = %d, want clamped at 1", m.cursor)
	}

	mi, _ = m.Update(tea.KeyMsg{Type: tea.KeyUp})
	m = mi.(model)
	if m.cursor != 0 {
		t.Errorf("cursor after up = %d, want 0", m.cursor)
	}
}

func TestModelEnterOpensMenuMatchingProtocol(t *testing.T) {
	root := &profile.Node{
		ID: "bastion", Host: "jump.example.com", Port: 22, Protocol: "ssh",
		Nexthop: &profile.Node{
			ID: "web", Host: "10.0.0.1", Port: 443, Protocol: "https",
			LocalBindAddress: "127.0.0.1", LocalBindPort: 8443,
			HostsFileEntry: "web.example.com",
		},
	}
	m := newModel(root)

	// Cursor starts on the bastion (ssh) -> "Shell in".
	mi, _ := m.Update(tea.KeyMsg{Type: tea.KeyEnter})
	m = mi.(model)
	if m.menu == nil || len(m.menu.options) != 1 || m.menu.options[0].kind != actionShell {
		t.Fatalf("bastion menu = %+v, want a single Shell in option", m.menu)
	}

	// Esc closes the menu without acting.
	mi, _ = m.Update(tea.KeyMsg{Type: tea.KeyEsc})
	m = mi.(model)
	if m.menu != nil {
		t.Fatalf("menu still open after esc")
	}

	// Move to the https leaf and open its menu.
	mi, _ = m.Update(tea.KeyMsg{Type: tea.KeyDown})
	m = mi.(model)
	mi, _ = m.Update(tea.KeyMsg{Type: tea.KeyEnter})
	m = mi.(model)
	if m.menu == nil || len(m.menu.options) != 1 || m.menu.options[0].kind != actionBrowser {
		t.Fatalf("web menu = %+v, want a single Open in browser option", m.menu)
	}
	wantURL := "https://web.example.com:8443"
	if m.menu.options[0].url != wantURL {
		t.Errorf("browser url = %q, want %q", m.menu.options[0].url, wantURL)
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
