"""
Comprehensive SCP integration tests for tunnelgraf.

This test suite performs end-to-end testing of the SCP functionality:
1. Starts Docker Compose stack
2. Runs tunnelgraf connect
3. Creates test files and directories
4. Copies files to/from containers
5. Verifies transfers
6. Cleans up everything
"""

import pytest
import subprocess
import time
import socket
import os
import tempfile
import shutil

# Define a constant for the common command prefix
HATCH_COMMAND_PREFIX = ["hatch", "run", "test:python", "src/", "--profile"]


def start_tunnelgraf(profile_path):
    """Start tunnelgraf in the background."""
    tunnel_process = subprocess.Popen(
        HATCH_COMMAND_PREFIX + [profile_path, "connect", "-d"], 
        preexec_fn=os.setsid
    )
    print("Started tunnelgraf with default stdout and stderr handling")
    return tunnel_process


def wait_for_tunnel(port, max_attempts=30):
    """Wait for a specific tunnel port to become available."""
    print(f"Waiting for tunnel on port {port} to establish...")
    attempts = 0
    while attempts < max_attempts:
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(("localhost", port))
            if result == 0:
                print(f"Tunnel on port {port} is ready")
                return
            print(
                f"Waiting for tunnel on port {port}... "
                f"(attempt {attempts+1}/{max_attempts})"
            )
        except socket.error as e:
            print(f"Socket error: {e}")
        finally:
            if sock is not None:
                sock.close()

        attempts += 1
        time.sleep(1)
    pytest.fail(f"Tunnel on port {port} did not become ready")


def wait_for_docker_services():
    """Wait for bastion to be ready."""
    services = {("localhost", 2222): "bastion"}

    max_attempts = 60
    for (host, port), service in services.items():
        attempts = 0
        while attempts < max_attempts:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex((host, port))
                if result == 0:
                    print(f"Service {service} is ready on port {port}")
                    break
                print(
                    f"Waiting for {service} on port {port}... "
                    f"(attempt {attempts+1}/{max_attempts})"
                )
            except socket.error as e:
                print(f"Socket error for {service}: {e}")
            finally:
                sock.close()

            attempts += 1
            time.sleep(1)
            if attempts == max_attempts:
                pytest.fail(
                    f"Service {service} did not become ready on port {port}")


def create_test_files(temp_dir):
    """Create test files and directories for SCP testing."""
    test_files = {
        "test_file.txt": "This is a test file for SCP transfer\nLine 2\nLine 3",
        "test_dir/test_subfile.txt": "This is a subfile in a directory",
        "test_dir/another_file.txt": "Another file in the test directory",
        "binary_file.bin": b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09",
        "empty_file.txt": "",
        "large_file.txt": "Large file content\n" * 1000,  # ~16KB file
    }
    
    created_files = []
    
    for file_path, content in test_files.items():
        full_path = os.path.join(temp_dir, file_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        
        with open(full_path, 'wb' if isinstance(content, bytes) else 'w') as f:
            f.write(content)
        
        created_files.append(full_path)
        print(f"Created test file: {full_path}")
    
    return created_files


def verify_file_transfer(source_path, dest_path, is_binary=False):
    """Verify that a file transfer was successful."""
    if not os.path.exists(dest_path):
        pytest.fail(f"Destination file does not exist: {dest_path}")
    
    if os.path.isdir(source_path):
        # For directories, check that all files are present
        source_files = set()
        dest_files = set()
        
        for root, dirs, files in os.walk(source_path):
            for file in files:
                rel_path = os.path.relpath(os.path.join(root, file), source_path)
                source_files.add(rel_path)
        
        for root, dirs, files in os.walk(dest_path):
            for file in files:
                rel_path = os.path.relpath(os.path.join(root, file), dest_path)
                dest_files.add(rel_path)
        
        missing_files = source_files - dest_files
        if missing_files:
            pytest.fail(f"Missing files in transfer: {missing_files}")
        
        print(f"✅ Directory transfer verified: {source_path} -> {dest_path}")
    else:
        # For files, compare content
        with open(source_path, 'rb' if is_binary else 'r') as f:
            source_content = f.read()
        
        with open(dest_path, 'rb' if is_binary else 'r') as f:
            dest_content = f.read()
        
        if source_content != dest_content:
            pytest.fail(f"File content mismatch: {source_path} -> {dest_path}")
        
        print(f"✅ File transfer verified: {source_path} -> {dest_path}")


def run_scp_command(source, destination, profile_path, tunnel_id=None):
    """Run SCP command using tunnelgraf."""
    cmd = HATCH_COMMAND_PREFIX + [profile_path, "scp"]
    
    if tunnel_id:
        cmd.extend(["--tunnel-id", tunnel_id])
    
    cmd.extend([source, destination])
    
    print(f"🔄 Running SCP command: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"❌ SCP command failed with return code {result.returncode}")
        print(f"STDOUT: {result.stdout}")
        print(f"STDERR: {result.stderr}")
        pytest.fail(f"SCP command failed: {' '.join(cmd)}")
    
    print(f"✅ SCP command successful: {source} -> {destination}")
    return result


def check_services_running():
    """Check if Docker Compose services and tunnelgraf are already running."""
    # Check if Docker Compose services are running
    try:
        result = subprocess.run(
            ["docker-compose", "ps", "-q"], 
            capture_output=True, 
            text=True, 
            check=True
        )
        services_running = bool(result.stdout.strip())
    except subprocess.CalledProcessError:
        services_running = False
    
    # Check if tunnelgraf is running by testing tunnel port
    tunnel_running = False
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(("localhost", 2224))
        tunnel_running = (result == 0)
        sock.close()
    except socket.error:
        tunnel_running = False
    
    return services_running, tunnel_running


@pytest.fixture(scope="module")
def scp_test_environment(profile_path):
    """Fixture to manage the complete SCP test environment efficiently."""
    # Check if we're being run from the test runner (which handles setup)
    if os.environ.get('TUNNELGRAF_TEST_RUNNER'):
        # We're being run from the test runner, just provide the environment
        yield {
            "tunnel_process": None,
            "temp_dir": tempfile.mkdtemp(prefix="tunnelgraf_scp_test_"),
            "profile_path": profile_path,
            "services_started": False,
            "tunnel_started": False
        }
        return
    
    # Original setup logic for when running tests directly
    tunnel_process = None
    temp_dir = None
    services_started = False
    tunnel_started = False
    
    try:
        # Check if services are already running
        services_running, tunnel_running = check_services_running()
        
        # Start Docker Compose stack only if not running
        if not services_running:
            print("\nStarting Docker Compose stack...")
            subprocess.run(
                ["docker-compose", "up", "--force-recreate", "--build", "-d"], 
                check=True
            )
            print("✓ Docker Compose services started successfully.")
            wait_for_docker_services()
            services_started = True
        else:
            print("✓ Docker Compose services already running")
        
        # Start tunnelgraf only if not running
        if not tunnel_running:
            print("\nStarting tunnelgraf...")
            tunnel_process = start_tunnelgraf(profile_path)
            wait_for_tunnel(2224)
            time.sleep(5)  # Give remaining tunnels time to establish
            tunnel_started = True
        else:
            print("✓ tunnelgraf already running")
        
        # Create temporary directory for test files
        temp_dir = tempfile.mkdtemp(prefix="tunnelgraf_scp_test_")
        print(f"✓ Created temporary test directory: {temp_dir}")

        yield {
            "tunnel_process": tunnel_process,
            "temp_dir": temp_dir,
            "profile_path": profile_path,
            "services_started": services_started,
            "tunnel_started": tunnel_started
        }
        
    finally:
        # Cleanup - only stop services if we started them
        print("\nCleaning up test environment...")
        
        if tunnel_process and tunnel_started:
            try:
                subprocess.run(HATCH_COMMAND_PREFIX + [profile_path, "stop"], check=True)
                print("✓ Stopped tunnelgraf")
            except subprocess.CalledProcessError as e:
                print(f"Failed to stop tunnels: {e}")
        
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
            print(f"✓ Removed temporary directory: {temp_dir}")
        
        # Only stop Docker Compose if we started it
        if services_started:
            try:
                subprocess.run(["docker-compose", "down"], check=True)
                print("✓ Stopped Docker Compose stack")
            except subprocess.CalledProcessError as e:
                print(f"Failed to stop Docker Compose: {e}")
        else:
            print("✓ Keeping Docker Compose stack running for next tests")


class TestSCPIntegration:
    """Test SCP functionality with full integration workflow."""

    def test_upload_single_file(self, scp_test_environment):
        """Test uploading a single file to a container."""
        temp_dir = scp_test_environment["temp_dir"]
        profile_path = scp_test_environment["profile_path"]
        
        # Create test file
        test_file = os.path.join(temp_dir, "upload_test.txt")
        with open(test_file, 'w') as f:
            f.write("This is a test file for upload\nLine 2\nLine 3")
        
        # Upload to bastion container
        remote_path = "bastion:/tmp/upload_test.txt"
        run_scp_command(test_file, remote_path, profile_path)
        
        # Verify upload by downloading and comparing
        download_path = os.path.join(temp_dir, "download_verify.txt")
        run_scp_command(remote_path, download_path, profile_path)
        
        verify_file_transfer(test_file, download_path)

    def test_upload_directory(self, scp_test_environment):
        """Test uploading a directory to a container."""
        temp_dir = scp_test_environment["temp_dir"]
        profile_path = scp_test_environment["profile_path"]
        
        # Create test directory with multiple files
        test_dir = os.path.join(temp_dir, "upload_dir")
        os.makedirs(test_dir, exist_ok=True)
        
        test_files = {
            "file1.txt": "Content of file 1",
            "file2.txt": "Content of file 2",
            "subdir/file3.txt": "Content of file 3 in subdir",
            "subdir/file4.txt": "Content of file 4 in subdir",
        }
        
        for file_path, content in test_files.items():
            full_path = os.path.join(test_dir, file_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, 'w') as f:
                f.write(content)
        
        # Upload directory to sshd1 container
        remote_path = "sshd1:/tmp/upload_dir"
        run_scp_command(test_dir, remote_path, profile_path)
        
        # Verify upload by downloading and comparing
        download_dir = os.path.join(temp_dir, "download_verify_dir")
        run_scp_command(remote_path, download_dir, profile_path)
        
        verify_file_transfer(test_dir, download_dir)

    def test_download_single_file(self, scp_test_environment):
        """Test downloading a single file from a container."""
        temp_dir = scp_test_environment["temp_dir"]
        profile_path = scp_test_environment["profile_path"]
        
        # Create test file on bastion container
        test_content = "This is a test file for download\nLine 2\nLine 3"
        test_file = os.path.join(temp_dir, "download_test.txt")
        with open(test_file, 'w') as f:
            f.write(test_content)
        
        # Upload first to create the file on the container
        remote_path = "bastion:/tmp/download_test.txt"
        run_scp_command(test_file, remote_path, profile_path)
        
        # Download the file
        download_path = os.path.join(temp_dir, "downloaded_file.txt")
        run_scp_command(remote_path, download_path, profile_path)
        
        verify_file_transfer(test_file, download_path)

    def test_download_directory(self, scp_test_environment):
        """Test downloading a directory from a container."""
        temp_dir = scp_test_environment["temp_dir"]
        profile_path = scp_test_environment["profile_path"]
        
        # Create test directory on sshd2 container
        test_dir = os.path.join(temp_dir, "download_dir")
        os.makedirs(test_dir, exist_ok=True)
        
        test_files = {
            "file1.txt": "Download test file 1",
            "file2.txt": "Download test file 2",
            "subdir/file3.txt": "Download test file 3 in subdir",
        }
        
        for file_path, content in test_files.items():
            full_path = os.path.join(test_dir, file_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, 'w') as f:
                f.write(content)
        
        # Upload directory to sshd2 container
        remote_path = "sshd2:/tmp/download_dir"
        run_scp_command(test_dir, remote_path, profile_path)
        
        # Download the directory
        download_dir = os.path.join(temp_dir, "downloaded_dir")
        run_scp_command(remote_path, download_dir, profile_path)
        
        verify_file_transfer(test_dir, download_dir)

    def test_binary_file_transfer(self, scp_test_environment):
        """Test transferring binary files."""
        temp_dir = scp_test_environment["temp_dir"]
        profile_path = scp_test_environment["profile_path"]
        
        # Create binary test file
        binary_file = os.path.join(temp_dir, "binary_test.bin")
        binary_data = b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09" * 100  # 1KB of data
        with open(binary_file, 'wb') as f:
            f.write(binary_data)
        
        # Upload binary file to sshd2 container (SSH-enabled)
        remote_path = "sshd2:/tmp/binary_test.bin"
        run_scp_command(binary_file, remote_path, profile_path)
        
        # Download and verify
        download_path = os.path.join(temp_dir, "downloaded_binary.bin")
        run_scp_command(remote_path, download_path, profile_path)
        
        verify_file_transfer(binary_file, download_path, is_binary=True)

    def test_large_file_transfer(self, scp_test_environment):
        """Test transferring large files."""
        temp_dir = scp_test_environment["temp_dir"]
        profile_path = scp_test_environment["profile_path"]
        
        # Create large test file (~1MB)
        large_file = os.path.join(temp_dir, "large_test.txt")
        large_content = "Large file content\n" * 50000  # ~1MB
        with open(large_file, 'w') as f:
            f.write(large_content)
        
        # Upload large file to bastion container
        remote_path = "bastion:/tmp/large_test.txt"
        run_scp_command(large_file, remote_path, profile_path)
        
        # Download and verify
        download_path = os.path.join(temp_dir, "downloaded_large.txt")
        run_scp_command(remote_path, download_path, profile_path)
        
        verify_file_transfer(large_file, download_path)

    def test_empty_file_transfer(self, scp_test_environment):
        """Test transferring empty files."""
        temp_dir = scp_test_environment["temp_dir"]
        profile_path = scp_test_environment["profile_path"]
        
        # Create empty test file
        empty_file = os.path.join(temp_dir, "empty_test.txt")
        with open(empty_file, 'w'):
            pass  # Create empty file
        
        # Upload empty file to sshd1 container
        remote_path = "sshd1:/tmp/empty_test.txt"
        run_scp_command(empty_file, remote_path, profile_path)
        
        # Download and verify
        download_path = os.path.join(temp_dir, "downloaded_empty.txt")
        run_scp_command(remote_path, download_path, profile_path)
        
        verify_file_transfer(empty_file, download_path)

    def test_multiple_container_transfers(self, scp_test_environment):
        """Test transfers to multiple containers in the tunnel chain."""
        temp_dir = scp_test_environment["temp_dir"]
        profile_path = scp_test_environment["profile_path"]
        
        # Create test file
        test_file = os.path.join(temp_dir, "multi_container_test.txt")
        with open(test_file, 'w') as f:
            f.write("Test file for multiple container transfers\n")
        
        # Test transfers to different containers (SSH-enabled only)
        containers = ["bastion", "sshd1", "sshd2"]
        
        for container in containers:
            print(f"\nTesting transfer to {container}...")
            
            # Upload to container
            remote_path = f"{container}:/tmp/multi_test_{container}.txt"
            run_scp_command(test_file, remote_path, profile_path)
            
            # Download from container
            download_path = os.path.join(temp_dir, f"downloaded_{container}.txt")
            run_scp_command(remote_path, download_path, profile_path)
            
            # Verify transfer
            verify_file_transfer(test_file, download_path)



    def test_error_handling_invalid_paths(self, scp_test_environment):
        """Test error handling for invalid paths."""
        profile_path = scp_test_environment["profile_path"]
        
        # Test non-existent local file upload
        with pytest.raises(Exception):
            run_scp_command("/non/existent/file.txt", "bastion:/tmp/test.txt", profile_path)
        
        # Test non-existent remote file download
        with pytest.raises(Exception):
            run_scp_command("bastion:/non/existent/file.txt", "/tmp/test.txt", profile_path)

    def test_error_handling_invalid_tunnel_id(self, scp_test_environment):
        """Test error handling for invalid tunnel IDs."""
        profile_path = scp_test_environment["profile_path"]
        
        # Create test file
        temp_dir = scp_test_environment["temp_dir"]
        test_file = os.path.join(temp_dir, "error_test.txt")
        with open(test_file, 'w') as f:
            f.write("Test file for error handling\n")
        
        # Test invalid tunnel ID
        with pytest.raises(Exception):
            run_scp_command(test_file, "invalid_tunnel:/tmp/test.txt", profile_path)

    def test_concurrent_transfers(self, scp_test_environment):
        """Test multiple concurrent file transfers."""
        temp_dir = scp_test_environment["temp_dir"]
        profile_path = scp_test_environment["profile_path"]
        
        # Create multiple test files
        test_files = []
        for i in range(5):
            test_file = os.path.join(temp_dir, f"concurrent_test_{i}.txt")
            with open(test_file, 'w') as f:
                f.write(f"Concurrent test file {i}\n")
            test_files.append(test_file)
        
        # Upload all files concurrently
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = []
            for i, test_file in enumerate(test_files):
                remote_path = f"bastion:/tmp/concurrent_test_{i}.txt"
                future = executor.submit(
                    run_scp_command, test_file, remote_path, profile_path
                )
                futures.append((future, test_file, i))
            
            # Wait for all uploads to complete
            for future, test_file, i in futures:
                future.result()
                print(f"✓ Concurrent upload {i} completed")
        
        # Download all files and verify
        for i, test_file in enumerate(test_files):
            remote_path = f"bastion:/tmp/concurrent_test_{i}.txt"
            download_path = os.path.join(temp_dir, f"downloaded_concurrent_{i}.txt")
            run_scp_command(remote_path, download_path, profile_path)
            verify_file_transfer(test_file, download_path) 