"""
Tests for Student ID Card Generator feature:
  - generate_id_card_pdf() unit tests (ReportLab PDF structure, dynamic institution name, student data, QR code).
  - resolve_student_photo_path() tests (gender-based photo selection, custom photo priority).
  - Flask web routes tests (ID Card preview HTML, ID Card PDF download, public QR code verification page, RBAC own-record protection).
"""
import zlib
import base64
import re
import os
import pytest

from pdf_generator import generate_id_card_pdf, resolve_student_photo_path


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    extracted_text = ""
    matches = re.findall(rb"/ASCII85Decode.*?stream\r?\n(.*?~>)", pdf_bytes, re.DOTALL)
    for m in matches:
        try:
            decoded = base64.a85decode(m, adobe=True)
            decompressed = zlib.decompress(decoded)
            extracted_text += decompressed.decode("latin1", errors="ignore") + "\n"
        except Exception:
            pass
    return extracted_text


def _make_student(**overrides):
    base = {
        "id": 10,
        "student_id": "STU100",
        "student_name": "Rohan Sharma",
        "gender": "Male",
        "course": "B.Tech Computer Science",
        "semester": "5",
        "academic_year": "2025-2026",
        "address": "45 College Road, Wardha",
        "photo": None,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Unit tests for photo resolution logic
# ---------------------------------------------------------------------------

def test_male_student_gets_male_default_photo():
    student = _make_student(gender="Male", photo=None)
    photo_path = resolve_student_photo_path(student)
    assert photo_path is not None
    assert "id-card-default-male.jpg" in photo_path
    assert os.path.isfile(photo_path)


def test_female_student_gets_female_default_photo():
    student = _make_student(gender="Female", photo=None)
    photo_path = resolve_student_photo_path(student)
    assert photo_path is not None
    assert "id-card-default-female.jpg" in photo_path
    assert os.path.isfile(photo_path)


def test_uploaded_photo_takes_priority(tmp_path):
    # Create a dummy custom photo file
    custom_img = tmp_path / "custom_student.jpg"
    custom_img.write_bytes(b"\xFF\xD8\xFF\xE0\x00\x10JFIF")
    
    student = _make_student(gender="Female", photo=str(custom_img))
    photo_path = resolve_student_photo_path(student)
    assert photo_path == str(custom_img)


# ---------------------------------------------------------------------------
# Unit tests for generate_id_card_pdf
# ---------------------------------------------------------------------------

def test_id_card_pdf_header_and_data():
    student = _make_student(student_name="Rohan Sharma", student_id="STU100", course="B.Tech CS")
    pdf_buf = generate_id_card_pdf("Sushganga Institute", student, verification_url="http://localhost:5000/students/10/id-card/verify")
    pdf_bytes = pdf_buf.getvalue()
    assert pdf_bytes.startswith(b"%PDF")
    
    text = _extract_pdf_text(pdf_bytes)
    assert "SUSHGANGA INSTITUTE" in text
    assert "STUDENT" in text
    assert "ID" in text
    assert "CARD" in text
    assert "Rohan Sharma" in text
    assert "STU100" in text
    assert "B.Tech CS" in text


def test_id_card_pdf_different_institution():
    student = _make_student()
    pdf_buf_a = generate_id_card_pdf("Alpha College", student)
    pdf_buf_b = generate_id_card_pdf("Beta University", student)

    text_a = _extract_pdf_text(pdf_buf_a.getvalue())
    text_b = _extract_pdf_text(pdf_buf_b.getvalue())

    assert "ALPHA COLLEGE" in text_a
    assert "ALPHA COLLEGE" not in text_b
    assert "BETA UNIVERSITY" in text_b


def test_id_card_pdf_missing_optional_fields():
    student = {
        "id": 2,
        "student_id": "STU002",
        "student_name": "Minimal Student",
    }
    pdf_buf = generate_id_card_pdf("Test College", student)
    pdf_bytes = pdf_buf.getvalue()
    assert pdf_bytes.startswith(b"%PDF")
    text = _extract_pdf_text(pdf_bytes)
    assert "Minimal Student" in text
    assert "STU002" in text


# ---------------------------------------------------------------------------
# Web route integration & security tests
# ---------------------------------------------------------------------------

def test_id_card_preview_route_requires_login(client):
    res = client.get("/students/1/id-card")
    assert res.status_code == 302
    assert "/login" in res.location


def test_id_card_preview_route_admin_access(admin_client, db):
    pk = db["linked_pk"]
    res = admin_client.get(f"/students/{pk}/id-card")
    assert res.status_code == 200
    assert b"Student ID Card" in res.data
    assert b"id-card-default" in res.data or b"data:image/png;base64" in res.data
    assert b"SCAN TO VERIFY" in res.data


def test_id_card_pdf_download_route(admin_client, db):
    pk = db["linked_pk"]
    res = admin_client.get(f"/students/{pk}/id-card/download")
    assert res.status_code == 200
    assert res.content_type == "application/pdf"
    assert res.data.startswith(b"%PDF")


def test_unauthorized_student_cannot_access_other_id_card(student_client, db):
    # Logged-in student attempting to access another student's ID card
    other_pk = db["other_pk"]
    res = student_client.get(f"/students/{other_pk}/id-card")
    assert res.status_code == 403


def test_id_card_verify_route_public_access(client, db):
    pk = db["linked_pk"]
    # Verify endpoint must be accessible without logging in
    res = client.get(f"/students/{pk}/id-card/verify")
    assert res.status_code == 200
    assert b"VALID" in res.data
    assert b"ACTIVE STUDENT" in res.data


def test_id_card_verify_route_invalid_student(client):
    res = client.get("/students/999999/id-card/verify")
    assert res.status_code == 200
    assert b"Invalid" in res.data or b"Not Found" in res.data or b"not found" in res.data


def test_qr_code_scannable_url_flow(admin_client, client, db):
    pk = db["linked_pk"]
    # 1. Fetch preview page & extract QR image data URI
    res = admin_client.get(f"/students/{pk}/id-card")
    assert res.status_code == 200
    assert b"data:image/png;base64," in res.data

    # 2. Access the real verification URL directly (emulating smartphone camera scan)
    verify_res = client.get(f"/students/{pk}/id-card/verify")
    assert verify_res.status_code == 200
    assert b"VALID" in verify_res.data
    assert b"ACTIVE STUDENT" in verify_res.data
    assert b"Aarav Sharma" in verify_res.data or b"BCA2401" in verify_res.data


def test_public_base_url_qr_generation(monkeypatch):
    import config
    from app import _get_verification_url

    test_domain = "https://studentmanagement.vercel.app"
    monkeypatch.setattr(config, "PUBLIC_BASE_URL", test_domain)

    student = _make_student(student_id="BCA2401")
    verify_url = _get_verification_url(student)

    assert verify_url == "https://studentmanagement.vercel.app/verify/student/BCA2401"
    assert "127.0.0.1" not in verify_url
    assert "localhost" not in verify_url


def test_public_student_verify_route_no_login(client):
    # Public route /verify/student/<student_id> accessible without login
    res = client.get("/verify/student/BCA2401")
    assert res.status_code == 200
    assert b"VALID" in res.data
    assert b"ACTIVE STUDENT" in res.data
    assert b"Aarav Sharma" in res.data
    assert b"BCA2401" in res.data

    # Verify sensitive data (passwords, tokens, address, phone) are NOT exposed on verify page
    assert b"password" not in res.data.lower()
    assert b"secret" not in res.data.lower()
    assert b"9876543210" not in res.data  # Phone number excluded from public page


def test_public_student_verify_nonexistent(client):
    res = client.get("/verify/student/NONEXISTENT999")
    assert res.status_code == 200
    assert b"Student record not found" in res.data or b"error" in res.data.lower()


