// Package interactive runs a PTY-backed interactive shell session over
// an already-authenticated ssh.Client, wiring it to the local
// terminal. It's shared by the `shell` subcommand and the connect TUI's
// "shell in" menu action.
package interactive

import (
	"errors"
	"fmt"
	"os"
	"os/signal"

	xssh "golang.org/x/crypto/ssh"
	"golang.org/x/term"
)

// Shell opens a PTY-backed session on client and wires it to the
// local terminal. Restores terminal state on exit regardless of how
// the session ended. A non-zero remote exit surfaces as
// *xssh.ExitError, matching session.Wait's behaviour, so callers that
// want ssh-like exit-code propagation (e.g. the `shell` subcommand)
// can check for it themselves; callers that just want to know the
// session ended (e.g. the connect TUI) can ignore it.
func Shell(client *xssh.Client) error {
	session, err := client.NewSession()
	if err != nil {
		return fmt.Errorf("new session: %w", err)
	}
	defer func() { _ = session.Close() }()

	fd := int(os.Stdin.Fd())
	if !term.IsTerminal(fd) {
		return errors.New("stdin is not a terminal; an interactive shell requires a TTY")
	}

	oldState, err := term.MakeRaw(fd)
	if err != nil {
		return fmt.Errorf("put terminal in raw mode: %w", err)
	}
	defer func() { _ = term.Restore(fd, oldState) }()

	w, hgt, err := term.GetSize(fd)
	if err != nil {
		return fmt.Errorf("get terminal size: %w", err)
	}

	modes := xssh.TerminalModes{
		xssh.ECHO:          1,
		xssh.TTY_OP_ISPEED: 14400,
		xssh.TTY_OP_OSPEED: 14400,
	}
	termEnv := os.Getenv("TERM")
	if termEnv == "" {
		termEnv = "xterm-256color"
	}
	if err := session.RequestPty(termEnv, hgt, w, modes); err != nil {
		return fmt.Errorf("request pty: %w", err)
	}

	// Forward local SIGWINCH to the remote PTY so remote apps resize
	// with the local window.
	winch := make(chan os.Signal, 1)
	subscribeWindowChange(winch)
	defer signal.Stop(winch)
	done := make(chan struct{})
	go func() {
		for {
			select {
			case <-winch:
				if w, h, err := term.GetSize(fd); err == nil {
					_ = session.WindowChange(h, w)
				}
			case <-done:
				return
			}
		}
	}()

	session.Stdin = os.Stdin
	session.Stdout = os.Stdout
	session.Stderr = os.Stderr

	if err := session.Shell(); err != nil {
		close(done)
		return fmt.Errorf("start shell: %w", err)
	}
	err = session.Wait()
	close(done)
	return err
}
