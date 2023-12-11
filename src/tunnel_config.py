from .lastpass_secrets import LastpassSecret
import ipaddress


class TunnelConfig:
    """TunnelConfig class - validates configuration properties"""

    def __init__(self, config: dict):
        if "nexthop" not in config.keys():
            raise ValueError("ERROR: No nexthop provided.")
        if "id" not in config.keys():
            raise ValueError("ERROR: No id: for tunnel provided.")
        self._id = config["id"]
        print(f"Creating tunnel config for {self._id}.")

        # Lookup LastPass secret if provided for bastion.
        if "lastpass" in config.keys():
            self._get_lastpass_secrets(config["lastpass"])
        else:
            if "user" not in config.keys():
                raise ValueError("ERROR: No bastion user provided.")
            self._bastion_user: str = config["user"]
            if "pass" not in config.keys():
                raise ValueError("ERROR: No bastion password provided.")
            self._bastion_pass: str = config["pass"]

        if "host" not in config.keys():
            if not self._bastion_endpoint:
                raise ValueError("ERROR: No bastion host provided.")
        else:
            self._bastion_endpoint: str | None = config["host"]
        if "port" not in config.keys():
            raise ValueError("ERROR: No bastion port provided at port")
        self._bastion_port: int = config["port"]

        # Lookup LastPass secret if provided for nexthop url.
        nexthop_url = None
        if "lastpass" in config["nexthop"].keys():
            nexthop_url = LastpassSecret(config["nexthop"]["lastpass"]).secret_url
        if "host" not in config["nexthop"].keys():
            if not nexthop_url:
                raise ValueError("ERROR: No remote host provided at nexthop.host")
            self._remote_endpoint = nexthop_url
        else:
            self._remote_endpoint = config["nexthop"]["host"]

        if "port" not in config["nexthop"].keys():
            raise ValueError("ERROR: No remote port provided at nexthop.port")
        self._remote_port: int = config["nexthop"]["port"]
        if "localbindport" not in config["nexthop"].keys():
            raise ValueError(
                "ERROR: No local bind port provided at nexthop.localbindport"
            )
        self._local_port: int = config["nexthop"]["localbindport"]
        if "localbindaddress" not in config["nexthop"].keys():
            config["nexthop"]["localbindaddress"] = "127.0.0.1"
        self._local_ip: str | None = config["nexthop"]["localbindaddress"]

    def _get_lastpass_secrets(self, secret_key: str):
        """Retrieves secrets from LastPass."""
        lps = LastpassSecret(secret_key)
        self._bastion_endpoint = lps.secret_url
        self._bastion_user = lps.secret_user
        self._bastion_pass = lps.secret_pass

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
        if not bp or isinstance(bp, int):
            raise ValueError("Bastion port must not be blank.")
        self._bastion_port = bp

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
        if not re or isinstance(re, str):
            raise ValueError("Remote endpoint must not be blank.")
        self._remote_endpoint = re

    # remote_port getter and setter
    @property
    def remote_port(self) -> int:
        """Returns remote_port property."""
        if not self._remote_port:
            raise ValueError("No remote port provided.")
        return self._remote_port

    @remote_port.setter
    def remote_port(self, bp: int) -> None:
        if not bp or isinstance(bp, int):
            raise ValueError("Remote port must not be blank.")
        self._remote_port = bp

    # local_port getter and setter
    @property
    def local_port(self) -> int:
        """Returns local_port property."""
        if not self._local_port:
            raise ValueError("No local port provided.")
        return self._local_port

    @local_port.setter
    def local_port(self, lp: int) -> None:
        if not lp or isinstance(lp, int):
            raise ValueError("Local port must not be blank.")
        self._local_port = lp

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
        self._local_ip = eip
