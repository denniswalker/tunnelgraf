package main

import (
	"github.com/spf13/cobra"
)

// globalFlags holds the flags that apply to every subcommand.
// We keep it as a struct so subcommands can read it without reaching into
// cobra's flag plumbing.
type globalFlags struct {
	profilePath string
	tunnelID    string
}

func newRootCmd() *cobra.Command {
	g := &globalFlags{}

	root := &cobra.Command{
		Use:           "tunnelgraf",
		Short:         "Hierarchical SSH tunnel management",
		Long:          "Connect through a graph of bastion hosts to many remote endpoints, exposing them as local ports.",
		SilenceUsage:  true,
		SilenceErrors: true,
	}

	pf := root.PersistentFlags()
	pf.StringVarP(&g.profilePath, "profile", "p", "", "Path to the connection profile (env: TUNNELGRAF_PROFILE)")
	pf.StringVarP(&g.tunnelID, "tunnel-id", "t", "", "Tunnel id to target")

	root.AddCommand(
		newShowCmd(g),
		newUrlsCmd(g),
		newConnectCmd(g),
		newCommandCmd(g),
		newShellCmd(g),
		newSCPCmd(g),
		newStopCmd(g),
	)

	return root
}
