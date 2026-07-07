// Package profile loads and normalises tunnelgraf YAML profiles.
//
// The YAML schema matches 1.x field-for-field so existing profiles load
// unchanged. Integration with ~/.ssh/config and external secrets backends
// is handled by separate packages and layered on top of the plain profile
// tree this package produces.
package profile

// Node is one entry in the tunnel tree. It mirrors the 1.x
// TunnelDefinition model; unknown YAML keys are rejected at load time.
type Node struct {
	ID               string   `yaml:"id"`
	Include          string   `yaml:"include,omitempty" json:"include,omitempty"`
	Host             string   `yaml:"host,omitempty" json:"host,omitempty"`
	Port             int      `yaml:"port,omitempty" json:"port,omitempty"`
	LocalBindAddress string   `yaml:"localbindaddress,omitempty" json:"localbindaddress,omitempty"`
	LocalBindPort    int      `yaml:"localbindport,omitempty" json:"localbindport,omitempty"`
	Protocol         string   `yaml:"protocol,omitempty" json:"protocol,omitempty"`
	SSHUser          string   `yaml:"sshuser,omitempty" json:"sshuser,omitempty"`
	SSHPass          string   `yaml:"sshpass,omitempty" json:"sshpass,omitempty"`
	SSHKeyFile       string   `yaml:"sshkeyfile,omitempty" json:"sshkeyfile,omitempty"`
	HostLookup       string   `yaml:"hostlookup,omitempty" json:"hostlookup,omitempty"`
	Nameserver       string   `yaml:"nameserver,omitempty" json:"nameserver,omitempty"`
	ProxyCommand     string   `yaml:"proxycommand,omitempty" json:"proxycommand,omitempty"`
	LastPass         string   `yaml:"lastpass,omitempty" json:"lastpass,omitempty"`
	HostsFileEntry   string   `yaml:"hosts_file_entry,omitempty" json:"hosts_file_entry,omitempty"`
	HostsFileEntries []string `yaml:"hosts_file_entries,omitempty" json:"hosts_file_entries,omitempty"`
	Nexthop          *Node    `yaml:"nexthop,omitempty" json:"nexthop,omitempty"`
	Nexthops         []*Node  `yaml:"nexthops,omitempty" json:"nexthops,omitempty"`
}

// applyDefaults fills in the values 1.x's Pydantic model defaulted.
// It only mutates fields that are their zero value, so explicit YAML
// always wins.
func (n *Node) applyDefaults() {
	if n.Port == 0 {
		n.Port = 22
	}
	if n.LocalBindAddress == "" {
		n.LocalBindAddress = "127.0.0.1"
	}
	if n.Protocol == "" {
		n.Protocol = "ssh"
	}
	if n.Nexthop != nil {
		n.Nexthop.applyDefaults()
	}
	for _, c := range n.Nexthops {
		c.applyDefaults()
	}
}

// Children returns the effective list of direct children regardless of
// whether the YAML used the singular or plural form.
func (n *Node) Children() []*Node {
	if len(n.Nexthops) > 0 {
		return n.Nexthops
	}
	if n.Nexthop != nil {
		return []*Node{n.Nexthop}
	}
	return nil
}
