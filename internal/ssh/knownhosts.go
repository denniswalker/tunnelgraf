package ssh

import (
	"errors"
	"fmt"
	"log/slog"
	"net"
	"os"
	"path/filepath"
	"sync"

	xssh "golang.org/x/crypto/ssh"
	"golang.org/x/crypto/ssh/knownhosts"
)

// HostKeyPolicy controls how the SSH client validates remote host keys.
type HostKeyPolicy int

const (
	// PolicyStrict rejects any host not already present in known_hosts.
	PolicyStrict HostKeyPolicy = iota
	// PolicyAcceptNew accepts unknown hosts on first connect and
	// appends them to known_hosts. Mismatches still fail. This matches
	// OpenSSH's StrictHostKeyChecking=accept-new.
	PolicyAcceptNew
	// PolicyInsecure skips verification entirely. Useful for ephemeral
	// test containers; a warning is logged.
	PolicyInsecure
)

// HostKeyCallback returns an ssh.HostKeyCallback implementing the given
// policy, reading/appending keys at path. An empty path defaults to
// ~/.config/tunnelgraf/known_hosts.
func HostKeyCallback(path string, policy HostKeyPolicy, log *slog.Logger) (xssh.HostKeyCallback, error) {
	if policy == PolicyInsecure {
		log.Warn("host-key verification disabled (--insecure-host-keys)")
		return xssh.InsecureIgnoreHostKey(), nil
	}

	if path == "" {
		home, err := os.UserHomeDir()
		if err != nil {
			return nil, err
		}
		path = filepath.Join(home, ".config", "tunnelgraf", "known_hosts")
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return nil, err
	}
	// Ensure the file exists so knownhosts.New doesn't error on it.
	if f, err := os.OpenFile(path, os.O_CREATE|os.O_WRONLY, 0o600); err != nil {
		return nil, err
	} else {
		_ = f.Close()
	}

	verify, err := knownhosts.New(path)
	if err != nil {
		return nil, fmt.Errorf("load known_hosts: %w", err)
	}

	if policy == PolicyStrict {
		return verify, nil
	}

	// accept-new: wrap the verifier, append on KeyError-unknown.
	var mu sync.Mutex
	return func(hostname string, remote net.Addr, key xssh.PublicKey) error {
		if err := verify(hostname, remote, key); err == nil {
			return nil
		} else {
			var keyErr *knownhosts.KeyError
			if !errors.As(err, &keyErr) || len(keyErr.Want) != 0 {
				// Either not a KeyError or a mismatch (Want is
				// populated when keys disagree). Reject.
				return err
			}
		}

		mu.Lock()
		defer mu.Unlock()

		f, err := os.OpenFile(path, os.O_APPEND|os.O_WRONLY, 0o600)
		if err != nil {
			return fmt.Errorf("append known_hosts: %w", err)
		}
		defer func() { _ = f.Close() }()
		line := knownhosts.Line([]string{knownhosts.Normalize(hostname)}, key)
		if _, err := fmt.Fprintln(f, line); err != nil {
			return fmt.Errorf("write known_hosts: %w", err)
		}
		log.Info("accepted new host key", "host", hostname, "type", key.Type())
		return nil
	}, nil
}
