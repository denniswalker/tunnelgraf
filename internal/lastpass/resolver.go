// Package lastpass enriches a profile tree with credentials looked up
// from LastPass via the `lpass` CLI. It's the lowest-precedence
// credential source: applied after YAML and ssh_config, matching
// 1.x's ordering (file, include, ssh_config, then LastPass).
package lastpass

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os/exec"
	"strings"

	"github.com/denniswalker/tunnelgraf/internal/profile"
)

// secret is one entry from `lpass show --json <name>`.
type secret struct {
	Username string `json:"username"`
	Password string `json:"password"`
	URL      string `json:"url"`
}

// lookupFunc fetches a named secret. Swapped out in tests.
type lookupFunc func(name string) (secret, error)

// Resolver applies LastPass-sourced credentials to profile nodes.
type Resolver struct {
	lookup lookupFunc
}

// New returns a Resolver backed by the real `lpass` CLI.
func New() *Resolver {
	return &Resolver{lookup: cliLookup}
}

func cliLookup(name string) (secret, error) {
	cmd := exec.Command("lpass", "show", "--json", name)
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		return secret{}, fmt.Errorf("lpass show %s: %w: %s", name, err, strings.TrimSpace(stderr.String()))
	}
	var secrets []secret
	if err := json.Unmarshal(stdout.Bytes(), &secrets); err != nil {
		return secret{}, fmt.Errorf("parse lpass output for %s: %w", name, err)
	}
	if len(secrets) == 0 {
		return secret{}, fmt.Errorf("no lastpass entry named %s", name)
	}
	return secrets[0], nil
}

// Enrich walks the tree rooted at n, resolving each node's `lastpass`
// field to host/sshuser/sshpass. Existing (YAML- or ssh_config-sourced)
// values always win: host is only set from the secret's URL when host
// is unset or still equal to id (the 1.x placeholder convention), and
// sshuser/sshpass are only set when empty.
func (r *Resolver) Enrich(n *profile.Node) error {
	if r == nil || n == nil {
		return nil
	}
	if err := r.enrichOne(n); err != nil {
		return err
	}
	if n.Nexthop != nil {
		if err := r.Enrich(n.Nexthop); err != nil {
			return err
		}
	}
	for _, c := range n.Nexthops {
		if err := r.Enrich(c); err != nil {
			return err
		}
	}
	return nil
}

func (r *Resolver) enrichOne(n *profile.Node) error {
	if n.LastPass == "" {
		return nil
	}
	s, err := r.lookup(n.LastPass)
	if err != nil {
		return fmt.Errorf("node %s: %w", n.ID, err)
	}
	if (n.Host == "" || n.Host == n.ID) && s.URL != "" {
		n.Host = strings.TrimPrefix(s.URL, "http://")
	}
	if n.SSHUser == "" {
		n.SSHUser = s.Username
	}
	if n.SSHPass == "" {
		n.SSHPass = s.Password
	}
	return nil
}
