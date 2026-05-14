package sshcfg

import (
	"path/filepath"
	"testing"

	"github.com/denniswalker/tunnelgraf/internal/profile"
)

func TestEnrichFillsMissingFields(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "config")
	mustWrite(t, path, `
Host sshd1
	HostName 10.0.0.1
	User root
	Port 2201
	IdentityFile /tmp/sshd1_id
`)

	r, err := Load(path)
	if err != nil {
		t.Fatalf("Load: %v", err)
	}

	n := &profile.Node{ID: "sshd1"}
	r.Enrich(n)

	if n.Host != "10.0.0.1" {
		t.Errorf("Host = %q, want 10.0.0.1", n.Host)
	}
	if n.SSHUser != "root" {
		t.Errorf("SSHUser = %q", n.SSHUser)
	}
	if n.Port != 2201 {
		t.Errorf("Port = %d", n.Port)
	}
	if n.SSHKeyFile != "/tmp/sshd1_id" {
		t.Errorf("SSHKeyFile = %q", n.SSHKeyFile)
	}
}

func TestEnrichDoesNotOverrideYAML(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "config")
	mustWrite(t, path, "Host sshd1\n\tHostName 10.0.0.1\n\tUser root\n")

	r, err := Load(path)
	if err != nil {
		t.Fatalf("Load: %v", err)
	}

	// YAML-provided values must win.
	n := &profile.Node{ID: "sshd1", Host: "explicit.example.com", SSHUser: "alice"}
	r.Enrich(n)

	if n.Host != "explicit.example.com" {
		t.Errorf("Host overwritten: %q", n.Host)
	}
	if n.SSHUser != "alice" {
		t.Errorf("SSHUser overwritten: %q", n.SSHUser)
	}
}

func TestEnrichMissingFileIsNoop(t *testing.T) {
	r, err := Load(filepath.Join(t.TempDir(), "does-not-exist"))
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	n := &profile.Node{ID: "sshd1"}
	r.Enrich(n) // should not panic or change n
	if n.Host != "" {
		t.Errorf("Host mutated: %q", n.Host)
	}
}

func TestEnrichWalksTree(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "config")
	mustWrite(t, path,
		"Host root\n\tHostName 10.0.0.1\n"+
			"Host leaf\n\tHostName 10.0.0.2\n",
	)
	r, err := Load(path)
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	root := &profile.Node{
		ID:      "root",
		Nexthop: &profile.Node{ID: "leaf"},
	}
	r.Enrich(root)
	if root.Host != "10.0.0.1" {
		t.Errorf("root host = %q", root.Host)
	}
	if root.Nexthop.Host != "10.0.0.2" {
		t.Errorf("leaf host = %q", root.Nexthop.Host)
	}
}
