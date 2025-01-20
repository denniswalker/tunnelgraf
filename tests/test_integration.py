import pytest
import subprocess
import time
import socket
import os
from click.testing import CliRunner
import pty

# Define a constant for the common command prefix
HATCH_COMMAND_PREFIX = ["hatch", "run", "test:python", "src/", "--profile"]


def start_tunnelgraf(profile_path):
    """Start tunnelgraf in the background without redirecting output."""
    tunnel_process = subprocess.Popen(
        HATCH_COMMAND_PREFIX + [profile_path, "connect", "-d"], preexec_fn=os.setsid
    )
    print("Started tunnelgraf with default stdout and stderr handling")
    return tunnel_process


def wait_for_tunnel(port, max_attempts=30):
    """Wait for a specific tunnel port to become available."""
    print(f"Waiting for tunnel on port {port} to establish...")
    attempts = 0
    while attempts < max_attempts:
        sock = None  # Initialize sock to None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(("localhost", port))
            if result == 0:
                print(f"Tunnel on port {port} is ready")
                return
            print(
                f"Waiting for tunnel on port {port}... (attempt {attempts+1}/{max_attempts})"
            )
        except socket.error as e:
            print(f"Socket error: {e}")
        finally:
            if sock is not None:  # Check if sock is initialized
                sock.close()

        attempts += 1
        time.sleep(1)
    pytest.fail(f"Tunnel on port {port} did not become ready")


@pytest.fixture(scope="module")
def standup_containers(profile_path):
    """Fixture to manage Docker Compose lifecycle."""
    tunnel_process = None
    try:
        subprocess.run(
            ["docker-compose", "up", "--force-recreate", "--build", "-d"], check=True
        )
        print("\nDocker Compose services started successfully.")
        wait_for_docker_services()

        # Start tunnelgraf process
        tunnel_process = start_tunnelgraf(profile_path)

        # Wait for first tunnel port to become available
        wait_for_tunnel(2224)

        # Give remaining tunnels time to establish
        time.sleep(5)

        yield tunnel_process
    finally:
        try:
            subprocess.run(HATCH_COMMAND_PREFIX +
                           [profile_path, "stop"], check=True)
        except subprocess.CalledProcessError as e:
            print(f"Failed to stop tunnels: {e}")


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
                    f"Waiting for {service} on port {port}... (attempt {attempts+1}/{max_attempts})"
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


@pytest.fixture
def runner():
    return CliRunner()


def test_all_ports_accessible(standup_containers):
    """Verify all tunnel ports are accessible after tunnelgraf connect."""
    ports_to_check = [2222, 2224, 2225, 2080]
    for port in ports_to_check:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(("localhost", port))
        sock.close()
        assert result == 0, f"Port {port} is not accessible"


def test_command_execution(standup_containers, profile_path):
    """Test the command subcommand executes successfully on different hosts."""
    test_cases = [
        {"tunnel_id": "bastion", "command": "hostname", "expected_output": "bastion"},
        {"tunnel_id": "sshd1", "command": "hostname", "expected_output": "sshd1"},
        {"tunnel_id": "sshd2", "command": "hostname", "expected_output": "sshd2"},
    ]

    for test in test_cases:
        result = subprocess.run(
            HATCH_COMMAND_PREFIX
            + [
                profile_path,
                "--tunnel-id",
                test["tunnel_id"],
                "command",
                test["command"],
            ],
            capture_output=True,
            text=True,
        )

        assert (
            result.returncode == 0
        ), f"Command failed with exit code {result.returncode}"
        assert (
            test["expected_output"] in result.stdout
        ), f"Expected output not found in stdout: {result.stdout}"


def test_shell_connection(standup_containers, profile_path):
    """Test shell connection to different hosts."""
    test_cases = ["bastion", "sshd1", "sshd2"]

    for tunnel_id in test_cases:
        master_fd, slave_fd = pty.openpty()
        process = subprocess.Popen(
            HATCH_COMMAND_PREFIX + [profile_path,
                                    "--tunnel-id", tunnel_id, "shell"],
            stdin=slave_fd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            close_fds=True,
        )

        try:
            time.sleep(2)
            assert (
                process.poll() is None
            ), f"Shell connection to {tunnel_id} failed to start"

            # Send "exit" command to the shell
            time.sleep(1)  # Wait for the shell to start.
            os.write(master_fd, b"exit\n")
            time.sleep(1)  # Wait for the command to be processed.
        finally:
            os.close(slave_fd)
            stdout, stderr = process.communicate()
            print(f"STDOUT for {tunnel_id}:\n{stdout.decode()}")
            print(f"STDERR for {tunnel_id}:\n{stderr.decode()}")
            process.terminate()
            process.wait()


def test_nginx_accessible(standup_containers):
    """Test the nginx is accessible through the tunnel chain."""
    curl_process = subprocess.run(
        ["curl", "-s", "-I", "http://localhost:2080"], capture_output=True, text=True
    )

    assert curl_process.returncode == 0
    assert "Server: nginx" in curl_process.stdout


def test_stop_tunnels(profile_path):
    """Test the ability to stop all tunnels."""
    try:
        args = HATCH_COMMAND_PREFIX + [profile_path, "stop"]
        subprocess.run(args=args, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Failed to stop tunnels: {e}")
