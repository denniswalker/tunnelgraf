""" Creates an ssh tunnel to remote device exposing ports 22 and 443."""

from sshtunnel import SSHTunnelForwarder

from tunnelgraf.tunnel_definition import TunnelDefinition


class TunnelBuilder:
    """Creates an ssh tunnel proxy through a bastion host to a remote machine's port."""

    def __init__(self, tunnel_def: TunnelDefinition):
        self.tunnel_config: TunnelDefinition = tunnel_def
        self.tunnel: SSHTunnelForwarder = self.create_tunnel()
        self.start_tunnel()

    # Public instance methods
    def create_tunnel(self) -> SSHTunnelForwarder:
        """Initializes the tunnel."""
        return SSHTunnelForwarder(
            (self.tunnel_config.host, self.tunnel_config.port),
            ssh_username=self.tunnel_config.sshuser,
            ssh_password=self.tunnel_config.sshpass,
            remote_bind_addresses=[
                (self.tunnel_config.nexthop.host, self.tunnel_config.nexthop.port)
            ],
            local_bind_addresses=[
                (
                    self.tunnel_config.nexthop.localbindaddress,
                    self.tunnel_config.nexthop.localbindport,
                )
            ],
        )

    def start_tunnel(self):
        """Starts tunnel."""
        print(
            f"Tunneling through {self.tunnel_config.host}:{self.tunnel_config.port} to {self.tunnel_config.nexthop.host}:{self.tunnel_config.nexthop.port}..."
        )
        self.tunnel.start()

    def destroy_tunnel(self):
        """Destroys tunnel."""
        self.tunnel.close()
        del self.tunnel
