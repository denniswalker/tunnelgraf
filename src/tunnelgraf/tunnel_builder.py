""" Creates an ssh tunnel to remote device exposing ports 22 and 443."""

from sshtunnel import SSHTunnelForwarder

from tunnelgraf.tunnel_definition import TunnelDefinition
import paramiko
from tunnelgraf.run_remote import RunCommand
from tunnelgraf.nslookup import NSLookup
from tunnelgraf.hosts_manager import HostsManager
import time

class TunnelBuilder:
    """Creates an ssh tunnel proxy through a bastion host to a remote machine's port."""

    def __init__(self, tunnel_def: TunnelDefinition):
        self.tunnel_config: TunnelDefinition = tunnel_def
        self.hosts_manager = HostsManager()
        if self.tunnel_config.nexthop is None:
            raise ValueError(
                "TunnelDefinition must have a nexthop when creating a tunnel."
            )
        if self.tunnel_config.proxycommand is not None:
            self.tunnel_kwargs["ssh_proxy"] = paramiko.ProxyCommand(
                self.tunnel_config.proxycommand
            )
        if self.tunnel_config.nexthop.hostlookup:
            self.tunnel_config.nexthop.host = self._lookup_host(self.tunnel_config)
        self.tunnel_kwargs: dict = {
            #"mute_exceptions": True,
            "compression": True,
            "ssh_username": self.tunnel_config.sshuser,
            "remote_bind_address": (
                self.tunnel_config.nexthop.host,
                self.tunnel_config.nexthop.port,
            ),
            "local_bind_address": (
                self.tunnel_config.nexthop.localbindaddress,
                self.tunnel_config.nexthop.localbindport,
            ),
        }
        if self.tunnel_config.sshkeyfile is not None:
            print("sshkeyfile present, using it instead of password.")
            self.tunnel_kwargs["ssh_pkey"] = self.tunnel_config.sshkeyfile
        else:
            self.tunnel_kwargs["ssh_password"] = self.tunnel_config.sshpass
        self.tunnel: SSHTunnelForwarder | None = None
        self.create_tunnel()
        self.hosts_manager.add_to_hosts(
            self.tunnel_config.nexthop.id,
            self.tunnel_config.nexthop.hosts_file_entries,
            self.tunnel_config.nexthop.hosts_file_entry,
            self.tunnel_config.nexthop.hostlookup,
        )

    # Public instance methods
    def create_tunnel(self) -> SSHTunnelForwarder:
        """Initializes the tunnel."""
        self.tunnel = SSHTunnelForwarder(
            (self.tunnel_config.host, self.tunnel_config.port), **self.tunnel_kwargs
        )
        self.start_tunnel()

    def start_tunnel(self):
        """Starts tunnel. Uses a non-blocking thread if there are no more nexthops."""
        # print(f"Tunnel ID: {self.tunnel_config.nexthop.id} - Tunneling through {self.tunnel_config.host}:{self.tunnel_config.port} to {self.tunnel_config.nexthop.host}:{self.tunnel_config.nexthop.port}...")
        retry_attempts = 3
        for attempt in range(retry_attempts):
            try:
                self.tunnel.start()
                print(
                    f"\033[92mTunnel ID: {self.tunnel_config.nexthop.id} - Created {self.tunnel.local_bind_host}:{self.tunnel.local_bind_port} to {self.tunnel._remote_binds[0][0]}:{self.tunnel._remote_binds[0][1]}\033[0m"
                )
                break
            except Exception as e:
                # Suppress the stack trace and handle the exception
                print(f"\033[91mTunnel ID: {self.tunnel_config.nexthop.id}. Failed to start tunnel. Attempt {attempt + 1} of {retry_attempts}. Error: {e}\033[0m")
                if attempt < retry_attempts - 1:
                    time.sleep(1)

    def destroy_tunnel(self):
        """Destroys tunnel."""
        self.tunnel.close()
        del self.tunnel
    
    # Private instance methods
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
