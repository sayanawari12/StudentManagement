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


# ---------------------------------------------------------------------------
# PDF Security & Safe Dynamic Content Hardening Tests (STEP 2B)
# ---------------------------------------------------------------------------

from pdf_generator import (
    generate_marksheet_pdf,
    generate_academic_transcript_pdf,
    generate_dashboard_pdf,
    generate_id_card_pdf
)


def test_bonafide_pdf_special_characters_and_injection():
    student = _make_student(
        student_name="A & B <script>alert(1)</script>",
        student_id="STU<001>",
        course="BCA & Tech",
        semester="3 <Advanced>"
    )
    pdf_buf = generate_bonafide_pdf(
        "College <Main & Branch>",
        student,
        institution_location="Wani & Yavatmal <Dist>",
        institution_affiliation="SGBAU & Amravati <Univ>"
    )
    pdf_bytes = pdf_buf.getvalue()
    assert pdf_bytes.startswith(b"%PDF")


def test_marksheet_pdf_special_characters_and_injection():
    student = _make_student(student_name="Alice <Bob>", student_id="STU&100", course="BCA <CS>")
    exam = {"exam_name": "Mid-Sem & Final <2026>", "exam_type": "Internal & Practical", "academic_year": "2026 & 2027"}
    result_summary = {
        "overall_status": "PASS <Verified>",
        "overall_grade": "A+ <Honor>",
        "total_obtained": 450.0,
        "total_max": 500.0,
        "overall_percentage": 90.0,
        "subject_results": [
            {
                "subject_code": "CS101 & 102",
                "subject_name": "Data Structures <C++>",
                "max_marks": 100.0,
                "obtained_marks": 95.0,
                "percentage": 95.0,
                "grade": "O <Excellent>",
                "status": "PASS"
            }
        ]
    }
    pdf_bytes = generate_marksheet_pdf(
        institution_name="Sushganga & Co <Inst>",
        student=student,
        exam=exam,
        result_summary=result_summary
    )
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF")


def test_academic_transcript_pdf_special_characters_and_injection():
    student = _make_student(student_name="Charlie <Delta>", student_id="STU<999>", course="BCA & IT")
    transcript_data = {
        "overall": {
            "has_data": True,
            "overall_result": "PASS & Distinction",
            "overall_grade": "A & Top",
            "total_semesters": 2,
            "total_exams": 2,
            "passed_subjects": 10,
            "total_subjects": 10,
            "total_obtained": 900.0,
            "total_max": 1000.0,
            "overall_percentage": 90.0
        },
        "ordered_semesters": ["1 & 2"],
        "semesters": {
            "1 & 2": {
                "exams": [
                    {
                        "exam": {"exam_name": "Sem Exam <1>", "academic_year": "2025 & 2026"},
                        "summary": {
                            "total_obtained": 450.0,
                            "total_max": 500.0,
                            "percentage": 90.0,
                            "overall_status": "PASS",
                            "overall_grade": "A+",
                            "subject_results": [
                                {
                                    "subject_code": "SUB&1",
                                    "subject_name": "C Programming <Advanced>",
                                    "max_marks": 100.0,
                                    "pass_marks": 40.0,
                                    "obtained_marks": 90.0,
                                    "percentage": 90.0,
                                    "grade": "A+",
                                    "status": "PASS"
                                }
                            ]
                        }
                    }
                ]
            }
        }
    }
    pdf_bytes = generate_academic_transcript_pdf(
        student=student,
        transcript_data=transcript_data,
        institution_name="Univ & College <Main>"
    )
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF")


def test_dashboard_pdf_special_characters():
    stats = {
        "total_students": 100,
        "total_bca": 80,
        "attendance_today": 75,
        "total_dues": 15000.5,
        "semester_counts": [{"semester": "1 & 2 <Special>", "total": 50}]
    }
    pdf_buf = generate_dashboard_pdf("College <Main & Branch>", stats, "2026-09-15 <Today>")
    pdf_bytes = pdf_buf.getvalue()
    assert pdf_bytes.startswith(b"%PDF")


def test_id_card_pdf_special_characters():
    student = _make_student(student_name="Test <User>", student_id="STU&777", course="BCA & Multi")
    pdf_buf = generate_id_card_pdf("Inst <Name>", student, verification_url="http://test.com?a=1&b=2")
    pdf_bytes = pdf_buf.getvalue()
    assert pdf_bytes.startswith(b"%PDF")


def test_pdf_generators_null_and_empty_handling():
    pdf_bonafide = generate_bonafide_pdf(None, {})
    assert pdf_bonafide.getvalue().startswith(b"%PDF")

    pdf_marksheet = generate_marksheet_pdf(institution_name=None, student=None, exam=None, result_summary=None)
    assert pdf_marksheet.startswith(b"%PDF")

    pdf_transcript = generate_academic_transcript_pdf(student=None, transcript_data=None, institution_name=None)
    assert pdf_transcript.startswith(b"%PDF")

    pdf_dash = generate_dashboard_pdf(None, {}, "")
    assert pdf_dash.getvalue().startswith(b"%PDF")

    pdf_id = generate_id_card_pdf(None, {})
    assert pdf_id.getvalue().startswith(b"%PDF")
