"""Tests for GET /students/export.

Verifies:
- Role guard (student cannot export, admin/teacher can).
- Response Content-Type and Content-Disposition.
- CSV header row exactly matches EXPECTED_CSV_HEADERS.
- Each data row has exactly the right columns in the right order.
- phone is wrapped as an Excel text-literal (=\"digits\") in the raw CSV so
  Excel never auto-converts it to scientific notation.
- date_of_birth is serialised as a plain ISO string (not a Python object repr).
- The `search` query param is forwarded to the DB query.
- A DB error flashes an error and redirects back to /students.
- Full phone round-trip: export wraps, import unwraps, stored value is plain.
"""

import csv
import datetime
import io
from unittest.mock import patch

import pytest

from app import EXPECTED_CSV_HEADERS


# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

FAKE_STUDENT_RAW = {
    "id": 1,
    "student_id": "S001",
    "student_name": "Alice Sharma",
    "email": "alice@example.com",
    "phone": "9000000001",
    "gender": "Female",
    "date_of_birth": datetime.date(2000, 6, 15),
    "course": "B.Sc CS",
    "semester": "3",
    "address": "123 Main St",
}

# FAKE_STUDENT_EXPORTED reflects the raw CSV cell values as they appear in the
# file (i.e. after export serialisation).  Phone is wrapped as an Excel
# text-literal formula so that Excel never auto-types it as a number.
FAKE_STUDENT_EXPORTED = {
    "student_id": "S001",
    "student_name": "Alice Sharma",
    "email": "alice@example.com",
    "phone": '="9000000001"',   # Excel text-literal wrapper
    "gender": "Female",
    "date_of_birth": "2000-06-15",
    "course": "B.Sc CS",
    "semester": "3",
    "address": "123 Main St",
}


def _parse_csv(response_data: bytes) -> list:
    """Decode (strip BOM) and parse CSV bytes into a list of row dicts."""
    text = response_data.decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


def _header_row(response_data: bytes) -> list:
    """Return just the header row of the CSV."""
    text = response_data.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    return next(reader)


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------

def test_export_requires_login(client):
    """Unauthenticated requests are redirected to login."""
    response = client.get("/students/export")
    assert response.status_code in (302, 401)
    loc = response.headers.get("Location", "")
    assert "login" in loc.lower() or response.status_code == 401


def test_export_forbidden_for_student_role(client):
    """Students cannot export."""
    with client.session_transaction() as sess:
        sess["user_id"] = 99
        sess["username"] = "student_user"
        sess["role"] = "student"

    response = client.get("/students/export")
    assert response.status_code in (302, 403)


def test_export_allowed_for_admin(client):
    """Admins can export."""
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["username"] = "admin"
        sess["role"] = "admin"

    with patch("database.get_all_students", return_value=[]):
        response = client.get("/students/export")

    assert response.status_code == 200


def test_export_allowed_for_teacher(client):
    """Teachers can export (read-only action)."""
    with client.session_transaction() as sess:
        sess["user_id"] = 2
        sess["username"] = "teacher"
        sess["role"] = "teacher"

    with patch("database.get_all_students", return_value=[]):
        response = client.get("/students/export")

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Helper: log in as admin and call /students/export
# ---------------------------------------------------------------------------

def _export_as_admin(client, query_string=""):
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["username"] = "admin"
        sess["role"] = "admin"
    url = "/students/export" + (f"?{query_string}" if query_string else "")
    return client.get(url)


# ---------------------------------------------------------------------------
# Response metadata
# ---------------------------------------------------------------------------

def test_export_content_type(client):
    with patch("database.get_all_students", return_value=[]):
        response = _export_as_admin(client)
    assert "text/csv" in response.content_type


def test_export_content_disposition(client):
    with patch("database.get_all_students", return_value=[]):
        response = _export_as_admin(client)
    cd = response.headers.get("Content-Disposition", "")
    assert "attachment" in cd
    assert "students_export.csv" in cd


# ---------------------------------------------------------------------------
# CSV structure
# ---------------------------------------------------------------------------

def test_export_header_row_matches_expected(client):
    """First row must be exactly EXPECTED_CSV_HEADERS in the defined order."""
    with patch("database.get_all_students", return_value=[FAKE_STUDENT_RAW]):
        response = _export_as_admin(client)

    assert _header_row(response.data) == EXPECTED_CSV_HEADERS


def test_export_data_row_values(client):
    """Data rows contain correct values for each column."""
    with patch("database.get_all_students", return_value=[FAKE_STUDENT_RAW]):
        response = _export_as_admin(client)

    rows = _parse_csv(response.data)
    assert len(rows) == 1
    row = rows[0]
    for field in EXPECTED_CSV_HEADERS:
        assert row[field] == FAKE_STUDENT_EXPORTED[field], (
            f"Field '{field}': expected {FAKE_STUDENT_EXPORTED[field]!r}, "
            f"got {row[field]!r}"
        )


def test_export_no_extra_columns(client):
    """The 'id' DB column (not in EXPECTED_CSV_HEADERS) must NOT appear."""
    with patch("database.get_all_students", return_value=[FAKE_STUDENT_RAW]):
        response = _export_as_admin(client)

    rows = _parse_csv(response.data)
    assert len(rows) == 1
    assert "id" not in rows[0]


def test_export_empty_db_returns_header_only(client):
    """When no students exist, the file has a header row but no data rows."""
    with patch("database.get_all_students", return_value=[]):
        response = _export_as_admin(client)

    rows = _parse_csv(response.data)
    assert rows == []
    assert _header_row(response.data) == EXPECTED_CSV_HEADERS


def test_export_date_of_birth_is_iso_string(client):
    """date_of_birth (a datetime.date) must be serialised as 'YYYY-MM-DD'."""
    with patch("database.get_all_students", return_value=[FAKE_STUDENT_RAW]):
        response = _export_as_admin(client)

    rows = _parse_csv(response.data)
    assert rows[0]["date_of_birth"] == "2000-06-15"


def test_export_multiple_rows(client):
    """Multiple students are all present in the export."""
    students = [
        {
            **FAKE_STUDENT_RAW,
            "student_id": f"S00{i}",
            "student_name": f"Student {i}",
        }
        for i in range(1, 6)
    ]
    with patch("database.get_all_students", return_value=students):
        response = _export_as_admin(client)

    rows = _parse_csv(response.data)
    assert len(rows) == 5


# ---------------------------------------------------------------------------
# Search param forwarding
# ---------------------------------------------------------------------------

def test_export_forwards_search_param(client):
    """The `search` query param is passed through to database.get_all_students."""
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["username"] = "admin"
        sess["role"] = "admin"

    with patch("database.get_all_students", return_value=[]) as mock_get:
        client.get("/students/export?search=Alice")

    mock_get.assert_called_once_with("Alice")


def test_export_empty_search_passes_none(client):
    """An empty search string is normalised to None (full list)."""
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["username"] = "admin"
        sess["role"] = "admin"

    with patch("database.get_all_students", return_value=[]) as mock_get:
        client.get("/students/export?search=")

    mock_get.assert_called_once_with(None)


# ---------------------------------------------------------------------------
# DB error handling
# ---------------------------------------------------------------------------

def test_export_db_error_redirects(client):
    """A DB error redirects to /students."""
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["username"] = "admin"
        sess["role"] = "admin"

    from mysql.connector import Error as MySQLError

    with patch("database.get_all_students", side_effect=MySQLError("boom")):
        response = client.get("/students/export", follow_redirects=False)

    assert response.status_code == 302
    assert "/students" in response.headers.get("Location", "")


def test_export_db_error_flash_message(client):
    """Flashed message mentions 'export' or 'database' on DB failure."""
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["username"] = "admin"
        sess["role"] = "admin"

    from mysql.connector import Error as MySQLError

    with patch("database.get_all_students", side_effect=MySQLError("boom")):
        response = client.get("/students/export", follow_redirects=True)

    body = response.data.lower()
    assert b"export" in body or b"database" in body


# ---------------------------------------------------------------------------
# Round-trip compatibility
# ---------------------------------------------------------------------------

def test_export_header_compatible_with_import(client):
    """Headers from the export are byte-for-byte equal to EXPECTED_CSV_HEADERS.

    This guarantees the exported file will be accepted by /students/import
    without any manual column reordering.
    """
    with patch("database.get_all_students", return_value=[FAKE_STUDENT_RAW]):
        response = _export_as_admin(client)

    assert _header_row(response.data) == EXPECTED_CSV_HEADERS, (
        "Export headers differ from EXPECTED_CSV_HEADERS — the file would be "
        "rejected by /students/import."
    )


# ---------------------------------------------------------------------------
# Phone Excel text-literal wrapping
# ---------------------------------------------------------------------------

def test_export_phone_wrapped_as_excel_literal(client):
    """The phone cell in the raw CSV must be the Excel text-literal =\"digits\".

    This prevents Excel from auto-converting a purely-numeric phone number to
    scientific notation (e.g. 9.88E+09) when the file is opened directly.
    """
    with patch("database.get_all_students", return_value=[FAKE_STUDENT_RAW]):
        response = _export_as_admin(client)

    rows = _parse_csv(response.data)
    assert len(rows) == 1
    raw_phone = rows[0]["phone"]
    assert raw_phone == '="9000000001"', (
        f"Expected Excel text-literal '=\"9000000001\"', got {raw_phone!r}"
    )
    # Other purely-alphanumeric fields must NOT be wrapped
    assert not rows[0]["student_id"].startswith('="'), (
        "student_id should not be wrapped — it is already alphanumeric"
    )


def test_phone_excel_wrapper_roundtrip(client):
    """Full phone round-trip: export wraps as =\"digits\", import unwraps to plain string.

    Steps:
    1. Export a student with phone '9876543210' — CSV cell must be '=\"9876543210\"'.
    2. Feed that exact exported CSV bytes back into POST /students/import.
    3. The import must call database.add_student with the plain string '9876543210',
       not the wrapped form.
    """
    import io as _io

    phone_raw = "9876543210"
    student = {
        **FAKE_STUDENT_RAW,
        "student_id": "S999",
        "phone": phone_raw,
    }

    # Step 1 — export
    with patch("database.get_all_students", return_value=[student]):
        export_resp = _export_as_admin(client)

    assert export_resp.status_code == 200
    csv_bytes = export_resp.data

    # Confirm the raw cell value in the exported file
    rows = _parse_csv(csv_bytes)
    assert rows[0]["phone"] == f'="{phone_raw}"', (
        "Export did not wrap phone as Excel text-literal"
    )

    # Step 2 — re-import the exact exported bytes
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["username"] = "admin"
        sess["role"] = "admin"

    captured_payload = {}

    def fake_add_student(payload):
        captured_payload.update(payload)

    def fake_get_by_student_id(sid):
        return None  # no duplicate

    with patch("database.insert_student", side_effect=fake_add_student), \
         patch("database.get_student_by_student_id", side_effect=fake_get_by_student_id):
        import_resp = client.post(
            "/students/import",
            data={
                "file": (_io.BytesIO(csv_bytes), "students_export.csv"),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )

    # Step 3 — stored phone must be the plain string
    assert "phone" in captured_payload, (
        "database.add_student was not called — import may have failed validation"
    )
    assert captured_payload["phone"] == phone_raw, (
        f"Expected stored phone {phone_raw!r}, got {captured_payload['phone']!r}. "
        "Import did not strip the Excel text-literal wrapper."
    )
