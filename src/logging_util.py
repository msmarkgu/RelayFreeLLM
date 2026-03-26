import logging
import os
import gzip
import shutil
from datetime import datetime, timedelta
from logging.handlers import TimedRotatingFileHandler


class CompressedTimedRotatingFileHandler(TimedRotatingFileHandler):
    """
    Extends TimedRotatingFileHandler to:
      - Compress rotated log files (.gz)
      - Move logs older than retention days to an archive folder
    """

    def __init__(self, filename, when="midnight", interval=1, backupCount=7,
                 encoding="utf-8", delay=False, utc=False, archive_dir=None):
        super().__init__(filename, when, interval, backupCount, encoding, delay, utc)
        self.archive_dir = archive_dir or os.path.join(os.path.dirname(filename), "archive")
        os.makedirs(self.archive_dir, exist_ok=True)

    def rotate(self, source, dest):
        """Compress the rotated log file and move old logs to archive."""
        # Rename the current log file
        super().rotate(source, dest)

        # Compress the rotated file
        if os.path.exists(dest):
            compressed = f"{dest}.gz"
            with open(dest, "rb") as f_in, gzip.open(compressed, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
            os.remove(dest)

        # Move old compressed logs to archive folder
        self._archive_old_logs()

    def _archive_old_logs(self):
        """Move logs older than retention period to archive folder."""
        log_dir = os.path.dirname(self.baseFilename)
        cutoff = datetime.now() - timedelta(days=self.backupCount)

        for file in os.listdir(log_dir):
            path = os.path.join(log_dir, file)
            if not os.path.isfile(path):
                continue
            if not file.endswith(".gz"):
                continue

            # Get modification time
            mtime = datetime.fromtimestamp(os.path.getmtime(path))
            if mtime < cutoff:
                shutil.move(path, os.path.join(self.archive_dir, file))


class ProjectLogger:
    """
    Centralized logger setup for the entire project.
    Each module/class can call get_logger(__name__) to get its own named logger.
    """

    _is_configured = False

    @classmethod
    def configure(cls, project_name: str, log_dir: str = "logs",
                  level=logging.INFO, retention_days: int = 7):
        """
        Configure the logging system for the whole project.
        Rotates daily, compresses rotated logs, and archives logs older than retention_days.
        """
        if cls._is_configured:
            return  # Prevent reconfiguration

        os.makedirs(log_dir, exist_ok=True)
        log_date = datetime.now().strftime("%Y-%m-%d")
        log_path = os.path.join(log_dir, f"{project_name}_{log_date}.log")

        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)

        # Rotating + compressing file handler
        file_handler = CompressedTimedRotatingFileHandler(
            log_path,
            when="midnight",
            interval=1,
            backupCount=retention_days,
            encoding="utf-8",
            utc=False,
            archive_dir=os.path.join(log_dir, "archive")
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)

        # Root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(level)
        root_logger.addHandler(console_handler)
        root_logger.addHandler(file_handler)

        cls._is_configured = True

    @staticmethod
    def get_logger(name: str) -> logging.Logger:
        """Return a module/class-specific logger by name."""
        return logging.getLogger(name)
