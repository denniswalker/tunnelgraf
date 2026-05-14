package main

import (
	"errors"
	"os"

	"github.com/denniswalker/tunnelgraf/internal/profile"
	"github.com/denniswalker/tunnelgraf/internal/sshcfg"
)

// loadProfile resolves the profile path from flags or TUNNELGRAF_PROFILE,
// loads it, and enriches the tree from ~/.ssh/config. Centralised so
// every verb gets the same behaviour.
func loadProfile(g *globalFlags) (*profile.Node, error) {
	path := g.profilePath
	if path == "" {
		path = os.Getenv("TUNNELGRAF_PROFILE")
	}
	if path == "" {
		return nil, errors.New("no profile specified (use -p or set TUNNELGRAF_PROFILE)")
	}
	root, err := profile.Load(path)
	if err != nil {
		return nil, err
	}
	r, err := sshcfg.LoadUser()
	if err != nil {
		return nil, err
	}
	r.Enrich(root)
	return root, nil
}
