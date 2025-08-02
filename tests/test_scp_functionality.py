"""
Tests for SCP functionality in tunnelgraf.
"""

import pytest
from unittest.mock import patch, MagicMock
from tunnelgraf.transfer import Transfer
import subprocess
import os


class TestTransfer:
    """Test the Transfer class for SCP functionality."""

    def test_transfer_initialization_upload(self):
        """Test transfer initialization for upload."""
        mock_config = MagicMock()
        mock_config.port = 22
        mock_config.sshuser = "testuser"
        mock_config.host = "testhost"
        mock_config.sshpass = "testpass"
        
        transfer = Transfer("local/path", "tunnel:/remote/path", mock_config)
        
        assert transfer.is_upload is True
        assert transfer.local_path == "local/path"
        assert transfer.tunnel_id == "tunnel"
        assert transfer.remote_path == "/remote/path"

    def test_transfer_initialization_download(self):
        """Test transfer initialization for download."""
        mock_config = MagicMock()
        mock_config.port = 22
        mock_config.sshuser = "testuser"
        mock_config.host = "testhost"
        mock_config.sshpass = "testpass"
        
        transfer = Transfer("tunnel:/remote/path", "local/path", mock_config)
        
        assert transfer.is_upload is False
        assert transfer.local_path == "local/path"
        assert transfer.tunnel_id == "tunnel"
        assert transfer.remote_path == "/remote/path"

    def test_validate_paths_both_local(self):
        """Test validation fails when both paths are local."""
        with pytest.raises(SystemExit):
            Transfer.validate_paths("local/path", "another/local/path")

    def test_validate_paths_both_remote(self):
        """Test validation fails when both paths are remote."""
        with pytest.raises(SystemExit):
            Transfer.validate_paths("tunnel1:/path", "tunnel2:/path")

    def test_validate_paths_valid(self):
        """Test validation passes for valid path combinations."""
        # Should not raise any exception
        Transfer.validate_paths("local/path", "tunnel:/remote/path")
        Transfer.validate_paths("tunnel:/remote/path", "local/path")

    @patch('subprocess.run')
    def test_get_scp_path_success(self, mock_run):
        """Test successful scp path detection."""
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = b"/usr/bin/scp\n"
        mock_run.return_value.stderr = b""
        
        mock_config = MagicMock()
        transfer = Transfer("local/path", "tunnel:/remote/path", mock_config)
        
        assert transfer.scp_path == "/usr/bin/scp"

    @patch('subprocess.run')
    def test_get_scp_path_failure(self, mock_run):
        """Test scp path detection failure."""
        mock_run.return_value.returncode = 1
        mock_run.return_value.stdout = b""
        mock_run.return_value.stderr = b"command not found\n"
        
        mock_config = MagicMock()
        with pytest.raises(Exception, match="SCP is not installed"):
            Transfer("local/path", "tunnel:/remote/path", mock_config)

    @patch('subprocess.run')
    def test_get_sshpass_path_success(self, mock_run):
        """Test successful sshpass path detection."""
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = b"/usr/bin/sshpass\n"
        mock_run.return_value.stderr = b""
        
        mock_config = MagicMock()
        transfer = Transfer("local/path", "tunnel:/remote/path", mock_config)
        
        assert transfer.sshpass_path == "/usr/bin/sshpass"

    def test_build_scp_options(self):
        """Test SCP options building."""
        mock_config = MagicMock()
        transfer = Transfer("local/path", "tunnel:/remote/path", mock_config)
        
        options = transfer._build_scp_options()
        assert "-r" in options  # recursive
        assert "-v" in options  # verbose
        assert "-C" in options  # compression
        assert "-p" in options  # preserve

    def test_get_ssh_options(self):
        """Test SSH options building."""
        mock_config = MagicMock()
        transfer = Transfer("local/path", "tunnel:/remote/path", mock_config)
        
        options = transfer._get_ssh_options(2222)
        assert "StrictHostKeyChecking=no" in options
        assert "UserKnownHostsFile=/dev/null" in options
        assert "-P 2222" in options

    @patch('os.path.exists')
    def test_validate_local_path_upload_exists(self, mock_exists):
        """Test local path validation for upload when path exists."""
        mock_exists.return_value = True
        mock_config = MagicMock()
        transfer = Transfer("local/path", "tunnel:/remote/path", mock_config)
        
        # Should not raise any exception
        transfer._validate_local_path("local/path")

    @patch('os.path.exists')
    def test_validate_local_path_upload_not_exists(self, mock_exists):
        """Test local path validation for upload when path doesn't exist."""
        mock_exists.return_value = False
        mock_config = MagicMock()
        transfer = Transfer("local/path", "tunnel:/remote/path", mock_config)
        
        with pytest.raises(FileNotFoundError):
            transfer._validate_local_path("local/path")

    @patch('subprocess.run')
    @patch('os.path.exists')
    def test_upload_command_generation(self, mock_exists, mock_run):
        """Test upload command generation."""
        # Mock both scp and sshpass path detection
        def mock_run_side_effect(*args, **kwargs):
            mock_result = MagicMock()
            if 'scp' in args[0]:
                mock_result.returncode = 0
                mock_result.stdout = b"/usr/bin/scp\n"
                mock_result.stderr = b""
            elif 'sshpass' in args[0]:
                mock_result.returncode = 0
                mock_result.stdout = b"/usr/bin/sshpass\n"
                mock_result.stderr = b""
            return mock_result
        
        mock_run.side_effect = mock_run_side_effect
        
        # Mock file existence check
        mock_exists.return_value = True
        
        mock_config = MagicMock()
        mock_config.port = 2222
        mock_config.sshuser = "testuser"
        mock_config.host = "testhost"
        mock_config.sshpass = "testpass"
        
        transfer = Transfer("local/path", "tunnel:/remote/path", mock_config)
        
        cmd = transfer.upload()
        
        assert "/usr/bin/scp" in cmd
        assert "-r" in cmd
        assert "-v" in cmd
        assert "-C" in cmd
        assert "-p" in cmd
        assert "StrictHostKeyChecking=no" in cmd
        assert "UserKnownHostsFile=/dev/null" in cmd
        assert "-P 2222" in cmd
        assert "testuser@testhost:/remote/path" in cmd
        assert "/usr/bin/sshpass -p testpass" in cmd

    def test_download_command_generation(self):
        """Test download command generation."""
        mock_config = MagicMock()
        mock_config.port = 2222
        mock_config.sshuser = "testuser"
        mock_config.host = "testhost"
        mock_config.sshpass = "testpass"
        
        transfer = Transfer("tunnel:/remote/path", "local/path", mock_config)
        transfer.scp_path = "/usr/bin/scp"
        transfer.sshpass_path = "/usr/bin/sshpass"
        
        cmd = transfer.download()
        
        assert "/usr/bin/scp" in cmd
        assert "-r" in cmd
        assert "-v" in cmd
        assert "-C" in cmd
        assert "-p" in cmd
        assert "StrictHostKeyChecking=no" in cmd
        assert "UserKnownHostsFile=/dev/null" in cmd
        assert "-P 2222" in cmd
        assert "testuser@testhost:/remote/path" in cmd
        assert "local/path" in cmd
        assert "/usr/bin/sshpass -p testpass" in cmd

    @patch('subprocess.run')
    @patch('os.path.exists')
    def test_upload_command_no_password(self, mock_exists, mock_run):
        """Test upload command generation without password."""
        # Mock both scp and sshpass path detection
        def mock_run_side_effect(*args, **kwargs):
            mock_result = MagicMock()
            if 'scp' in args[0]:
                mock_result.returncode = 0
                mock_result.stdout = b"/usr/bin/scp\n"
                mock_result.stderr = b""
            elif 'sshpass' in args[0]:
                mock_result.returncode = 0
                mock_result.stdout = b"/usr/bin/sshpass\n"
                mock_result.stderr = b""
            return mock_result
        
        mock_run.side_effect = mock_run_side_effect
        
        # Mock file existence check
        mock_exists.return_value = True
        
        mock_config = MagicMock()
        mock_config.port = 2222
        mock_config.sshuser = "testuser"
        mock_config.host = "testhost"
        mock_config.sshpass = None
        
        transfer = Transfer("local/path", "tunnel:/remote/path", mock_config)
        
        cmd = transfer.upload()
        
        assert "/usr/bin/scp" in cmd
        assert "testuser@testhost:/remote/path" in cmd
        assert "/usr/bin/sshpass" not in cmd  # No sshpass when no password

    @patch('subprocess.Popen')
    @patch('subprocess.run')
    @patch('os.path.exists')
    def test_execute_upload_success(self, mock_exists, mock_run, mock_popen):
        """Test successful upload execution."""
        mock_exists.return_value = True
        
        # Mock subprocess.run for scp and sshpass path detection
        def mock_run_side_effect(*args, **kwargs):
            mock_result = MagicMock()
            if 'scp' in args[0]:
                mock_result.returncode = 0
                mock_result.stdout = b"/usr/bin/scp\n"
                mock_result.stderr = b""
            elif 'sshpass' in args[0]:
                mock_result.returncode = 0
                mock_result.stdout = b"/usr/bin/sshpass\n"
                mock_result.stderr = b""
            return mock_result
        
        mock_run.side_effect = mock_run_side_effect
        
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.stdout = MagicMock()
        mock_process.stdout.readline = MagicMock(side_effect=["Transferring file...\n", "Transfer complete\n", ""])
        mock_popen.return_value = mock_process
        
        mock_config = MagicMock()
        mock_config.port = 2222
        mock_config.sshuser = "testuser"
        mock_config.host = "testhost"
        mock_config.sshpass = "testpass"
        
        transfer = Transfer("local/path", "tunnel:/remote/path", mock_config)
        
        # Should not raise any exception
        transfer.execute()

    @patch('subprocess.Popen')
    @patch('subprocess.run')
    @patch('os.path.exists')
    def test_execute_upload_failure(self, mock_exists, mock_run, mock_popen):
        """Test upload execution failure."""
        mock_exists.return_value = True
        
        # Mock subprocess.run for scp and sshpass path detection
        def mock_run_side_effect(*args, **kwargs):
            mock_result = MagicMock()
            if 'scp' in args[0]:
                mock_result.returncode = 0
                mock_result.stdout = b"/usr/bin/scp\n"
                mock_result.stderr = b""
            elif 'sshpass' in args[0]:
                mock_result.returncode = 0
                mock_result.stdout = b"/usr/bin/sshpass\n"
                mock_result.stderr = b""
            return mock_result
        
        mock_run.side_effect = mock_run_side_effect
        
        mock_process = MagicMock()
        mock_process.returncode = 1
        mock_process.stdout = MagicMock()
        mock_process.stdout.readline = MagicMock(side_effect=["Error: Permission denied\n", ""])
        mock_popen.return_value = mock_process
        
        mock_config = MagicMock()
        mock_config.port = 2222
        mock_config.sshuser = "testuser"
        mock_config.host = "testhost"
        mock_config.sshpass = "testpass"
        
        transfer = Transfer("local/path", "tunnel:/remote/path", mock_config)
        
        with pytest.raises(Exception, match="SCP upload failed"):
            transfer.execute()


class TestSCPCommandExecution:
    """Test actual SCP command execution with real file operations."""
    
    def test_scp_command_help(self):
        """Test that the SCP command is available and shows help."""
        result = subprocess.run(
            ["hatch", "run", "test:python", "src/", "--help"], 
            capture_output=True, text=True
        )
        
        # Check that the command runs without errors
        assert result.returncode == 0, f"Command failed: {result.stderr}"
        
        # Check that scp subcommand is mentioned in help
        help_output = result.stdout
        assert "scp" in help_output.lower(), "SCP subcommand not found in help"
    
    def test_scp_command_syntax_validation(self):
        """Test SCP command syntax validation."""
        # Test with missing arguments
        result = subprocess.run(
            ["hatch", "run", "test:python", "src/", "scp"], 
            capture_output=True, text=True
        )
        
        # Should fail due to missing arguments
        assert result.returncode != 0, "SCP command should fail with missing args"
        assert "error" in result.stderr.lower(), "Should show error for missing args"
    
    def test_scp_command_invalid_paths(self):
        """Test SCP command with invalid paths."""
        # Test with non-existent local file
        result = subprocess.run(
            ["hatch", "run", "test:python", "src/", "scp", 
             "/non/existent/file.txt", "bastion:/tmp/test.txt"], 
            capture_output=True, text=True
        )
        
        # Should fail due to non-existent file
        assert result.returncode != 0, "SCP should fail with non-existent file"
    
    def test_scp_command_invalid_tunnel_id(self):
        """Test SCP command with invalid tunnel ID."""
        # Create a temporary test file
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("test content")
            temp_file = f.name
        
        try:
            # Test with invalid tunnel ID
            result = subprocess.run(
                ["hatch", "run", "test:python", "src/", "scp", 
                 temp_file, "invalid_tunnel:/tmp/test.txt"], 
                capture_output=True, text=True
            )
            
            # Should fail due to invalid tunnel ID
            assert result.returncode != 0, "SCP should fail with invalid tunnel ID"
        finally:
            # Clean up
            os.unlink(temp_file) 