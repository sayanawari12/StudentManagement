"""
tests/test_file_security.py — Deep File and Path Security Audit Tests

Verifies:
1. Path traversal protection (../, ..\\, %2e%2e%2f, absolute paths, UNC paths)
2. Safe path helper behavior (_get_safe_document_path)
3. Cross-student document download/preview authorization
4. Arbitrary file read & deletion prevention
5. Malicious upload filenames & extensions (executable, double extensions, control chars)
6. MIME & magic-byte validation
7. Oversized file upload prevention
8. Static directory isolation (uploads are outside static/)
9. Non-existent document file handling
"""

import io
import os
import pytest
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
    content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n"
    bio = io.BytesIO(content)
    bio.name = "test.pdf"
    bio.filename = "test.pdf"
    bio.content_type = "application/pdf"
    return bio


# ---------------------------------------------------------------------------
# 1. Safe Path Helper Unit Tests
# ---------------------------------------------------------------------------

def test_safe_document_path_helper_valid():
    filename = "doc_1234567890abcdef1234567890abcdef.pdf"
    res = flask_app._get_safe_document_path(filename)
    assert res is not None
    assert os.path.basename(res) == filename
    assert res.startswith(flask_app.DOCUMENT_UPLOAD_DIR)


def test_safe_document_path_helper_traversal_payloads():
    traversal_inputs = [
        "../secret.txt",
        "..\\secret.txt",
        "....//....//secret.txt",
        "/etc/passwd",
        "C:\\Windows\\system32\\cmd.exe",
        "\\\\server\\share\\file.txt",
        "doc/../../secret.txt",
        "doc\\..\\secret.txt",
        "%2e%2e%2fsecret.txt",
        "",
        None,
    ]
    for inp in traversal_inputs:
        res = flask_app._get_safe_document_path(inp)
        assert res is None, f"Expected None for unsafe path input: {inp!r}, got {res!r}"


# ---------------------------------------------------------------------------
# 2. Upload Validation Tests (Malicious Extensions, MIME & Magic Bytes)
# ---------------------------------------------------------------------------

def test_upload_executable_extension_rejected():
    exec_files = [
        ("test.php", "application/x-php", b"<?php echo 1; ?>"),
        ("test.py", "text/x-python", b"print('hello')"),
        ("test.exe", "application/octet-stream", b"MZ12345"),
        ("test.sh", "application/x-sh", b"#!/bin/bash"),
        ("test.html", "text/html", b"<html></html>"),
        ("file.jpg.php", "image/jpeg", b"\xff\xd8\xff\xe0\x00\x10JFIF"),
        ("file.php.jpg", "text/x-php", b"\xff\xd8\xff\xe0\x00\x10JFIF"),
    ]
    for fname, mime, content in exec_files:
        bio = io.BytesIO(content)
        bio.name = fname
        bio.filename = fname
        bio.content_type = mime
        valid, err = flask_app._validate_document_file(bio)
        assert not valid, f"Expected validation failure for executable upload {fname!r}"


def test_upload_magic_byte_mismatch_rejected():
    # PDF extension but JPEG header
    bio = io.BytesIO(b"\xff\xd8\xff\xe0\x00\x10JFIF")
    bio.name = "fake.pdf"
    bio.filename = "fake.pdf"
    bio.content_type = "application/pdf"
    valid, err = flask_app._validate_document_file(bio)
    assert not valid
    assert "header" in err.lower() or "signature" in err.lower() or "mime" in err.lower()


def test_upload_oversized_file_rejected():
    # 6MB file (> 5MB limit)
    large_content = b"%PDF-1.4\n" + b"A" * (6 * 1024 * 1024)
    bio = io.BytesIO(large_content)
    bio.name = "large.pdf"
    bio.filename = "large.pdf"
    bio.content_type = "application/pdf"
    valid, err = flask_app._validate_document_file(bio)
    assert not valid
    assert "exceeds maximum limit" in err


# ---------------------------------------------------------------------------
# 3. Cross-Student Document Access & Authorization
# ---------------------------------------------------------------------------

def test_unauthorized_document_preview_rejected(client):
    # Unauthenticated user access to document preview
    response = client.get("/student/1/documents/1/preview")
    assert response.status_code in (302, 401, 403)


def test_cross_student_document_download_blocked(client):
    students = database.get_all_students()
    assert len(students) >= 2, "At least 2 students required for cross-student security test"
    s1 = students[0]
    s2 = students[1]

    # Student 1 trying to access Student 2's document preview/download
    _login_as(client, role="student", user_id=s1["id"], linked_student_id=s1["id"])
    
    doc_id = database.insert_student_document(
        stud_id=s2["id"],
        doc_type="Marksheet",
        custom_doc_name=None,
        original_filename="s2_doc.pdf",
        stored_filename="doc_s2_test.pdf",
        mime_type="application/pdf",
        file_size_bytes=100,
        uploaded_by=1
    )

    try:
        # Requesting student 2's doc as student 1 -> must return 403 Forbidden
        res = client.get(f"/student/{s2['id']}/documents/{doc_id}/download")
        assert res.status_code == 403

        res_prev = client.get(f"/student/{s2['id']}/documents/{doc_id}/preview")
        assert res_prev.status_code == 403
    finally:
        # Cleanup
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM student_documents WHERE id = %s", (doc_id,))
        conn.commit()
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# 4. Arbitrary File Read & Missing File Handling
# ---------------------------------------------------------------------------

def test_preview_missing_file_returns_404(client):
    _login_as(client, role="admin", user_id=1)
    
    doc_id = database.insert_student_document(
        stud_id=1,
        doc_type="Marksheet",
        custom_doc_name=None,
        original_filename="missing.pdf",
        stored_filename="doc_nonexistent_12345.pdf",
        mime_type="application/pdf",
        file_size_bytes=100,
        uploaded_by=1
    )

    try:
        res = client.get(f"/student/1/documents/{doc_id}/preview")
        assert res.status_code == 404
    finally:
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM student_documents WHERE id = %s", (doc_id,))
        conn.commit()
        cursor.close()
        conn.close()


def test_preview_traversal_stored_filename_aborts(client):
    _login_as(client, role="admin", user_id=1)

    # Insert a malicious stored_filename record simulating DB tampering
    doc_id = database.insert_student_document(
        stud_id=1,
        doc_type="Marksheet",
        custom_doc_name=None,
        original_filename="evil.pdf",
        stored_filename="../../app.py",
        mime_type="application/pdf",
        file_size_bytes=100,
        uploaded_by=1
    )

    try:
        res = client.get(f"/student/1/documents/{doc_id}/preview")
        assert res.status_code == 404
    finally:
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM student_documents WHERE id = %s", (doc_id,))
        conn.commit()
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# 5. Static Directory Exposure Verification
# ---------------------------------------------------------------------------

def test_uploads_not_in_static_directory():
    static_dir = os.path.abspath(os.path.join(flask_app.app.root_path, "static"))
    upload_dir = os.path.abspath(flask_app.DOCUMENT_UPLOAD_DIR)
    assert not upload_dir.startswith(static_dir), "Upload directory must NOT be located inside static/"
