import pytest
from tunnel_definition import TunnelDefinition


def test_tunnel_definition_required_fields():
    data = {"id": "tunnel1", "port": 22, "localbindport": 8080}
    tunnel = TunnelDefinition(**data)
    assert tunnel.id == "tunnel1"
    assert tunnel.port == 22
    assert tunnel.localbindport == 8080


def test_tunnel_definition_optional_fields():
    data = {
        "id": "tunnel1",
        "port": 22,
        "localbindport": 8080,
        "host": "example.com",
        "sshuser": "user",
        "sshpass": "password",
        "lastpass": "secret",
        "hosts_file_entry": "127.0.0.1 localhost",
        "nexthop": {"id": "tunnel2", "port": 22, "localbindport": 8081},
    }
    tunnel = TunnelDefinition(**data)
    assert tunnel.host == "example.com"
    assert tunnel.sshuser == "user"
    assert tunnel.sshpass == "password"
    assert tunnel.lastpass == "secret"
    assert tunnel.hosts_file_entry == "127.0.0.1 localhost"
    assert tunnel.nexthop.id == "tunnel2"
    assert tunnel.nexthop.port == 22
