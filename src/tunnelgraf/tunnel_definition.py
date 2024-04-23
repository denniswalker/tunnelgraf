from typing import List, Optional

from pydantic import BaseModel, Field
from paramiko import SSHConfig, SSHConfigDict
from pathlib import Path
from os import path
from deepmerge import always_merger
import yaml
from tunnelgraf.lastpass_secrets import LastpassSecret
from tunnelgraf import config


class TunnelDefinition(BaseModel):
    id: str = Field(..., alias="id")  # Required field
    include: Optional[str] = Field(None, alias="include")  # Not required
    host: Optional[str] = Field(None, alias="host")  # Not Required
    port: Optional[int] = Field(22, alias="port")  # Not Required
    localbindaddress: Optional[str] = Field("127.0.0.1", alias="localbindaddress")
    localbindport: int = Field(..., alias="localbindport")  # Required field
    protocol: Optional[str] = Field("ssh", alias="protocol")  # Not required
    sshuser: Optional[str] = Field(None, alias="sshuser")  # Not required
    sshpass: Optional[str] = Field(None, alias="sshpass")  # Not required
    sshkeyfile: Optional[str] = Field(None, alias="sshkeyfile")  # Not required
    hostlookup: Optional[str] = Field(None, alias="hostlookup")  # Not required
    nameserver: Optional[str] = Field(None, alias="nameserver")  # Not required
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
        self._included_vars = self.fetch_include_values()
        if self._included_vars:
            always_merger.merge(self._included_vars, data)
            super().__init__(**self._included_vars)

        # Load defaults from the ssh config file
        self._ssh_config = SSHConfig()
        ssh_config_file = path.join(Path.home(), ".ssh", "config")
        self._ssh_config.parse(open(ssh_config_file))
        self.get_ssh_config()

        # Load defaults from lastpass if lastpass is provided
        self.get_lastpass_secret_config()

        # Validate the model
        self.validate()

    def fetch_include_values(self) -> None | dict:
        if self.include and config.CONFIG_FILE_PATH is not None:
            if path.isabs(self.include):
                f = open(self.include, "r")
            else:
                self.include = path.join(config.CONFIG_FILE_PATH, self.include)
                f = open(self.include, "r")
            return yaml.safe_load(f)
        else:
            return None

    def get_ssh_config(self) -> None:
        """Looks up the ssh config file for the host, port, and credentials."""
        this_ssh_config: SSHConfigDict = self._ssh_config.lookup(self.id)
        # print(f"INFO: ssh config values for {self.id} are {this_ssh_config}")
        if self.sshuser is None:
            self.sshuser = this_ssh_config.get("user", None)
        if self.sshpass is None:
            self.sshpass = this_ssh_config.get("password", None)
        if self.port == 22:
            self.port = this_ssh_config.get("port", 22)
        if self.host is None:
            self.host = this_ssh_config.get("hostname", self.host)
        if self.sshkeyfile is None:
            self.sshkeyfile = this_ssh_config.get("identityfile", self.sshkeyfile)
            if isinstance(self.sshkeyfile, list):
                self.sshkeyfile = self.sshkeyfile[0]

    def get_lastpass_secret_config(self) -> None:
        """Returns the lastpass secret."""
        if self.lastpass is not None:
            self._secret_data = LastpassSecret(self.lastpass)
            if (
                self.host is None or self.host == self.id
            ) and self._secret_data.secret_url != "":
                self.host = self._secret_data.secret_url
            if self.sshuser is None:
                self.sshuser = self._secret_data.secret_user
            if self.sshpass is None:
                self.sshpass = self._secret_data.secret_pass

    def validate(self):
        """Validates the model."""
        self._check_field_not_empty("id")
        self._check_field_not_empty("localbindport")
        self._check_field_not_empty("host")
        self._check_field_not_empty("port")

    def _check_field_not_empty(self, attrib: str):
        """Checks if the field is not empty."""
        if getattr(self, attrib) is None:
            raise ValueError(f"Field {attrib} cannot be empty.")
