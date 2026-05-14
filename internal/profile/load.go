package profile

import (
	"fmt"
	"os"
	"path/filepath"

	"gopkg.in/yaml.v3"
)

// Load reads a profile from disk, resolves its `include` chain, and
// returns the root node with defaults applied.
//
// Precedence (highest first) matches 1.x: the loaded file, then its
// included file, then (later, in higher layers) ssh_config, then
// LastPass. Here we only implement the first two.
func Load(path string) (*Node, error) {
	abs, err := filepath.Abs(path)
	if err != nil {
		return nil, fmt.Errorf("resolve profile path: %w", err)
	}

	root, err := loadOne(abs)
	if err != nil {
		return nil, err
	}

	// The include directive is applied at the root level only: an
	// included file provides defaults that the loading file overrides.
	// 1.x only resolves include on the TunnelDefinition currently being
	// constructed, so recursive includes on children aren't a feature
	// we need to preserve.
	if root.Include != "" {
		includePath := root.Include
		if !filepath.IsAbs(includePath) {
			includePath = filepath.Join(filepath.Dir(abs), includePath)
		}
		included, err := loadOne(includePath)
		if err != nil {
			return nil, fmt.Errorf("include %q: %w", root.Include, err)
		}
		root = merge(included, root)
		root.Include = ""
	}

	root.applyDefaults()
	return root, nil
}

func loadOne(path string) (*Node, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read profile: %w", err)
	}
	var n Node
	dec := yaml.NewDecoder(bytesReader(data))
	dec.KnownFields(true)
	if err := dec.Decode(&n); err != nil {
		return nil, fmt.Errorf("parse %s: %w", path, err)
	}
	return &n, nil
}

// merge returns a new Node that is `base` with every non-zero field of
// `override` copied on top. Children lists are replaced, not merged, to
// match deepmerge's list-replace behaviour in 1.x when the override is a
// non-empty list.
func merge(base, override *Node) *Node {
	if base == nil {
		return override
	}
	if override == nil {
		return base
	}
	out := *base
	if override.ID != "" {
		out.ID = override.ID
	}
	if override.Include != "" {
		out.Include = override.Include
	}
	if override.Host != "" {
		out.Host = override.Host
	}
	if override.Port != 0 {
		out.Port = override.Port
	}
	if override.LocalBindAddress != "" {
		out.LocalBindAddress = override.LocalBindAddress
	}
	if override.LocalBindPort != 0 {
		out.LocalBindPort = override.LocalBindPort
	}
	if override.Protocol != "" {
		out.Protocol = override.Protocol
	}
	if override.SSHUser != "" {
		out.SSHUser = override.SSHUser
	}
	if override.SSHPass != "" {
		out.SSHPass = override.SSHPass
	}
	if override.SSHKeyFile != "" {
		out.SSHKeyFile = override.SSHKeyFile
	}
	if override.HostLookup != "" {
		out.HostLookup = override.HostLookup
	}
	if override.Nameserver != "" {
		out.Nameserver = override.Nameserver
	}
	if override.ProxyCommand != "" {
		out.ProxyCommand = override.ProxyCommand
	}
	if override.LastPass != "" {
		out.LastPass = override.LastPass
	}
	if override.HostsFileEntry != "" {
		out.HostsFileEntry = override.HostsFileEntry
	}
	if len(override.HostsFileEntries) > 0 {
		out.HostsFileEntries = override.HostsFileEntries
	}
	if override.Nexthop != nil {
		out.Nexthop = override.Nexthop
	}
	if len(override.Nexthops) > 0 {
		out.Nexthops = override.Nexthops
	}
	return &out
}
