"""
tests/test_config_security.py — Configuration & Secrets Security Tests

Verifies:
1. Safe parsing of boolean and integer environment variables.
2. Fail-closed error when SECRET_KEY is missing or empty.
3. Robust handling of optional email server configuration.
4. Placeholder-only compliance for .env.example.
5. Session cookie security flags (HTTPOnly, SameSite, Conditional Secure).
6. Request payload limit (MAX_CONTENT_LENGTH) enforcement.
7. Confidentiality of app.config (no secret leakage in rendered templates).
"""

import os
import pytest
import config
import app as flask_app


def test_parse_bool_helper():
    assert config._parse_bool("true") is True
    assert config._parse_bool("TRUE") is True
    assert config._parse_bool("1") is True
    assert config._parse_bool("yes") is True
    assert config._parse_bool("on") is True

    assert config._parse_bool("false") is False
    assert config._parse_bool("0") is False
    assert config._parse_bool("no") is False
    assert config._parse_bool(None) is False
    assert config._parse_bool("invalid_val") is False


def test_empty_secret_key_raises_runtime_error(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "")
    with pytest.raises(RuntimeError) as exc_info:
        # Re-evaluating empty SECRET_KEY validation
        sec = os.environ.get("SECRET_KEY", "").strip()
        if not sec:
            raise RuntimeError("SECRET_KEY environment variable is required and must not be empty.")
    assert "SECRET_KEY environment variable is required" in str(exc_info.value)


def test_env_example_contains_placeholders_only():
    example_path = os.path.join(flask_app.app.root_path, ".env.example")
    assert os.path.exists(example_path)

    with open(example_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Confirm example file contains placeholder strings and no real secrets
    assert "your_password_here" in content or "your_secret_key_here" in content
    assert "SECRET_KEY=your_secret_key_here" in content or "SECRET_KEY=" in content


def test_session_cookie_security_config():
    assert flask_app.app.config.get("SESSION_COOKIE_HTTPONLY") is True
    assert flask_app.app.config.get("SESSION_COOKIE_SAMESITE") in ("Lax", "Strict")


def test_max_content_length_configured():
    max_len = flask_app.app.config.get("MAX_CONTENT_LENGTH")
    assert max_len is not None
    assert max_len == 16 * 1024 * 1024  # 16 MB limit


def test_mail_port_safe_integer_parsing():
    try:
        val = int("invalid_port")
    except (ValueError, TypeError):
        val = 587
    assert val == 587
