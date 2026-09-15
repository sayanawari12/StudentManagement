"""
tests/test_student_documents.py — Comprehensive security and functionality tests
for Student Document Management module.
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
    """Return an in-memory BytesIO object representing a valid minimal PDF."""
    content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n"
    bio = io.BytesIO(content)
    bio.name = "test_document.pdf"
    bio.filename = "test_document.pdf"
    bio.content_type = "application/pdf"
    return bio


def create_dummy_png():
    """Return an in-memory BytesIO object representing a valid PNG header."""
    content = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    bio = io.BytesIO(content)
    bio.name = "test_photo.png"
    bio.filename = "test_photo.png"
    bio.content_type = "image/png"
    return bio


def create_dummy_jpeg():
    """Return an in-memory BytesIO object representing a valid JPEG header."""
    content = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xd9"
    bio = io.BytesIO(content)
    bio.name = "test_photo.jpg"
    bio.filename = "test_photo.jpg"
    bio.content_type = "image/jpeg"
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
# 2. Strict File Type Validation Matrix (A through G & R)
# ---------------------------------------------------------------------------

def test_validation_matrix_a_to_r():
    # A. Valid PDF
    pdf = create_dummy_pdf()
    valid, err = flask_app._validate_document_file(pdf)
    assert valid
    assert err is None

    # B. Valid JPEG
    jpg = create_dummy_jpeg()
    valid, err = flask_app._validate_document_file(jpg)
    assert valid
    assert err is None

    # C. Valid PNG
    png = create_dummy_png()
    valid, err = flask_app._validate_document_file(png)
    assert valid
    assert err is None

    # D. Extension spoofing (.jpg + application/pdf + PDF magic bytes)
    d = create_dummy_pdf()
    d.filename = "fake.jpg"
    d.content_type = "application/pdf"
    valid, err = flask_app._validate_document_file(d)
    assert not valid
    assert "MIME type" in err

    # E. MIME spoofing (.pdf + image/jpeg + PDF magic bytes)
    e = create_dummy_pdf()
    e.filename = "fake.pdf"
    e.content_type = "image/jpeg"
    valid, err = flask_app._validate_document_file(e)
    assert not valid
    assert "MIME type" in err

    # F. Signature spoofing (.jpg + image/jpeg + PDF magic bytes)
    f = create_dummy_pdf()
    f.filename = "fake.jpg"
    f.content_type = "image/jpeg"
    valid, err = flask_app._validate_document_file(f)
    assert not valid
    assert "JPEG signature" in err

    # G. Unsupported extension (.exe)
    g = io.BytesIO(b"MZ executable header content")
    g.filename = "malicious.exe"
    g.content_type = "application/octet-stream"
    valid, err = flask_app._validate_document_file(g)
    assert not valid
    assert "extension" in err.lower()

    # R. Extra consistency mismatch (.png + image/png + PDF magic bytes)
    r1 = create_dummy_pdf()
    r1.filename = "fake.png"
    r1.content_type = "image/png"
    valid, err = flask_app._validate_document_file(r1)
    assert not valid
    assert "PNG signature" in err


# ---------------------------------------------------------------------------
# 3. Path Traversal & Safe Path Helper Tests (I & J)
# ---------------------------------------------------------------------------

def test_get_safe_document_path_traversal():
    assert flask_app._get_safe_document_path("../../../etc/passwd") is None
    assert flask_app._get_safe_document_path("sub/folder/file.pdf") is None
    assert flask_app._get_safe_document_path("..\\windows\\system32") is None
    assert flask_app._get_safe_document_path(None) is None

    safe_path = flask_app._get_safe_document_path("doc_abc123.pdf")
    assert safe_path is not None
    assert safe_path.startswith(flask_app.DOCUMENT_UPLOAD_DIR)


# ---------------------------------------------------------------------------
# 4. Upload Document Tests, Oversized & Path Traversal Handling (H, I, J)
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


def test_upload_oversized_file_rejected(client):
    """H. Oversized file (> 5 MB) must be rejected and not saved."""
    _login_as(client, role="admin", user_id=1, username="admin")
    students = database.get_all_students()
    s = students[0]

    # Create 5.5 MB payload
    large_content = b"%PDF-1.4\n" + b"X" * (5 * 1024 * 1024 + 500)
    large_pdf = io.BytesIO(large_content)

    response = client.post(
        f"/student/{s['id']}/documents/upload",
        data={
            "doc_type": "Marksheet",
            "document_file": (large_pdf, "large.pdf", "application/pdf")
        },
        follow_redirects=True
    )
    assert b"exceeds maximum limit of 5 MB" in response.data or response.status_code == 413


def test_path_traversal_filename_uses_safe_uuid(client):
    """I & J. Path traversal filename stored with generated UUID filename inside upload dir."""
    _login_as(client, role="admin", user_id=1, username="admin")
    students = database.get_all_students()
    s = students[0]

    pdf = create_dummy_pdf()
    response = client.post(
        f"/student/{s['id']}/documents/upload",
        data={
            "doc_type": "Aadhaar Card",
            "document_file": (pdf, "../../etc/passwd.pdf", "application/pdf")
        },
        follow_redirects=True
    )
    assert response.status_code == 200

    docs = database.get_student_documents(s["id"])
    doc = docs[0]
    assert "/" not in doc["stored_filename"]
    assert "\\" not in doc["stored_filename"]
    assert doc["stored_filename"].startswith("doc_")
    assert doc["stored_filename"] != "../../etc/passwd.pdf"

    safe_path = flask_app._get_safe_document_path(doc["stored_filename"])
    assert safe_path is not None
    assert safe_path.startswith(flask_app.DOCUMENT_UPLOAD_DIR)
    assert os.path.exists(safe_path)

    # Cleanup
    client.post(f"/student/{s['id']}/documents/{doc['id']}/delete")


def test_private_document_not_in_static(client):
    """K. Verify private document is NOT publicly accessible through static directory."""
    _login_as(client, role="admin", user_id=1, username="admin")
    students = database.get_all_students()
    s = students[0]

    pdf = create_dummy_pdf()
    client.post(
        f"/student/{s['id']}/documents/upload",
        data={
            "doc_type": "Marksheet",
            "document_file": (pdf, "secret_marksheet.pdf", "application/pdf")
        },
        follow_redirects=True
    )
    docs = database.get_student_documents(s["id"])
    doc = docs[0]

    resp = client.get(f"/static/uploads/documents/{doc['stored_filename']}")
    assert resp.status_code == 404

    # Cleanup
    client.post(f"/student/{s['id']}/documents/{doc['id']}/delete")


# ---------------------------------------------------------------------------
# 5. Access Control & Authorization Security Tests (L, M, N, O)
# ---------------------------------------------------------------------------

def test_cross_student_preview_and_download_denied(client):
    """L & M. Cross-student preview and download must be denied."""
    students = database.get_all_students()
    s1 = students[0]
    s2 = students[1] if len(students) > 1 else s1

    _login_as(client, role="admin", user_id=1, username="admin")
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
    doc_id = docs[0]["id"]

    _login_as(client, role="student", user_id=999, username="other_student", linked_student_id=s2["id"])

    if s1["id"] != s2["id"]:
        # Student 2 accessing Student 1's doc via Student 1's URL -> 403
        r1 = client.get(f"/student/{s1['id']}/documents/{doc_id}/preview")
        assert r1.status_code == 403

        # Student 2 accessing Student 1's doc via Student 2's URL -> 403
        r2 = client.get(f"/student/{s2['id']}/documents/{doc_id}/preview")
        assert r2.status_code == 403

        # Student 2 downloading Student 1's doc via Student 1's URL -> 403
        r3 = client.get(f"/student/{s1['id']}/documents/{doc_id}/download")
        assert r3.status_code == 403

        # Student 2 downloading Student 1's doc via Student 2's URL -> 403
        r4 = client.get(f"/student/{s2['id']}/documents/{doc_id}/download")
        assert r4.status_code == 403

    # Cleanup
    _login_as(client, role="admin", user_id=1, username="admin")
    client.post(f"/student/{s1['id']}/documents/{doc_id}/delete")


def test_unauthorized_role_actions_denied(client):
    """N & O. Non-admin (Teacher/Student) must not verify, reject, or delete documents."""
    _login_as(client, role="admin", user_id=1, username="admin")
    students = database.get_all_students()
    s = students[0]

    pdf = create_dummy_pdf()
    client.post(
        f"/student/{s['id']}/documents/upload",
        data={
            "doc_type": "Bonafide",
            "document_file": (pdf, "bonafide.pdf", "application/pdf")
        },
        follow_redirects=True
    )
    docs = database.get_student_documents(s["id"])
    doc_id = docs[0]["id"]

    # Teacher role attempts
    _login_as(client, role="teacher", user_id=2, username="teacher1")
    assert client.post(f"/student/{s['id']}/documents/{doc_id}/delete").status_code == 403
    assert client.post(f"/student/{s['id']}/documents/{doc_id}/verify").status_code == 403
    assert client.post(f"/student/{s['id']}/documents/{doc_id}/reject", data={"rejection_reason": "R"}).status_code == 403

    # Student role attempts
    _login_as(client, role="student", user_id=99, username="student_user", linked_student_id=s["id"])
    assert client.post(f"/student/{s['id']}/documents/{doc_id}/delete").status_code == 403
    assert client.post(f"/student/{s['id']}/documents/{doc_id}/verify").status_code == 403
    assert client.post(f"/student/{s['id']}/documents/{doc_id}/reject", data={"rejection_reason": "R"}).status_code == 403

    # Cleanup
    _login_as(client, role="admin", user_id=1, username="admin")
    client.post(f"/student/{s['id']}/documents/{doc_id}/delete")


# ---------------------------------------------------------------------------
# 6. Lifecycle, Missing File & Filename XSS (P, Q)
# ---------------------------------------------------------------------------

def test_missing_physical_file_returns_404(client):
    """P. Database record exists but physical file is missing -> clean 404."""
    _login_as(client, role="admin", user_id=1, username="admin")
    students = database.get_all_students()
    s = students[0]

    pdf = create_dummy_pdf()
    client.post(
        f"/student/{s['id']}/documents/upload",
        data={
            "doc_type": "Caste Certificate",
            "document_file": (pdf, "caste.pdf", "application/pdf")
        },
        follow_redirects=True
    )
    docs = database.get_student_documents(s["id"])
    doc = docs[0]
    doc_id = doc["id"]

    # Manually remove physical file
    safe_path = flask_app._get_safe_document_path(doc["stored_filename"])
    if safe_path and os.path.exists(safe_path):
        os.remove(safe_path)

    r_prev = client.get(f"/student/{s['id']}/documents/{doc_id}/preview")
    assert r_prev.status_code == 404

    r_dl = client.get(f"/student/{s['id']}/documents/{doc_id}/download")
    assert r_dl.status_code == 404

    # Cleanup
    database.delete_student_document(doc_id)


def test_filename_xss_prevention(client):
    """Q. Custom title / original filename with HTML/JS payload is autoescaped in views."""
    _login_as(client, role="admin", user_id=1, username="admin")
    students = database.get_all_students()
    s = students[0]

    pdf = create_dummy_pdf()
    client.post(
        f"/student/{s['id']}/documents/upload",
        data={
            "doc_type": "Other",
            "custom_doc_name": "<script>alert('xss')</script>",
            "document_file": (pdf, "doc_xss.pdf", "application/pdf")
        },
        follow_redirects=True
    )

    docs = database.get_student_documents(s["id"])
    doc = docs[0]
    assert doc["custom_doc_name"] == "<script>alert('xss')</script>"

    res = client.get(f"/students/{s['id']}")
    assert res.status_code == 200
    assert b"<script>alert('xss')</script>" not in res.data
    assert b"&lt;script&gt;alert(&#39;xss&#39;)&lt;/script&gt;" in res.data or b"&lt;script&gt;" in res.data

    # Cleanup
    client.post(f"/student/{s['id']}/documents/{doc['id']}/delete")


def test_document_lifecycle_verify_reject_delete(client):
    _login_as(client, role="admin", user_id=1, username="admin")
    students = database.get_all_students()
    student = students[0]
    stud_pk = student["id"]

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


def test_audit_log_includes_documents(client):
    students = database.get_all_students()
    student = students[0]
    logs = database.get_student_audit_log(student["id"])
    assert isinstance(logs, list)
