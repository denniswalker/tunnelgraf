// Package transfer copies files between local and remote filesystems
// over an existing ssh.Client, using SFTP. It replaces 1.x's shell-out
// to /usr/bin/scp + sshpass, so passwords never reach argv and no
// external binaries need to be on PATH.
package transfer

import (
	"errors"
	"strings"
)

// Direction encodes which way the bytes are moving.
type Direction int

const (
	Upload   Direction = iota // local -> remote
	Download                  // remote -> local
)

// Spec is a parsed source/destination pair.
type Spec struct {
	TunnelID  string
	Local     string
	Remote    string
	Direction Direction
}

// ParseSpec interprets a pair of scp-style arguments. A bare local
// path stays local; `id:path` is remote-on-the-node-named-id.
// explicitTunnelID, if set, overrides any prefix found in the args —
// this lets two bare local paths turn into an upload when the user
// has told us which tunnel to target via --tunnel-id.
func ParseSpec(source, destination, explicitTunnelID string) (Spec, error) {
	srcID, srcPath, srcRemote := splitRemote(source)
	dstID, dstPath, dstRemote := splitRemote(destination)

	if srcRemote && dstRemote {
		return Spec{}, errors.New("cannot transfer between two remote locations")
	}

	switch {
	case srcRemote:
		id := srcID
		if explicitTunnelID != "" {
			id = explicitTunnelID
		}
		return Spec{TunnelID: id, Remote: srcPath, Local: destination, Direction: Download}, nil
	case dstRemote:
		id := dstID
		if explicitTunnelID != "" {
			id = explicitTunnelID
		}
		return Spec{TunnelID: id, Remote: dstPath, Local: source, Direction: Upload}, nil
	default:
		if explicitTunnelID == "" {
			return Spec{}, errors.New("either source or destination must use tunnel_id:path, or pass --tunnel-id")
		}
		// Both bare paths + explicit id: treat as upload so users can
		// do `tunnelgraf -t web scp ./deploy.sh /opt/app/deploy.sh`
		// without the `web:` prefix noise.
		return Spec{TunnelID: explicitTunnelID, Local: source, Remote: destination, Direction: Upload}, nil
	}
}

// splitRemote reports whether s is in `id:path` form. A colon at
// position 0 or after a path separator doesn't count.
func splitRemote(s string) (id, path string, remote bool) {
	// A leading '/' or '.' or '~' means a local path; no scan needed.
	if s == "" {
		return "", "", false
	}
	if s[0] == '/' || s[0] == '.' || s[0] == '~' {
		return "", s, false
	}
	i := strings.Index(s, ":")
	if i <= 0 {
		return "", s, false
	}
	// Reject if a path separator appears before the colon — that's a
	// local relative path like `foo/bar:baz`, not a tunnel prefix.
	if strings.ContainsAny(s[:i], "/\\") {
		return "", s, false
	}
	return s[:i], s[i+1:], true
}
