import pytest
from pydantic import ValidationError
import subprocess

from tunnelgraf.tunnel_definition import TunnelDefinition


@pytest.fixture(scope="session", autouse=True)
def docker_compose():
    """Pytest fixture to manage Docker Compose lifecycle."""
    # Setup: Start Docker Compose services
    try:
        subprocess.run(
            ["docker-compose", "up", "--force-recreate", "--build", "-d"],
            check=True
        )
        print("Docker Compose services started successfully.")
        
        # Run additional command in an interactive session
        subprocess.run(
            ["hatch", "run", "python3", ".", "-p", "tests/four_in_a_row.yaml", "connect"],
            check=True
        )
        print("Additional setup command executed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"An error occurred during setup: {e}")
        pytest.exit("Exiting due to setup failure.")
    import ipdb; ipdb.set_trace()

    # Yield control to the test
    yield

    # Teardown: Stop Docker Compose services
    try:
        subprocess.run(
            ["docker-compose", "down"],
            check=True
        )
        print("Docker Compose services stopped successfully.")
    except subprocess.CalledProcessError as e:
        print(f"An error occurred while stopping Docker Compose services: {e}")


def test_tunnel_definition_required_fields():
    data = {"id": "tunnel1", "port": 22, "localbindport": 8080}
    tunnel = TunnelDefinition(**data)
    assert tunnel.id == "tunnel1"
    assert tunnel.port == 22
    assert tunnel.localbindport == 8080

    # Test with incomplete data
    without_localbindport_data = {"id": "tunnel1", "port": 22}
    with pytest.raises(ValidationError):
        TunnelDefinition(**without_localbindport_data)
    without_port_data = {"id": "tunnel1", "localbindport": 8080}
    with pytest.raises(ValidationError):
        TunnelDefinition(**without_port_data)
    without_id_data = {"port": 22, "localbindport": 8080}
    with pytest.raises(ValidationError):
        TunnelDefinition(**without_id_data)


def test_tunnel_definition_optional_fields():
    data = {
        "id": "tunnel1",
        "port": 22,
        "localbindport": 8080,
        "host": "example.com",
        "sshuser": "user",
        "sshpass": "password",
        "hosts_file_entry": "example.local",
        "nexthop": {"id": "tunnel2", "port": 22, "localbindport": 8081},
    }
    tunnel = TunnelDefinition(**data)
    assert tunnel.host == "example.com"
    assert tunnel.sshuser == "user"
    assert tunnel.sshpass == "password"
    assert tunnel.hosts_file_entry == "example.local"
    assert tunnel.nexthop.id == "tunnel2"
    assert tunnel.nexthop.port == 22
