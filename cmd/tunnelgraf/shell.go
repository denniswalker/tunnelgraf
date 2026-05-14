package main

import (
	"errors"
	"fmt"
	"log/slog"
	"os"
	"os/signal"

	"github.com/spf13/cobra"
	xssh "golang.org/x/crypto/ssh"
	"golang.org/x/term"

	tgssh "github.com/denniswalker/tunnelgraf/internal/ssh"
	"github.com/denniswalker/tunnelgraf/internal/tunnel"
)

func newShellCmd(g *globalFlags) *cobra.Command {
	var insecure bool
	cmd := &cobra.Command{
		Use:   "shell",
		Short: "Open an interactive shell on the targeted tunnel",
		RunE: func(cmd *cobra.Command, args []string) error {
			if g.tunnelID == "" {
				return errors.New("-t/--tunnel-id is required for shell")
			}
			root, err := loadProfile(g)
			if err != nil {
				return err
			}

			log := slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: slog.LevelWarn}))
			policy := tgssh.PolicyAcceptNew
			if insecure {
				policy = tgssh.PolicyInsecure
			}
			hk, err := tgssh.HostKeyCallback("", policy, log)
			if err != nil {
				return err
			}

			h, err := tunnel.ConnectPath(cmd.Context(), root, g.tunnelID, &tgssh.Dialer{HostKey: hk})
			if err != nil {
				return err
			}
			defer h.Close()

			return interactiveShell(h.Target)
		},
	}
	cmd.Flags().BoolVar(&insecure, "insecure-host-keys", false, "Skip SSH host-key verification")
	return cmd
}

// interactiveShell opens a PTY-backed session on client and wires it
// to the local terminal. Restores terminal state on exit regardless of
// how the session ended.
func interactiveShell(client *xssh.Client) error {
	session, err := client.NewSession()
	if err != nil {
		return fmt.Errorf("new session: %w", err)
	}
	defer func() { _ = session.Close() }()

	fd := int(os.Stdin.Fd())
	if !term.IsTerminal(fd) {
		return errors.New("stdin is not a terminal; `shell` requires an interactive TTY (use `command` for non-interactive)")
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

	var exitErr *xssh.ExitError
	if errors.As(err, &exitErr) {
		_ = term.Restore(fd, oldState)
		os.Exit(exitErr.ExitStatus())
	}
	return err
}
