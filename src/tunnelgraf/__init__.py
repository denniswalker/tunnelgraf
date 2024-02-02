from .tunnels import Tunnels
import sys


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] == "--help":
        print("Usage: tunnelgraf <config_file>")
        sys.exit(0)
    Tunnels(sys.argv[1])


if __name__ == "__main__":
    main()
