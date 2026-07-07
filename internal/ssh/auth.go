// Package ssh wraps golang.org/x/crypto/ssh with the bits tunnelgraf
// needs: client config built from a profile.Node, direct or
// through-bastion dial, and a TOFU host-key callback.
package ssh

import (
	"errors"
	"fmt"
	"os"

	xssh "golang.org/x/crypto/ssh"

	"github.com/denniswalker/tunnelgraf/internal/profile"
)

// authMethods picks auth methods from a profile.Node. A key file, if
// given, wins over a password — matching 1.x's precedence.
func authMethods(n *profile.Node) ([]xssh.AuthMethod, error) {
	if n.SSHKeyFile != "" {
		m, err := keyfileAuth(n.SSHKeyFile)
		if err != nil {
			return nil, fmt.Errorf("load key %s: %w", n.SSHKeyFile, err)
		}
		return []xssh.AuthMethod{m}, nil
	}
	if n.SSHPass != "" {
		return []xssh.AuthMethod{xssh.Password(n.SSHPass)}, nil
	}
	return nil, errors.New("no ssh credentials (need sshkeyfile or sshpass)")
}

func keyfileAuth(path string) (xssh.AuthMethod, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	signer, err := xssh.ParsePrivateKey(b)
	if err != nil {
		// Encrypted keys land here; we don't prompt for a passphrase
		// yet. Surface the reason so users know what to do.
		return nil, fmt.Errorf("parse private key (passphrase-protected keys not yet supported): %w", err)
	}
	return xssh.PublicKeys(signer), nil
}
