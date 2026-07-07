package profile

import (
	"path/filepath"
	"testing"
)

func TestLoadFourInARow(t *testing.T) {
	path := filepath.Join("..", "..", "tests", "connections_profiles", "four_in_a_row.yaml")
	root, err := Load(path)
	if err != nil {
		t.Fatalf("Load: %v", err)
	}

	if root.ID != "bastion" {
		t.Errorf("root id = %q, want bastion", root.ID)
	}
	if root.Port != 2222 {
		t.Errorf("root port = %d, want 2222", root.Port)
	}
	if root.LocalBindAddress != "127.0.0.1" {
		t.Errorf("default localbindaddress not applied: %q", root.LocalBindAddress)
	}
	if root.Protocol != "ssh" {
		t.Errorf("default protocol not applied: %q", root.Protocol)
	}

	// Walk down to the leaf and check defaults propagate.
	leaf := root.Nexthop.Nexthop.Nexthop
	if leaf == nil || leaf.ID != "nginx" {
		t.Fatalf("leaf not reachable, got %+v", leaf)
	}
	if leaf.Protocol != "ssh" {
		t.Errorf("leaf protocol default not applied: %q", leaf.Protocol)
	}
	if leaf.HostsFileEntry != "nginx.local" {
		t.Errorf("leaf hosts_file_entry = %q", leaf.HostsFileEntry)
	}
}

func TestLoadIncludePrecedence(t *testing.T) {
	root, err := Load(filepath.Join("testdata", "overlay.yaml"))
	if err != nil {
		t.Fatalf("Load: %v", err)
	}

	// Overlay wins over base.
	if root.ID != "overlay_bastion" {
		t.Errorf("id = %q, want overlay_bastion (overlay should win)", root.ID)
	}
	if root.LocalBindPort != 2223 {
		t.Errorf("localbindport = %d, want 2223 (overlay)", root.LocalBindPort)
	}
	if root.SSHUser != "overlay_user" {
		t.Errorf("sshuser = %q, want overlay_user", root.SSHUser)
	}

	// Fields only present in base come through.
	if len(root.Nexthops) != 1 {
		t.Fatalf("nexthops count = %d, want 1", len(root.Nexthops))
	}
	if root.Nexthops[0].ID != "defaulted_node" {
		t.Errorf("nexthop id = %q", root.Nexthops[0].ID)
	}
	if root.Nexthops[0].Port != 443 {
		t.Errorf("nexthop port = %d", root.Nexthops[0].Port)
	}
}

func TestFlattenRewritesChildHostPort(t *testing.T) {
	path := filepath.Join("..", "..", "tests", "connections_profiles", "four_in_a_row.yaml")
	root, err := Load(path)
	if err != nil {
		t.Fatalf("Load: %v", err)
	}

	entries := Flatten(root, FlattenOptions{})
	if len(entries) != 4 {
		t.Fatalf("entries = %d, want 4", len(entries))
	}

	// Root keeps its own host/port — that's what the user types at.
	if entries[0].ID != "bastion" || entries[0].Host != "localhost" || entries[0].Port != 2222 {
		t.Errorf("root entry = %+v", entries[0])
	}
	// Children are rewritten to their local bind.
	if entries[3].ID != "nginx" || entries[3].Host != "127.0.0.1" || entries[3].Port != 2080 {
		t.Errorf("leaf entry = %+v", entries[3])
	}
}

func TestFlattenStripsCredentialsByDefault(t *testing.T) {
	path := filepath.Join("..", "..", "tests", "connections_profiles", "four_in_a_row.yaml")
	root, err := Load(path)
	if err != nil {
		t.Fatalf("Load: %v", err)
	}

	entries := Flatten(root, FlattenOptions{})
	for _, e := range entries {
		if e.SSHPass != "" || e.SSHUser != "" || e.SSHKeyFile != "" {
			t.Errorf("credentials leaked in default Flatten: %+v", e)
		}
	}

	entriesWithCreds := Flatten(root, FlattenOptions{IncludeCredentials: true})
	if entriesWithCreds[0].SSHPass != "tunnelgraf" {
		t.Errorf("credentials missing with IncludeCredentials: %+v", entriesWithCreds[0])
	}
}

func TestUnknownFieldsRejected(t *testing.T) {
	// Writing a temp profile with an unknown key should fail the strict
	// decoder, matching what we want from a schema-validated loader.
	dir := t.TempDir()
	bad := filepath.Join(dir, "bad.yaml")
	mustWriteFile(t, bad, "id: x\nlocalbindport: 1\nunknown_field: boom\n")
	if _, err := Load(bad); err == nil {
		t.Fatal("expected error on unknown field, got nil")
	}
}
