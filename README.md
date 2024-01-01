# Pytunnels - Hierarchical SSH tunnel management

---

Pytunnels is a CLI tool for connecting through a variable number of Bastion
hosts to many remote server endpoints, exposing them all as local ports. Its
intuitive YAML definitions enable version-controlled management of complex
hierarchical connections.

Pytunnels supports the lookup of credentials and hostname/IP endpoints via
Lastpass, making sharing connection schemes more secure.

Finally, it can also populate host file entries to redirect DNS names to
localhost.

## Getting Started

---

1. Checkout the repo
1. Run `pyinstaller --onefile ./pytunnels`.
1. Move the executable in the 'dist' directory into your PATH.
1. Create a yaml file describing the connection hierarchy (reference the config
   example below).
1. Recommended: For personal computers, change the permissions of the hosts file
   to make it writeable by your user. e.g. `sudo shown $(whoami) /etc/hosts`
1. Run `pytunnels ./[your config].yml`

Pytunnels will occupy the session until ctrl-c is pressed.

## Example Config File

---

```yaml
---
id: primary_bastion
port: 22
# Retrieves the hostname, user, and password
lastpass: primary_bastion
nexthop:
  id: secondary_bastion
  port: 22
  lastpass: secondary_bastion
  localbindport: 2222
  nexthop:
    id: tertiary_bastion
    port: 22
    lastpass: tertiary_bastion
    localbindport: 2223
    hosts_file_entry: this.fqdn.domain.local
    nexthop:
      - id: node1
        # Example using specific credentials
        host: node1
        user: [some user]
        pass: [some pass]
        port: 22
        localbindport: 2224
      - id: baseline_node
        host: baseline_node
        lastpass: baseline_node
        port: 22
        localbindport: 2225
      - id: another_endpoint
        host: gw-service.local
        hosts_file_entries:
          - gw-service.local
          - thisother.fqdn.domain.local
        port: 443
        localbindport: 8443
```

In the above example pytunnels opens nested ssh tunnels for the primary,
secondary, and tertiary bastion hosts. It then connects to the final 3 endpoints
through the tertiary endpoint.
