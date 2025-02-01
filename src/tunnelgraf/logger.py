import logging
import os
import sys

# Create logger
logger = logging.getLogger("tunnelgraf")

# Create console handler and set level based on env var
console_handler = logging.StreamHandler(sys.stdout)

# Set third party loggers to use same level
paramiko_logger = logging.getLogger("paramiko")
paramiko_logger.setLevel(logging.DEBUG)
sshtunnel_logger = logging.getLogger("sshtunnel")
sshtunnel_logger.setLevel(logging.DEBUG)

# Hide output from paramiko and sshtunnel
paramiko_logger.addHandler(logging.NullHandler())
sshtunnel_logger.addHandler(logging.NullHandler())

# Get log level from environment variable, default to WARNING
log_level = os.environ.get("TUNNELGRAF_LOG_LEVEL", "INFO").upper()
try:
    logger.setLevel(getattr(logging, log_level))
except AttributeError:
    logger.setLevel(logging.INFO)
    logger.warning(f"Invalid log level {log_level}, defaulting to INFO")

# Create formatter
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)

# Add console handler to logger
logger.addHandler(console_handler)
