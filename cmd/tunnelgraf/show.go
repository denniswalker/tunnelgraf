package main

import (
	"encoding/json"
	"fmt"
	"os"

	"github.com/spf13/cobra"

	"github.com/denniswalker/tunnelgraf/internal/profile"
)

func newShowCmd(g *globalFlags) *cobra.Command {
	var showCreds bool
	cmd := &cobra.Command{
		Use:   "show",
		Short: "Print the resolved tunnel configuration as JSON",
		RunE: func(cmd *cobra.Command, args []string) error {
			root, err := loadProfile(g)
			if err != nil {
				return err
			}
			entries := profile.Flatten(root, profile.FlattenOptions{IncludeCredentials: showCreds})

			if g.tunnelID != "" {
				for _, e := range entries {
					if e.ID == g.tunnelID {
						return writeJSON(os.Stdout, e)
					}
				}
				return fmt.Errorf("tunnel id %q not found", g.tunnelID)
			}
			return writeJSON(os.Stdout, entries)
		},
	}
	cmd.Flags().BoolVar(&showCreds, "show-credentials", false, "Include sshuser/sshpass/sshkeyfile in the output")
	return cmd
}

func writeJSON(w *os.File, v any) error {
	enc := json.NewEncoder(w)
	enc.SetIndent("", "    ")
	return enc.Encode(v)
}
