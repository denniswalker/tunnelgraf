package main

import (
	"fmt"
	"log/slog"
	"os"
	"os/signal"
	"syscall"

	"github.com/spf13/cobra"
	"golang.org/x/term"

	"github.com/denniswalker/tunnelgraf/internal/hostsfile"
	"github.com/denniswalker/tunnelgraf/internal/profile"
	tgssh "github.com/denniswalker/tunnelgraf/internal/ssh"
	"github.com/denniswalker/tunnelgraf/internal/tui"
	"github.com/denniswalker/tunnelgraf/internal/tunnel"
)

func newConnectCmd(g *globalFlags) *cobra.Command {
	var (
		insecure       bool
		knownHostsPath string
		noTUI          bool
		noHostsFile    bool
		hostsFilePath  string
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

			dialer := &tgssh.Dialer{HostKey: hk}
			events := make(chan tunnel.Event, 128)
			mgr := tunnel.New(root, tunnel.Options{
				Dialer: dialer,
				Log:    log,
				Events: events,
			})

			ctx, cancel := signal.NotifyContext(cmd.Context(), syscall.SIGINT, syscall.SIGTERM)
			defer cancel()

			if err := mgr.Start(ctx); err != nil {
				return err
			}

			if !noHostsFile {
				hm := hostsfile.New(hostsFilePath)
				if err := hm.Apply(hostsFileNames(root)); err != nil {
					log.Warn("hosts file not updated", "err", err)
				}
				defer func() {
					if err := hm.Restore(); err != nil {
						log.Warn("hosts file not restored", "err", err)
					}
				}()
			}

			if useTUI {
				err = tui.Run(ctx, root, events, dialer)
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
	cmd.Flags().BoolVar(&noHostsFile, "no-hosts-file", false, "Don't add hosts_file_entry(ies) to the hosts file")
	cmd.Flags().StringVar(&hostsFilePath, "hosts-file", hostsfile.DefaultPath(), "Override the hosts file path")
	return cmd
}

// hostsFileNames flattens the profile and collects every
// hosts_file_entry / hosts_file_entries value in tree order.
func hostsFileNames(root *profile.Node) []string {
	var names []string
	for _, e := range profile.Flatten(root, profile.FlattenOptions{}) {
		if e.HostsFileEntry != "" {
			names = append(names, e.HostsFileEntry)
		}
		names = append(names, e.HostsFileEntries...)
	}
	return names
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
