package main

import (
	"fmt"
	"log/slog"
	"os"
	"os/signal"
	"syscall"

	"github.com/spf13/cobra"
	"golang.org/x/term"

	tgssh "github.com/denniswalker/tunnelgraf/internal/ssh"
	"github.com/denniswalker/tunnelgraf/internal/tui"
	"github.com/denniswalker/tunnelgraf/internal/tunnel"
)

func newConnectCmd(g *globalFlags) *cobra.Command {
	var (
		insecure       bool
		knownHostsPath string
		noTUI          bool
	)
	cmd := &cobra.Command{
		Use:   "connect",
		Short: "Connect to all tunnels defined in the profile",
		RunE: func(cmd *cobra.Command, args []string) error {
			root, err := loadProfile(g)
			if err != nil {
				return err
			}

			// Default slog goes to stderr; the TUI paints on stdout.
			// We keep slog at warn so the dashboard isn't interleaved
			// with info lines when a TTY is in use.
			logLevel := slog.LevelInfo
			useTUI := !noTUI && term.IsTerminal(int(os.Stdout.Fd()))
			if useTUI {
				logLevel = slog.LevelWarn
			}
			log := slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: logLevel}))

			policy := tgssh.PolicyAcceptNew
			if insecure {
				policy = tgssh.PolicyInsecure
			}
			hk, err := tgssh.HostKeyCallback(knownHostsPath, policy, log)
			if err != nil {
				return fmt.Errorf("host-key callback: %w", err)
			}

			events := make(chan tunnel.Event, 128)
			mgr := tunnel.New(root, tunnel.Options{
				Dialer: &tgssh.Dialer{HostKey: hk},
				Log:    log,
				Events: events,
			})

			ctx, cancel := signal.NotifyContext(cmd.Context(), syscall.SIGINT, syscall.SIGTERM)
			defer cancel()

			if err := mgr.Start(ctx); err != nil {
				return err
			}

			if useTUI {
				err = tui.Run(ctx, root, events)
			} else {
				fmt.Fprintf(os.Stderr, "Tunnels started: %d forward(s). Ctrl-C to stop.\n", mgr.TunnelCount())
				go drainEvents(events, log)
				<-ctx.Done()
				fmt.Fprintln(os.Stderr, "\nStopping tunnels...")
			}
			mgr.Stop()
			close(events)
			return err
		},
	}
	cmd.Flags().BoolVar(&insecure, "insecure-host-keys", false, "Skip SSH host-key verification (dangerous; for ephemeral test hosts)")
	cmd.Flags().StringVar(&knownHostsPath, "known-hosts", "", "Override the known_hosts path (default: ~/.config/tunnelgraf/known_hosts)")
	cmd.Flags().BoolVar(&noTUI, "no-tui", false, "Disable the live dashboard even when stdout is a terminal")
	return cmd
}

// drainEvents keeps the manager's events channel from blocking when
// the TUI isn't running. Interesting transitions are logged.
func drainEvents(events <-chan tunnel.Event, log *slog.Logger) {
	for e := range events {
		switch e.Kind {
		case tunnel.EventConnected:
			log.Info("connected", "node", e.NodeID)
		case tunnel.EventDown:
			log.Warn("client dropped", "node", e.NodeID)
		case tunnel.EventRetry:
			log.Warn("reconnect failed", "node", e.NodeID, "err", e.Err)
		}
	}
}
