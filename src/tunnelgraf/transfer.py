"""
Handles file transfers between local and remote hosts using SFTP.
"""

import sys
import subprocess
from tunnelgraf.logger import logger
from tunnelgraf.tunnel_definition import TunnelDefinition


class Transfer:
    """Handles file transfers between local and remote hosts using SFTP."""

    def __init__(self, source: str, destination: str, tunnel_config: TunnelDefinition):
        """
        Initialize transfer configuration and validate arguments.

        Args:
            source: Source path (local or remote in format tunnel_id:path)
            destination: Destination path (local or remote in format tunnel_id:path)
            tunnel_config: Dictionary containing SSH connection details
        """
        self.validate_paths(source, destination)
        self.scp_path = self._get_scp_path()
        self.sshpass_path = self._get_sshpass_path()

        if ":" in source:
            self.tunnel_id, self.remote_path = source.split(":", 1)
            self.local_path = destination
            self.is_upload = False
        else:
            self.tunnel_id, self.remote_path = destination.split(":", 1)
            self.local_path = source
            self.is_upload = True

        self.tunnel_config = tunnel_config
        self.scp_options = '-r'

    def _get_scp_path(self):
        result = subprocess.run('which scp', shell=True, capture_output=True)
        stdout = result.stdout.decode("utf-8").strip()
        stderr = result.stderr.decode("utf-8").strip()
        logger.debug(f"scp path: {stdout}")
        if result.returncode != 0:
            raise Exception(
                f"Could not find scp. {stdout} - {stderr}"
            )
        return stdout

    def _get_sshpass_path(self):
        result = subprocess.run('which sshpass', shell=True, capture_output=True)
        stdout = result.stdout.decode("utf-8").strip()
        stderr = result.stderr.decode("utf-8").strip()
        logger.debug(f"sshpass path: {stdout}")
        if result.returncode != 0:
            raise Exception(
                f"Could not find sshpass. {stdout} - {stderr}"
            )
        return stdout

    @staticmethod
    def validate_paths(source: str, destination: str) -> None:
        """
        Validate source and destination paths.

        Args:
            source: Source path
            destination: Destination path

        Raises:
            SystemExit: If validation fails
        """
        if ":" not in source and ":" not in destination:
            print(
                "Error: Either source or destination must specify a remote location using tunnel_id:path format"
            )
            sys.exit(1)
        if ":" in source and ":" in destination:
            print("Error: Cannot transfer between two remote locations")
            sys.exit(1)

    def _get_ssh_options(self, port: int | None) -> str: # type: ignore
        return f"-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -P {port}"

    def upload(self) -> str:
        """Upload files and directories to the remote location using sftpretty."""
        ssh_options = self._get_ssh_options(self.tunnel_config['port'])
        cmd = f"{self.scp_path} {self.scp_options} {ssh_options} {self.local_path}"
        cmd = f"{cmd} {self.tunnel_config['sshuser']}@{self.tunnel_config['host']}:{self.remote_path}"
        if self.tunnel_config['sshpass']:
            cmd = f"{self.sshpass_path} -p {self.tunnel_config['sshpass']} {cmd}"
        return cmd

    def download(self) -> str:
        """Download files and directories from the remote location using sftpretty."""
        ssh_options = self._get_ssh_options(self.tunnel_config['port'])
        cmd = f"{self.scp_path} {self.scp_options} {ssh_options}" 
        cmd = f"{cmd} {self.tunnel_config['sshuser']}@{self.tunnel_config['host']}:{self.remote_path}"
        cmd = f"{cmd} {self.local_path}"
        if self.tunnel_config['sshpass']:
            cmd = f"{self.sshpass_path} -p {self.tunnel_config['sshpass']} {cmd}"
        return cmd

    def execute(self) -> None:
        """Execute the transfer operation."""
        if self.is_upload:
            cmd = self.upload()
        else:
            cmd = self.download()
        logger.debug(f"{cmd}")

        # Split the command string into a list of arguments
        cmd_list = cmd.split()
        result = subprocess.Popen(cmd_list, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

        # Print stdout line by line as the command executes
        for line in iter(result.stdout.readline, ''):
            print(line, end='')

        result.stdout.close()
        result.wait()  # Wait for the process to complete

        if result.returncode != 0:
            raise Exception(
                f"Error running scp {self.local_path} -> {self.remote_path}; {cmd}"
            )
        if self.is_upload:
            logger.info(f"Uploaded file(s): {self.local_path} -> {self.tunnel_id}:{self.remote_path}")
        else:
            logger.info(f"Downloaded file(s): {self.tunnel_id}:{self.remote_path} -> {self.local_path}")
