package hostsfile

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func writeTemp(t *testing.T, content string) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), "hosts")
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatalf("write temp hosts: %v", err)
	}
	return path
}

func TestApplyAppendsAndRestoreReverts(t *testing.T) {
	const original = "127.0.0.1 localhost\n::1 localhost\n"
	path := writeTemp(t, original)

	m := New(path)
	if err := m.Apply([]string{"gitlab.example.com", "app.example.com"}); err != nil {
		t.Fatalf("Apply: %v", err)
	}

	got, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read: %v", err)
	}
	if !strings.Contains(string(got), original) {
		t.Errorf("original content missing after Apply:\n%s", got)
	}
	if !strings.Contains(string(got), "127.0.0.1 gitlab.example.com "+marker) {
		t.Errorf("gitlab entry missing:\n%s", got)
	}
	if !strings.Contains(string(got), "127.0.0.1 app.example.com "+marker) {
		t.Errorf("app entry missing:\n%s", got)
	}

	if err := m.Restore(); err != nil {
		t.Fatalf("Restore: %v", err)
	}
	restored, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read after restore: %v", err)
	}
	if string(restored) != original {
		t.Errorf("Restore = %q, want %q", restored, original)
	}
}

func TestApplyNoNamesIsNoop(t *testing.T) {
	const original = "127.0.0.1 localhost\n"
	path := writeTemp(t, original)

	m := New(path)
	if err := m.Apply(nil); err != nil {
		t.Fatalf("Apply: %v", err)
	}
	got, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read: %v", err)
	}
	if string(got) != original {
		t.Errorf("file changed on empty Apply: %q", got)
	}
	// Restore before Apply ever added anything must also be a no-op.
	if err := m.Restore(); err != nil {
		t.Fatalf("Restore: %v", err)
	}
}

func TestApplyDedupesNames(t *testing.T) {
	path := writeTemp(t, "127.0.0.1 localhost\n")

	m := New(path)
	if err := m.Apply([]string{"a.example.com", "a.example.com"}); err != nil {
		t.Fatalf("Apply: %v", err)
	}
	got, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read: %v", err)
	}
	if n := strings.Count(string(got), "a.example.com"); n != 1 {
		t.Errorf("a.example.com appears %d times, want 1:\n%s", n, got)
	}
}

// TestApplySelfHealsStaleEntries simulates a prior run that crashed
// before Restore ran: its tunnelgraf-tagged lines are still in the
// file. A fresh Apply should treat those as noise, not as part of the
// "original" content to preserve, so Restore ends up clean instead of
// re-accumulating stale entries forever.
func TestApplySelfHealsStaleEntries(t *testing.T) {
	stale := "127.0.0.1 localhost\n" +
		"127.0.0.1 old.example.com " + marker + "\n"
	path := writeTemp(t, stale)

	m := New(path)
	if err := m.Apply([]string{"new.example.com"}); err != nil {
		t.Fatalf("Apply: %v", err)
	}
	got, _ := os.ReadFile(path)
	if strings.Contains(string(got), "old.example.com") {
		t.Errorf("stale entry survived Apply:\n%s", got)
	}

	if err := m.Restore(); err != nil {
		t.Fatalf("Restore: %v", err)
	}
	restored, _ := os.ReadFile(path)
	if strings.Contains(string(restored), marker) {
		t.Errorf("Restore left tunnelgraf-tagged lines behind:\n%s", restored)
	}
	if !strings.Contains(string(restored), "127.0.0.1 localhost") {
		t.Errorf("Restore lost unrelated content:\n%s", restored)
	}
}
