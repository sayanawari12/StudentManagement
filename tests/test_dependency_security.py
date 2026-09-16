"""
tests/test_dependency_security.py — Dependency & Supply-Chain Security Tests

Verifies:
1. Requirements manifest integrity and exact version pinning (==).
2. Required security-sensitive Python packages (Flask, Flask-WTF, Flask-Limiter, PyOTP, ReportLab).
3. GitHub Actions workflow security (least-privilege permissions: contents: read).
4. Docker build context isolation (.dockerignore excludes .env, .git, venv, tests).
5. Repository environment isolation (.env is excluded by .gitignore).
"""

import os
import pytest
import app as flask_app


# ---------------------------------------------------------------------------
# 1. Dependency Manifest Integrity & Pinning
# ---------------------------------------------------------------------------

def test_requirements_txt_exists_and_pinned():
    req_path = os.path.join(flask_app.app.root_path, "requirements.txt")
    assert os.path.exists(req_path), "requirements.txt must exist"
    
    with open(req_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        
    assert len(lines) > 0, "requirements.txt must not be empty"
    for line in lines:
        assert "==" in line, f"Requirement {line!r} must use exact version pinning (==)"


def test_requirements_dev_txt_exists_and_pinned():
    req_dev_path = os.path.join(flask_app.app.root_path, "requirements-dev.txt")
    assert os.path.exists(req_dev_path), "requirements-dev.txt must exist"

    with open(req_dev_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    assert len(lines) > 0, "requirements-dev.txt must not be empty"
    for line in lines:
        assert "==" in line, f"Dev requirement {line!r} must use exact version pinning (==)"


def test_core_security_packages_declared():
    req_path = os.path.join(flask_app.app.root_path, "requirements.txt")
    with open(req_path, "r", encoding="utf-8") as f:
        content = f.read().lower()

    required_packages = ["flask", "flask-wtf", "flask-limiter", "pyotp", "reportlab"]
    for pkg in required_packages:
        assert pkg in content, f"Essential security package {pkg!r} missing from requirements.txt"


# ---------------------------------------------------------------------------
# 2. GitHub Actions Workflow Least Privilege
# ---------------------------------------------------------------------------

def test_github_actions_permissions_least_privilege():
    ci_path = os.path.join(flask_app.app.root_path, ".github", "workflows", "ci.yml")
    assert os.path.exists(ci_path), ".github/workflows/ci.yml must exist"

    with open(ci_path, "r", encoding="utf-8") as f:
        wf_content = f.read()

    # Verify least privilege permissions are declared in workflow
    assert "permissions:" in wf_content, "CI workflow must specify an explicit permissions block"
    assert "contents: read" in wf_content, "CI workflow must grant least privilege (contents: read)"


# ---------------------------------------------------------------------------
# 3. Docker & Repository Secret Isolation
# ---------------------------------------------------------------------------

def test_dockerignore_excludes_sensitive_paths():
    dignore_path = os.path.join(flask_app.app.root_path, ".dockerignore")
    assert os.path.exists(dignore_path), ".dockerignore must exist"

    with open(dignore_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    assert ".env" in lines, ".dockerignore must exclude .env"
    assert ".git" in lines, ".dockerignore must exclude .git"
    assert "tests/" in lines, ".dockerignore must exclude tests/"


def test_gitignore_excludes_env_files():
    gitignore_path = os.path.join(flask_app.app.root_path, ".gitignore")
    assert os.path.exists(gitignore_path), ".gitignore must exist"

    with open(gitignore_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    assert ".env" in lines, ".gitignore must exclude .env"
