import yaml
import os
from .tunnel_builder import TunnelBuilder
from .tunnel_config import TunnelConfig
from time import sleep


class Tunnels:
    """
    Creates an ssh tunnel, connecting a remote endpoint through a bastion
    and binding it to a local port, as specified in the provided config file.
    """

    def __init__(self, config_file: str):
        self._config_file: str = config_file
        self.config: dict | list = self._get_config()
        self.tunnels: list[TunnelBuilder] = []
        self.make_tunnels()
        try:
            print("Tunnels started. Press Ctrl-C to stop.")
            # On a mac, this can be verified by checking open ports with 'netstat -anvp tcp | awk 'NR<3 || /LISTEN/'
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
        self, nexthop_config: dict, this_parent_tunnel: TunnelBuilder
    ):
        """Updates the bastion address and port to reference the one just created."""
        nhcfg = nexthop_config
        nhcfg["host"] = this_parent_tunnel.tunnel.local_bind_address[0]
        nhcfg["port"] = this_parent_tunnel.tunnel.local_bind_address[1]
        return nhcfg

    def make_tunnels(self):
        """Creates tunnels from the config file."""
        if isinstance(self.config, list):
            for tunnel in self.config:
                self.make_tunnel(tunnel)
        if isinstance(self.config, dict):
            self.make_tunnel(self.config)

    def make_tunnel(self, this_config: dict):
        """Creates a tunnel from the provided config."""
        if "nexthop" in this_config.keys() and isinstance(this_config["nexthop"], dict):
            tc = TunnelConfig(this_config)
            self.tunnels.append(TunnelBuilder(tc))
            print(
                f"Created tunnel {tc.local_ip}:{tc.local_port} to {tc.remote_endpoint}:{tc.remote_port}"
            )
            nexthop_config = self._update_bastion_address(
                this_config["nexthop"], self.tunnels[-1]
            )
            self.make_tunnel(nexthop_config)

        if "nexthop" in this_config.keys() and isinstance(this_config["nexthop"], list):
            this_parent_tunnel = self.tunnels[-1]
            for tunnel in this_config["nexthop"]:
                nexthop_config = this_config
                nexthop_config["nexthop"] = tunnel
                nexthop_config = self._update_bastion_address(
                    nexthop_config, this_parent_tunnel
                )
                self.make_tunnel(nexthop_config)

    def stop_tunnels(self):
        """Stops all tunnels."""
        print("Stopping tunnels...")
        for this_tunnel in list(reversed(self.tunnels)):
            print(
                f"Closing tunnel {this_tunnel.tunnel_config.id} at {this_tunnel.tunnel_config.local_port}..."
            )
            this_tunnel.destroy_tunnel()
