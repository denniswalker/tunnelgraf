import paramiko
from paramiko import RSAKey, DSSKey, ECDSAKey, Ed25519Key
import pydantic
from typing import Optional
import time


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
        except paramiko.AuthenticationException:
            print("\033[91mAuthentication failed\033[0m")
            exit(1)
        except paramiko.SSHException as e:
            print(f"\033[91mNo valid connection. Did the parent tunnel start? {e}\033[0m")
            exit(1)
        except Exception as e:
            print(f"\033[91mUnexpected error: {e}\033[0m")
            exit(1)

    def run(self, command):
        if self._client is None:
            raise ValueError("SSH client is not connected")
        attempts = 3
        for attempt in range(attempts):
            try:
                stdin, stdout, stderr = self.client.exec_command(command, get_pty=True, timeout=10)
                break  # Exit the loop if successful
            except paramiko.ssh_exception.NoValidConnectionsError as e:
                if attempt == attempts - 1:
                    # Raise an exception after the last attempt
                    raise ValueError(f"Unable to connect to {self.host}:{self.port} after {attempts} attempts - {e}")
                else:
                    print(f"Attempt {attempt + 1} failed, retrying in 1 second...")
                    time.sleep(1)  # Wait for 1 second before retrying

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
