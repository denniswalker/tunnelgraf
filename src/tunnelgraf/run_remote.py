import paramiko
from paramiko import RSAKey, DSSKey, ECDSAKey, Ed25519Key
import pydantic
from typing import Optional
import time
from tunnelgraf.logger import logger
from tunnelgraf.constants import COLOR_RED, COLOR_RESET, COLOR_YELLOW
import sys


class RunCommand(pydantic.BaseModel):
    host: str = pydantic.Field("localhost", alias="host")
    user: str = pydantic.Field("root", alias="user")
    identityfile: Optional[str] = pydantic.Field(None, alias="identityfile")
    password: Optional[str] = pydantic.Field(None, alias="password")
    port: int = pydantic.Field(22, alias="port")
    silent: Optional[bool] = pydantic.Field(False, alias="silent")

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
                banner_timeout=5,
                timeout=8
            )
        except paramiko.AuthenticationException:
            logger.error(f"{COLOR_RED}Authentication failed while running remote command.{COLOR_RESET}")
            exit(1)
        except paramiko.SSHException:
            logger.debug(f"{COLOR_YELLOW}No valid connection. Did the parent tunnel start?{COLOR_RESET}")
            exit(1)
        except Exception:
            logger.debug(f"{COLOR_RED}Unexpected error while running remote command.{COLOR_RESET}")
            exit(1)

    def run(self, command):
        if self._client is None:
            logger.debug(f"{COLOR_RED}SSH client is not connected.{COLOR_RESET}")
        attempts = 3
        for attempt in range(attempts):
            try:
                stdin, stdout, stderr = self.client.exec_command(command, get_pty=True, timeout=10)
                break
            except paramiko.SSHException:
                if attempt == attempts - 1:
                    logger.error(f"Unable to connect to {self.host}:{self.port} after {attempts} attempts.")
                else:
                    logger.warning(f"Attempt {attempt + 1} failed, retrying in 1 second...")
                    time.sleep(1)
        this_stderr: str = stderr.read().decode("utf-8").strip()
        this_result: str = stdout.read().decode("utf-8").strip()
        exit_code = stdout.channel.recv_exit_status()
        if not self.silent:
            # Pass along stderr
            if this_stderr != "":
                sys.stderr.write(f"{this_stderr}\n")
            # Pass along stdout
            if this_result != "":
                sys.stdout.write(f"{this_result}\n")
            # Pass along exit code
            if exit_code != 0:
                sys.exit(exit_code)
        self._client.close()
        return this_result

    def load_private_key(self, filename, password=None):
        key_classes = [RSAKey, DSSKey, ECDSAKey, Ed25519Key]
        for key_class in key_classes:
            try:
                self._pkey = key_class.from_private_key_file(
                    filename=filename, password=password
                )
                logger.debug(f"Loaded key using {key_class.__name__}")
                break
            except Exception as e:
                logger.debug(f"Failed to load with {key_class.__name__}: {e}")
                continue
        if not self._pkey:
            logger.error("Failed to load private key with any supported format")
            raise ValueError("Could not load private key")

    @property
    def client(self):
        return self._client
