# ANSI Color Codes
COLOR_GREEN = "\033[92m"
COLOR_RED = "\033[91m"
COLOR_YELLOW = "\033[93m"
COLOR_RESET = "\033[0m"

# Status Messages
STATUS_ACTIVE = f"{COLOR_GREEN}All tunnels are active {COLOR_RESET}"
STATUS_DOWN = f"{COLOR_RED}Down tunnels: {COLOR_RESET}"
STATUS_CLOSING = f"{COLOR_GREEN}Closing tunnel{COLOR_RESET}"
STATUS_FAILED = f"{COLOR_RED}Failed to stop tunnel{COLOR_RESET}" 