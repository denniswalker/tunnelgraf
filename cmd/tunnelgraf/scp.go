package main

import (
	"log/slog"
	"os"

	"github.com/spf13/cobra"

	tgssh "github.com/denniswalker/tunnelgraf/internal/ssh"
	"github.com/denniswalker/tunnelgraf/internal/transfer"
	"github.com/denniswalker/tunnelgraf/internal/tunnel"
)

func newSCPCmd(g *globalFlags) *cobra.Command {
	var insecure bool
	cmd := &cobra.Command{
		Use:   "scp <source> <destination>",
		Short: "Copy files to/from a remote host (SFTP-backed)",
		Long: `Copy files or directories between the local machine and a tunnel target.

Source or destination may be in tunnel_id:path form, or both bare when
--tunnel-id is set (in which case the transfer is treated as upload).

Transfers run in-process over SFTP; no 'scp' or 'sshpass' binary is
required on the system PATH.`,
		Args: cobra.ExactArgs(2),
		RunE: func(cmd *cobra.Command, args []string) error {
			spec, err := transfer.ParseSpec(args[0], args[1], g.tunnelID)
			if err != nil {
				return err
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

			h, err := tunnel.ConnectPath(cmd.Context(), root, spec.TunnelID, &tgssh.Dialer{HostKey: hk})
			if err != nil {
				return err
			}
			defer h.Close()

			return transfer.Execute(cmd.Context(), h.Target, spec, os.Stderr)
		},
	}
	cmd.Flags().BoolVar(&insecure, "insecure-host-keys", false, "Skip SSH host-key verification")
	return cmd
}
