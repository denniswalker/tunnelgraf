import logging
import os
import sys

# Create main logger
logger = logging.getLogger("tunnelgraf")

# Create console handler and set level based on env var
console_handler = logging.StreamHandler(sys.stdout)

# Custom filter to suppress specific log messages
class SuppressCWDAndHostKeyFilter(logging.Filter):
    def filter(self, record):
        message = record.getMessage()
        return not (message.startswith("Current Working Directory") or "Host Key:" in message)

# Set third party loggers to use same level
paramiko_logger = logging.getLogger("paramiko")
sshtunnel_logger = logging.getLogger("sshtunnel")
sftpretty_logger = logging.getLogger("SFTPretty")
sftpretty_logger.addFilter(SuppressCWDAndHostKeyFilter())  # Add custom filter

# Get log level from environment variable, default to INFO
log_level = os.environ.get("TUNNELGRAF_LOG_LEVEL", "INFO").upper()
try:
    logger.setLevel(getattr(logging, log_level))
    sftpretty_logger.setLevel(getattr(logging, log_level))
    paramiko_logger.setLevel(getattr(logging, log_level))
    sshtunnel_logger.setLevel(getattr(logging, log_level))
except AttributeError:
    logger.setLevel(logging.INFO)
    sftpretty_logger.setLevel(logging.INFO)
    paramiko_logger.setLevel(logging.INFO)
    sshtunnel_logger.setLevel(logging.INFO)
    logger.warning(f"Invalid log level {log_level}, defaulting to INFO")

# Create formatter
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)

# Add console handler to main logger
logger.addHandler(console_handler)

# Hide output from paramiko and sshtunnel
paramiko_logger.addHandler(logging.NullHandler())
sshtunnel_logger.addHandler(logging.NullHandler())
sftpretty_logger.addHandler(logging.NullHandler())
