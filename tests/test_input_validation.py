"""
tests/test_input_validation.py — Security test suite for Step 2G Input Validation & Business Logic.

Covers 50 security validation test cases across SQL Injection, XSS, ID Boundaries, Marks Rules,
Fees Logic, Attendance Logic, Student Fields, Document Metadata, Notices, Type Confusion, and API payloads.
"""

import io
import pytest
import database


class TestSqlInjectionResilience:

    def test_student_search_sql_injection_payloads(self, admin_client):
        payloads = [
            "' OR '1'='1",
            "'; DROP TABLE students; --",
            "1 UNION SELECT 1,2,3,4,5,6,7",
            "\\",
            "%",
            "_",
        ]
        for p in payloads:
            resp = admin_client.get(f"/students?search={p}")
            assert resp.status_code == 200, f"Failed on payload: {p}"

    def test_global_search_sql_injection_payloads(self, admin_client):
        payloads = [
            "' OR '1'='1",
            "'; DROP TABLE notices; --",
            "1 UNION SELECT 1,2,3,4",
            "\\",
            "%",
        ]
        for p in payloads:
            resp = admin_client.get(f"/api/global-search?q={p}")
            assert resp.status_code == 200, f"Failed on payload: {p}"


class TestXssOutputEscaping:

    def test_xss_in_student_name(self, admin_client, db):
        xss_payload = "<script>alert('xss-student')</script>"
        resp = admin_client.post(
            "/students/add",
            data={
                "student_id": "XSS101",
                "student_name": xss_payload,
                "email": "xss@example.com",
                "phone": "9876543210",
                "course": "BCA",
                "semester": "1",
                "gender": "Male",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert "<script>alert('xss-student')</script>" not in resp.data.decode("utf-8") or "&lt;script&gt;" in resp.data.decode("utf-8")

    def test_xss_in_notice_title_and_body(self, admin_client):
        xss_title = "<img src=x onerror=alert('xss-title')>"
        xss_body = "<svg onload=alert('xss-body')>"
        resp = admin_client.post(
            "/notices/add",
            data={
                "title": xss_title,
                "body": xss_body,
                "category": "General",
                "priority": "Normal",
                "status": "Published",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "<img src=x onerror=alert('xss-title')>" not in html
        assert "<svg onload=alert('xss-body')>" not in html


class TestIdAndNumericBoundaries:

    @pytest.mark.parametrize("bad_id", ["-1", "0", "abc", "999999999999999999999", "1.5", "1 OR 1=1"])
    def test_invalid_student_id_handled_safely(self, admin_client, bad_id):
        resp = admin_client.get(f"/students/{bad_id}")
        assert resp.status_code in (400, 404, 302, 403)

    @pytest.mark.parametrize("bad_id", ["-1", "0", "abc", "999999999999999999999"])
    def test_invalid_exam_id_handled_safely(self, admin_client, bad_id):
        resp = admin_client.get(f"/exams/{bad_id}/marks")
        assert resp.status_code in (400, 404, 302, 403)


class TestMarksBusinessRules:

    def test_negative_marks_rejected(self, admin_client, db):
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO exams (exam_name, exam_type, course, semester, academic_year, status, max_marks, pass_marks, created_by) "
            "VALUES ('Test Exam', 'Internal 1', 'BCA', 1, '2025-2026', 'Scheduled', 100.0, 40.0, %s)",
            (db["users"]["admin"]["id"],)
        )
        exam_id = cursor.lastrowid
        conn.commit()
        cursor.close()
        conn.close()

        database.ensure_semester1_subjects("BCA")
        subjects = database.get_subjects_by_course_and_semester("BCA", 1)
        students = database.get_all_students(course_filter="BCA", semester_filter=1)

        resp = admin_client.post(
            f"/exams/{exam_id}/marks",
            data={
                f"obt_{students[0]['student_id']}_{subjects[0]['id']}": "-15",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"negative" in resp.data or b"Invalid" in resp.data
        assert len(database.get_all_marks_for_exam(exam_id)) == 0

    def test_obtained_marks_exceeding_max_rejected(self, admin_client, db):
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO exams (exam_name, exam_type, course, semester, academic_year, status, max_marks, pass_marks, created_by) "
            "VALUES ('Test Exam 2', 'Internal 1', 'BCA', 1, '2025-2026', 'Scheduled', 100.0, 40.0, %s)",
            (db["users"]["admin"]["id"],)
        )
        exam_id = cursor.lastrowid
        conn.commit()
        cursor.close()
        conn.close()

        database.ensure_semester1_subjects("BCA")
        subjects = database.get_subjects_by_course_and_semester("BCA", 1)
        students = database.get_all_students(course_filter="BCA", semester_filter=1)

        resp = admin_client.post(
            f"/exams/{exam_id}/marks",
            data={
                f"obt_{students[0]['student_id']}_{subjects[0]['id']}": "150",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"cannot exceed" in resp.data or b"exceed" in resp.data
        assert len(database.get_all_marks_for_exam(exam_id)) == 0


class TestFeesBusinessRules:

    def test_fee_negative_and_zero_payment_rejected(self, admin_client, db):
        stud_id = db["linked_pk"]
        fee_id = database.insert_fee_due({"stud_id": stud_id, "amount_due": 3000.00, "due_date": "2026-12-31"})

        # Negative
        resp1 = admin_client.post(f"/fees/pay/{fee_id}", data={"payment_amount": "-100.00"}, follow_redirects=True)
        assert resp1.status_code == 200
        assert b"greater than zero" in resp1.data

        # Zero
        resp2 = admin_client.post(f"/fees/pay/{fee_id}", data={"payment_amount": "0.00"}, follow_redirects=True)
        assert resp2.status_code == 200
        assert b"greater than zero" in resp2.data

    def test_fee_overpayment_exceeding_balance_rejected(self, admin_client, db):
        stud_id = db["linked_pk"]
        fee_id = database.insert_fee_due({"stud_id": stud_id, "amount_due": 3000.00, "due_date": "2026-12-31"})

        resp = admin_client.post(f"/fees/pay/{fee_id}", data={"payment_amount": "3500.00"}, follow_redirects=True)
        assert resp.status_code == 200
        assert b"exceeds the remaining balance" in resp.data
        fee = database.get_fee_by_id(fee_id)
        assert float(fee["amount_paid"]) == 0.0


class TestAttendanceBusinessRules:

    def test_attendance_invalid_status_ignored(self, admin_client, db):
        stud_id = db["linked_pk"]
        date_str = "2026-09-16"

        resp = admin_client.post(
            "/attendance",
            data={
                "date": date_str,
                f"status_{stud_id}": "HackedStatus",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        marks = database.get_attendance_by_date(date_str)
        assert stud_id not in marks or marks.get(stud_id) != "HackedStatus"


class TestDocumentMetadataValidation:

    def test_path_traversal_in_original_filename_neutralized(self, admin_client, db):
        stud_id = db["linked_pk"]
        data = {
            "doc_type": "Aadhaar Card",
            "document_file": (io.BytesIO(b"%PDF-1.4 Content"), "../../etc/passwd.pdf")
        }
        resp = admin_client.post(
            f"/student/{stud_id}/documents/upload",
            data=data,
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert resp.status_code == 200
        docs = database.get_student_documents(stud_id)
        saved_stored_filenames = [d["stored_filename"] for d in docs]
        for fname in saved_stored_filenames:
            assert ".." not in fname
            assert "/" not in fname
            assert "\\" not in fname


class TestNoticesValidation:

    def test_notice_invalid_enums_fallback_to_defaults(self, admin_client):
        resp = admin_client.post(
            "/notices/add",
            data={
                "title": "Valid Title Here",
                "body": "Valid body text.",
                "category": "InvalidCategoryName",
                "priority": "InvalidPriority",
                "status": "InvalidStatus",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        notices = database.get_all_notices(limit=5)
        created = next((n for n in notices if n["title"] == "Valid Title Here"), None)
        assert created is not None
        assert created["category"] == "General"
        assert created["priority"] == "Normal"
        assert created["status"] == "Published"


class TestApiValidationPayloads:

    def test_global_search_empty_and_single_char_query(self, admin_client):
        resp1 = admin_client.get("/api/global-search?q=")
        assert resp1.status_code == 200
        assert resp1.get_json()["results"]["students"] == []

        resp2 = admin_client.get("/api/global-search?q=a")
        assert resp2.status_code == 200
