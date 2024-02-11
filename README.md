# Tunnelgraf - Hierarchical SSH tunnel management

---

Tunnelgraf is a CLI tool for connecting through a variable number of Bastion
hosts to many remote server endpoints, exposing them all as local ports. Its
intuitive YAML definitions enable version-controlled management of complex
hierarchical connections.

Tunnelgraf supports the lookup of credentials and hostname/IP endpoints via your
local ssh config file (~/.ssh/config) or Lastpass, making sharing connection
schemes more secure.

Finally, it can also populate host file entries to redirect DNS names to
localhost.

## Advantages

- Connect to arrays of sibling endpoints at any level, e.g. application servers,
  databases, etc.
- Hide credentials and hostnames so connection schemas can be securely shared
  with peers.
- Look up local bind ports in external automation tooling in the YAML config
  file.
- Populate hosts file entries in /etc/hosts and access endpoints requiring
  domain names in request headers.

## Getting Started

---

1. Install tunnelgraf with pip `pip3 install tunnelgraf`. If you run into
   dependency conflicts with other packages, use pipx insteadi, e.g.
   `pipx install tunnelgraf`.
1. Create a yaml file describing the connection hierarchy (reference the config
   example below).
1. Recommended: For personal computers, change the permissions of the hosts file
   to make it writeable by your user, e.g. `sudo chown $(whoami) /etc/hosts`.
   Also, make a backup copy of your hosts file, as this is early software.
1. Optional: If you want to use Lastpass for secrets management, install
   lastpass-cli. e.g. `brew install lastpass-cli`
1. Run `tunnelgraf ./[your config].yml`

Tunnelgraf will occupy the session until ctrl-c is pressed.

## Example Config File

---

```yaml
---
id: primary_bastion
port: 22
# Retrieves the hostname, user, and password
lastpass: primary_bastion
localbindport: 2222
nexthop:
  id: secondary_bastion
  port: 22
  sshuser: <A User>
  sshpass: <A password>
  localbindport: 2223
  nexthop:
    id: tertiary_bastion
    port: 22
    lastpass: tertiary_bastion
    localbindport: 2224
    hosts_file_entry: this.fqdn.domain.local
    nexthops:
      - id: node1
        # Example using specific credentials
        host: node1
        sshuser: <some user>
        sshpass: <some pass>
        port: 22
        localbindport: 2225
      - id: baseline_node
        host: baseline_node
        lastpass: baseline_node
        port: 22
        localbindport: 2226
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

## Configuration Precedence

Configuration data is merged from three data sources with the following
precedence.

1. The yml file data has the top priority.
2. The ssh config file has the next priority.
3. Data from Lastpass has the last priority.

An example scenario where credential come from lastpass, the host comes from the
ssh config even though it is also in lastpass, and the port is overridden in the
yml file.

Separately, if an sshkey file is specified, it takes priority over the password.
