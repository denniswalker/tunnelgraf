import os
import sys
from time import sleep
from pathlib import Path

import yaml
from python_hosts import Hosts, HostsEntry, HostsException

from tunnelgraf import config
from tunnelgraf.tunnel_builder import TunnelBuilder
from tunnelgraf.tunnel_definition import TunnelDefinition
from tunnelgraf.run_remote import RunCommand
from tunnelgraf.nslookup import NSLookup


class Tunnels:
    """
    Creates an ssh tunnel, connecting a remote endpoint through a bastion
    and binding it to a local port, as specified in the provided config file.
    """

    def __init__(
        self,
        config_file_path: Path,
        connect_tunnels: bool = True,
        show_credentials: bool = False,
    ):
        with config_file_path.open() as cf:
            self._config_file: str = cf.read()
        self.config: dict | list = self._get_config()
        config.CONFIG_FILE_PATH = str(config_file_path.parent)
        self.tunnel_defs: TunnelDefinition | list[TunnelDefinition] = TunnelDefinition(
            **self.config
        )
        self._excluded_fields: list[str] = [
            "nexthop",
            "nexthops",
            "localbindaddress",
            "localbindport",
        ]
        if not show_credentials:
            self._excluded_fields += ["sshuser", "sshpass", "sshkeyfile"]
        self.tunnels: list[TunnelBuilder] = []
        self.tunnel_configs: list[TunnelDefinition] = []
        self.original_hosts = Hosts()
        self.new_hosts = Hosts()
        self._connect_tunnels: bool = connect_tunnels
        self.make_tunnels()
        if self._connect_tunnels:
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
        return yaml.load(self.config_file, Loader=yaml.FullLoader)

    def _update_bastion_address(self, nexthop_config: TunnelDefinition):
        """Updates the bastion address and port to reference the one just created."""
        nhcfg = nexthop_config
        nhcfg.host = nexthop_config.localbindaddress
        nhcfg.port = nexthop_config.localbindport
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

    def _add_to_hosts(
        self,
        what_for: str,
        hosts: list,
        this_host: str | None = None,
        this_host_lookup: str | None = None,
    ) -> None:
        """Adds a host to the hosts list."""
        if this_host is not None:
            hosts.append(this_host)
        if this_host_lookup is not None:
            hosts.append(this_host_lookup)
        if len(hosts) > 0:
            for host in hosts:
                if self._connect_tunnels:
                    print(f"{host} will be added to hosts file.")
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

        self._add_to_processed_configs(this_tunnel_def)
        if this_tunnel_def.nexthop is not None:
            if self._connect_tunnels:
                if this_tunnel_def.nexthop.hostlookup is not None:
                    this_tunnel_def.nexthop.host = self._lookup_host(this_tunnel_def)
                self.tunnels.append(TunnelBuilder(this_tunnel_def))
                tc = self.tunnels[-1].tunnel
                print(
                    f"Tunnel ID: {this_tunnel_def.nexthop.id} - Created {tc.local_bind_host}:{tc.local_bind_port} to {tc._remote_binds[0][0]}:{tc._remote_binds[0][1]}"
                )
            self._add_to_hosts(
                this_tunnel_def.nexthop.id,
                this_tunnel_def.nexthop.hosts_file_entries,
                this_tunnel_def.nexthop.hosts_file_entry,
                this_tunnel_def.nexthop.hostlookup,
            )

            nexthop_config = self._update_bastion_address(this_tunnel_def.nexthop)
            self.make_tunnel(nexthop_config)

        if this_tunnel_def.nexthops is not None:
            for tunnel in this_tunnel_def.nexthops:
                nexthop_config = this_tunnel_def
                nexthop_config.nexthop = tunnel
                nexthop_config.nexthops = None
                nexthop_config = self._update_bastion_address(nexthop_config)
                self.make_tunnel(nexthop_config)

    def _lookup_host(self, this_tunnel_def: TunnelDefinition) -> str | None:
        print(
            f"Tunnel ID: {this_tunnel_def.nexthop.id} - Looking up {this_tunnel_def.nexthop.hostlookup}..."
        )
        this_connection = RunCommand(
            host=this_tunnel_def.host,
            user=this_tunnel_def.sshuser,
            identityfile=this_tunnel_def.sshkeyfile,
            password=this_tunnel_def.sshpass,
            port=this_tunnel_def.localbindport,
        )
        return NSLookup(
            record=this_tunnel_def.nexthop.hostlookup,
            nameserver=this_tunnel_def.nexthop.nameserver,
            connection=this_connection,
        ).host_ip

    def _add_to_processed_configs(self, this_tunnel_def: TunnelDefinition):
        """Adds a tunnel to the processed configs."""
        if not any(this_tunnel_def.id == t["id"] for t in self.tunnel_configs):
            self.tunnel_configs.append(
                this_tunnel_def.model_dump(exclude=self._excluded_fields)
            )

    def stop_tunnels(self):
        """Stops all tunnels."""
        print("Restoring original hosts file.")
        self.original_hosts.write()
        print("Stopping tunnels...")
        for this_tunnel in list(reversed(self.tunnels)):
            print(
                f"Closing tunnel {this_tunnel.tunnel.local_bind_hosts[0]}:{this_tunnel.tunnel.local_bind_ports[0]}..."
            )
            this_tunnel.destroy_tunnel()
