// Package tui renders the live connect dashboard using Bubble Tea.
// It subscribes to Manager events and paints a tree of nodes with
// per-node status.
package tui

import (
	"context"
	"fmt"
	"strings"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"

	"github.com/denniswalker/tunnelgraf/internal/profile"
	"github.com/denniswalker/tunnelgraf/internal/tunnel"
)

// Run starts the TUI against root. It blocks until the user quits
// (q/Ctrl-C) or cancelCtx is cancelled (external SIGINT/SIGTERM).
// events is the channel wired to Manager.Options.Events.
func Run(cancelCtx context.Context, root *profile.Node, events <-chan tunnel.Event) error {
	m := newModel(root)
	p := tea.NewProgram(m, tea.WithAltScreen())

	// Pump events from the manager into the TUI as tea messages.
	go func() {
		for e := range events {
			p.Send(eventMsg(e))
		}
	}()

	// External cancellation (signal handler) quits the TUI.
	go func() {
		<-cancelCtx.Done()
		p.Quit()
	}()

	_, err := p.Run()
	return err
}

// --- model ---------------------------------------------------------

type model struct {
	root   *profile.Node
	states map[string]nodeState
	width  int
	height int
	start  time.Time
}

type nodeState struct {
	kind    tunnel.EventKind
	at      time.Time
	err     error
	retries int
}

type eventMsg tunnel.Event
type tickMsg time.Time

func newModel(root *profile.Node) model {
	m := model{
		root:   root,
		states: map[string]nodeState{},
		start:  time.Now(),
	}
	// Every interior node starts in connecting state; leaves have no
	// own client so they inherit the parent's status implicitly.
	seedStates(root, m.states)
	return m
}

func seedStates(n *profile.Node, states map[string]nodeState) {
	if n == nil {
		return
	}
	if len(n.Children()) > 0 {
		states[n.ID] = nodeState{kind: tunnel.EventConnecting, at: time.Now()}
	}
	for _, c := range n.Children() {
		seedStates(c, states)
	}
}

func (m model) Init() tea.Cmd {
	return tick()
}

func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.KeyMsg:
		switch msg.String() {
		case "q", "ctrl+c":
			return m, tea.Quit
		}
	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height
	case eventMsg:
		prev := m.states[msg.NodeID]
		st := nodeState{kind: msg.Kind, at: msg.At, err: msg.Err, retries: prev.retries}
		if msg.Kind == tunnel.EventRetry {
			st.retries++
		}
		m.states[msg.NodeID] = st
	case tickMsg:
		return m, tick()
	}
	return m, nil
}

func tick() tea.Cmd {
	return tea.Tick(time.Second, func(t time.Time) tea.Msg { return tickMsg(t) })
}

// --- styling + render ----------------------------------------------

var (
	styleHeader     = lipgloss.NewStyle().Bold(true)
	styleHelp       = lipgloss.NewStyle().Faint(true)
	styleID         = lipgloss.NewStyle().Bold(true)
	styleConnected  = lipgloss.NewStyle().Foreground(lipgloss.Color("10")) // green
	styleConnecting = lipgloss.NewStyle().Foreground(lipgloss.Color("11")) // yellow
	styleDown       = lipgloss.NewStyle().Foreground(lipgloss.Color("9"))  // red
	styleFaint      = lipgloss.NewStyle().Faint(true)
)

func (m model) View() string {
	var b strings.Builder
	b.WriteString(styleHeader.Render("tunnelgraf") + "  ")
	b.WriteString(styleFaint.Render(fmt.Sprintf("uptime %s", time.Since(m.start).Round(time.Second))))
	b.WriteString("\n")
	b.WriteString(styleHelp.Render("press q or Ctrl-C to stop tunnels"))
	b.WriteString("\n\n")

	m.renderNode(&b, m.root, "", true, true)
	return b.String()
}

func (m model) renderNode(b *strings.Builder, n *profile.Node, prefix string, isLast, isRoot bool) {
	var branch string
	if isRoot {
		branch = ""
	} else if isLast {
		branch = "└─ "
	} else {
		branch = "├─ "
	}

	status, style := m.statusFor(n)
	line := fmt.Sprintf("%s%s%s  %s  %s",
		prefix, branch,
		style.Render(status),
		styleID.Render(n.ID),
		styleFaint.Render(hostPortLabel(n)),
	)
	b.WriteString(line)
	b.WriteString("\n")

	var childPrefix string
	if isRoot {
		childPrefix = prefix
	} else if isLast {
		childPrefix = prefix + "   "
	} else {
		childPrefix = prefix + "│  "
	}

	children := n.Children()
	for i, c := range children {
		m.renderNode(b, c, childPrefix, i == len(children)-1, false)
	}
}

// statusFor returns a short glyph + style for a node. Leaves have no
// client of their own — they inherit visual state from the parent that
// terminates their tunnel, so we look at that parent's state.
func (m model) statusFor(n *profile.Node) (string, lipgloss.Style) {
	if len(n.Children()) > 0 {
		return labelFor(m.states[n.ID].kind)
	}
	return labelForLeaf(m.statesOfParent(n))
}

func labelFor(k tunnel.EventKind) (string, lipgloss.Style) {
	switch k {
	case tunnel.EventConnected:
		return "● UP   ", styleConnected
	case tunnel.EventDown, tunnel.EventRetry:
		return "● DOWN ", styleDown
	default:
		return "○ ...  ", styleConnecting
	}
}

func labelForLeaf(parent tunnel.EventKind) (string, lipgloss.Style) {
	switch parent {
	case tunnel.EventConnected:
		return "→ fwd  ", styleConnected
	case tunnel.EventDown, tunnel.EventRetry:
		return "→ down ", styleDown
	default:
		return "→ ...  ", styleConnecting
	}
}

// statesOfParent finds the enclosing interior node's state for leaf n
// by walking from root. Inefficient but fine at UI frame rate for the
// small graphs this tool handles.
func (m model) statesOfParent(leaf *profile.Node) tunnel.EventKind {
	var walk func(n *profile.Node) (tunnel.EventKind, bool)
	walk = func(n *profile.Node) (tunnel.EventKind, bool) {
		for _, c := range n.Children() {
			if c.ID == leaf.ID {
				return m.states[n.ID].kind, true
			}
			if k, ok := walk(c); ok {
				return k, true
			}
		}
		return 0, false
	}
	k, _ := walk(m.root)
	return k
}

func hostPortLabel(n *profile.Node) string {
	if n.LocalBindPort == 0 {
		return fmt.Sprintf("%s:%d", n.Host, n.Port)
	}
	return fmt.Sprintf("127.0.0.1:%d → %s:%d", n.LocalBindPort, n.Host, n.Port)
}
