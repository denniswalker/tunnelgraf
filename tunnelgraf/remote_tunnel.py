import time
from tunnelgraf.tunnel_definition import TunnelDefinition
from tunnelgraf.run_remote import RunCommand
from tunnelgraf.tunnel_interface import TunnelInterface

class RemoteTunnel(TunnelInterface):
    """Manages a remote SSH tunnel."""

    def __init__(self, tunnel_def: TunnelDefinition, parent_tunnel: TunnelDefinition):
        print("Initializing RemoteTunnel...")
        self.tunnel_config = tunnel_def
        self.parent_tunnel = parent_tunnel
        self.ssh_command = self.prepare_ssh_command()
        
        # Initialize run_command as an object attribute
        self.run_command = RunCommand(
            host=self.parent_tunnel.host,
            user=self.parent_tunnel.sshuser,
            identityfile=self.parent_tunnel.sshkeyfile,
            password=self.parent_tunnel.sshpass,
            port=self.parent_tunnel.port
        )

        # Check if the local port is free before running the SSH command
        # if self.check_connection_status():
        #     raise RuntimeError("Local bind port is already in use.")
        
        # Run the SSH command to establish the tunnel
        self.start_tunnel()
        
        # Check if the local port is active after running the SSH command
        # if not self.check_connection_status():
        #     raise RuntimeError("Failed to establish the tunnel; connectionis not active.")
        # print("RemoteTunnel initialized successfully.")

    def prepare_ssh_command(self) -> str:
        """Prepares the SSH command to be run on the remote host."""
        print("Preparing SSH command...")
        # Prepare the SSH command
        command = (
            f"/usr/bin/bash -c 'nohup "
            f"ssh -fN -v -o StrictHostKeyChecking=no"
            f" -o ServerAliveInterval=120"
            f" -o ExitOnForwardFailure=yes"
            f" -o UserKnownHostsFile=/dev/null"
            f" -L {self.tunnel_config.localbindaddress}:"
        )

        # Append localbindport only if localbindaddress is not a socket
        if not self.tunnel_config.is_localbindaddress_a_socket():
            command += f"{self.tunnel_config.nexthop.localbindport}:" 
        
        command += f"{self.tunnel_config.nexthop.host}:"

        # Append port only if host is not a socket
        if not self.tunnel_config.nexthop.is_host_a_socket():
            command += f"{self.tunnel_config.nexthop.port} "
        
        # Append the user and host to connect through.
        command += f"{self.tunnel_config.sshuser}@{self.tunnel_config.host}"
        
        # Append the port if the host is not a socket
        if not self.tunnel_config.is_host_a_socket():
            command += f" -p {self.tunnel_config.port}"

        # Append the ssh keyfile if provided.
        if self.tunnel_config.sshkeyfile is not None:
            command += f" -i {self.tunnel_config.sshkeyfile}"

        # Append the proxy command if provided.
        if self.tunnel_config.proxycommand is not None:
            command += f" -o ProxyCommand=\"{self.tunnel_config.proxycommand}\""  

        # Append the nohup and background command.
        command += f" &'"

        # Append the pgrep command to check if the ssh process is running.
        # command += f" && pgrep -u $(whoami) -f \"ssh -fN\"'"

        # Print the command to be run.
        print(f"Running: {command} on host {self.parent_tunnel.host}:{self.parent_tunnel.port}")
        return command.join("")
    
    def check_connection_status(self) -> bool:
        """Checks if the connection to the remote host is active."""
        print("Checking connection status...")
        if self.tunnel_config.is_localbindaddress_a_socket():
            self.check_local_socket_status()
        else:
            self.check_local_port_status()

    def check_local_port_status(self) -> bool:
        """Checks if the local bind port is free and active on the remote host using RunCommand."""
        print("Checking local port status...")
        time.sleep(3)
        try:
            # Combined command to check if the port is in use
            command = (
                f"if command -v netstat > /dev/null; then "
                f"netstat -an | grep {self.tunnel_config.localbindport}; "
                f"else "
                f"ss -an | grep {self.tunnel_config.localbindport}; "
                f"fi"
            )

            output = self.run_command.run(command)

            if output:
                print(f"Port {self.tunnel_config.nexthop.localbindport} is already in use on the remote host.")
                return False
            print(f"Port {self.tunnel_config.nexthop.localbindport} is free.")
            return True
        except ValueError as e:
            print(f"Error checking port status: {e}")
            return False

    def check_local_socket_status(self) -> bool:
        """Checks if the local socket is active on the remote host using RunCommand."""
        print("Checking local socket status on remote host...")
        try:
            # Command to check if the socket is active
            command = (
                f"if [ -S {self.tunnel_config.localbindaddress} ]; then "
                f"echo 'Socket is active'; "
                f"else "
                f"echo 'Socket is not active'; "
                f"fi"
            )

            output = self.run_command.run(command)

            if "Socket is active" in output:
                print(f"Socket {self.tunnel_config.localbindaddress} is active on the remote host.")
                return True
            else:
                print(f"Socket {self.tunnel_config.localbindaddress} is not active on the remote host.")
                return False
        except ValueError as e:
            print(f"Error checking socket status: {e}")
            return False

    def start_tunnel(self):
        """Runs the SSH command to establish the tunnel."""
        print("Running SSH command to establish the tunnel...")
        try:
            output = self.run_command.run(self.ssh_command)
            import ipdb; ipdb.set_trace()
            print(f"stdout: {output}")
            print(f"SSH command executed successfully. Output: {output}")
        except ValueError as e:
            print(f"Error running SSH command: {e}")

    def destroy_tunnel(self):
        """Tears down the remote tunnel using RunCommand."""
        print("Closing the remote tunnel...")
        try:
            # Command to terminate the SSH process
            command = f"pkill -f '{self.ssh_command}'"
            self.run_command.run(command)
            print("Remote tunnel closed successfully.")
        except ValueError as e:
            print(f"Error tearing down tunnel: {e}") 
        if self.check_connection_status():
            raise RuntimeError("Failed to tear down tunnel; local connection is still active.")
        if self.tunnel_config.is_localbindaddress_a_socket():
            try:
                # Command to delete the socket
                command = (
                    f"if [ -S {self.tunnel_config.localbindaddress} ] && "
                    f"[ $(stat -c '%U' {self.tunnel_config.localbindaddress}) = $(whoami) ]; then "
                    f"rm -f {self.tunnel_config.localbindaddress}; "
                    f"fi"
                )
                self.run_command.run(command)
                print("Local socket deleted successfully.")
            except ValueError as e:
                print(f"Error deleting local socket: {e}")
        