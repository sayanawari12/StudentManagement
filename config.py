import os
from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()

# Database configuration
DB_HOST = os.environ["DB_HOST"]
DB_USER = os.environ["DB_USER"]
DB_PASSWORD = os.environ["DB_PASSWORD"]
DB_NAME = os.environ["DB_NAME"]

# Used by Flask to sign session cookies and CSRF tokens
SECRET_KEY = os.environ["SECRET_KEY"]

# Debug mode — defaults to False (safe for production).
# Set FLASK_DEBUG=true in .env for local development to get auto-reload.
# NEVER set this to true on a real deployment.
FLASK_DEBUG = os.environ.get("FLASK_DEBUG", "false").lower() == "true"

# Optional Email Configuration (Flask-Mail)
MAIL_SERVER = os.environ.get("MAIL_SERVER", None)
MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "true").lower() == "true"
MAIL_USERNAME = os.environ.get("MAIL_USERNAME", None)
MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", None)
MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", None)
