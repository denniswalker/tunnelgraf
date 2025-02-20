"""
Handles file transfers between local and remote hosts using SFTP.
"""
import sys
import os
from typing import Dict, Any
from sftpretty import Connection, CnOpts
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
        self.connection: Connection | None

        # Transfer configuration
        self.preserve_mtime = True
        self.prefetch = True
        self.max_concurrent_prefetch_requests = 64
        self.tries = 3
        self.resume = True
        self.callback = None

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

    @staticmethod
    def log_progress(filename, bytes_so_far, bytes_total, logger=logger):
        """Log progress of file transfer."""
        mb_so_far = round(bytes_so_far / 1024 / 1024, 2)
        mb_total = round(bytes_total / 1024 / 1024, 2)
        message = (f'Transfer of File: [{filename}] @ '
                f'{100.0 * mb_so_far / mb_total:.1f}% '
                f'{mb_so_far:d}:{mb_total:d} MB ')
        if logger:
            logger.info(message)
        else:
            print(message)

    def connect(self) -> None:
        """Establish SFTP connection with retry capabilities."""
        try:
            # Configure connection options
            cnopts = CnOpts()
            cnopts.hostkeys = None
            cnopts.timeout = 20
            cnopts.allow_agent = False
            cnopts.user_known_hosts_file = None
            cnopts.compress = True
            cnopts.knownhosts = None

            # Set up connection parameters
            conn_params = {
                'host': self.tunnel_config['host'],
                'port': self.tunnel_config['port'],
                'username': self.tunnel_config['sshuser'],
                'cnopts': cnopts,
            }

            # Add authentication method
            if self.tunnel_config.get('sshkeyfile'):
                conn_params['private_key'] = self.tunnel_config['sshkeyfile']
            else:
                conn_params['password'] = self.tunnel_config.get('sshpass')
            self.connection = Connection(**conn_params)
        except Exception as e:
            logger.error(f"Error connecting: {str(e)}")
            sys.exit(1)

    def transfer_recursive(self, local: str, remote: str, is_upload: bool) -> None:
        """
        Recursively transfer files and directories with retry capability.
        
        Args:
            local: Local path
            remote: Remote path
            is_upload: True if uploading, False if downloading
        """
        logger.debug(f"Starting recursive transfer: local={local}, remote={remote}, is_upload={is_upload}")

        try:
            if is_upload:
                self.upload(local, remote)
            else:
                self.download(local, remote)
        except Exception as e:
            logger.error(f"Error transferring {local if is_upload else remote}: {str(e)}")
            raise

    def upload(self, local: str, remote: str) -> None:
        """Upload files and directories to the remote location using sftpretty."""
        try:
            if os.path.isdir(local):
                self.connection.put_r(
                    local, remote,
                    preserve_mtime=self.preserve_mtime,
                    tries=self.tries,
                    resume=self.resume,
                    logger=logger,
                    callback=self.callback
                )
                logger.info(f"Uploaded directory: {local} -> {remote}")
            else:
                self.connection.put(
                    local, remote,
                    preserve_mtime=self.preserve_mtime,
                    tries=self.tries,
                    resume=self.resume,
                    logger=logger,
                    callback=self.callback
                )
                logger.info(f"Uploaded file: {local} -> {remote}")
        except Exception as e:
            logger.error(f"Failed to upload {local}: {str(e)}")

    def download(self, local: str, remote: str) -> None:
        """Download files and directories from the remote location using sftpretty."""
        try:
            if self.connection.isdir(remote):
                self.connection.get_r(
                    remote, local,
                    preserve_mtime=self.preserve_mtime,
                    prefetch=self.prefetch,
                    max_concurrent_prefetch_requests=self.max_concurrent_prefetch_requests,
                    tries=self.tries,
                    resume=self.resume,
                    logger=logger,
                    callback=self.callback
                )
                logger.info(f"Downloaded directory: {remote} -> {local}")
            else:
                self.connection.get(
                    remote, local,
                    preserve_mtime=self.preserve_mtime,
                    prefetch=self.prefetch,
                    max_concurrent_prefetch_requests=self.max_concurrent_prefetch_requests,
                    tries=self.tries,
                    resume=self.resume,
                    logger=logger,
                    callback=self.callback
                )
                logger.info(f"Downloaded file: {remote} -> {local}")
        except Exception as e:
            logger.error(f"Failed to download {remote}: {str(e)}")

    def execute(self) -> None:
        """Execute the transfer operation."""
        try:
            self.connect()
            with self.connection:  # Use context manager for automatic cleanup
                self.transfer_recursive(self.local_path, self.remote_path, self.is_upload)
        except Exception as e:
            logger.error(f"Transfer failed: {str(e)}")
            sys.exit(1)