import json
import pytest
from click.testing import CliRunner
from tunnelgraf import cli

@pytest.fixture
def runner():
    return CliRunner()

def test_show_command(runner):
    """Test the show command output matches expected structure"""
    result = runner.invoke(cli, ['--profile', 'tests/connections_profiles/four_in_a_row.yaml', 'show'])
    assert result.exit_code == 0
    
    # Parse the JSON output
    output = json.loads(result.output)
    
    # Verify it's a list of tunnel configurations
    assert isinstance(output, list)
    
    # Verify expected structure for each tunnel
    expected_tunnels = [
        {
            "id": "bastion",
            "host": "localhost",
            "port": 2222,
            "protocol": "ssh",
        },
        {
            "id": "sshd1",
            "port": 2224,
            "protocol": "ssh",
        },
        {
            "id": "sshd2",
            "port": 2225,
            "protocol": "ssh",
        },
        {
            "id": "nginx",
            "port": 2080,
            "protocol": "ssh",
            "hosts_file_entry": "nginx.local"
        }
    ]
    
    # Check each tunnel has expected fields
    for expected in expected_tunnels:
        matching = [t for t in output if t["id"] == expected["id"]]
        assert len(matching) == 1
        tunnel = matching[0]
        for key, value in expected.items():
            assert tunnel[key] == value

def test_show_command_with_credentials(runner):
    """Test the show command with credentials flag shows sensitive information"""
    result = runner.invoke(cli, [
        '--profile', 
        'tests/connections_profiles/four_in_a_row.yaml', 
        'show',
        '--show-credentials'
    ])
    assert result.exit_code == 0
    
    output = json.loads(result.output)
    
    # Check that credential fields are present
    bastion = next(t for t in output if t["id"] == "bastion")
    assert "sshuser" in bastion
    assert "sshpass" in bastion
    assert bastion["sshuser"] == "root"
    assert bastion["sshpass"] == "tunnelgraf"

def test_show_specific_tunnel(runner):
    """Test showing configuration for a specific tunnel"""
    result = runner.invoke(cli, [
        '--profile',
        'tests/connections_profiles/four_in_a_row.yaml',
        '--tunnel-id',
        'nginx',
        'show'
    ])
    assert result.exit_code == 0
    
    output = json.loads(result.output)
    assert output["id"] == "nginx"
    assert output["port"] == 2080
    assert output["hosts_file_entry"] == "nginx.local"

def test_urls_command(runner):
    """Test the urls command output"""
    result = runner.invoke(cli, ['--profile', 'tests/connections_profiles/four_in_a_row.yaml', 'urls'])
    assert result.exit_code == 0
    
    output = json.loads(result.output)
    
    # Verify expected URL structure
    expected_urls = {
        "bastion": ["ssh://localhost:2222"],
        "sshd1": ["ssh://127.0.0.1:2224"],
        "sshd2": ["ssh://127.0.0.1:2225"],
        "nginx": ["ssh://nginx.local:2080"]
    }
    
    assert output == expected_urls

def test_invalid_tunnel_id(runner):
    """Test showing configuration for a non-existent tunnel"""
    result = runner.invoke(cli, [
        '--profile',
        'tests/connections_profiles/four_in_a_row.yaml',
        '--tunnel-id',
        'nonexistent',
        'show'
    ])
    assert result.exit_code == 1
    assert "Tunnel id nonexistent not found" in result.output 