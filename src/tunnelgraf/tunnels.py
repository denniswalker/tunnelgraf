import os
import threading
from time import sleep
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import signal
import sys
import time

import yaml
from python_hosts import Hosts, HostsEntry, HostsException

from tunnelgraf import config
from tunnelgraf.tunnel_builder import TunnelBuilder
from tunnelgraf.tunnel_definition import TunnelDefinition
from tunnelgraf.run_remote import RunCommand
from tunnelgraf.nslookup import NSLookup
from tunnelgraf.hosts_manager import HostsManager


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
        detach: bool = False,
    ):
        self.detach = detach
        with config_file_path.open() as cf:
            self._config_file: str = cf.read()
        self.config: dict | list = self._get_config()
        config.CONFIG_FILE_PATH = str(config_file_path.parent)
        self.tunnel_defs: TunnelDefinition | list[TunnelDefinition] = TunnelDefinition(
            **self.config
        )
        self._excluded_fields: list[str] = self._get_excluded_fields(show_credentials)
        self.tunnels: list[TunnelBuilder] = []
        self.tunnel_configs: list[TunnelDefinition] = []
        self.hosts_manager = HostsManager()
        self._connect_tunnels: bool = connect_tunnels
        self.threads: list[threading.Thread] = []
        self.make_tunnels()
        if self._connect_tunnels:
            self._monitor_tunnels()

    def _get_excluded_fields(self, show_credentials: bool) -> list[str]:
        fields = ["nexthop", "nexthops", "localbindaddress", "localbindport"]
        if not show_credentials:
            fields += ["sshuser", "sshpass", "sshkeyfile"]
        return fields

    def _monitor_tunnels(self):
        try:
            for thread in self.threads:
                thread.join()
            self.hosts_manager.write_changes_to_hosts_file()
            print("Tunnels started. Press Ctrl-C to stop.")
            while True:
                self._check_tunnel_status()
                sleep(5)
        except KeyboardInterrupt:
            self.stop_tunnels()
            print("Goodbye!")
            exit(0)

    def _check_tunnel_status(self):
        """Checks the status of tunnels and prints the number of active tunnels and IDs of down tunnels."""
        active_tunnels = 0
        down_tunnels = []
        for tunnel in self.tunnels:
            if tunnel.tunnel.tunnel_is_up:
                active_tunnels += 1
            else:
                down_tunnels.append(tunnel.tunnel_config.nexthop.id)
        status_message = f"Active tunnels: {active_tunnels} of {len(self.tunnels)}"
        if down_tunnels:
            status_message += f"\033[91m, Down tunnels: {', '.join(down_tunnels)}\033[0m"
        else:
            status_message += "\033[92m, All tunnels are active.\033[0m"
        if not self.detach:
            print(f"\r{status_message}", end="")
        else:
            print(f"{status_message}")

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

    def make_tunnels(self):
        """Creates tunnels from the config file."""
        if isinstance(self.tunnel_defs, list):
            for tunnel in self.tunnel_defs:
                self.make_tunnel(tunnel)
        elif isinstance(self.tunnel_defs, TunnelDefinition):
            self.make_tunnel(self.tunnel_defs) 

    def make_tunnel(self, this_tunnel_def: TunnelDefinition):
        """Creates a tunnel from the provided config."""
        self._add_to_processed_configs(this_tunnel_def)
        if this_tunnel_def.nexthop:
            if this_tunnel_def.nexthop.nexthops is None and this_tunnel_def.nexthop.nexthop is None:
                tunnel_thread = threading.Thread(target=self._process_nexthop, args=(this_tunnel_def,))
                tunnel_thread.start()
                self.threads.append(tunnel_thread)
            else:
                self._process_nexthop(this_tunnel_def)
        if this_tunnel_def.nexthops:
            self._process_nexthops(this_tunnel_def)

    def _process_nexthop(self, this_tunnel_def: TunnelDefinition):
        if self._connect_tunnels:
            self.tunnels.append(TunnelBuilder(this_tunnel_def))
        nexthop_config = self._update_bastion_address(this_tunnel_def.nexthop)
        self.make_tunnel(nexthop_config)

    def _process_nexthops(self, this_tunnel_def: TunnelDefinition):
        for tunnel in this_tunnel_def.nexthops:
            nexthop_config = this_tunnel_def.model_copy(update={"nexthop": tunnel, "nexthops": None})
            nexthop_config = self._update_bastion_address(nexthop_config)
            self.make_tunnel(nexthop_config)

    def _add_to_processed_configs(self, this_tunnel_def: TunnelDefinition):
        """Adds a tunnel to the processed configs."""
        if not any(this_tunnel_def.id == t["id"] for t in self.tunnel_configs):
            self.tunnel_configs.append(
                this_tunnel_def.model_dump(exclude=self._excluded_fields)
            )

    def stop_tunnels(self):
        """Stops all tunnels."""
        self.hosts_manager.restore_original_hosts_file()
        print("Stopping tunnels...")
        for this_tunnel in reversed(self.tunnels):
            try:
                print(
                    f"\033[92mTunnel ID: {this_tunnel.tunnel_config.nexthop.id} - Closing tunnel {this_tunnel.tunnel.local_bind_hosts[0]}:{this_tunnel.tunnel.local_bind_ports[0]}...\033[0m"
                )
                this_tunnel.destroy_tunnel()
            except Exception as e:
                print(f"\033[91mFailed to stop tunnel ID: {this_tunnel.tunnel_config.nexthop.id}. Error: {e}\033[0m")
