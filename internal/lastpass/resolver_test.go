package lastpass

import (
	"errors"
	"testing"

	"github.com/denniswalker/tunnelgraf/internal/profile"
)

func fakeResolver(secrets map[string]secret) *Resolver {
	return &Resolver{lookup: func(name string) (secret, error) {
		s, ok := secrets[name]
		if !ok {
			return secret{}, errors.New("no such secret")
		}
		return s, nil
	}}
}

func TestEnrichFillsMissingFields(t *testing.T) {
	r := fakeResolver(map[string]secret{
		"bastion_secret": {Username: "denwal", Password: "hunter2", URL: "http://10.0.0.1"},
	})
	n := &profile.Node{ID: "bastion", LastPass: "bastion_secret"}
	if err := r.Enrich(n); err != nil {
		t.Fatalf("Enrich: %v", err)
	}
	if n.Host != "10.0.0.1" {
		t.Errorf("Host = %q, want 10.0.0.1", n.Host)
	}
	if n.SSHUser != "denwal" {
		t.Errorf("SSHUser = %q", n.SSHUser)
	}
	if n.SSHPass != "hunter2" {
		t.Errorf("SSHPass = %q", n.SSHPass)
	}
}

func TestEnrichHostPlaceholderEqualToID(t *testing.T) {
	r := fakeResolver(map[string]secret{
		"bastion_secret": {URL: "http://10.0.0.1"},
	})
	// 1.x convention: host left as the node id acts as a placeholder.
	n := &profile.Node{ID: "bastion", Host: "bastion", LastPass: "bastion_secret"}
	if err := r.Enrich(n); err != nil {
		t.Fatalf("Enrich: %v", err)
	}
	if n.Host != "10.0.0.1" {
		t.Errorf("Host = %q, want 10.0.0.1", n.Host)
	}
}

func TestEnrichDoesNotOverrideExplicitValues(t *testing.T) {
	r := fakeResolver(map[string]secret{
		"bastion_secret": {Username: "denwal", Password: "hunter2", URL: "http://10.0.0.1"},
	})
	n := &profile.Node{
		ID:       "bastion",
		Host:     "explicit.example.com",
		SSHUser:  "alice",
		SSHPass:  "explicit-pass",
		LastPass: "bastion_secret",
	}
	if err := r.Enrich(n); err != nil {
		t.Fatalf("Enrich: %v", err)
	}
	if n.Host != "explicit.example.com" {
		t.Errorf("Host overwritten: %q", n.Host)
	}
	if n.SSHUser != "alice" {
		t.Errorf("SSHUser overwritten: %q", n.SSHUser)
	}
	if n.SSHPass != "explicit-pass" {
		t.Errorf("SSHPass overwritten: %q", n.SSHPass)
	}
}

func TestEnrichNoLastPassFieldIsNoop(t *testing.T) {
	r := fakeResolver(nil)
	n := &profile.Node{ID: "bastion"}
	if err := r.Enrich(n); err != nil {
		t.Fatalf("Enrich: %v", err)
	}
	if n.Host != "" {
		t.Errorf("Host mutated: %q", n.Host)
	}
}

func TestEnrichLookupErrorPropagates(t *testing.T) {
	r := fakeResolver(nil)
	n := &profile.Node{ID: "bastion", LastPass: "missing"}
	if err := r.Enrich(n); err == nil {
		t.Fatal("expected error, got nil")
	}
}

func TestEnrichWalksTree(t *testing.T) {
	r := fakeResolver(map[string]secret{
		"root_secret": {Username: "root_user", URL: "http://10.0.0.1"},
		"leaf_secret": {Username: "leaf_user", URL: "http://10.0.0.2"},
	})
	root := &profile.Node{
		ID:       "root",
		LastPass: "root_secret",
		Nexthop:  &profile.Node{ID: "leaf", LastPass: "leaf_secret"},
	}
	if err := r.Enrich(root); err != nil {
		t.Fatalf("Enrich: %v", err)
	}
	if root.SSHUser != "root_user" {
		t.Errorf("root SSHUser = %q", root.SSHUser)
	}
	if root.Nexthop.SSHUser != "leaf_user" {
		t.Errorf("leaf SSHUser = %q", root.Nexthop.SSHUser)
	}
}

func TestEnrichWalksNexthops(t *testing.T) {
	r := fakeResolver(map[string]secret{
		"a_secret": {Username: "a_user"},
		"b_secret": {Username: "b_user"},
	})
	root := &profile.Node{
		ID: "root",
		Nexthops: []*profile.Node{
			{ID: "a", LastPass: "a_secret"},
			{ID: "b", LastPass: "b_secret"},
		},
	}
	if err := r.Enrich(root); err != nil {
		t.Fatalf("Enrich: %v", err)
	}
	if root.Nexthops[0].SSHUser != "a_user" {
		t.Errorf("a SSHUser = %q", root.Nexthops[0].SSHUser)
	}
	if root.Nexthops[1].SSHUser != "b_user" {
		t.Errorf("b SSHUser = %q", root.Nexthops[1].SSHUser)
	}
}

func TestEnrichNilReceiverAndNode(t *testing.T) {
	var r *Resolver
	if err := r.Enrich(&profile.Node{ID: "x"}); err != nil {
		t.Errorf("nil receiver: %v", err)
	}
	r2 := New()
	if err := r2.Enrich(nil); err != nil {
		t.Errorf("nil node: %v", err)
	}
}
