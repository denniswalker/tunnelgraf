import pydantic
from typing import Optional
from tunnelgraf.run_remote import RunCommand


class NSLookup(pydantic.BaseModel):
    record: str = pydantic.Field(..., alias="record")
    nameserver: Optional[str] = pydantic.Field(None, alias="nameserver")
    connection: RunCommand = pydantic.Field(..., alias="connection")
    host_ip: Optional[str] = pydantic.Field(None, alias="host_ip")

    def __init__(self, **data):
        super().__init__(**data)
        self._nslookup_string: str = self._make_lookup_cmd()
        self.host_ip = self._run_nslookup()

    def _make_lookup_cmd(self) -> str:
        this_string = f"dig +short {self.record}"
        if self.nameserver:
            this_string = f"{this_string} @{self.nameserver}"
        return this_string

    def _run_nslookup(self) -> str:
        result: str = self.connection.run(self._nslookup_string)
        return result
