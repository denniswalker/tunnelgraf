package main

import (
	"errors"
	"fmt"
	"log/slog"
	"os"

	"github.com/spf13/cobra"
	xssh "golang.org/x/crypto/ssh"

	tgssh "github.com/denniswalker/tunnelgraf/internal/ssh"
	"github.com/denniswalker/tunnelgraf/internal/tunnel"
)

func newCommandCmd(g *globalFlags) *cobra.Command {
	var insecure bool
	cmd := &cobra.Command{
		Use:   "command <cmd>",
		Short: "Run a shell command on the targeted tunnel",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			if g.tunnelID == "" {
				return errors.New("-t/--tunnel-id is required for command")
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

			return runRemote(h.Target, args[0])
		},
	}
	cmd.Flags().BoolVar(&insecure, "insecure-host-keys", false, "Skip SSH host-key verification")
	return cmd
}

// runRemote executes cmd on the given client, streams stdout+stderr to
// the caller's streams, and exits with the remote exit code so shell
// scripts can chain `tunnelgraf command` the way they'd chain ssh.
func runRemote(client *xssh.Client, cmdline string) error {
	session, err := client.NewSession()
	if err != nil {
		return fmt.Errorf("new session: %w", err)
	}
	defer func() { _ = session.Close() }()

	session.Stdout = os.Stdout
	session.Stderr = os.Stderr

	err = session.Run(cmdline)
	if err == nil {
		return nil
	}
	// Propagate remote exit code when we can. cobra will print nothing
	// for a SilentExitError and we'll os.Exit directly.
	var exitErr *xssh.ExitError
	if errors.As(err, &exitErr) {
		os.Exit(exitErr.ExitStatus())
	}
	return fmt.Errorf("remote command failed: %w", err)
}
