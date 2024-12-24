import json
import subprocess
import re


class LastpassSecret:
    """A class to retrieve a Lastpass secret. Wraps lpass-cli."""

    def __init__(self, secret_name):
        self.secret_name = secret_name
        # print(f"INFO: Retrieving secret: {self.secret_name}")
        self.secret_response = self._get_secret()
        self.name = self.secret_response["name"]
        self.secret_user = self.secret_response["username"]
        self.secret_pass = self.secret_response["password"]
        self.secret_url = re.sub(r"^http://", "", self.secret_response["url"])

    def _get_secret(self):
        """Returns the secret from Lastpass."""
        # Get the secret from Lastpass
        cmd = f"lpass show --json {self.secret_name}"
        result = subprocess.run(cmd, shell=True, capture_output=True)
        stdout = result.stdout.decode("utf-8").strip()
        stderr = result.stderr.decode("utf-8").strip()
        if result.returncode != 0:
            raise Exception(
                f"Error retrieving secret {self.secret_name}: {stdout} - {stderr}"
            )
        return json.loads(stdout)[0]
