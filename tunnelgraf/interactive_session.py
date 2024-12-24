import paramiko
from pydantic import BaseModel, Field, PrivateAttr
import os
import sys
import select
import termios
import tty
from typing import Optional
import signal
import fcntl
import struct

class InteractiveSSHSession(BaseModel):
    host: str
    user: str
    password: Optional[str] = None
    identityfile: Optional[str] = None
    port: int = Field(default=22)

    # Define client as a private attribute
    _client: paramiko.SSHClient = PrivateAttr()

    def __init__(self, **data):
        super().__init__(**data)
        self._client = paramiko.SSHClient()  # Use the private attribute
        self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        # Validate that at least one of password or identityfile is provided
        if not self.password and not self.identityfile:
            raise ValueError("Either password or identityfile must be provided.")

    def connect(self):
        try:
            # Connect to the SSH server using identityfile if available, otherwise use password
            if self.identityfile:
                self._client.connect(self.host, self.port, self.user, key_filename=self.identityfile)
            else:
                self._client.connect(self.host, self.port, self.user, self.password)
            print(f"Connected to {self.host}")
            return True
        except Exception as e:
            print(f"Error connecting to {self.host}: {e}")
            return False

    def start_interactive_session(self):
        if not self.connect():
            return

        try:
            chan = self._open_shell()
            old_tty = self._set_terminal_raw_mode()
            self._resize_pty(chan)  # Initial resize
            signal.signal(signal.SIGWINCH, lambda signum, frame: self._resize_pty(chan))  # Handle terminal resize
            try:
                self._interactive_loop(chan)
            finally:
                self._restore_terminal_settings(old_tty)
        except Exception as e:
            print(f"Error during interactive session: {e}")
        finally:
            self._client.close()

    def _open_shell(self):
        # Open a session and request a pseudo-terminal
        chan = self._client.invoke_shell()
        print("Interactive shell session opened.")
        return chan

    def _set_terminal_raw_mode(self):
        # Save the original terminal settings and set to raw mode
        old_tty = termios.tcgetattr(sys.stdin)
        tty.setraw(sys.stdin.fileno())
        return old_tty

    def _restore_terminal_settings(self, old_tty):
        # Restore the original terminal settings
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_tty)

    def _resize_pty(self, chan):
        # Correct the buffer size for the ioctl call
        s = struct.pack('HHHH', 0, 0, 0, 0)
        size = fcntl.ioctl(sys.stdin, termios.TIOCGWINSZ, s)
        rows, cols, _, _ = struct.unpack('HHHH', size)
        chan.resize_pty(width=cols, height=rows)

    def _interactive_loop(self, chan):
        chan.settimeout(0.0)
        try:
            while True:
                # Wait for input from the user or server
                readable, _, _ = select.select([sys.stdin, chan], [], [])
                if sys.stdin in readable:
                    # Send user input to the server
                    data = os.read(sys.stdin.fileno(), 1024)
                    if data:
                        # Check for an exit command
                        if data.strip() == b'exit':
                            print("\nExiting session.")
                            break
                        chan.send(data)
                if chan in readable:
                    # Read data from the server and print it
                    data = chan.recv(1024)
                    if not data:
                        print("\nConnection closed.")
                        break
                    sys.stdout.write(data.decode())
                    sys.stdout.flush()
        except KeyboardInterrupt:
            print("\nSession interrupted by user.")
