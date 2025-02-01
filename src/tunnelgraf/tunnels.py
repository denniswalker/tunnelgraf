import os
import threading
from time import sleep
from pathlib import Path
import yaml
import time
import signal
from tunnelgraf import config
from tunnelgraf.tunnel_builder import TunnelBuilder
from tunnelgraf.tunnel_definition import TunnelDefinition
from tunnelgraf.run_remote import RunCommand
from tunnelgraf.nslookup import NSLookup
from tunnelgraf.hosts_manager import HostsManager
from tunnelgraf.logger import logger
from tunnelgraf.constants import (
    STATUS_ACTIVE,
    STATUS_DOWN,
    STATUS_CLOSING,
    STATUS_FAILED,
)
from tunnelgraf.tunnel_count import TunnelCount


class Tunnels:
    """
    Creates an ssh tunnel, connecting a remote endpoint through a bastion
    and binding it to a local port, as specified in the provided config file.
    """

    def __init__(
        self,
        config_file_path: Path,
        connect_tunnels: bool = True,
        show_credentials: bool = False,
        detach: bool = False,
    ):
        self.detach = detach
        with config_file_path.open() as cf:
            self._config_file: str = cf.read()
        self.config: dict | list = self._get_config()
        config.CONFIG_FILE_PATH = str(config_file_path.parent)
        self.tunnel_defs: TunnelDefinition | list[TunnelDefinition] = TunnelDefinition(
            **self.config
        )
        self._excluded_fields: list[str] = self._get_excluded_fields(show_credentials)
        self.tunnels: list[TunnelBuilder] = []
        self.tunnel_configs: list[TunnelDefinition] = []
        self.hosts_manager = HostsManager()
        self._connect_tunnels: bool = connect_tunnels
        self.threads: list[threading.Thread] = []
        self.make_tunnels()
        if self._connect_tunnels:
            self._monitor_tunnels()

    def _get_excluded_fields(self, show_credentials: bool) -> list[str]:
        fields = ["nexthop", "nexthops", "localbindaddress", "localbindport"]
        if not show_credentials:
            fields += ["sshuser", "sshpass", "sshkeyfile"]
        return fields

    def _monitor_tunnels(self):
        def handle_sigint(signum, frame):
            self.stop_tunnels()
            print("Goodbye!")
            exit(0)

        # Register the SIGINT handler
        signal.signal(signal.SIGINT, handle_sigint)
        try:
            for thread in self.threads:
                thread.join()
            self.hosts_manager.write_changes_to_hosts_file()
            print("Tunnels started. Press 'q' to quit.")
            last_check_time = time.time()
            self._check_tunnel_status(last_check_time)
            while True:
                current_time = time.time()
                if current_time - last_check_time >= 5:
                    self._check_tunnel_status(current_time)
                    last_check_time = current_time
                
                # Check for 'q' input to quit
                if self._check_for_quit():
                    self.stop_tunnels()
                    print("Goodbye!")
                    break

        except KeyboardInterrupt:
            self.stop_tunnels()
            print("Goodbye!")

    def _check_for_quit(self):
        """Check if 'q' is pressed to quit."""
        # TODO: Split this out into a separate file.
        import sys

        if sys.platform == 'win32':
            import msvcrt
            # Check if a key has been pressed
            if msvcrt.kbhit():
                # Get the key pressed
                key = msvcrt.getch().decode('utf-8').lower()
                if key == 'q':
                    return True
        else:
            import tty
            import termios
            import select

            # Ensure sys.stdin is open
            if sys.stdin.closed:
                return False

            # Save the terminal settings
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            try:
                # Set the terminal to raw mode
                tty.setraw(sys.stdin.fileno())
                # Non-blocking input check
                i, o, e = select.select([sys.stdin], [], [], 0.1)
                if i:
                    key = sys.stdin.read(1).lower()
                    if key == 'q':
                        return True
            finally:
                # Restore the terminal settings
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        return False

    def _check_tunnel_status(self, current_time: float):
        """Checks the status of tunnels and prints the number of active tunnels and IDs of down tunnels."""
        active_tunnels = 0
        down_tunnels = TunnelCount().tunnels
        #print(f"Down tunnels: {down_tunnels}")
        for tunnel in self.tunnels:
            if tunnel.tunnel.tunnel_is_up:
                active_tunnels += 1
                if tunnel.tunnel_config.nexthop.id in down_tunnels:
                    down_tunnels.remove(tunnel.tunnel_config.nexthop.id)
        status_message = f"Active tunnels: {active_tunnels} of {TunnelCount().count}"
        if down_tunnels:
            status_message += f", {STATUS_DOWN}{', '.join(down_tunnels)}"
        else:
            status_message += f", {STATUS_ACTIVE}"
        
        # Add current time to the status message
        current_time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(current_time))
        status_message += f" as of {current_time_str}"
        
        if not self.detach:
            print(f"\r{status_message}", end="")
        else:
            logger.info(f"{status_message}")

    @property
    def config_file(self):
        """Returns the config file."""
        return self._config_file

    @config_file.setter
    def config_file(self, cf: str):
        """Sets the config file."""
        if not cf or isinstance(cf, str):
            raise ValueError("Config file must not be blank.")
        if not os.path.isfile(cf):
            raise ValueError(f"Config file {cf} does not exist.")
        self._config_file = cf

    def _get_config(self):
        """Returns the config file."""
        return yaml.load(self.config_file, Loader=yaml.FullLoader)

    def _update_bastion_address(self, nexthop_config: TunnelDefinition):
        """Updates the bastion address and port to reference the one just created."""
        nhcfg = nexthop_config
        nhcfg.host = nexthop_config.localbindaddress
        nhcfg.port = nexthop_config.localbindport
        return nhcfg

    def make_tunnels(self):
        """Creates tunnels from the config file."""
        if isinstance(self.tunnel_defs, list):
            for tunnel in self.tunnel_defs:
                self.make_tunnel(tunnel)
        elif isinstance(self.tunnel_defs, TunnelDefinition):
            self.make_tunnel(self.tunnel_defs) 

    def make_tunnel(self, this_tunnel_def: TunnelDefinition):
        """Creates a tunnel from the provided config."""
        self._add_to_processed_configs(this_tunnel_def)
        if this_tunnel_def.nexthop:
            if this_tunnel_def.nexthop.nexthops is None and this_tunnel_def.nexthop.nexthop is None:
                tunnel_thread = threading.Thread(target=self._process_nexthop, args=(this_tunnel_def,))
                tunnel_thread.start()
                self.threads.append(tunnel_thread)
            else:
                self._process_nexthop(this_tunnel_def)
        if this_tunnel_def.nexthops:
            self._process_nexthops(this_tunnel_def)

    def _process_nexthop(self, this_tunnel_def: TunnelDefinition):
        if self._connect_tunnels:
            self.tunnels.append(TunnelBuilder(this_tunnel_def))
        nexthop_config = self._update_bastion_address(this_tunnel_def.nexthop)
        self.make_tunnel(nexthop_config)

    def _process_nexthops(self, this_tunnel_def: TunnelDefinition):
        for tunnel in this_tunnel_def.nexthops:
            nexthop_config = this_tunnel_def.model_copy(update={"nexthop": tunnel, "nexthops": None})
            nexthop_config = self._update_bastion_address(nexthop_config)
            self.make_tunnel(nexthop_config)

    def _add_to_processed_configs(self, this_tunnel_def: TunnelDefinition):
        """Adds a tunnel to the processed configs."""
        if not any(this_tunnel_def.id == t["id"] for t in self.tunnel_configs):
            self.tunnel_configs.append(
                this_tunnel_def.model_dump(exclude=self._excluded_fields)
            )

    def stop_tunnels(self):
        """Stops all tunnels."""
        logger.info("\nStopping tunnels...")
        self.hosts_manager.restore_original_hosts_file()
        TunnelCount().reset()  # Reset the counter when stopping tunnels
        for this_tunnel in reversed(self.tunnels):
            try:
                print(
                    f"{STATUS_CLOSING} {this_tunnel.tunnel.local_bind_hosts[0]}:{this_tunnel.tunnel.local_bind_ports[0]}..."
                )
                this_tunnel.destroy_tunnel()
            except Exception as e:
                logger.error(f"{STATUS_FAILED} ID: {this_tunnel.tunnel_config.nexthop.id}.")
