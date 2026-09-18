import logging
import os
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone


LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "greenpulse.log")


class UTCFormatter(logging.Formatter):
    """Format log timestamps as UTC ISO-8601 timestamps."""

    converter = lambda self, timestamp: datetime.fromtimestamp(
        timestamp, tz=timezone.utc
    )

    def formatTime(self, record, datefmt=None):
        dt = self.converter(record.created)

        if datefmt:
            return dt.strftime(datefmt)

        return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def setup_logging():
    """Configure console + rotating file logging."""

    os.makedirs(LOG_DIR, exist_ok=True)

    logger = logging.getLogger("greenpulse")
    logger.setLevel(logging.INFO)

    # Prevent duplicate handlers if setup_logging() is called more than once.
    if logger.handlers:
        return logger

    formatter = UTCFormatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    # Console logging
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    # File logging
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    logger.info("GreenPulse logging initialized")

    return logger


logger = setup_logging()