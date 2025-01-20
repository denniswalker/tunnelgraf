import pytest
import subprocess
import time
import socket
import signal
import os
from click.testing import CliRunner
from tunnelgraf import cli

# Define a constant for the common command prefix
HATCH_COMMAND_PREFIX = ["hatch", "run", "test:python", "src/", "--profile"]

def start_tunnelgraf(profile_path):
    """Start tunnelgraf in the background without redirecting output."""
    tunnel_process = subprocess.Popen(
        HATCH_COMMAND_PREFIX + [profile_path, "connect", "-d"],
        preexec_fn=os.setsid
    )
    print("Started tunnelgraf with default stdout and stderr handling")
    return tunnel_process

@pytest.fixture(scope="module")
def docker_compose(request, profile_path):
    """Fixture to manage Docker Compose lifecycle."""
    tunnel_process = None
    try:
        subprocess.run(
            ["docker-compose", "up", "--force-recreate", "--build", "-d"],
            check=True
        )
        print("\nDocker Compose services started successfully.")
        wait_for_services()
        
        # Start tunnelgraf process
        tunnel_process = start_tunnelgraf(profile_path)
        
        # Wait for first tunnel port to become available
        print("Waiting for first tunnel (port 2223) to establish...")
        max_attempts = 30
        attempts = 0
        while attempts < max_attempts:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex(('localhost', 2223))
                if result == 0:
                    print("First tunnel is ready")
                    break
                print(f"Waiting for first tunnel... (attempt {attempts+1}/{max_attempts})")
            except socket.error as e:
                print(f"Socket error: {e}")
            finally:
                sock.close()
            
            attempts += 1
            time.sleep(1)
            if attempts == max_attempts:
                pytest.fail("First tunnel did not become ready")
        
        # Give remaining tunnels time to establish
        time.sleep(5)
        
        yield tunnel_process
    finally:
        try:
            subprocess.run(
                HATCH_COMMAND_PREFIX + [profile_path, "stop"],
                check=True
            )
        except subprocess.CalledProcessError as e:
            print(f"Failed to stop tunnels: {e}")

def wait_for_services():
    """Wait for bastion to be ready."""
    services = {
        ("localhost", 2222): "bastion"
    }
    
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
                print(f"Waiting for {service} on port {port}... (attempt {attempts+1}/{max_attempts})")
            except socket.error as e:
                print(f"Socket error for {service}: {e}")
            finally:
                sock.close()
            
            attempts += 1
            time.sleep(1)
            if attempts == max_attempts:
                pytest.fail(f"Service {service} did not become ready on port {port}")

@pytest.fixture
def runner():
    return CliRunner()

def test_all_ports_accessible(docker_compose):
    """Verify all tunnel ports are accessible after tunnelgraf connect."""
    ports_to_check = [2222, 2223, 2224, 2080]
    for port in ports_to_check:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('localhost', port))
        sock.close()
        assert result == 0, f"Port {port} is not accessible"

def test_command_execution(docker_compose, runner):
    """Test the command subcommand executes successfully on different hosts."""
    test_cases = [
        {
            "tunnel_id": "bastion",
            "command": "hostname",
            "expected_output": "bastion"
        },
        {
            "tunnel_id": "sshd1",
            "command": "hostname",
            "expected_output": "sshd1"
        },
        {
            "tunnel_id": "nginx",
            "command": "hostname",
            "expected_output": "nginx"
        }
    ]
    
    for test in test_cases:
        result = runner.invoke(cli, [
            '--profile',
            'tests/connections_profiles/four_in_a_row.yaml',
            '--tunnel-id',
            test["tunnel_id"],
            'command',
            test["command"]
        ])
        
        assert result.exit_code == 0
        assert test["expected_output"] in result.output

def test_shell_connection(docker_compose, runner):
    """Test shell connection to different hosts."""
    test_cases = ["bastion", "sshd1", "sshd2", "nginx"]
    
    for tunnel_id in test_cases:
        process = subprocess.Popen(
            ["hatch", "run", "test:python", "src/",
             "--profile", "tests/connections_profiles/four_in_a_row.yaml",
             "--tunnel-id", tunnel_id,
             "shell"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        try:
            time.sleep(2)
            assert process.poll() is None, f"Shell connection to {tunnel_id} failed to start"
        finally:
            process.terminate()
            process.wait()

def test_nginx_accessible(docker_compose):
    """Test the nginx is accessible through the tunnel chain."""
    curl_process = subprocess.run(
        ["curl", "-s", "-I", "http://localhost:2080"],
        capture_output=True,
        text=True
    )
    
    assert curl_process.returncode == 0
    assert "Server: nginx" in curl_process.stdout 

def test_stop_tunnels(docker_compose):
    """Test the ability to stop all tunnels."""
    try:
        profile_path = "tests/connections_profiles/four_in_a_row.yaml"  # Ensure this matches your actual profile path
        args = HATCH_COMMAND_PREFIX + [profile_path, "stop"]
        subprocess.run(
            args=args,
            check=True
        )
    except subprocess.CalledProcessError as e:
        print(f"Failed to stop tunnels: {e}") 