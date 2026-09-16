import os
from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()


def _parse_bool(val, default=False):
    """Safely parse environment variable string into a boolean."""
    if val is None:
        return default
    return str(val).strip().lower() in {"true", "1", "yes", "on"}


# Database configuration
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_USER = os.environ.get("DB_USER", "root")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_NAME = os.environ.get("DB_NAME", "student_management")

# Used by Flask to sign session cookies and CSRF tokens
SECRET_KEY = os.environ.get("SECRET_KEY", "").strip()
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY environment variable is required and must not be empty.")

# Debug mode — defaults to False (safe for production).
# Set FLASK_DEBUG=true in .env for local development to get auto-reload.
# NEVER set this to true on a real deployment.
FLASK_DEBUG = _parse_bool(os.environ.get("FLASK_DEBUG"), default=False)

# Configurable public base URL for ID Card QR verification scans
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")

# Optional Email Configuration (Flask-Mail)
MAIL_SERVER = os.environ.get("MAIL_SERVER", None)
try:
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
except (ValueError, TypeError):
    MAIL_PORT = 587

MAIL_USE_TLS = _parse_bool(os.environ.get("MAIL_USE_TLS"), default=True)
MAIL_USERNAME = os.environ.get("MAIL_USERNAME", None)
MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", None)
MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", None)



