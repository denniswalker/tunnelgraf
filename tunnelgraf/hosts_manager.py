from python_hosts import Hosts, HostsEntry, HostsException
import sys

class HostsManager:
    _instance = None  # Class-level attribute to store the singleton instance

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(HostsManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, '_initialized'):  # Ensure __init__ is only called once
            self.original_hosts = Hosts()
            self.new_hosts = Hosts()
            self._initialized = True

    def write_changes_to_hosts_file(self):
        """Writes the changes to the hosts file."""
        print("Updating hosts file...")
        try:
            self.new_hosts.write()
        except HostsException as e:
            print(
                f"Error writing hosts file. Are you root or do you own the hosts file? Error: {e}"
            )
            sys.exit(1)

    def add_to_hosts(
        self,
        what_for: str,
        hosts: list,
        this_host: str | None = None,
        this_host_lookup: str | None = None,
    ) -> None:
        """Adds a host to the hosts list."""
        if this_host is not None:
            hosts.append(this_host)
        if this_host_lookup is not None:
            hosts.append(this_host_lookup)
        if len(hosts) > 0:
            for host in hosts:
                print(f"{host} will be added to hosts file.")
                this_entry = HostsEntry(
                    address="127.0.0.1",
                    names=[host],
                    entry_type="ipv4",
                    comment=f"pytunnels entry for {what_for}",
                )
                self.new_hosts.add(entries=[this_entry], allow_address_duplication=True)

    def restore_original_hosts_file(self):
        """Restores the original hosts file."""
        print("Restoring original hosts file.")
        self.original_hosts.write() 