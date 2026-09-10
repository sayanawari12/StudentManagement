"""
test_bulk_import.py — Tests for CSV Bulk Student Import feature.
"""

import io
import pytest
import database


HEADER = "student_id,student_name,email,phone,gender,date_of_birth,course,semester,address\n"


def _make_csv(rows_lines):
    return (HEADER + "\n".join(rows_lines)).encode("utf-8")


class TestBulkImportPermissions:
    """Access control tests for /students/import."""

    def test_admin_access_allowed(self, admin_client):
        resp = admin_client.get("/students/import")
        assert resp.status_code == 200
        assert b"Import Students via CSV" in resp.data

    def test_teacher_access_forbidden(self, teacher_client):
        assert teacher_client.get("/students/import").status_code == 403

    def test_student_access_forbidden(self, student_client):
        assert student_client.get("/students/import").status_code == 403


class TestBulkImportProcessing:
    """Functional CSV parsing, validation, and database insertion tests."""

    def test_valid_csv_imports_all_students(self, admin_client, db):
        csv_bytes = _make_csv([
            "BCA2481,Import One,import1@example.com,9876543210,Male,2005-01-01,BCA,1,Addr1",
            "BCA2482,Import Two,import2@example.com,9876543211,Female,2005-02-02,BCA,2,Addr2",
            "BCA2483,Import Three,import3@example.com,9876543212,Male,2005-03-03,BCA,3,Addr3",
        ])

        resp = admin_client.post(
            "/students/import",
            data={"file": (io.BytesIO(csv_bytes), "students.csv")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200
        assert b"3 Imported Successfully" in resp.data

        # Verify DB insertions
        for sid in ("BCA2481", "BCA2482", "BCA2483"):
            st = database.get_student_by_student_id(sid)
            assert st is not None, f"Student {sid} should exist in DB"

    def test_mixed_csv_partial_import(self, admin_client, db):
        # BCA2401 already exists in sample DB
        csv_bytes = _make_csv([
            "BCA2484,Valid User,valid@example.com,9876543214,Male,2005-04-04,BCA,4,Addr4",
            "BCA2401,Existing DB User,exist@example.com,9876543215,Female,2005-05-05,BCA,5,Addr5",  # DB Duplicate
            ",Missing ID User,noid@example.com,9876543216,Male,2005-06-06,BCA,1,Addr6",              # Missing required student_id
            "BCA2485,Valid User Two,valid2@example.com,9876543217,Female,2005-07-07,BCA,2,Addr7",
        ])

        resp = admin_client.post(
            "/students/import",
            data={"file": (io.BytesIO(csv_bytes), "mixed.csv")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200
        assert b"2 Imported Successfully" in resp.data
        assert b"2 Skipped" in resp.data
        assert b"Student ID already exists in database" in resp.data
        assert b"Student ID is required" in resp.data

        assert database.get_student_by_student_id("BCA2484") is not None
        assert database.get_student_by_student_id("BCA2485") is not None

    def test_in_file_duplicate_student_id_skipped(self, admin_client, db):
        csv_bytes = _make_csv([
            "BCA2490,First Duplicate,dup1@example.com,9876543210,Male,2005-01-01,BCA,1,Addr1",
            "BCA2490,Second Duplicate,dup2@example.com,9876543211,Female,2005-02-02,BCA,2,Addr2",
        ])

        resp = admin_client.post(
            "/students/import",
            data={"file": (io.BytesIO(csv_bytes), "in_file_dup.csv")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200
        assert b"1 Imported Successfully" in resp.data
        assert b"1 Skipped" in resp.data
        assert b"Student ID is duplicate within this file" in resp.data

    def test_short_row_with_fewer_columns_handled_gracefully(self, admin_client, db):
        """
        Simulates an Excel/Sheets export where trailing empty cells were dropped.
        Must return 200 (not 500), skip the short row, and import valid rows.
        """
        # Row 2 has missing trailing fields (only student_id, student_name provided)
        csv_bytes = _make_csv([
            "BCA2491,Valid Short Test,short1@example.com,9876543210,Male,2005-01-01,BCA,1,Addr1",
            "BCA2492,Short Incomplete Row",  # Missing email, phone, gender, dob, course, semester, address
            "BCA2493,Valid Short Test Two,short2@example.com,9876543211,Female,2005-02-02,BCA,2,Addr2",
        ])

        resp = admin_client.post(
            "/students/import",
            data={"file": (io.BytesIO(csv_bytes), "short_rows.csv")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200
        assert b"2 Imported Successfully" in resp.data
        assert b"1 Skipped" in resp.data
        assert b"Course is required" in resp.data or b"Email is required" in resp.data

        assert database.get_student_by_student_id("BCA2491") is not None
        assert database.get_student_by_student_id("BCA2493") is not None

    def test_invalid_headers_rejects_whole_file(self, admin_client, db):
        bad_csv = "id,name,email_addr,phone_num\n1,Test,t@example.com,1234567890\n".encode("utf-8")

        resp = admin_client.post(
            "/students/import",
            data={"file": (io.BytesIO(bad_csv), "bad_headers.csv")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200
        assert b"Invalid CSV headers" in resp.data
        assert database.get_student_by_student_id("1") is None

    def test_non_csv_extension_rejected(self, admin_client):
        data = b"some plain text file"
        resp = admin_client.post(
            "/students/import",
            data={"file": (io.BytesIO(data), "document.pdf")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200
        assert b"Only .csv files are supported" in resp.data

    def test_oversized_file_rejected(self, admin_client):
        # Create dummy CSV > 1MB
        large_content = HEADER + ("BCA9999,Large Student,l@ex.com,9876543210,Male,2005-01-01,BCA,1,Addr\n" * 16000)
        csv_bytes = large_content.encode("utf-8")
        assert len(csv_bytes) > 1 * 1024 * 1024

        resp = admin_client.post(
            "/students/import",
            data={"file": (io.BytesIO(csv_bytes), "large.csv")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200
        assert b"exceeds maximum allowed limit of 1MB" in resp.data
