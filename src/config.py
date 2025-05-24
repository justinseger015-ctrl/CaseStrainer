import os
import json
from dotenv import load_dotenv
import logging
from typing import Optional

# Optional Sentry integration
try:
    import sentry_sdk
except ImportError:
    sentry_sdk = None

# Load environment variables from .env if present
load_dotenv()

# Load config.json once
CONFIG_JSON_PATH = os.path.join(os.path.dirname(__file__), "..", "config.json")
try:
    with open(CONFIG_JSON_PATH, "r") as f:
        CONFIG_JSON = json.load(f)
except Exception:
    CONFIG_JSON = {}


def get_config_value(key, default=None):
    # Try environment variable (case-sensitive)
    value = os.environ.get(key)
    if value is not None and value != "":
        return value
    # Try config.json (case-sensitive, then lower-case fallback)
    if key in CONFIG_JSON:
        return CONFIG_JSON[key]
    if key.lower() in CONFIG_JSON:
        return CONFIG_JSON[key.lower()]
    return default


# General app config (use get_config_value for all relevant keys)
SECRET_KEY: str = get_config_value("SECRET_KEY", "devkey")
DATABASE_FILE: str = get_config_value("DATABASE_FILE", "citations.db")
UPLOAD_FOLDER: str = get_config_value("UPLOAD_FOLDER", "uploads")
ALLOWED_EXTENSIONS = set(
    get_config_value("ALLOWED_EXTENSIONS", ["txt", "pdf", "docx", "doc"])
)
COURTLISTENER_API_URL: str = get_config_value(
    "COURTLISTENER_API_URL", "https://www.courtlistener.com/api/rest/v4/opinions/"
)
COURTLISTENER_API_KEY: str = get_config_value("COURTLISTENER_API_KEY", "")
LANGSEARCH_API_KEY: str = get_config_value("LANGSEARCH_API_KEY", "")
SESSION_TYPE: str = get_config_value("SESSION_TYPE", "filesystem")
SESSION_FILE_DIR: str = get_config_value(
    "SESSION_FILE_DIR",
    os.path.join(os.path.dirname(__file__), "..", "casestrainer_sessions"),
)
SESSION_COOKIE_PATH: str = get_config_value("SESSION_COOKIE_PATH", "/casestrainer/")
SENTRY_DSN: Optional[str] = get_config_value("SENTRY_DSN")

if SENTRY_DSN and sentry_sdk:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        traces_sample_rate=0.1,  # Adjust as needed
        environment=os.environ.get("ENVIRONMENT", "production"),
    )


def configure_logging(log_level: int = logging.INFO) -> None:
    """
    Configure logging for the CaseStrainer application.
    Uses ConcurrentRotatingFileHandler for robust log rotation on Windows (requires concurrent-log-handler package).
    Creates a 'logs' directory if it does not exist and sets up file and stream handlers.
    Args:
        log_level (int): Logging level (default: logging.INFO)
    """
    import sys

    # Use ConcurrentRotatingFileHandler for robust log rotation on Windows
    try:
        from concurrent_log_handler import ConcurrentRotatingFileHandler

        file_handler = ConcurrentRotatingFileHandler(
            "logs/casestrainer.log", maxBytes=5 * 1024 * 1024, backupCount=5
        )
    except ImportError:
        file_handler = logging.FileHandler("logs/casestrainer.log")
    try:
        from colorama import init, Fore, Style

        init()
        COLORAMA_AVAILABLE = True
    except ImportError:
        COLORAMA_AVAILABLE = False

    os.makedirs("logs", exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(log_level)

    # Stream handler (console)
    class ColorizingStreamHandler(logging.StreamHandler):
        def emit(self, record):
            try:
                msg = self.format(record)
                if COLORAMA_AVAILABLE:
                    if record.levelno >= logging.ERROR:
                        msg = f"{Fore.RED}{msg}{Style.RESET_ALL}"
                    elif record.levelno == logging.WARNING:
                        msg = f"{Fore.YELLOW}{msg}{Style.RESET_ALL}"
                    elif record.levelno == logging.INFO:
                        msg = f"{Fore.CYAN}{msg}{Style.RESET_ALL}"
                self.stream.write(msg + self.terminator)
                self.flush()
            except Exception:
                self.handleError(record)

    stream_handler = ColorizingStreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(log_level)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()
    root_logger.addHandler(file_handler)
    root_logger.addHandler(stream_handler)
