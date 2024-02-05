import os
import sys
from time import sleep

import yaml
from python_hosts import Hosts, HostsEntry, HostsException

from tunnelgraf.tunnel_builder import TunnelBuilder
from tunnelgraf.tunnel_definition import TunnelDefinition


class Tunnels:
    """
    Creates an ssh tunnel, connecting a remote endpoint through a bastion
    and binding it to a local port, as specified in the provided config file.
    """

    def __init__(self, config_file: str):
        self._config_file: str = config_file
        self.config: dict | list = self._get_config()
        self.tunnel_defs: TunnelDefinition | list[TunnelDefinition] = TunnelDefinition(
            **self.config
        )
        self.tunnels: list[TunnelBuilder] = []
        self.original_hosts = Hosts()
        self.new_hosts = Hosts()
        self.make_tunnels()
        self._write_changes_to_hosts_file()
        try:
            print("Tunnels started. Press Ctrl-C to stop.")
            # INFO: on mac, check open ports 'netstat -anvp tcp | awk 'NR<3 || /LISTEN/'
            while True:
                sleep(5)
        except KeyboardInterrupt:
            print("Closing tunnels...")
            self.stop_tunnels()

    @property
    def config_file(self):
        """Returns the config file."""
        return self._config_file

    @config_file.setter
    def config_file(self, cf: str):
        """Sets the config file."""
        if not cf or isinstance(cf, str):
            raise ValueError("Config file must not be blank.")
        if not os.path.isfile(cf):
            raise ValueError(f"Config file {cf} does not exist.")
        self._config_file = cf

    def _get_config(self):
        """Returns the config file."""
        with open(self.config_file) as f:
            return yaml.load(f, Loader=yaml.FullLoader)

    def _update_bastion_address(
        self, nexthop_config: TunnelDefinition, this_parent_tunnel: TunnelBuilder
    ):
        """Updates the bastion address and port to reference the one just created."""
        nhcfg = nexthop_config
        nhcfg.host = this_parent_tunnel.tunnel.local_bind_address[0]
        nhcfg.port = this_parent_tunnel.tunnel.local_bind_address[1]
        return nhcfg

    def _write_changes_to_hosts_file(self):
        """Writes the changes to the hosts file."""
        print("Updating hosts file...")
        try:
            self.new_hosts.write()
        except HostsException as e:
            print(
                f"Error writing hosts file. Are you root or do you own the hosts file? Error: {e}"
            )
            sys.exit(1)

    def _add_to_hosts(self, what_for: str, hosts: list, this_host: str = None) -> None:
        """Adds a host to the hosts list."""
        if this_host is not None:
            hosts.append(this_host)
        if len(hosts) > 0:
            for host in hosts:
                print(f"Adding {host} to hosts file.")
                this_entry = HostsEntry(
                    address="127.0.0.1",
                    names=[host],
                    entry_type="ipv4",
                    comment=f"pytunnels entry for {what_for}",
                )
                self.new_hosts.add(entries=[this_entry], allow_address_duplication=True)

    def make_tunnels(self):
        """Creates tunnels from the config file."""
        if isinstance(self.tunnel_defs, list):
            for tunnel in self.tunnel_defs:
                self.make_tunnel(tunnel)
        if isinstance(self.tunnel_defs, TunnelDefinition):
            self.make_tunnel(self.tunnel_defs)

    def make_tunnel(self, this_tunnel_def: TunnelDefinition):
        """Creates a tunnel from the provided config."""
        if this_tunnel_def.nexthop is not None:
            # print(f"DW: Creating tunnel {this_tunnel_def}...")
            self.tunnels.append(TunnelBuilder(this_tunnel_def))
            self._add_to_hosts(
                this_tunnel_def.nexthop.id,
                this_tunnel_def.nexthop.hosts_file_entries,
                this_tunnel_def.nexthop.hosts_file_entry,
            )
            tc = self.tunnels[-1].tunnel

            print(
                f"Created tunnel {this_tunnel_def.id}: {tc.local_bind_host}:{tc.local_bind_port} to {tc._remote_binds[0][0]}:{tc._remote_binds[0][1]}"
            )
            nexthop_config = self._update_bastion_address(
                this_tunnel_def.nexthop, self.tunnels[-1]
            )
            self.make_tunnel(nexthop_config)

        if this_tunnel_def.nexthops is not None:
            this_parent_tunnel = self.tunnels[-1]
            for tunnel in this_tunnel_def.nexthops:
                nexthop_config = this_tunnel_def
                nexthop_config.nexthop = tunnel
                nexthop_config.nexthops = None
                nexthop_config = self._update_bastion_address(
                    nexthop_config, this_parent_tunnel
                )
                self.make_tunnel(nexthop_config)

    def stop_tunnels(self):
        """Stops all tunnels."""
        print("Restoring original hosts file.")
        self.original_hosts.write()
        print("Stopping tunnels...")
        for this_tunnel in list(reversed(self.tunnels)):
            print(
                f"Closing tunnel {this_tunnel.tunnel_config.id} at {this_tunnel.tunnel_config.nexthop.localbindport}..."
            )
            this_tunnel.destroy_tunnel()
