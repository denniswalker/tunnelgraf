package profile

// Entry is one row in the flattened view of the tunnel tree, as
// produced by 1.x's `show` / `urls` output. The Host and Port fields
// are the local bind address that callers on this machine should use,
// not the upstream's original address.
type Entry struct {
	ID               string   `json:"id"`
	Host             string   `json:"host"`
	Port             int      `json:"port"`
	Protocol         string   `json:"protocol"`
	SSHUser          string   `json:"sshuser,omitempty"`
	SSHPass          string   `json:"sshpass,omitempty"`
	SSHKeyFile       string   `json:"sshkeyfile,omitempty"`
	HostsFileEntry   string   `json:"hosts_file_entry,omitempty"`
	HostsFileEntries []string `json:"hosts_file_entries,omitempty"`
	LastPass         string   `json:"lastpass,omitempty"`
	HostLookup       string   `json:"hostlookup,omitempty"`
	Nameserver       string   `json:"nameserver,omitempty"`
}

// FlattenOptions controls what Flatten emits.
type FlattenOptions struct {
	// IncludeCredentials keeps sshuser/sshpass/sshkeyfile in the output.
	// 1.x defaults to stripping them (show_credentials=False).
	IncludeCredentials bool
}

// Flatten walks the tree and returns each reachable node as an Entry.
// The root's own host/port are preserved; every child's host/port are
// rewritten to its local bind, matching 1.x's _update_bastion_address
// behaviour which makes the flat view a "how do I reach this from
// localhost?" listing.
func Flatten(root *Node, opts FlattenOptions) []Entry {
	if root == nil {
		return nil
	}
	var out []Entry
	seen := map[string]bool{}
	// The root entry uses the root's own host/port — this is the
	// jumpbox the user actually types at. Subsequent entries are
	// children reached through their local bind.
	walk(root, &out, seen, opts, true)
	return out
}

func walk(n *Node, out *[]Entry, seen map[string]bool, opts FlattenOptions, isRoot bool) {
	if n == nil || seen[n.ID] {
		return
	}
	seen[n.ID] = true

	host, port := n.Host, n.Port
	if !isRoot {
		// 1.x rewrites host/port to the local bind when this node is
		// reached through a parent tunnel.
		host = n.LocalBindAddress
		port = n.LocalBindPort
	}

	e := Entry{
		ID:               n.ID,
		Host:             host,
		Port:             port,
		Protocol:         n.Protocol,
		HostsFileEntry:   n.HostsFileEntry,
		HostsFileEntries: n.HostsFileEntries,
		LastPass:         n.LastPass,
		HostLookup:       n.HostLookup,
		Nameserver:       n.Nameserver,
	}
	if opts.IncludeCredentials {
		e.SSHUser = n.SSHUser
		e.SSHPass = n.SSHPass
		e.SSHKeyFile = n.SSHKeyFile
	}
	*out = append(*out, e)

	for _, c := range n.Children() {
		walk(c, out, seen, opts, false)
	}
}
