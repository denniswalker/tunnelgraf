package main

import (
	"errors"
	"log/slog"
	"os"

	"github.com/spf13/cobra"
	xssh "golang.org/x/crypto/ssh"

	"github.com/denniswalker/tunnelgraf/internal/interactive"
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

			err = interactive.Shell(h.Target)
			// Propagate the remote exit code, matching how `ssh` and
			// `tunnelgraf command` behave, so shell scripts can chain
			// on it.
			var exitErr *xssh.ExitError
			if errors.As(err, &exitErr) {
				os.Exit(exitErr.ExitStatus())
			}
			return err
		},
	}
	cmd.Flags().BoolVar(&insecure, "insecure-host-keys", false, "Skip SSH host-key verification")
	return cmd
}
