from abc import ABC, abstractmethod
from tunnelgraf.tunnel_definition import TunnelDefinition

class TunnelInterface(ABC):
    """Interface for tunnel operations.

    Attributes:
        tunnel_definition (TunnelDefinition): Required attribute for tunnel configuration.
    """

    def __init__(self, tunnel_def: TunnelDefinition):
        """Initialize with a tunnel definition."""
        self.tunnel_def = tunnel_def

    @abstractmethod
    def start_tunnel(self):
        """Starts the tunnel."""
        pass

    @abstractmethod
    def destroy_tunnel(self):
        """Destroys the tunnel."""
        pass 