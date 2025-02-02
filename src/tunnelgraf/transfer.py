import os
import sys
import stat
import paramiko
from pathlib import Path
from typing import Dict, Any
from tunnelgraf.logger import logger


class Transfer:
    """Handles file transfers between local and remote hosts using SFTP."""

    def __init__(self, source: str, destination: str, tunnel_config: Dict[str, Any]):
        """
        Initialize transfer configuration and validate arguments.

        Args:
            source: Source path (local or remote in format tunnel_id:path)
            destination: Destination path (local or remote in format tunnel_id:path)
            tunnel_config: Dictionary containing SSH connection details
        """
        self.validate_paths(source, destination)
        
        if ':' in source:
            self.tunnel_id, self.remote_path = source.split(':', 1)
            self.local_path = destination
            self.is_upload = False
        else:
            self.tunnel_id, self.remote_path = destination.split(':', 1)
            self.local_path = source
            self.is_upload = True

        self.tunnel_config = tunnel_config
        self.ssh = None
        self.sftp = None

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
        if ':' not in source and ':' not in destination:
            print("Error: Either source or destination must specify a remote location using tunnel_id:path format")
            sys.exit(1)
        if ':' in source and ':' in destination:
            print("Error: Cannot transfer between two remote locations")
            sys.exit(1)

    def connect(self) -> None:
        """Establish SSH and SFTP connections."""
        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        try:
            if self.tunnel_config.get("sshkeyfile"):
                self.ssh.connect(
                    self.tunnel_config["host"],
                    port=self.tunnel_config["port"],
                    username=self.tunnel_config["sshuser"],
                    key_filename=self.tunnel_config["sshkeyfile"]
                )
            else:
                self.ssh.connect(
                    self.tunnel_config["host"],
                    port=self.tunnel_config["port"],
                    username=self.tunnel_config["sshuser"],
                    password=self.tunnel_config.get("sshpass")
                )

            self.sftp = self.ssh.open_sftp()
        except Exception as e:
            print(f"Error connecting: {str(e)}")
            sys.exit(1)

    def transfer_recursive(self, local: str, remote: str, is_upload: bool) -> None:
        """
        Recursively transfer files and directories.
        
        Args:
            local: Local path
            remote: Remote path
            is_upload: True if uploading, False if downloading
        """
        logger.debug(f"Starting recursive transfer: local={local}, remote={remote}, is_upload={is_upload}")
        local_path, remote_path = local, remote
        stat_func, list_func, is_dir_func, join_func = self.get_transfer_functions(is_upload)

        if is_upload:
            self.create_remote_directories(remote_path)
        else:
            self.create_local_directories(local_path)

        try:
            if is_dir_func(remote_path if is_upload else local_path):
                self.transfer_directory(local_path, remote_path, is_upload, list_func, join_func)
            else:
                self.transfer_file(local_path, remote_path, is_upload)
        except Exception as e:
            logger.error(f"Error transferring {local_path}: {str(e)}")

    def get_transfer_functions(self, is_upload: bool):
        """Get appropriate functions for file operations based on transfer direction."""
        logger.debug(f"Getting transfer functions for {'upload' if is_upload else 'download'}")
        if is_upload:
            return os.stat, os.listdir, os.path.isdir, os.path.join
        else:
            return self.sftp.stat, self.sftp.listdir, lambda p: stat.S_ISDIR(self.sftp.stat(p).st_mode), os.path.join

    def create_remote_directories(self, remote_path: str) -> None:
        """Create parent directories for the remote path if they do not exist."""
        logger.debug(f"Creating remote directories for path: {remote_path}")
        remote_parent = os.path.dirname(remote_path.rstrip('/'))
        if remote_parent:
            try:
                self.sftp.stat(remote_parent)
            except FileNotFoundError:
                current_path = ''
                for part in remote_parent.split('/'):
                    if not part:
                        continue
                    current_path = os.path.join(current_path, part)
                    try:
                        self.sftp.stat(current_path)
                    except FileNotFoundError:
                        self.sftp.mkdir(current_path)

    def create_local_directories(self, local_path: str) -> None:
        """Create parent directories for the local path if they do not exist."""
        logger.debug(f"Creating local directories for path: {local_path}")
        local_parent = os.path.dirname(local_path.rstrip('/'))
        if local_parent:
            os.makedirs(local_parent, exist_ok=True)

    def transfer_directory(self, local_path: str, remote_path: str, is_upload: bool, list_func, join_func) -> None:
        """Transfer directory contents recursively."""
        logger.debug(f"Transferring directory: local={local_path}, remote={remote_path}, is_upload={is_upload}")
        if not local_path.endswith('/'):
            remote_path = join_func(remote_path, os.path.basename(local_path))
            local_path = join_func(local_path, os.path.basename(local_path))

        try:
            if is_upload:
                self.sftp.mkdir(remote_path)
            else:
                os.makedirs(local_path, exist_ok=True)
        except OSError:
            pass  # Directory might already exist

        items = list_func(local_path if is_upload else remote_path)
        for item in items:
            local_item = join_func(local_path, item)
            remote_item = join_func(remote_path, item)
            self.transfer_recursive(local_item, remote_item, is_upload)

    def transfer_file(self, local_path: str, remote_path: str, is_upload: bool) -> None:
        """Transfer a single file."""
        logger.debug(f"Transferring file: local={local_path}, remote={remote_path}, is_upload={is_upload}")
        if is_upload:
            self.sftp.put(local_path, remote_path, confirm=True)
            logger.info(f"Uploaded: {local_path} -> {remote_path}")
        else:
            self.sftp.get(remote_path, local_path)
            logger.info(f"Downloaded: {remote_path} -> {local_path}")

    def execute(self) -> None:
        """Execute the transfer operation."""
        try:
            self.connect()
            self.transfer_recursive(self.local_path, self.remote_path, self.is_upload)
        finally:
            if self.sftp:
                self.sftp.close()
            if self.ssh:
                self.ssh.close() 