import pytest
from pydantic import ValidationError

from tunnelgraf.tunnel_definition import TunnelDefinition


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
