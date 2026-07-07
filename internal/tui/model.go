// Package tui renders the live connect dashboard using Bubble Tea.
// It subscribes to Manager events and paints a tree of nodes with
// per-node status.
package tui

import (
	"context"
	"fmt"
	"io"
	"os/exec"
	"runtime"
	"strings"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"

	"github.com/denniswalker/tunnelgraf/internal/interactive"
	"github.com/denniswalker/tunnelgraf/internal/profile"
	tgssh "github.com/denniswalker/tunnelgraf/internal/ssh"
	"github.com/denniswalker/tunnelgraf/internal/tunnel"
)

// Run starts the TUI against root. It blocks until the user quits
// (q/Ctrl-C) or cancelCtx is cancelled (external SIGINT/SIGTERM).
// events is the channel wired to Manager.Options.Events. dialer is
// used on demand to open one-shot connections for menu actions (e.g.
// "shell in"); it doesn't touch the Manager's own tunnels.
func Run(cancelCtx context.Context, root *profile.Node, events <-chan tunnel.Event, dialer *tgssh.Dialer) error {
	m := newModel(root)
	m.ctx = cancelCtx
	m.dialer = dialer
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

	// order lists every node in the same order they're rendered, so
	// cursor is a plain index into it.
	order  []*profile.Node
	cursor int
	menu   *menuState
	status string

	// ctx and dialer back on-demand menu actions ("shell in"); Run
	// populates them, tests that only exercise rendering can leave
	// them zero.
	ctx    context.Context
	dialer *tgssh.Dialer
}

// menuActionKind identifies what a menuOption does when chosen.
type menuActionKind int

const (
	actionShell menuActionKind = iota
	actionBrowser
)

// menuOption is one selectable row in the popup menu.
type menuOption struct {
	kind  menuActionKind
	label string
	url   string // set for actionBrowser
}

// menuState is non-nil while the popup menu is open for a node.
type menuState struct {
	node    *profile.Node
	options []menuOption
	cursor  int
}

// actionDoneMsg reports the outcome of a menu action, shown as a
// status line until the next one replaces it.
type actionDoneMsg struct {
	info string
	err  error
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
	m.order = orderedNodes(root)
	return m
}

// orderedNodes walks the tree in the same order renderNode draws it,
// so a plain cursor index lines up with the rendered row.
func orderedNodes(n *profile.Node) []*profile.Node {
	if n == nil {
		return nil
	}
	out := []*profile.Node{n}
	for _, c := range n.Children() {
		out = append(out, orderedNodes(c)...)
	}
	return out
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
		if m.menu != nil {
			return m.updateMenu(msg)
		}
		switch msg.String() {
		case "q", "ctrl+c":
			return m, tea.Quit
		case "up", "k":
			if m.cursor > 0 {
				m.cursor--
			}
		case "down", "j":
			if m.cursor < len(m.order)-1 {
				m.cursor++
			}
		case "enter":
			if m.cursor < len(m.order) {
				if opts := menuOptionsFor(m.order[m.cursor]); len(opts) > 0 {
					m.menu = &menuState{node: m.order[m.cursor], options: opts}
				}
			}
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
	case actionDoneMsg:
		if msg.err != nil {
			m.status = fmt.Sprintf("%s: %v", msg.info, msg.err)
		} else {
			m.status = msg.info
		}
	}
	return m, nil
}

// updateMenu handles key input while the popup menu is open. It never
// falls through to the base keymap so an accidental "q" closes the
// menu instead of quitting the whole session.
func (m model) updateMenu(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	switch msg.String() {
	case "esc", "q":
		m.menu = nil
	case "up", "k":
		if m.menu.cursor > 0 {
			m.menu.cursor--
		}
	case "down", "j":
		if m.menu.cursor < len(m.menu.options)-1 {
			m.menu.cursor++
		}
	case "enter":
		opt := m.menu.options[m.menu.cursor]
		node := m.menu.node
		m.menu = nil
		return m, m.runAction(opt, node)
	}
	return m, nil
}

// menuOptionsFor returns the actions available for n based on its
// protocol: one "open in browser" row per hosts-file name for
// http/https, or a single "shell in" row for ssh. Other protocols get
// no menu at all.
func menuOptionsFor(n *profile.Node) []menuOption {
	switch n.Protocol {
	case "http", "https":
		names := n.HostsFileEntries
		if len(names) == 0 {
			names = []string{firstNonEmpty(n.HostsFileEntry, n.LocalBindAddress, n.Host)}
		}
		port := n.LocalBindPort
		if port == 0 {
			port = n.Port
		}
		opts := make([]menuOption, 0, len(names))
		for _, host := range names {
			url := fmt.Sprintf("%s://%s:%d", n.Protocol, host, port)
			opts = append(opts, menuOption{kind: actionBrowser, label: "Open " + url, url: url})
		}
		return opts
	case "ssh":
		return []menuOption{{kind: actionShell, label: "Shell in"}}
	default:
		return nil
	}
}

func firstNonEmpty(vals ...string) string {
	for _, v := range vals {
		if v != "" {
			return v
		}
	}
	return ""
}

// runAction dispatches a chosen menu option.
func (m model) runAction(opt menuOption, node *profile.Node) tea.Cmd {
	switch opt.kind {
	case actionBrowser:
		return openBrowserCmd(opt.url)
	case actionShell:
		return m.shellCmd(node)
	default:
		return nil
	}
}

// openBrowserCmd shells out to the OS's URL opener. It doesn't need
// the terminal, so it runs as a plain (non-Exec) tea.Cmd.
func openBrowserCmd(url string) tea.Cmd {
	return func() tea.Msg {
		return actionDoneMsg{info: "opened " + url, err: openBrowser(url)}
	}
}

func openBrowser(url string) error {
	var c *exec.Cmd
	switch runtime.GOOS {
	case "darwin":
		c = exec.Command("open", url)
	case "windows":
		c = exec.Command("rundll32", "url.dll,FileProtocolHandler", url)
	default:
		c = exec.Command("xdg-open", url)
	}
	return c.Start()
}

// shellCmd hands the terminal to an interactive SSH session on node,
// then resumes the dashboard once it exits. tea.Exec takes care of
// releasing/restoring the alt screen around the blocking call.
func (m model) shellCmd(node *profile.Node) tea.Cmd {
	sc := &sshExecCommand{ctx: m.ctx, root: m.root, dialer: m.dialer, nodeID: node.ID}
	return tea.Exec(sc, func(err error) tea.Msg {
		return actionDoneMsg{info: fmt.Sprintf("shell session on %s ended", node.ID), err: err}
	})
}

// sshExecCommand adapts a one-shot "connect to node, run an
// interactive shell" operation to tea.ExecCommand so bubbletea can
// suspend the TUI around it exactly like it would an editor subprocess.
// It ignores the std{in,out,err} bubbletea offers, since Shell already
// talks to the real os.Std{in,out,err} directly (matching the
// standalone `shell` subcommand's behaviour).
type sshExecCommand struct {
	ctx    context.Context
	root   *profile.Node
	dialer *tgssh.Dialer
	nodeID string
}

func (s *sshExecCommand) SetStdin(io.Reader)  {}
func (s *sshExecCommand) SetStdout(io.Writer) {}
func (s *sshExecCommand) SetStderr(io.Writer) {}

func (s *sshExecCommand) Run() error {
	h, err := tunnel.ConnectPath(s.ctx, s.root, s.nodeID, s.dialer)
	if err != nil {
		return err
	}
	defer h.Close()
	return interactive.Shell(h.Target)
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
	b.WriteString(styleHelp.Render("↑/↓ select · enter for actions · q or Ctrl-C to stop tunnels"))
	b.WriteString("\n")
	if m.status != "" {
		b.WriteString(styleFaint.Render(m.status))
		b.WriteString("\n")
	}
	b.WriteString("\n")

	m.renderNode(&b, m.root, "", true, true)
	m.renderMenu(&b)
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

	selected := len(m.order) > 0 && m.cursor < len(m.order) && m.order[m.cursor].ID == n.ID
	status, style := m.statusFor(n)
	idStyle, faintStyle := styleID, styleFaint
	if selected {
		style = style.Reverse(true)
		idStyle = idStyle.Reverse(true)
		faintStyle = faintStyle.Reverse(true)
	}
	line := fmt.Sprintf("%s%s%s  %s  %s",
		prefix, branch,
		style.Render(status),
		idStyle.Render(n.ID),
		faintStyle.Render(hostPortLabel(n)),
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

var styleMenuBox = lipgloss.NewStyle().Border(lipgloss.RoundedBorder()).Padding(0, 1)

// renderMenu appends the popup menu box below the tree when one is
// open. It's drawn inline rather than as a true floating overlay,
// which keeps the layout simple at the cost of pushing content down —
// acceptable for a dashboard that's mostly read, not scrolled.
func (m model) renderMenu(b *strings.Builder) {
	if m.menu == nil {
		return
	}
	var body strings.Builder
	fmt.Fprintf(&body, "%s\n", styleHeader.Render("actions: "+m.menu.node.ID))
	for i, opt := range m.menu.options {
		cursor := "  "
		label := opt.label
		if i == m.menu.cursor {
			cursor = "> "
			label = lipgloss.NewStyle().Bold(true).Render(label)
		}
		fmt.Fprintf(&body, "%s%s\n", cursor, label)
	}
	body.WriteString(styleHelp.Render("↑/↓ select · enter confirm · esc cancel"))

	b.WriteString("\n")
	b.WriteString(styleMenuBox.Render(body.String()))
	b.WriteString("\n")
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
