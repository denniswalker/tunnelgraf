import paramiko
from paramiko import RSAKey, DSSKey, ECDSAKey, Ed25519Key
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
        self._pkey: paramiko.PKey | None = None
        if self.identityfile:
            self.load_private_key(filename=self.identityfile)
        self._client = paramiko.SSHClient()
        self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            self._client.connect(
                self.host,
                username=self.user,
                password=self.password,
                pkey=self._pkey,
                port=self.port,
            )
            print(f"Connected to {self.host}:{self.port} as {self.user}")
        except paramiko.AuthenticationException:
            print("Authentication failed")
            exit(1)
        except paramiko.SSHException as e:
            print(f"No valid connection. Did the parent tunnel start? {e}")
            exit(1)
        except Exception as e:
            print(f"Unexpected error: {e}")
            exit(1)

    def run(self, command):
        if self._client is None:
            raise ValueError("SSH client is not connected")
        try:
            stdin, stdout, stderr = self.client.exec_command(command, get_pty=True, timeout=10)
        except paramiko.ssh_exception.NoValidConnectionsError as e:
            raise ValueError(f"Unable to connect to {self.host}:{self.port} - {e}")

        this_stderr: str = stderr.read().decode("utf-8").strip()
        if this_stderr != "":
            raise ValueError(f"Error from {command}: {this_stderr}")
        this_result: str = stdout.read().decode("utf-8").strip()
        if this_result == "":
            raise ValueError(f"No result found for: {command}")
        self._client.close()
        return this_result

    def load_private_key(self, filename, password=None):
        key_classes = [RSAKey, DSSKey, ECDSAKey, Ed25519Key]
        for key_class in key_classes:
            try:
                # Attempt to load the key using the current key class
                self._pkey = key_class.from_private_key_file(
                    filename=filename, password=password
                )
                print(f"Loaded key using {key_class.__name__}")
            except Exception as e:
                # Print the exception for debugging purposes
                # print(f"Tried to load with {key_class.__name__}: {e}")
                pass

    @property
    def client(self):
        return self._client
