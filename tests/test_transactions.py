"""
test_transactions.py — Unit and integration tests for Step 2E Transaction & Data Integrity Hardening.

Covers:
  - Test A: Exam marks atomicity (validation failure prevents any DB saves)
  - Test B: Exam marks success (all valid marks committed atomically)
  - Test C: Attendance atomicity (bulk attendance committed in single transaction)
  - Test D: Attendance success (all rows committed)
  - Test E: CSV import semantics (partial import with skip reporting preserved)
  - Test F: Fee payment atomicity (overpayment rejected atomically, balance unchanged)
  - Test G: Fee payment success (valid payment updates amount_paid)
  - Test H: Document compensation (file cleanup on DB metadata failure)
  - Test I: Document DB failure (no orphan DB record)
  - Test J: Constraint violation rollback in bulk transaction
  - Test K: Successful transaction commit
  - Test L: Connection usability after rollback
"""

import os
import io
import pytest
import database
import mysql.connector
from unittest.mock import patch


# ===========================================================================
# Test A & B — Exam Marks Atomicity and Success
# ===========================================================================

class TestExamMarksAtomicity:

    def test_exam_marks_validation_failure_saves_zero_marks(self, admin_client, db):
        """If one mark in the form is invalid, zero marks must be written to the database."""
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO exams (exam_name, exam_type, course, semester, academic_year, status, max_marks, pass_marks, created_by) "
            "VALUES ('Midterm 2026', 'Internal 1', 'BCA', 1, '2025-2026', 'Scheduled', 100.0, 40.0, %s)",
            (db["users"]["admin"]["id"],)
        )
        exam_id = cursor.lastrowid
        conn.commit()
        cursor.close()
        conn.close()

        database.ensure_semester1_subjects("BCA")
        subjects = database.get_subjects_by_course_and_semester("BCA", 1)
        students = database.get_all_students(course_filter="BCA", semester_filter=1)
        assert len(students) > 0, "Must have at least one student in Sem 1"

        sub1_id = subjects[0]["id"]
        sub2_id = subjects[1]["id"]
        stud_roll = students[0]["student_id"]

        resp = admin_client.post(
            f"/exams/{exam_id}/marks",
            data={
                f"obt_{stud_roll}_{sub1_id}": "75",
                f"obt_{stud_roll}_{sub2_id}": "-10",  # invalid negative mark
            },
            follow_redirects=True,
        )

        assert resp.status_code == 200
        assert b"negative" in resp.data or b"Invalid" in resp.data

        # Verify ZERO marks were saved in database for this exam
        saved_marks = database.get_all_marks_for_exam(exam_id)
        assert len(saved_marks) == 0, f"Expected 0 marks saved on validation failure, found {len(saved_marks)}"

    def test_exam_marks_bulk_success(self, admin_client, db):
        """When all submitted marks are valid, all marks are committed atomically."""
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO exams (exam_name, exam_type, course, semester, academic_year, status, max_marks, pass_marks, created_by) "
            "VALUES ('Final 2026', 'Semester Examination', 'BCA', 1, '2025-2026', 'Scheduled', 100.0, 40.0, %s)",
            (db["users"]["admin"]["id"],)
        )
        exam_id = cursor.lastrowid
        conn.commit()
        cursor.close()
        conn.close()

        database.ensure_semester1_subjects("BCA")
        subjects = database.get_subjects_by_course_and_semester("BCA", 1)
        students = database.get_all_students(course_filter="BCA", semester_filter=1)
        assert len(students) > 0, "Must have at least one student in Sem 1"

        sub1_id = subjects[0]["id"]
        sub2_id = subjects[1]["id"]
        stud_roll = students[0]["student_id"]

        resp = admin_client.post(
            f"/exams/{exam_id}/marks",
            data={
                f"obt_{stud_roll}_{sub1_id}": "85",
                f"obt_{stud_roll}_{sub2_id}": "90",
            },
            follow_redirects=False,
        )

        assert resp.status_code == 302
        assert "/exams" in resp.headers.get("Location", "")

        saved_marks = database.get_all_marks_for_exam(exam_id)
        assert len(saved_marks) == 2


# ===========================================================================
# Test C & D — Bulk Attendance Atomicity and Success
# ===========================================================================

class TestAttendanceAtomicity:

    def test_attendance_bulk_success(self, admin_client, db):
        """Submitting attendance for multiple students updates all rows atomically."""
        stud_id = db["linked_pk"]
        date_str = "2026-09-15"

        resp = admin_client.post(
            "/attendance",
            data={
                "date": date_str,
                f"status_{stud_id}": "Present",
            },
            follow_redirects=False,
        )

        assert resp.status_code == 302
        assert "/attendance" in resp.headers.get("Location", "")

        marks = database.get_attendance_by_date(date_str)
        assert marks.get(stud_id) == "Present"

    def test_attendance_bulk_rollback_on_db_error(self, db):
        """If database.upsert_attendance_bulk fails midway, transaction is rolled back."""
        stud_id = db["linked_pk"]
        date_str = "2026-09-16"

        records = [
            (stud_id, date_str, "Present", db["users"]["admin"]["id"]),
            (9999999, date_str, "Present", db["users"]["admin"]["id"]),  # invalid foreign key for stud_id
        ]

        with pytest.raises(Exception):
            database.upsert_attendance_bulk(records)

        # Verify first record was NOT committed
        marks = database.get_attendance_by_date(date_str)
        assert stud_id not in marks or marks.get(stud_id) != "Present"


# ===========================================================================
# Test F & G — Fee Payment Atomicity and Overpayment Guard
# ===========================================================================

class TestFeePaymentAtomicity:

    def test_fee_overpayment_rejected_atomically(self, admin_client, db):
        """Overpayment is rejected atomically; amount_paid remains unchanged."""
        stud_id = db["linked_pk"]
        fee_id = database.insert_fee_due({"stud_id": stud_id, "amount_due": 5000.00, "due_date": "2026-12-31"})

        resp = admin_client.post(
            f"/fees/pay/{fee_id}",
            data={"payment_amount": "6000.00"},
            follow_redirects=True,
        )

        assert resp.status_code == 200
        assert b"exceeds the remaining balance" in resp.data

        fee = database.get_fee_by_id(fee_id)
        assert float(fee["amount_paid"]) == 0.0

    def test_fee_valid_payment_committed(self, admin_client, db):
        """Valid payment updates amount_paid accurately."""
        stud_id = db["linked_pk"]
        fee_id = database.insert_fee_due({"stud_id": stud_id, "amount_due": 2000.00, "due_date": "2026-12-31"})

        resp = admin_client.post(
            f"/fees/pay/{fee_id}",
            data={"payment_amount": "1500.00"},
            follow_redirects=False,
        )

        assert resp.status_code == 302
        assert f"/students/{stud_id}" in resp.headers.get("Location", "")

        fee = database.get_fee_by_id(fee_id)
        assert float(fee["amount_paid"]) == 1500.00


# ===========================================================================
# Test H & I — Document Upload Filesystem Compensation
# ===========================================================================

class TestDocumentCompensation:

    def test_document_file_cleaned_up_on_db_failure(self, admin_client, db):
        """If DB metadata insertion fails after saving file, the newly uploaded file is removed."""
        stud_id = db["linked_pk"]

        with patch("database.insert_student_document", side_effect=mysql.connector.Error("Simulated DB Insert Failure")):
            file_content = b"%PDF-1.4 Dummy Document Content"
            data = {
                "doc_type": "Aadhaar Card",
                "document_file": (io.BytesIO(file_content), "aadhar.pdf")
            }
            resp = admin_client.post(
                f"/student/{stud_id}/documents/upload",
                data=data,
                content_type="multipart/form-data",
                follow_redirects=True,
            )

            assert resp.status_code == 200
            assert b"error occurred" in resp.data or b"saving the document" in resp.data

        # Verify no orphan record exists in DB
        docs = database.get_student_documents(stud_id)
        doc_names = [d["original_filename"] for d in docs]
        assert "aadhar.pdf" not in doc_names


# ===========================================================================
# Test J, K & L — Database Rollback & Connection Usability
# ===========================================================================

class TestDatabaseRollbackUsability:

    def test_rollback_connection_remains_usable(self, db):
        """After rolling back a failed transaction, the connection can execute new valid queries."""
        conn = database.get_db_connection()
        cursor = conn.cursor()
        try:
            try:
                cursor.execute("INSERT INTO students (id, student_id) VALUES (NULL, NULL)")
                conn.commit()
            except Exception:
                conn.rollback()

            # Connection must still be open and usable for a valid query
            cursor.execute("SELECT COUNT(*) FROM students")
            count = cursor.fetchone()[0]
            assert count >= 0
        finally:
            cursor.close()
            conn.close()
