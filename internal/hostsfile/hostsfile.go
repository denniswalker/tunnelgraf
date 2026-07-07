// Package hostsfile adds and removes /etc/hosts entries for the
// hosts_file_entry / hosts_file_entries nodes in a profile, so
// endpoints that need a domain name (vhost routing, TLS SNI, etc.)
// resolve to their local tunnel bind. This mirrors 1.x's
// HostsManager: entries point at 127.0.0.1, get tagged with a marker
// comment, and the pre-connect file contents are restored on
// disconnect.
package hostsfile

import (
	"fmt"
	"os"
	"runtime"
	"strings"
)

// marker tags every line tunnelgraf adds, so a later Restore call can
// tell its own entries apart from anything the user or another tool
// put there.
const marker = "# added by tunnelgraf"

// DefaultPath returns the OS-appropriate hosts file location.
func DefaultPath() string {
	if runtime.GOOS == "windows" {
		return `C:\Windows\System32\drivers\etc\hosts`
	}
	return "/etc/hosts"
}

// Manager adds tunnelgraf-managed 127.0.0.1 entries to a hosts file
// and restores the original contents afterward. The zero value is not
// usable; construct with New.
type Manager struct {
	path     string
	original []byte // nil until Apply has run
}

// New returns a Manager for the hosts file at path.
func New(path string) *Manager {
	return &Manager{path: path}
}

// Apply reads the current file, strips any leftover tunnelgraf lines
// from a prior run that never got to Restore (e.g. after a crash), and
// appends one 127.0.0.1 line per name in names. The stripped content
// is kept as the baseline for Restore. Duplicate names are collapsed.
// A nil/empty names is a no-op that never touches the file.
func (m *Manager) Apply(names []string) error {
	names = dedupe(names)
	if len(names) == 0 {
		return nil
	}

	info, err := os.Stat(m.path)
	if err != nil {
		return fmt.Errorf("stat hosts file %s: %w", m.path, err)
	}
	raw, err := os.ReadFile(m.path)
	if err != nil {
		return fmt.Errorf("read hosts file %s: %w", m.path, err)
	}
	m.original = stripManaged(raw)

	var b strings.Builder
	b.Write(m.original)
	if b.Len() > 0 && !strings.HasSuffix(b.String(), "\n") {
		b.WriteByte('\n')
	}
	for _, n := range names {
		fmt.Fprintf(&b, "127.0.0.1 %s %s\n", n, marker)
	}

	if err := os.WriteFile(m.path, []byte(b.String()), info.Mode()); err != nil {
		return fmt.Errorf("write hosts file %s (are you root, or does your user own the file? see README): %w", m.path, err)
	}
	return nil
}

// Restore writes the pre-Apply contents back. A no-op if Apply was
// never called or added nothing.
func (m *Manager) Restore() error {
	if m.original == nil {
		return nil
	}
	mode := os.FileMode(0o644)
	if info, err := os.Stat(m.path); err == nil {
		mode = info.Mode()
	}
	if err := os.WriteFile(m.path, m.original, mode); err != nil {
		return fmt.Errorf("restore hosts file %s: %w", m.path, err)
	}
	return nil
}

// stripManaged drops every line carrying marker, preserving the rest
// verbatim (including blank lines and trailing newline shape).
func stripManaged(content []byte) []byte {
	lines := strings.Split(string(content), "\n")
	kept := lines[:0]
	for _, l := range lines {
		if strings.Contains(l, marker) {
			continue
		}
		kept = append(kept, l)
	}
	return []byte(strings.Join(kept, "\n"))
}

// dedupe returns names with blanks dropped and repeats collapsed,
// preserving first-seen order.
func dedupe(names []string) []string {
	seen := make(map[string]bool, len(names))
	out := make([]string, 0, len(names))
	for _, n := range names {
		if n == "" || seen[n] {
			continue
		}
		seen[n] = true
		out = append(out, n)
	}
	return out
}
