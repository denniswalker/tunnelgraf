from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from tunnelgraf.lastpass_secrets import LastpassSecret


class TunnelDefinition(BaseModel):
    id: str = Field(..., alias="id")  # Required field
    host: Optional[str] = Field(None, alias="host")  # Not Required
    port: int = Field(..., alias="port")  # Required field
    localbindaddress: Optional[str] = Field("127.0.0.1", alias="localbindaddress")
    localbindport: int = Field(..., alias="localbindport")  # Required field
    sshuser: Optional[str] = Field(None, alias="sshuser")  # Not required
    sshpass: Optional[str] = Field(None, alias="sshpass")  # Not required
    lastpass: Optional[str] = Field(
        None, alias="lastpass"
    )  # Required or None allowed with alias
    hosts_file_entry: Optional[str] = Field(
        None, alias="hosts_file_entry"
    )  # Not required
    hosts_file_entries: List[Optional[str]] = Field(
        [], alias="hosts_file_entries"
    )  # Default to empty list if not provided
    nexthop: Optional["TunnelDefinition"] = Field(
        None, alias="nexthop"
    )  # Not required, can be a TunnelDefinition object
    nexthops: List[Optional["TunnelDefinition"]] = Field(
        None, alias="nexthops"
    )  # Default to empty list if not provided
    _secret_data: Optional[LastpassSecret] = None

    def __init__(self, **data):
        super().__init__(**data)

        # Call the factory function on the `lastpass` field and use its result
        # as the default for the `host` field.
        if "lastpass" in data and self.lastpass is not None:
            self._secret_data = LastpassSecret(self.lastpass)
            if self.host is None:
                self.host = self._secret_data.secret_url
            if self.sshuser is None:
                self.sshuser = self._secret_data.secret_user
            if self.sshpass is None:
                self.sshpass = self._secret_data.secret_pass

    @field_validator("host", "lastpass")
    def check_at_least_one(cls, v):
        if v is None:
            raise ValueError("At least one of host or lastpass must be present")
        return v
