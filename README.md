# Student Management System

A Flask + Jinja2 + MySQL application for managing student records, attendance, and fee collections with role-based access control.

## Environment setup

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
2. Open `.env` and fill in your real MySQL credentials (`DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`) and a secure `SECRET_KEY`.
3. Install dependencies and run the application:
   ```bash
   pip install -r requirements.txt
   python app.py
   ```

> **Security Note:** The initial development password (`root123`) was previously committed to this repository's git history in earlier commits. It is strongly recommended to change the actual MySQL root password used for your database server, as removing secrets from `config.py` does not purge them from past commit history.
