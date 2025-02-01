class TunnelCount:
    _instance = None
    _count = 0
    _tunnels = []

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TunnelCount, cls).__new__(cls)
        return cls._instance
    
    @property
    def tunnels(self):
        # Deduplicate tunnels by converting to a set and back to a list
        return list(set(self._tunnels[:-1]))

    @property
    def count(self):
        return len(self.tunnels)

    def add_tunnel(self, tunnel):
        self._tunnels.append(tunnel)

    def reset(self):
        self._tunnels = [] 