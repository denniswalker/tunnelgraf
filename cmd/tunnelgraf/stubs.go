package main

import (
	"errors"

	"github.com/spf13/cobra"
)

// errNotYet is returned by verbs whose implementation is still pending in
// the 2.0 rewrite. They remain registered so `--help` shows the full CLI
// surface and users can see what's coming.
var errNotYet = errors.New("not implemented in 2.0-alpha — tracked in REWRITE_PLAN.md milestone M1")

func newStopCmd(_ *globalFlags) *cobra.Command {
	return &cobra.Command{
		Use:   "stop",
		Short: "Stop tunnels associated with a profile (pending)",
		RunE:  func(cmd *cobra.Command, args []string) error { return errNotYet },
	}
}
