""" Creates an ssh tunnel to remote device exposing ports 22 and 443."""

from typing import Optional
import os
from sshtunnel import SSHTunnelForwarder
import paramiko
from tunnelgraf.remote_tunnel import RemoteTunnel
from tunnelgraf.tunnel_definition import TunnelDefinition
from tunnelgraf.tunnel_interface import TunnelInterface
from tunnelgraf.socket_tunnel import UnixSocketSSHTunnelForwarder


class TunnelBuilder(TunnelInterface):
    """Creates an ssh tunnel proxy through a bastion host to a remote machine's port."""

    def __init__(self, tunnel_def: TunnelDefinition):
        super().__init__(tunnel_def)
        self.tunnel_config: TunnelDefinition = tunnel_def
        if self.tunnel_config.nexthop is None:
            raise ValueError(
                "TunnelDefinition must have a nexthop when creating a tunnel."
            )
        self.tunnel_kwargs: dict = {
            "ssh_username": self.tunnel_config.sshuser,
            "remote_bind_address": (
                self.tunnel_config.nexthop.host if self.tunnel_config.nexthop.is_host_a_socket()
                else (self.tunnel_config.nexthop.host, self.tunnel_config.nexthop.port)
            ),
            "local_bind_address": (
                self.tunnel_config.nexthop.localbindaddress if self.tunnel_config.nexthop.is_localbindaddress_a_socket()
                else (self.tunnel_config.nexthop.localbindaddress, self.tunnel_config.nexthop.localbindport)
            ),
        }
        if self.tunnel_config.proxycommand is not None:
            self.tunnel_kwargs["ssh_proxy"] = paramiko.ProxyCommand(
                self.tunnel_config.proxycommand
            )
        if self.tunnel_config.sshkeyfile is not None:
            print("sshkeyfile present, using it instead of password.")
            self.tunnel_kwargs["ssh_pkey"] = self.tunnel_config.sshkeyfile
        else:
            self.tunnel_kwargs["ssh_password"] = self.tunnel_config.sshpass
        self.tunnel: SSHTunnelForwarder
        self.create_tunnel()
        self.start_tunnel()

    def create_tunnel(self) -> SSHTunnelForwarder:
        """Initializes the tunnel."""
        self._delete_socket_files()
        import ipdb; ipdb.set_trace()
        try:
            # Determine if the host is a socket
            if self.tunnel_config.is_host_a_socket():
                # Use UnixSocketSSHTunnelForwarder for Unix socket connections
                self.tunnel = UnixSocketSSHTunnelForwarder(
                    self.tunnel_config.host,
                    **self.tunnel_kwargs
                )
            else:
                self.tunnel = SSHTunnelForwarder(
                    (self.tunnel_config.host, self.tunnel_config.port or 22),
                    **self.tunnel_kwargs
                )
        except Exception as e:
            print(f"Failed to create tunnel: {e}")
            self._delete_socket_files()
            raise

    def start_tunnel(self):
        """Starts tunnel."""
        print(
            f"Tunnel ID: {self.tunnel_config.nexthop.id} - Tunneling through {self.tunnel_config.host}:{self.tunnel_config.port} to {self.tunnel_config.nexthop.host}:{self.tunnel_config.nexthop.port}..."
        )
        self.tunnel.start()

    def destroy_tunnel(self):
        """Destroys tunnel."""
        self.tunnel.close()
        del self.tunnel
        self._delete_socket_files()

    def _delete_socket_files(self):
        """Deletes socket files if they exist."""
        if self.tunnel_config.is_localbindaddress_a_socket() and os.path.exists(self.tunnel_config.localbindaddress):
            os.remove(self.tunnel_config.localbindaddress)
        if self.tunnel_config.is_host_a_socket() and os.path.exists(self.tunnel_config.host):
            os.remove(self.tunnel_config.host)
