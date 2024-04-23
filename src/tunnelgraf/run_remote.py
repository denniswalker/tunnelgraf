import paramiko
import pydantic
from typing import Optional


class RunCommand(pydantic.BaseModel):
    host: str = pydantic.Field("localhost", alias="host")
    user: str = pydantic.Field("root", alias="user")
    identityfile: Optional[str] = pydantic.Field(None, alias="identityfile")
    password: Optional[str] = pydantic.Field(None, alias="password")
    port: int = pydantic.Field(22, alias="port")

    def __init__(self, **data):
        super().__init__(**data)
        pkey: paramiko.PKey | None = None
        if self.identityfile:
            pkey = paramiko.pkey.from_private_key_file(self.identityfile)
        self._client = paramiko.SSHClient()
        self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            self._client.connect(
                self.host,
                username=self.user,
                password=self.password,
                pkey=pkey,
                port=self.port,
            )
        except paramiko.ssh_exception.AuthenticationException:
            raise ValueError("Authentication failed")
        except paramiko.ssh_exception.NoValidConnectionsError:
            raise ValueError("No valid connection")

    def run(self, command):
        stdin, stdout, stderr = self.client.exec_command(command, get_pty=True)
        this_stderr: str = stderr.read().decode("utf-8").strip()
        if this_stderr != "":
            raise ValueError(f"Error from {command}: {this_stderr}")
        this_result: str = stdout.read().decode("utf-8").strip()
        if this_result == "":
            raise ValueError(f"No result found for: {command}")
        self._client.close()
        return this_result

    @property
    def client(self):
        return self._client
