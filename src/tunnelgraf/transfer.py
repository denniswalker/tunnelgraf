"""
Handles file transfers between local and remote hosts using SCP.
"""

import sys
import subprocess
import os
from tunnelgraf.logger import logger
from tunnelgraf.tunnel_definition import TunnelDefinition


class Transfer:
    """Handles file transfers between local and remote hosts using SCP."""

    def __init__(self, source: str, destination: str,
                 tunnel_config: TunnelDefinition, 
                 explicit_tunnel_id: str | None = None):
        """
        Initialize transfer configuration and validate arguments.

        Args:
            source: Source path (local or remote in format tunnel_id:path)
            destination: Destination path (local or remote in format
                        tunnel_id:path)
            tunnel_config: TunnelDefinition object containing SSH connection 
                         details
            explicit_tunnel_id: Tunnel ID explicitly specified via --tunnel-id
        """
        self.validate_paths(source, destination, explicit_tunnel_id)
        self.scp_path = self._get_scp_path()
        self.sshpass_path = self._get_sshpass_path()

        # Determine transfer direction and paths
        if ":" in source:
            # Download: remote -> local
            if explicit_tunnel_id:
                self.tunnel_id = explicit_tunnel_id
                self.remote_path = (source.split(":", 1)[1] 
                                  if ":" in source else source)
            else:
                self.tunnel_id, self.remote_path = source.split(":", 1)
            self.local_path = destination
            self.is_upload = False
        elif ":" in destination:
            # Upload: local -> remote
            if explicit_tunnel_id:
                self.tunnel_id = explicit_tunnel_id
                self.remote_path = (destination.split(":", 1)[1] 
                                  if ":" in destination else destination)
            else:
                self.tunnel_id, self.remote_path = destination.split(":", 1)
            self.local_path = source
            self.is_upload = True
        else:
            # Both are local paths, use explicit tunnel_id
            if not explicit_tunnel_id:
                raise ValueError("Either specify --tunnel-id or use "
                               "tunnel_id:path format")
            self.tunnel_id = explicit_tunnel_id
            # Assume upload (local -> remote) when tunnel_id is explicit
            self.local_path = source
            self.remote_path = destination
            self.is_upload = True

        self.tunnel_config = tunnel_config
        self.scp_options = self._build_scp_options()

    def _build_scp_options(self) -> str:
        """Build SCP options based on transfer type and file attributes."""
        options = ['-r']  # Always recursive for directories
        
        # Add verbose output for better progress reporting
        options.append('-v')
        
        # Add compression for better performance over slow connections
        options.append('-C')
        
        # Add preserve timestamps and permissions
        options.append('-p')
        
        return ' '.join(options)

    def _get_scp_path(self):
        result = subprocess.run('which scp', shell=True, 
                              capture_output=True)
        stdout = result.stdout.decode("utf-8").strip()
        stderr = result.stderr.decode("utf-8").strip()
        logger.debug(f"scp path: {stdout}")
        if result.returncode != 0:
            raise Exception(
                "SCP is not installed or not found in PATH. "
                "Please install OpenSSH client which includes scp. "
                f"Error: {stdout} - {stderr}"
            )
        return stdout

    def _get_sshpass_path(self):
        result = subprocess.run('which sshpass', shell=True, 
                              capture_output=True)
        stdout = result.stdout.decode("utf-8").strip()
        stderr = result.stderr.decode("utf-8").strip()
        logger.debug(f"sshpass path: {stdout}")
        if result.returncode != 0:
            raise Exception(
                "sshpass is not installed or not found in PATH. "
                "Please install sshpass for password authentication. "
                f"Error: {stdout} - {stderr}"
            )
        return stdout

    @staticmethod
    def validate_paths(source: str, destination: str,
                      explicit_tunnel_id: str | None = None) -> None:
        """
        Validate source and destination paths.

        Args:
            source: Source path
            destination: Destination path
            explicit_tunnel_id: Tunnel ID explicitly specified via --tunnel-id

        Raises:
            SystemExit: If validation fails
        """
        # If explicit_tunnel_id is provided, we can have both local paths
        if explicit_tunnel_id:
            if ":" in source and ":" in destination:
                print("Error: Cannot transfer between two remote locations")
                sys.exit(1)
            return

        # Without explicit tunnel_id, at least one path must be remote
        if ":" not in source and ":" not in destination:
            print(
                "Error: Either source or destination must specify a remote "
                "location using tunnel_id:path format, or use --tunnel-id"
            )
            sys.exit(1)
        if ":" in source and ":" in destination:
            print("Error: Cannot transfer between two remote locations")
            sys.exit(1)

    def _get_ssh_options(self, port: int | None) -> str:  # type: ignore
        """Build SSH options for SCP command."""
        options = [
            "-o StrictHostKeyChecking=no",
            "-o UserKnownHostsFile=/dev/null",
            f"-P {port}"
        ]
        return " ".join(options)

    def _validate_local_path(self, path: str) -> None:
        """Validate that local path exists for uploads."""
        if self.is_upload and not os.path.exists(path):
            raise FileNotFoundError(f"Local path does not exist: {path}")

    def upload(self) -> str:
        """Upload files and directories to the remote location using SCP."""
        self._validate_local_path(self.local_path)
        ssh_options = self._get_ssh_options(self.tunnel_config.port)
        cmd = (f"{self.scp_path} {self.scp_options} {ssh_options} "
               f"{self.local_path}")
        cmd = (f"{cmd} {self.tunnel_config.sshuser}@"
               f"{self.tunnel_config.host}:{self.remote_path}")
        if self.tunnel_config.sshpass:
            cmd = f"{self.sshpass_path} -p {self.tunnel_config.sshpass} {cmd}"
        return cmd

    def download(self) -> str:
        """Download files and directories from the remote location using SCP."""
        ssh_options = self._get_ssh_options(self.tunnel_config.port)
        cmd = f"{self.scp_path} {self.scp_options} {ssh_options}"
        cmd = (f"{cmd} {self.tunnel_config.sshuser}@"
               f"{self.tunnel_config.host}:{self.remote_path}")
        cmd = f"{cmd} {self.local_path}"
        if self.tunnel_config.sshpass:
            cmd = f"{self.sshpass_path} -p {self.tunnel_config.sshpass} {cmd}"
        return cmd

    def execute(self) -> None:
        """Execute the transfer operation with enhanced progress reporting."""
        if self.is_upload:
            cmd = self.upload()
            operation = "upload"
            source = self.local_path
            dest = f"{self.tunnel_id}:{self.remote_path}"
        else:
            cmd = self.download()
            operation = "download"
            source = f"{self.tunnel_id}:{self.remote_path}"
            dest = self.local_path

        logger.debug(f"Executing SCP command: {cmd}")
        print(f"Starting {operation}: {source} -> {dest}")

        # Split the command string into a list of arguments
        cmd_list = cmd.split()
        result = subprocess.Popen(
            cmd_list, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT, 
            text=True
        )

        # Print stdout line by line as the command executes
        if result.stdout:
            for line in iter(result.stdout.readline, ''):
                print(line, end='')
            result.stdout.close()
        result.wait()  # Wait for the process to complete

        if result.returncode != 0:
            error_msg = (f"SCP {operation} failed: {source} -> {dest}. "
                        f"Command: {cmd}")
            logger.error(error_msg)
            raise Exception(error_msg)

        success_msg = f"Successfully {operation}ed: {source} -> {dest}"
        logger.info(success_msg)
        print(f"✓ {success_msg}")
