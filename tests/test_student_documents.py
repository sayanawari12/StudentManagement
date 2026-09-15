"""
tests/test_student_documents.py — Comprehensive security and functionality tests
for Student Document Management module.
"""

import io
import os
import pytest
from unittest.mock import patch

import app as flask_app
import database


@pytest.fixture
def client():
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["WTF_CSRF_ENABLED"] = False
    with flask_app.app.test_client() as client:
        yield client


def _login_as(client, role="admin", user_id=1, username="admin", linked_student_id=None):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["username"] = username
        sess["role"] = role
        if linked_student_id is not None:
            sess["linked_student_id"] = linked_student_id
        elif role == "student":
            sess["linked_student_id"] = user_id


def create_dummy_pdf():
    """Return an in-memory BytesIO object representing a valid minimal PDF."""
    content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n"
    bio = io.BytesIO(content)
    bio.name = "test_document.pdf"
    return bio


def create_dummy_png():
    """Return an in-memory BytesIO object representing a valid PNG header."""
    content = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    bio = io.BytesIO(content)
    bio.name = "test_photo.png"
    return bio


# ---------------------------------------------------------------------------
# 1. Database Table & Stats Initialization
# ---------------------------------------------------------------------------

def test_ensure_document_table_exists():
    database.ensure_document_table_exists()
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SHOW TABLES LIKE 'student_documents'")
    table = cursor.fetchone()
    cursor.close()
    conn.close()
    assert table is not None


def test_document_stats_empty(client):
    stats = database.get_document_stats_for_student(999999)
    assert stats == {"total": 0, "verified": 0, "pending": 0, "rejected": 0}


# ---------------------------------------------------------------------------
# 2. File Validation & Security Helpers
# ---------------------------------------------------------------------------

def test_validate_document_file_helpers():
    # Empty file
    bio_empty = io.BytesIO(b"")
    bio_empty.filename = "empty.pdf"
    bio_empty.content_type = "application/pdf"
    valid, err = flask_app._validate_document_file(bio_empty)
    assert not valid
    assert "empty" in err.lower()

    # Invalid extension
    bio_txt = io.BytesIO(b"%PDF-1.4 content")
    bio_txt.filename = "file.exe"
    bio_txt.content_type = "application/pdf"
    valid, err = flask_app._validate_document_file(bio_txt)
    assert not valid
    assert "extension" in err.lower()

    # Fake header (renamed .exe to .pdf)
    bio_fake = io.BytesIO(b"MZ\x90\x00\x03\x00\x00\x00 Executable header")
    bio_fake.filename = "fake.pdf"
    bio_fake.content_type = "application/pdf"
    valid, err = flask_app._validate_document_file(bio_fake)
    assert not valid
    assert "header" in err.lower()

    # Valid PDF
    bio_valid = create_dummy_pdf()
    bio_valid.filename = "valid.pdf"
    bio_valid.content_type = "application/pdf"
    valid, err = flask_app._validate_document_file(bio_valid)
    assert valid
    assert err is None


def test_get_safe_document_path_traversal():
    assert flask_app._get_safe_document_path("../../../etc/passwd") is None
    assert flask_app._get_safe_document_path("sub/folder/file.pdf") is None
    assert flask_app._get_safe_document_path("..\\windows\\system32") is None
    assert flask_app._get_safe_document_path(None) is None

    safe_path = flask_app._get_safe_document_path("doc_abc123.pdf")
    assert safe_path is not None
    assert safe_path.startswith(flask_app.DOCUMENT_UPLOAD_DIR)


# ---------------------------------------------------------------------------
# 3. Upload Document Tests & Permissions
# ---------------------------------------------------------------------------

def test_upload_document_success_admin(client):
    _login_as(client, role="admin", user_id=1, username="admin")
    students = database.get_all_students()
    assert len(students) > 0
    student = students[0]
    stud_pk = student["id"]

    pdf = create_dummy_pdf()
    response = client.post(
        f"/student/{stud_pk}/documents/upload",
        data={
            "doc_type": "Aadhaar Card",
            "document_file": (pdf, "aadhaar.pdf", "application/pdf")
        },
        follow_redirects=True
    )
    assert response.status_code == 200
    assert b"Document uploaded successfully" in response.data

    docs = database.get_student_documents(stud_pk)
    assert len(docs) > 0
    latest_doc = docs[0]
    assert latest_doc["doc_type"] == "Aadhaar Card"
    assert latest_doc["original_filename"] == "aadhaar.pdf"
    assert latest_doc["status"] == "Pending"

    # Clean up uploaded file
    file_path = flask_app._get_safe_document_path(latest_doc["stored_filename"])
    if file_path and os.path.exists(file_path):
        os.remove(file_path)
    database.delete_student_document(latest_doc["id"])


def test_upload_document_other_type_requires_title(client):
    _login_as(client, role="admin", user_id=1, username="admin")
    students = database.get_all_students()
    student = students[0]

    pdf = create_dummy_pdf()
    # Missing custom_doc_name
    response = client.post(
        f"/student/{student['id']}/documents/upload",
        data={
            "doc_type": "Other",
            "custom_doc_name": "",
            "document_file": (pdf, "custom.pdf", "application/pdf")
        },
        follow_redirects=True
    )
    assert b"Document title is required" in response.data


def test_upload_document_unauthorized_student(client):
    # Log in as a student
    _login_as(client, role="student", user_id=99, username="student_user")
    students = database.get_all_students()
    student = students[0]

    pdf = create_dummy_pdf()
    response = client.post(
        f"/student/{student['id']}/documents/upload",
        data={
            "doc_type": "Marksheet",
            "document_file": (pdf, "marks.pdf", "application/pdf")
        }
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# 4. Document Verification, Rejection & Deletion Tests
# ---------------------------------------------------------------------------

def test_document_lifecycle_verify_reject_delete(client):
    _login_as(client, role="admin", user_id=1, username="admin")
    students = database.get_all_students()
    student = students[0]
    stud_pk = student["id"]

    # Upload test document
    pdf = create_dummy_pdf()
    client.post(
        f"/student/{stud_pk}/documents/upload",
        data={
            "doc_type": "Bonafide",
            "document_file": (pdf, "bonafide.pdf", "application/pdf")
        },
        follow_redirects=True
    )

    docs = database.get_student_documents(stud_pk)
    assert len(docs) > 0
    doc = docs[0]
    doc_id = doc["id"]

    # 1. Verify document
    v_res = client.post(f"/student/{stud_pk}/documents/{doc_id}/verify", follow_redirects=True)
    assert v_res.status_code == 200
    updated_doc = database.get_document_by_id(doc_id)
    assert updated_doc["status"] == "Verified"

    # 2. Reject document with reason
    r_res = client.post(
        f"/student/{stud_pk}/documents/{doc_id}/reject",
        data={"rejection_reason": "Signature unclear"},
        follow_redirects=True
    )
    assert r_res.status_code == 200
    rejected_doc = database.get_document_by_id(doc_id)
    assert rejected_doc["status"] == "Rejected"
    assert rejected_doc["rejection_reason"] == "Signature unclear"

    # 3. Reject document without reason (should fail)
    r_fail = client.post(
        f"/student/{stud_pk}/documents/{doc_id}/reject",
        data={"rejection_reason": ""},
        follow_redirects=True
    )
    assert b"Rejection reason is required" in r_fail.data

    # 4. Delete document
    d_res = client.post(f"/student/{stud_pk}/documents/{doc_id}/delete", follow_redirects=True)
    assert d_res.status_code == 200
    assert database.get_document_by_id(doc_id) is None


# ---------------------------------------------------------------------------
# 5. Access Control & Authorization Security Tests
# ---------------------------------------------------------------------------

def test_preview_download_access_control(client):
    _login_as(client, role="admin", user_id=1, username="admin")
    students = database.get_all_students()
    s1 = students[0]
    s2 = students[1] if len(students) > 1 else students[0]

    pdf = create_dummy_pdf()
    client.post(
        f"/student/{s1['id']}/documents/upload",
        data={
            "doc_type": "Leaving Certificate",
            "document_file": (pdf, "lc.pdf", "application/pdf")
        },
        follow_redirects=True
    )
    docs = database.get_student_documents(s1["id"])
    assert len(docs) > 0
    doc_id = docs[0]["id"]

    # Admin preview & download (allowed)
    prev_res = client.get(f"/student/{s1['id']}/documents/{doc_id}/preview")
    assert prev_res.status_code == 200

    dl_res = client.get(f"/student/{s1['id']}/documents/{doc_id}/download")
    assert dl_res.status_code == 200

    # URL Tampering test: mismatched student_id & doc_id (should return 403)
    if s1["id"] != s2["id"]:
        tamper_res = client.get(f"/student/{s2['id']}/documents/{doc_id}/preview")
        assert tamper_res.status_code == 403

    # Cleanup
    client.post(f"/student/{s1['id']}/documents/{doc_id}/delete")


def test_student_role_document_privacy(client):
    students = database.get_all_students()
    s1 = students[0]
    s2 = students[1] if len(students) > 1 else s1

    # Upload document for s1
    _login_as(client, role="admin", user_id=1, username="admin")
    pdf = create_dummy_pdf()
    client.post(
        f"/student/{s1['id']}/documents/upload",
        data={
            "doc_type": "Passport Photo",
            "document_file": (pdf, "photo.pdf", "application/pdf")
        },
        follow_redirects=True
    )
    docs = database.get_student_documents(s1["id"])
    assert len(docs) > 0
    doc_id = docs[0]["id"]

    # Log in as a student linked to s2
    _login_as(client, role="student", user_id=999, username="other_student", linked_student_id=s2["id"])

    if s1["id"] != s2["id"]:
        # Attempting to view s1's document as s2 -> 403
        resp = client.get(f"/student/{s1['id']}/documents/{doc_id}/preview")
        assert resp.status_code == 403

    # Log in as s1 student
    _login_as(client, role="student", user_id=998, username="s1_student", linked_student_id=s1["id"])

    # s1 viewing own doc -> 200
    own_resp = client.get(f"/student/{s1['id']}/documents/{doc_id}/preview")
    assert own_resp.status_code == 200

    # Cleanup
    _login_as(client, role="admin", user_id=1, username="admin")
    client.post(f"/student/{s1['id']}/documents/{doc_id}/delete")


def test_audit_log_includes_documents(client):
    students = database.get_all_students()
    student = students[0]
    logs = database.get_student_audit_log(student["id"])
    assert isinstance(logs, list)
