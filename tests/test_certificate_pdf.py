import zlib
import base64
import re
from pdf_generator import generate_bonafide_pdf, generate_dashboard_pdf


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    extracted_text = ""
    # Extract ASCII85 + FlateDecode streams
    matches = re.findall(rb"/ASCII85Decode.*?stream\r?\n(.*?~>)", pdf_bytes, re.DOTALL)
    for m in matches:
        try:
            decoded = base64.a85decode(m, adobe=True)
            decompressed = zlib.decompress(decoded)
            extracted_text += decompressed.decode("latin1", errors="ignore") + "\n"
        except Exception:
            pass
    return extracted_text


def test_generate_bonafide_pdf_content_and_header():
    mock_student = {
        "id": 1,
        "student_id": "STU001",
        "student_name": "Jane Doe",
        "gender": "Female",
        "course": "BCA",
        "semester": "4",
        "address": "123 Main St"
    }

    pdf_buf = generate_bonafide_pdf("SUSHGANGA INSTITUTE OF COMPUTER APPLICATIONS", mock_student)
    pdf_bytes = pdf_buf.getvalue()

    assert len(pdf_bytes) > 0
    assert pdf_bytes.startswith(b"%PDF")

    pdf_text = _extract_pdf_text(pdf_bytes)

    # 1. Header checks
    assert "SUSHGANGA INSTITUTE OF" in pdf_text
    assert "COMPUTER APPLICATIONS" in pdf_text
    assert "Wani, Maharashtra" in pdf_text
    assert "Sant Gadge Baba Amravati University" in pdf_text
    assert "YOUR COLLEGE NAME HERE" not in pdf_text

    # 2. Certificate title
    assert "BONAFIDE CERTIFICATE" in pdf_text

    # 3. Dynamic Student Data
    assert "Jane Doe" in pdf_text
    assert "STU001" in pdf_text
    assert "BCA" in pdf_text
    assert "Semester 4" in pdf_text
    assert "She is currently studying" in pdf_text

    # 4. Principal Section
    assert "Sayan Awari" in pdf_text
    assert "Principal" in pdf_text


def test_generate_bonafide_pdf_with_none_institution_name():
    mock_student = {
        "id": 2,
        "student_id": "STU002",
        "student_name": "John Smith",
        "gender": "Male",
        "course": "BCA",
        "semester": "2",
        "address": "456 Park Ave"
    }

    # Even if institution_name is None, placeholder must never appear
    pdf_buf = generate_bonafide_pdf(None, mock_student)
    pdf_bytes = pdf_buf.getvalue()

    pdf_text = _extract_pdf_text(pdf_bytes)

    assert "YOUR COLLEGE NAME HERE" not in pdf_text
    assert "SUSHGANGA INSTITUTE OF" in pdf_text
    assert "John Smith" in pdf_text
    assert "He is currently studying" in pdf_text
