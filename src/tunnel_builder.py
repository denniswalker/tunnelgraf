""" Creates an ssh tunnel to remote device exposing ports 22 and 443."""
from sshtunnel import SSHTunnelForwarder
from .tunnel_config import TunnelConfig


class TunnelBuilder:
    """Creates an ssh tunnel proxy through a bastion host to a remote machine's port."""

    def __init__(self, tunnel_config: TunnelConfig):
        self.tunnel_config: TunnelConfig = tunnel_config
        self.tunnel: SSHTunnelForwarder = self.create_tunnel()
        self.start_tunnel()

    # Public instance methods
    def create_tunnel(self) -> SSHTunnelForwarder:
        """Initializes the tunnel."""
        return SSHTunnelForwarder(
            (self.tunnel_config.bastion_endpoint, self.tunnel_config.bastion_port),
            ssh_username=self.tunnel_config.bastion_user,
            ssh_password=self.tunnel_config.bastion_pass,
            remote_bind_addresses=[
                (self.tunnel_config.remote_endpoint, self.tunnel_config.remote_port)
            ],
            local_bind_addresses=[
                (self.tunnel_config.local_ip, self.tunnel_config.local_port)
            ],
        )

    def start_tunnel(self):
        """Starts tunnel."""
        print(
            f"Tunneling through {self.tunnel_config.bastion_endpoint}:{self.tunnel_config.bastion_port} to {self.tunnel_config.remote_endpoint}:{self.tunnel_config.remote_port}..."
        )
        self.tunnel.start()

    def destroy_tunnel(self):
        """Destroys tunnel."""
        self.tunnel.close()
        del self.tunnel
