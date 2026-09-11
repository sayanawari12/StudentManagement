"""
Tests for generate_bonafide_pdf():
  - The header must reflect whatever institution_name is passed in.
  - No hardcoded college name or signer name may be baked into the test expectations.
  - Structural elements (BONAFIDE CERTIFICATE title, student data, cert number,
    Principal label) must all be present.
"""
import zlib
import base64
import re

from pdf_generator import generate_bonafide_pdf


# ---------------------------------------------------------------------------
# PDF text extraction helper (ASCII85 + FlateDecode page streams)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_student(**overrides):
    base = {
        "id": 1,
        "student_id": "STU001",
        "student_name": "Jane Doe",
        "gender": "Female",
        "course": "BCA",
        "semester": "4",
        "address": "123 Main St",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Tests: institution_name parameter actually controls the header
# ---------------------------------------------------------------------------

def test_institution_name_appears_in_header():
    """The institution_name passed in should appear in the PDF text."""
    pdf_buf = generate_bonafide_pdf("Test College", _make_student())
    pdf_text = _extract_pdf_text(pdf_buf.getvalue())
    assert "TEST COLLEGE" in pdf_text, (
        "institution_name 'Test College' should appear uppercased in the PDF header"
    )


def test_different_institution_name_replaces_header():
    """Passing a different institution_name must change the header, not keep any old value."""
    pdf_buf_a = generate_bonafide_pdf("Alpha University", _make_student())
    pdf_buf_b = generate_bonafide_pdf("Beta Institute", _make_student())

    text_a = _extract_pdf_text(pdf_buf_a.getvalue())
    text_b = _extract_pdf_text(pdf_buf_b.getvalue())

    assert "ALPHA UNIVERSITY" in text_a
    assert "ALPHA UNIVERSITY" not in text_b

    assert "BETA INSTITUTE" in text_b
    assert "BETA INSTITUTE" not in text_a


def test_none_institution_name_falls_back_to_placeholder():
    """Passing None should fall back to the generic placeholder, not crash or embed a specific name."""
    pdf_buf = generate_bonafide_pdf(None, _make_student())
    pdf_text = _extract_pdf_text(pdf_buf.getvalue())
    # Generic placeholder must appear; no specific institution should be hard-wired
    assert "YOUR COLLEGE NAME HERE" in pdf_text


# ---------------------------------------------------------------------------
# Tests: structural certificate elements are always present
# ---------------------------------------------------------------------------

def test_bonafide_certificate_title_present():
    pdf_buf = generate_bonafide_pdf("Any Institution", _make_student())
    pdf_text = _extract_pdf_text(pdf_buf.getvalue())
    assert "BONAFIDE CERTIFICATE" in pdf_text


def test_student_data_appears_in_certificate():
    student = _make_student(student_name="Jane Doe", student_id="STU001", course="BCA", semester="4")
    pdf_buf = generate_bonafide_pdf("Any Institution", student)
    pdf_text = _extract_pdf_text(pdf_buf.getvalue())

    assert "Jane Doe" in pdf_text
    assert "STU001" in pdf_text
    assert "BCA" in pdf_text
    assert "Semester 4" in pdf_text
    assert "She is currently studying" in pdf_text


def test_male_student_pronoun():
    student = _make_student(student_name="John Smith", student_id="STU002", gender="Male")
    pdf_buf = generate_bonafide_pdf("Any Institution", student)
    pdf_text = _extract_pdf_text(pdf_buf.getvalue())
    assert "He is currently studying" in pdf_text


def test_principal_label_present_without_specific_name():
    """The signature block must contain 'Principal' but must NOT contain any hardcoded person's name."""
    pdf_buf = generate_bonafide_pdf("Any Institution", _make_student())
    pdf_text = _extract_pdf_text(pdf_buf.getvalue())
    assert "Principal" in pdf_text
    # Must not bake in any specific individual's name
    assert "Sayan Awari" not in pdf_text


def test_pdf_is_valid_bytes():
    pdf_buf = generate_bonafide_pdf("Any Institution", _make_student())
    pdf_bytes = pdf_buf.getvalue()
    assert len(pdf_bytes) > 0
    assert pdf_bytes.startswith(b"%PDF")
