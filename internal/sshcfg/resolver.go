// Package sshcfg enriches a profile tree with values pulled from
// ~/.ssh/config. It's separate from profile.Load so tests and tools
// that don't want host-environment state can opt out.
package sshcfg

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strconv"

	"github.com/kevinburke/ssh_config"

	"github.com/denniswalker/tunnelgraf/internal/profile"
)

// Resolver wraps a parsed ssh_config and applies its values to
// profile nodes. The zero Resolver is a no-op, so callers can pass a
// Resolver{} when a config file is absent.
type Resolver struct {
	cfg *ssh_config.Config
}

// LoadUser opens the user's ~/.ssh/config. A missing file is not an
// error — we return an empty Resolver. Parse errors are surfaced.
func LoadUser() (*Resolver, error) {
	home, err := os.UserHomeDir()
	if err != nil {
		return nil, err
	}
	return Load(filepath.Join(home, ".ssh", "config"))
}

// Load parses an ssh_config file at the given path.
func Load(path string) (*Resolver, error) {
	f, err := os.Open(path)
	if errors.Is(err, os.ErrNotExist) {
		return &Resolver{}, nil
	}
	if err != nil {
		return nil, fmt.Errorf("open ssh_config: %w", err)
	}
	defer func() { _ = f.Close() }()
	cfg, err := ssh_config.Decode(f)
	if err != nil {
		return nil, fmt.Errorf("parse ssh_config: %w", err)
	}
	return &Resolver{cfg: cfg}, nil
}

// Enrich walks the tree rooted at n and fills in fields missing from
// YAML using per-node id lookups. Precedence matches 1.x exactly,
// including the quirk that port==22 is treated as "unset" — users who
// set port=22 explicitly in YAML will have ssh_config overrides win,
// just as they did on 1.x.
func (r *Resolver) Enrich(n *profile.Node) {
	if r == nil || r.cfg == nil || n == nil {
		return
	}
	r.enrichOne(n)
	if n.Nexthop != nil {
		r.Enrich(n.Nexthop)
	}
	for _, c := range n.Nexthops {
		r.Enrich(c)
	}
}

func (r *Resolver) enrichOne(n *profile.Node) {
	get := func(key string) string {
		v, _ := r.cfg.Get(n.ID, key)
		return v
	}
	if n.SSHUser == "" {
		n.SSHUser = get("User")
	}
	// 1.x: "if self.port == 22". Treat 0 OR 22 as "open for ssh_config
	// to override", so users who set port=22 explicitly in YAML still
	// get ssh_config overrides (matches 1.x quirk for migration).
	if n.Port == 0 || n.Port == 22 {
		if p := get("Port"); p != "" {
			if parsed, err := strconv.Atoi(p); err == nil {
				n.Port = parsed
			}
		}
	}
	if n.Host == "" {
		n.Host = get("HostName")
	}
	if n.SSHKeyFile == "" {
		n.SSHKeyFile = get("IdentityFile")
	}
	// ssh_config has no standard "Password" key — 1.x read it anyway
	// from a custom field. Support it for drop-in compatibility.
	if n.SSHPass == "" {
		n.SSHPass = get("Password")
	}
}
