from .lastpass_secrets import LastpassSecret
import ipaddress


class TunnelConfig:
    """TunnelConfig class - validates configuration properties"""

    def __init__(self, config: dict):
        self._config_args = config
        self._nexthop_exists()

        self.id = self._config_args["id"]
        self.nexthop_id = self._config_args["nexthop"]["id"]
        print(f"Creating tunnel config for {self._id}.")

        # Lookup LastPass secret if provided for bastion, otherwise user/pass.
        self._get_credentials()

        # Get the bastion host
        self._get_bastion_host()
        self._get_bastion_port()

        # Lookup LastPass secret if provided for nexthop url, otherwise host.
        self._get_nexthop_url()
        self._get_nexthop_port()

        # Get the local IP and port
        self._get_local_ip()
        self._get_local_port()

        # Add the host(s) to the hosts list
        self._hosts_file_entries: list = []
        self._get_hosts()

    def _nexthop_exists(self):
        """Validates that nexthop exists."""
        if "nexthop" not in self._config_args.keys():
            raise ValueError("ERROR: No nexthop provided.")

    def _get_lastpass_secrets(self, secret_key: str):
        """Retrieves secrets from LastPass."""
        lps = LastpassSecret(secret_key)
        self.bastion_endpoint = lps.secret_url
        self.bastion_user = lps.secret_user
        self.bastion_pass = lps.secret_pass

    def _get_credentials(self):
        """Returns a dictionary of credentials."""
        if "lastpass" in self._config_args.keys():
            self._get_lastpass_secrets(self._config_args["lastpass"])
        else:
            if "user" not in self._config_args.keys():
                raise ValueError("ERROR: No bastion user provided.")
            self.bastion_user = self._config_args["user"]
            if "pass" not in self._config_args.keys():
                raise ValueError("ERROR: No bastion password provided.")
            self.bastion_pass = self._config_args["pass"]

    def _get_bastion_host(self):
        """Returns the host for the tunnel."""
        if "host" not in self._config_args.keys():
            if not self.bastion_endpoint:
                raise ValueError("ERROR: No bastion host provided.")
        else:
            self.bastion_endpoint = self._config_args["host"]

    def _get_bastion_port(self):
        """Returns the port for the tunnel."""
        if "port" not in self._config_args.keys():
            raise ValueError("ERROR: No bastion port provided.")
        else:
            self.bastion_port = self._config_args["port"]

    def _get_nexthop_url(self):
        """Returns the nexthop url for the tunnel."""
        nexthop_url = None
        if "lastpass" in self._config_args["nexthop"].keys():
            nexthop_url = LastpassSecret(
                self._config_args["nexthop"]["lastpass"]
            ).secret_url
        if "host" not in self._config_args["nexthop"].keys():
            if not nexthop_url:
                raise ValueError("ERROR: No remote host at nexthop.host")
            self.remote_endpoint = nexthop_url
        else:
            self.remote_endpoint = self._config_args["nexthop"]["host"]

    def _get_nexthop_port(self):
        """Returns the nexthop port for the tunnel."""
        if "port" not in self._config_args["nexthop"].keys():
            raise ValueError("ERROR: No remote port at nexthop.port")
        self.remote_port = self._config_args["nexthop"]["port"]

    def _get_local_ip(self):
        """Returns the local IP address for the tunnel."""
        if "localbindaddress" not in self._config_args["nexthop"].keys():
            self._config_args["nexthop"]["localbindaddress"] = "127.0.0.1"
        self.local_ip = self._config_args["nexthop"]["localbindaddress"]

    def _get_local_port(self):
        """Returns the local port for the tunnel."""
        if "localbindport" not in self._config_args["nexthop"].keys():
            raise ValueError("ERROR: No local port at nexthop.localbindport")
        self.local_port = self._config_args["nexthop"]["localbindport"]

    def _get_hosts(self):
        """Returns a list of hosts."""
        if "hosts_file_entries" in self._config_args["nexthop"].keys() and isinstance(
            self._config_args["nexthop"]["hosts_file_entries"], list
        ):
            for host in self._config_args["nexthop"]["hosts_file_entries"]:
                self._add_hosts_file_entry(host)
        if "hosts_file_entry" in self._config_args["nexthop"].keys():
            self._add_hosts_file_entry(self._config_args["nexthop"]["hosts_file_entry"])

    @property
    def id(self) -> str:
        """Returns the id property."""
        return self._id

    @id.setter
    def id(self, i: str) -> None:
        """Sets the id property."""
        if not i or not isinstance(i, str):
            raise ValueError("ID must not be blank.")
        self._id = i

    # nexthop_id getter and setter
    @property
    def nexthop_id(self) -> str:
        """Returns nexthop_id property."""
        return self._nexthop_id

    @nexthop_id.setter
    def nexthop_id(self, ni: str) -> None:
        if not ni or not isinstance(ni, str):
            raise ValueError("Nexthop ID must not be blank.")
        self._nexthop_id: str = ni

    # bastion_ip getter and setter
    @property
    def bastion_endpoint(self) -> str | None:
        """Returns bastion_endpoint property."""
        return self._bastion_endpoint

    @bastion_endpoint.setter
    def bastion_endpoint(self, be: str | None) -> None:
        self._bastion_endpoint = be

    # bastion_port getter and setter
    @property
    def bastion_port(self) -> int:
        """Returns bastion_port property."""
        if not self._bastion_port:
            raise ValueError("No bastion port provided.")
        return self._bastion_port

    @bastion_port.setter
    def bastion_port(self, bp: int) -> None:
        if not bp or not isinstance(bp, int):
            raise ValueError("Bastion port must not be blank.")
        self._bastion_port: int = bp

    # bastion_user getter and setter
    @property
    def bastion_user(self) -> str:
        """Returns bastion_user property."""
        if not self._bastion_user:
            raise ValueError("No bastion user provided.")
        return self._bastion_user

    @bastion_user.setter
    def bastion_user(self, bus: str) -> None:
        if not bus or not isinstance(bus, str):
            raise ValueError("Bastion User must not be blank.")
        else:
            self._bastion_user = bus

    # bastion_pass getter and setter
    @property
    def bastion_pass(self) -> str:
        """Returns bastion_pass property."""
        if not self._bastion_pass:
            raise ValueError("No ssh password provided for the bastion host.")
        return self._bastion_pass

    @bastion_pass.setter
    def bastion_pass(self, b_pass: str) -> None:
        if not b_pass:
            raise ValueError("Bastion pass must not be blank.")
        self._bastion_pass = b_pass

    # remote_endpoint getter and setter
    @property
    def remote_endpoint(self) -> str:
        """Returns remote_endpoint property."""
        if not self._remote_endpoint:
            raise ValueError("No remote endpoint address specified.")
        return self._remote_endpoint

    @remote_endpoint.setter
    def remote_endpoint(self, re: str) -> None:
        if not re or not isinstance(re, str):
            raise ValueError("Remote endpoint must not be blank.")
        self._remote_endpoint: str = re

    # remote_port getter and setter
    @property
    def remote_port(self) -> int:
        """Returns remote_port property."""
        if not self._remote_port:
            raise ValueError("No remote port provided.")
        return self._remote_port

    @remote_port.setter
    def remote_port(self, bp: int) -> None:
        if not bp or not isinstance(bp, int):
            raise ValueError("Remote port must not be blank.")
        self._remote_port: int = bp

    # local_port getter and setter
    @property
    def local_port(self) -> int:
        """Returns local_port property."""
        if not self._local_port:
            raise ValueError("No local port provided.")
        return self._local_port

    @local_port.setter
    def local_port(self, lp: int) -> None:
        if not lp or not isinstance(lp, int):
            raise ValueError("Local port must not be blank.")
        self._local_port: int = lp

    # local_ip getter and setter
    @property
    def local_ip(self) -> str:
        """Returns local_ip property."""
        if not self._local_ip:
            raise ValueError("No local IP address specified.")
        return self._local_ip

    @local_ip.setter
    def local_ip(self, eip: str) -> None:
        try:
            ipaddress.ip_address(eip)
        except ValueError:
            print(f"Local IP address/netmask is invalid: {eip}")
        self._local_ip: str = eip

    @property
    def hosts_file_entries(self) -> list:
        """Returns a list of hosts."""
        return self._hosts_file_entries

    @hosts_file_entries.setter
    def hosts_file_entries(self, hfe: list) -> None:
        """Sets the hosts list."""
        if not isinstance(hfe, list):
            raise ValueError("Hosts file entries must be a list.")
        self._hosts_file_entries = hfe

    def _add_hosts_file_entry(self, host: str) -> None:
        """Sets the hosts list."""
        self._hosts_file_entries.append(host)
