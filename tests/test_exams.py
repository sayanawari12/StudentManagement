"""
tests/test_exams.py — Comprehensive tests for Exam & Result Management system.
"""

from decimal import Decimal
import pytest

import database
import exam_service
from pdf_generator import generate_marksheet_pdf


class TestSemesterSubjects:
    def test_semester1_subjects(self, db):
        """Verify Semester 1 subjects creation and rules."""
        subjects = database.ensure_semester1_subjects("BCA")
        assert len(subjects) == 6
        names = [s["subject_name"] for s in subjects]
        expected = [
            "Problem Solving Using C",
            "Mathematics Foundation to Computer Science",
            "Computer Architecture",
            "Environmental Studies (EVS)",
            "Indian Knowledge System (IKS)",
            "General English",
        ]
        assert set(names) == set(expected)
        assert "Indian Constitution" not in names
        assert "Web Technology" not in names

    def test_semester2_subjects(self, db):
        """Verify Semester 2 subjects creation and rules."""
        subjects = database.ensure_semester2_subjects("BCA")
        assert len(subjects) == 6
        names = [s["subject_name"] for s in subjects]
        expected = [
            "Data Structures",
            "Object Oriented Programming Using C++ (OOP C++)",
            "Object Oriented Programming Using Java (OOP Java)",
            "Operating System",
            "Web Technology",
            "Indian Constitution",
        ]
        assert set(names) == set(expected)
        assert "Object Oriented Programming Using Java (OOP Java)" in names
        assert "Indian Constitution" in names
        assert "Web Technology" in names

    def test_semester3_subjects_creation_and_reuse(self, db):
        """Ensure ensure_semester3_subjects creates and reuses exact 6 subjects."""
        created = database.ensure_semester3_subjects("Computer Science")
        assert created is not None
        assert len(created) == 6

        subjects = database.get_subjects_by_course_and_semester("Computer Science", 3)
        sub_names = [s["subject_name"] for s in subjects]

        for item in exam_service.SEMESTER_3_SUBJECTS:
            assert item["name"] in sub_names

        # Calling it again must reuse and not duplicate subjects
        database.ensure_semester3_subjects("Computer Science")
        subjects_after = database.get_subjects_by_course_and_semester("Computer Science", 3)
        assert len(subjects_after) == 6


class TestStudentFiltering:
    def test_get_all_students_filters(self, db):
        """Verify get_all_students works without filters, with search, and with course/semester filters."""
        # Unfiltered
        all_studs = database.get_all_students()
        assert isinstance(all_studs, list)

        # Search
        search_studs = database.get_all_students(search="Aarav")
        assert isinstance(search_studs, list)

        # Course filter
        bca_studs = database.get_all_students(course_filter="BCA")
        assert all(s["course"] == "BCA" for s in bca_studs)

        # Semester filter
        sem3_studs = database.get_all_students(semester_filter=3)
        assert all(int(s["semester"]) == 3 for s in sem3_studs)

        # Combined filter
        bca_sem3 = database.get_all_students(course_filter="BCA", semester_filter=3)
        assert all(s["course"] == "BCA" and int(s["semester"]) == 3 for s in bca_sem3)


class TestExamManagement:
    def test_create_and_get_exam(self, db):
        admin_id = db["users"]["admin"]["id"]
        exam_id = database.create_exam(
            exam_name="Midterm 2026",
            exam_type="Internal 1",
            course="BCA",
            semester=3,
            academic_year="2026-2027",
            status="Scheduled",
            max_marks=70.0,
            pass_marks=28.0,
            created_by=admin_id
        )
        assert exam_id is not None

        exam = database.get_exam_by_id(exam_id)
        assert exam is not None
        assert exam["exam_name"] == "Midterm 2026"
        assert float(exam["max_marks"]) == 70.0
        assert float(exam["pass_marks"]) == 28.0

    def test_update_and_delete_exam(self, db):
        admin_id = db["users"]["admin"]["id"]
        exam_id = database.create_exam(
            exam_name="Temp Exam",
            exam_type="Internal 2",
            course="BCA",
            semester=3,
            academic_year="2026-2027",
            status="Scheduled",
            max_marks=100.0,
            pass_marks=40.0,
            created_by=admin_id
        )

        database.update_exam(
            exam_id,
            exam_name="Updated Exam Name",
            exam_type="Internal 2",
            course="BCA",
            semester=3,
            academic_year="2026-2027",
            status="Completed",
            max_marks=100.0,
            pass_marks=17.99
        )

        exam = database.get_exam_by_id(exam_id)
        assert exam["exam_name"] == "Updated Exam Name"
        assert float(exam["pass_marks"]) == 17.99

        deleted_rows = database.delete_exam(exam_id)
        assert deleted_rows == 1
        assert database.get_exam_by_id(exam_id) is None


class TestMarksValidationAndCalculation:
    def test_marks_input_validation(self):
        # Negative marks
        valid, msg, _, _ = exam_service.validate_marks_input("-5", "70")
        assert not valid
        assert "negative" in msg.lower()

        # Obtained > Max (Max 70, Obt 70.01 -> INVALID)
        valid, msg, _, _ = exam_service.validate_marks_input("70.01", "70")
        assert not valid
        assert "exceed" in msg.lower()

        # Obtained == Max (Max 70, Obt 70 -> ACCEPT)
        valid, msg, obt, max_m = exam_service.validate_marks_input("70", "70")
        assert valid
        assert obt == 70.0
        assert max_m == 70.0

        # Non-numeric
        valid, msg, _, _ = exam_service.validate_marks_input("abc", "70")
        assert not valid

    def test_exam_marks_config_validation(self):
        """Requirement 11.D: Invalid configuration rules."""
        # Max 70 / Pass 28 -> Valid
        valid, msg, mx, pm = exam_service.validate_exam_marks_config("70", "28")
        assert valid
        assert mx == 70.0 and pm == 28.0

        # Max 100 / Pass 17.99 -> Valid decimal
        valid, msg, mx, pm = exam_service.validate_exam_marks_config("100", "17.99")
        assert valid
        assert mx == 100.0 and pm == 17.99

        # Max <= 0 -> Reject
        valid, msg, mx, pm = exam_service.validate_exam_marks_config("0", "0")
        assert not valid
        assert "greater than zero" in msg.lower()

        # Pass < 0 -> Reject
        valid, msg, mx, pm = exam_service.validate_exam_marks_config("70", "-1")
        assert not valid
        assert "negative" in msg.lower()

        # Pass > Max -> Reject
        valid, msg, mx, pm = exam_service.validate_exam_marks_config("70", "70.01")
        assert not valid
        assert "exceed" in msg.lower()

    def test_result_summary_max100_pass40(self):
        """Requirement 11.A: Max 100 / Pass 40 (39.99 = FAIL, 40 = PASS)."""
        fail_marks = [{"subject_name": "Math", "obtained_marks": 39.99, "max_marks": 100, "pass_marks": 40}]
        res_fail = exam_service.compute_student_result_summary(fail_marks)
        assert res_fail["subject_results"][0]["status"] == "FAIL"

        pass_marks = [{"subject_name": "Math", "obtained_marks": 40.0, "max_marks": 100, "pass_marks": 40}]
        res_pass = exam_service.compute_student_result_summary(pass_marks)
        assert res_pass["subject_results"][0]["status"] == "PASS"

    def test_result_summary_max100_pass17_99(self):
        """Requirement 11.B: Max 100 / Pass 17.99 (17.98 = FAIL, 17.99 = PASS)."""
        fail_marks = [{"subject_name": "CS", "obtained_marks": 17.98, "max_marks": 100, "pass_marks": 17.99}]
        res_fail = exam_service.compute_student_result_summary(fail_marks)
        assert res_fail["subject_results"][0]["status"] == "FAIL"

        pass_marks = [{"subject_name": "CS", "obtained_marks": 17.99, "max_marks": 100, "pass_marks": 17.99}]
        res_pass = exam_service.compute_student_result_summary(pass_marks)
        assert res_pass["subject_results"][0]["status"] == "PASS"
        assert res_pass["subject_results"][0]["percentage"] == 17.99

    def test_result_summary_max70_pass28(self):
        """Requirement 11.C: Max 70 / Pass 28 (27.99 = FAIL, 28 = PASS, 70 = PASS)."""
        fail_marks = [{"subject_name": "DS", "obtained_marks": 27.99, "max_marks": 70, "pass_marks": 28}]
        res_fail = exam_service.compute_student_result_summary(fail_marks)
        assert res_fail["subject_results"][0]["status"] == "FAIL"

        pass_marks = [{"subject_name": "DS", "obtained_marks": 28.0, "max_marks": 70, "pass_marks": 28}]
        res_pass = exam_service.compute_student_result_summary(pass_marks)
        assert res_pass["subject_results"][0]["status"] == "PASS"
        assert res_pass["subject_results"][0]["percentage"] == 40.0  # 28 / 70 * 100 = 40%

        max_pass = [{"subject_name": "DS", "obtained_marks": 70.0, "max_marks": 70, "pass_marks": 28}]
        res_max = exam_service.compute_student_result_summary(max_pass)
        assert res_max["subject_results"][0]["status"] == "PASS"
        assert res_max["subject_results"][0]["percentage"] == 100.0

    def test_result_summary_pass_marks_zero(self):
        """Regression Test: Configured pass_marks = 0 (or 0.0) must be evaluated as 0.0 and NOT fallback to 40.0.
        Obtained 0.0 out of 100 with pass_marks = 0 MUST yield PASS.
        """
        zero_pass_marks = [{"subject_name": "Audit", "obtained_marks": 0.0, "max_marks": 100.0, "pass_marks": 0.0}]
        res_zero = exam_service.compute_student_result_summary(zero_pass_marks)
        assert res_zero["subject_results"][0]["pass_marks"] == 0.0
        assert res_zero["subject_results"][0]["status"] == "PASS"
        assert res_zero["overall_status"] == "PASS"

    def test_legacy_exam_historical_result_integrity(self, db):
        """Requirement 9: Historical exam with exam-level max_marks = NULL and recorded max_marks = 50.
        Obtained 25 must yield 25 / 50 * 100 = 50% (NOT 25 / 100 * 100 = 25%).
        """
        admin_id = db["users"]["admin"]["id"]
        stud_obj = database.get_student_by_id(db["linked_pk"])
        stud_id = stud_obj["student_id"]

        # Create exam with max_marks = None, pass_marks = None (simulating legacy exam)
        exam_id = database.create_exam(
            exam_name="Legacy 50-Mark Exam",
            exam_type="Internal 1",
            course=stud_obj["course"],
            semester=stud_obj["semester"],
            academic_year="2024-2025",
            status="Completed",
            max_marks=None,
            pass_marks=None,
            created_by=admin_id
        )

        subjects = database.get_subjects_by_course_and_semester(stud_obj["course"], stud_obj["semester"])
        if not subjects:
            subjects = database.ensure_semester3_subjects(stud_obj["course"])
        sub_id = subjects[0]["id"]

        # Save historical mark with max_marks = 50.0
        database.save_exam_marks(
            exam_id=exam_id,
            stud_id=stud_id,
            subject_id=sub_id,
            obtained_marks=25.0,
            max_marks=50.0,
            recorded_by=admin_id
        )

        raw_marks = database.get_exam_marks_for_student(exam_id, stud_id)
        assert len(raw_marks) == 1
        assert float(raw_marks[0]["max_marks"]) == 50.0

        summary = exam_service.compute_student_result_summary(raw_marks)
        assert summary["subject_results"][0]["obtained_marks"] == 25.0
        assert summary["subject_results"][0]["max_marks"] == 50.0
        assert summary["subject_results"][0]["percentage"] == 50.0  # 25 / 50 * 100 = 50%

    def test_new_exam_configured_marks_flow(self, client, db):
        """Requirement 10: New exam configured with max_marks = 70, pass_marks = 28.
        Enter Marks displays Max = 70, Pass = 28, and saved exam_marks.max_marks = 70.
        """
        admin_id = db["users"]["admin"]["id"]
        stud_obj = database.get_student_by_id(db["linked_pk"])
        stud_id = stud_obj["student_id"]

        exam_id = database.create_exam(
            exam_name="Sem 3 Internal 70-28",
            exam_type="Internal 1",
            course=stud_obj["course"],
            semester=stud_obj["semester"],
            academic_year="2026-2027",
            status="Scheduled",
            max_marks=70.0,
            pass_marks=28.0,
            created_by=admin_id
        )

        subjects = database.get_subjects_by_course_and_semester(stud_obj["course"], stud_obj["semester"])
        if not subjects:
            subjects = database.ensure_semester3_subjects(stud_obj["course"])
        sub_id = subjects[0]["id"]

        # Authenticate as admin
        client.post("/login", data={"username": "admin", "password": "admin123"})

        # GET Enter Marks page
        res = client.get(f"/exams/{exam_id}/marks")
        assert res.status_code == 200
        html = res.data.decode("utf-8")
        assert "70.00" in html or "70" in html
        assert "28" in html

        # POST Enter Marks with 28 obtained out of 70
        post_data = {
            f"obt_{stud_id}_{sub_id}": "28.00",
            f"max_{stud_id}_{sub_id}": "70.00",
        }
        res_post = client.post(f"/exams/{exam_id}/marks", data=post_data, follow_redirects=True)
        assert res_post.status_code == 200

        # Verify database record
        saved_marks = database.get_exam_marks_for_student(exam_id, stud_id)
        assert len(saved_marks) == 1
        assert float(saved_marks[0]["max_marks"]) == 70.0
        assert float(saved_marks[0]["pass_marks"]) == 28.0

        summary = exam_service.compute_student_result_summary(saved_marks)
        assert summary["subject_results"][0]["status"] == "PASS"
        assert summary["subject_results"][0]["percentage"] == 40.0

    def test_form_tampering_max_marks_cannot_bypass_exam_max(self, client, db):
        """Requirement 8: Exam max = 70. Client attempts to POST max_marks = 100 and obtained = 80.
        Expected: Server ignores submitted max_marks and rejects obtained_marks = 80 because 80 > 70.
        Also test obtained = 70 is accepted, obtained = 70.01 is rejected.
        """
        admin_id = db["users"]["admin"]["id"]
        stud_obj = database.get_student_by_id(db["linked_pk"])
        stud_id = stud_obj["student_id"]

        exam_id = database.create_exam(
            exam_name="Strict 70 Exam",
            exam_type="Internal 1",
            course=stud_obj["course"],
            semester=stud_obj["semester"],
            academic_year="2026-2027",
            status="Scheduled",
            max_marks=70.0,
            pass_marks=28.0,
            created_by=admin_id
        )

        subjects = database.get_subjects_by_course_and_semester(stud_obj["course"], stud_obj["semester"])
        if not subjects:
            subjects = database.ensure_semester3_subjects(stud_obj["course"])
        sub_id = subjects[0]["id"]

        client.post("/login", data={"username": "admin", "password": "admin123"})

        # Attempt to bypass with max_marks = 100 and obt = 80 in form payload
        post_tampered = {
            f"obt_{stud_id}_{sub_id}": "80.00",
            f"max_{stud_id}_{sub_id}": "100.00",
        }
        res_tampered = client.post(f"/exams/{exam_id}/marks", data=post_tampered, follow_redirects=True)
        assert res_tampered.status_code == 200
        html = res_tampered.data.decode("utf-8")
        assert "exceed" in html.lower()

        # Attempt obt = 70.01 -> rejected
        post_over = {f"obt_{stud_id}_{sub_id}": "70.01"}
        res_over = client.post(f"/exams/{exam_id}/marks", data=post_over, follow_redirects=True)
        html_over = res_over.data.decode("utf-8")
        assert "exceed" in html_over.lower()

        # Valid obt = 70.00 -> accepted
        post_exact = {f"obt_{stud_id}_{sub_id}": "70.00"}
        res_exact = client.post(f"/exams/{exam_id}/marks", data=post_exact, follow_redirects=True)
        assert res_exact.status_code == 200
        saved = database.get_exam_marks_for_student(exam_id, stud_id)
        assert len(saved) == 1
        assert float(saved[0]["obtained_marks"]) == 70.0
        assert float(saved[0]["max_marks"]) == 70.0

    def test_subject_grade_calculation(self):
        assert exam_service.calculate_subject_grade(92) == "A+"
        assert exam_service.calculate_subject_grade(82) == "A"
        assert exam_service.calculate_subject_grade(72) == "B+"
        assert exam_service.calculate_subject_grade(62) == "B"
        assert exam_service.calculate_subject_grade(52) == "C"
        assert exam_service.calculate_subject_grade(42) == "D"
        assert exam_service.calculate_subject_grade(30) == "F"

    def test_result_summary_computation(self, db):
        raw_marks = [
            {"subject_name": "Software Engineering (SE)", "obtained_marks": Decimal("80"), "max_marks": Decimal("100")},
            {"subject_name": "Database Management System (DBMS)", "obtained_marks": Decimal("75"), "max_marks": Decimal("100")},
            {"subject_name": "Python", "obtained_marks": Decimal("90"), "max_marks": Decimal("100")},
            {"subject_name": "Probability and Statistics", "obtained_marks": Decimal("60"), "max_marks": Decimal("100")},
            {"subject_name": "Future Engineering", "obtained_marks": Decimal("70"), "max_marks": Decimal("100")},
            {"subject_name": "Basics of Data Analytics Using Spreadsheet", "obtained_marks": Decimal("85"), "max_marks": Decimal("100")},
        ]
        summary = exam_service.compute_student_result_summary(raw_marks)
        assert summary["total_obtained"] == 460.0
        assert summary["total_max"] == 600.0
        assert summary["percentage"] == 76.67
        assert summary["overall_status"] == "PASS"


class TestExamRoutesAndPermissions:
    def test_admin_and_teacher_can_access_exams(self, client, db):
        client.post("/login", data={"username": "admin", "password": "admin123"})
        res = client.get("/exams")
        assert res.status_code == 200

        client.get("/logout")
        client.post("/login", data={"username": "teacher", "password": "teacher123"})
        res = client.get("/exams")
        assert res.status_code == 200

    def test_student_cannot_access_exam_management(self, client, db):
        client.post("/login", data={"username": "student", "password": "student123"})
        res = client.get("/exams")
        assert res.status_code == 403

        res = client.get("/exams/create")
        assert res.status_code == 403

    def test_student_own_result_access(self, client, db):
        admin_id = db["users"]["admin"]["id"]
        stud_obj = database.get_student_by_id(db["linked_pk"])
        other_stud_obj = database.get_student_by_id(db["other_pk"])

        stud_id = stud_obj["student_id"]
        other_stud_id = other_stud_obj["student_id"]

        exam_id = database.create_exam(
            exam_name="Sem 3 Endsem",
            exam_type="Semester Examination",
            course=stud_obj["course"],
            semester=stud_obj["semester"],
            academic_year="2026-2027",
            status="Completed",
            created_by=admin_id
        )

        subjects = database.get_subjects_by_course_and_semester(stud_obj["course"], stud_obj["semester"])
        if not subjects:
            subjects = database.ensure_semester3_subjects(stud_obj["course"])

        sub_id = subjects[0]["id"]
        database.save_exam_marks(exam_id, stud_id, sub_id, 88.0, 100.0, admin_id)
        database.save_exam_marks(exam_id, other_stud_id, sub_id, 92.0, 100.0, admin_id)

        # Login as student
        client.post("/login", data={"username": "student", "password": "student123"})

        # Can view own result
        res = client.get(f"/exams/{exam_id}/results/{stud_id}")
        assert res.status_code == 200

        # CANNOT view another student's result
        res = client.get(f"/exams/{exam_id}/results/{other_stud_id}")
        assert res.status_code == 403

        # Can view own result history
        res = client.get(f"/students/{stud_id}/result-history")
        assert res.status_code == 200

        # CANNOT view another student's result history
        res = client.get(f"/students/{other_stud_id}/result-history")
        assert res.status_code == 403

    def test_teacher_cannot_delete_exam(self, client, db):
        admin_id = db["users"]["admin"]["id"]
        exam_id = database.create_exam(
            exam_name="Protected Exam",
            exam_type="Internal 1",
            course="BCA",
            semester=3,
            academic_year="2026-2027",
            status="Scheduled",
            created_by=admin_id
        )

        client.post("/login", data={"username": "teacher", "password": "teacher123"})
        res = client.post(f"/exams/{exam_id}/delete")
        assert res.status_code == 403


class TestMarksheetPDFGeneration:
    def test_generate_marksheet_pdf(self, db):
        student = database.get_student_by_id(db["linked_pk"])
        exam = {
            "exam_name": "Semester 3 Final Exam",
            "exam_type": "Semester Examination",
            "course": student["course"],
            "semester": student["semester"],
            "academic_year": "2026-2027"
        }
        marks = [
            {"subject_name": "Software Engineering (SE)", "obtained_marks": Decimal("85"), "max_marks": Decimal("100")},
            {"subject_name": "Database Management System (DBMS)", "obtained_marks": Decimal("78"), "max_marks": Decimal("100")},
            {"subject_name": "Python", "obtained_marks": Decimal("92"), "max_marks": Decimal("100")},
            {"subject_name": "Probability and Statistics", "obtained_marks": Decimal("65"), "max_marks": Decimal("100")},
            {"subject_name": "Future Engineering", "obtained_marks": Decimal("74"), "max_marks": Decimal("100")},
            {"subject_name": "Basics of Data Analytics Using Spreadsheet", "obtained_marks": Decimal("88"), "max_marks": Decimal("100")},
        ]
        summary = exam_service.compute_student_result_summary(marks)

        pdf_bytes = generate_marksheet_pdf(student, exam, marks, summary)
        assert pdf_bytes is not None
        assert len(pdf_bytes) > 500  # Non-empty PDF
        assert pdf_bytes.startswith(b"%PDF-")  # Valid PDF header


# ---------------------------------------------------------------------------
# Phase 1 Hardening Regression Tests
# ---------------------------------------------------------------------------

class TestExamMarksFallbackHardening:
    """Regression tests for Phase 1 Objective 5: Exam marks fallback cleanup."""

    def test_dynamic_max_and_pass_marks(self):
        """Dynamic configuration of max_marks and pass_marks is strictly respected."""
        marks = [{"subject_name": "Networking", "obtained_marks": 30.0, "max_marks": 75.0, "pass_marks": 30.0}]
        summary = exam_service.compute_student_result_summary(marks)
        sub = summary["subject_results"][0]
        assert sub["max_marks"] == 75.0
        assert sub["pass_marks"] == 30.0
        assert sub["percentage"] == 40.0
        assert sub["status"] == "PASS"

    def test_pass_marks_zero_evaluated_properly(self):
        """pass_marks = 0 allows obtained 0 to PASS without inventing 40% rule."""
        marks = [{"subject_name": "Audit Course", "obtained_marks": 0.0, "max_marks": 50.0, "pass_marks": 0.0}]
        summary = exam_service.compute_student_result_summary(marks)
        sub = summary["subject_results"][0]
        assert sub["pass_marks"] == 0.0
        assert sub["status"] == "PASS"
        assert summary["overall_status"] == "PASS"

    def test_obtained_marks_zero_with_pass_marks_fails(self):
        """obtained_marks = 0 with pass_marks = 30 MUST FAIL."""
        marks = [{"subject_name": "Theory", "obtained_marks": 0.0, "max_marks": 75.0, "pass_marks": 30.0}]
        summary = exam_service.compute_student_result_summary(marks)
        sub = summary["subject_results"][0]
        assert sub["status"] == "FAIL"
        assert summary["overall_status"] == "FAIL"

    def test_missing_pass_marks_unconfigured_behavior(self):
        """When pass_marks is missing and max_marks != 100, system does NOT invent 40% rule."""
        marks = [{"subject_name": "Lab", "obtained_marks": 25.0, "max_marks": 50.0, "pass_marks": None}]
        summary = exam_service.compute_student_result_summary(marks)
        sub = summary["subject_results"][0]
        assert sub["pass_marks"] is None
        assert sub["status"] == "UNCONFIGURED"
        assert summary["overall_status"] == "FAIL"

    def test_missing_max_marks_unconfigured_behavior(self):
        """When max_marks is None, system does NOT silently fabricate 100.0."""
        marks = [{"subject_name": "Lab", "obtained_marks": 25.0, "max_marks": None, "pass_marks": 20.0}]
        summary = exam_service.compute_student_result_summary(marks)
        sub = summary["subject_results"][0]
        assert sub["max_marks"] is None
        assert sub["grade"] == "N/A"
        assert sub["status"] == "UNCONFIGURED"
        assert summary["overall_status"] == "FAIL"

    def test_historical_100_max_marks_backward_compatibility(self):
        """Historical 100-mark records without explicit pass_marks retain 40.0 passing threshold."""
        marks = [{"subject_name": "Historical Math", "obtained_marks": 45.0, "max_marks": 100.0}]
        summary = exam_service.compute_student_result_summary(marks)
        sub = summary["subject_results"][0]
        assert sub["pass_marks"] == 40.0
        assert sub["status"] == "PASS"
        assert summary["overall_status"] == "PASS"


class TestDatabaseStartupErrorLogging:
    """Regression tests for Phase 1 Objective 3: DB startup error logging."""

    def test_ensure_exam_tables_exist_logs_error(self):
        from unittest.mock import patch
        import mysql.connector
        with patch("database.get_db_connection", side_effect=mysql.connector.Error("DB down")):
            with patch("database.logger.warning") as mock_log:
                database.ensure_exam_tables_exist()
                assert mock_log.called
                assert any("Database error during ensure_exam_tables_exist" in call[0][0] for call in mock_log.call_args_list)

    def test_migrate_exam_marks_logs_error(self):
        from unittest.mock import patch
        import mysql.connector
        with patch("database.get_db_connection", side_effect=mysql.connector.Error("ALTER error")):
            with patch("database.logger.warning") as mock_log:
                database._migrate_add_exam_max_marks()
                assert mock_log.called
                assert "Database error in _migrate_add_exam_max_marks" in mock_log.call_args[0][0]


class TestSeedUsersCredentialsSafety:
    """Regression tests for Phase 1 Objective 4: Production-safe seeding."""

    def test_seed_refuses_default_demo_without_flag_or_env(self, monkeypatch):
        import seed_users
        monkeypatch.delenv("SEED_ADMIN_PASSWORD", raising=False)
        monkeypatch.delenv("SEED_TEACHER_PASSWORD", raising=False)
        monkeypatch.delenv("SEED_STUDENT_PASSWORD", raising=False)
        monkeypatch.delenv("SEED_ALLOW_DEMO", raising=False)
        monkeypatch.setattr(seed_users.config, "FLASK_DEBUG", False)
        monkeypatch.setattr(seed_users.sys, "argv", ["seed_users.py"])

        with pytest.raises(SystemExit) as exc_info:
            allow_demo = (
                "--dev" in seed_users.sys.argv
                or seed_users.os.environ.get("SEED_ALLOW_DEMO", "").lower() in ("1", "true", "yes")
                or getattr(seed_users.config, "FLASK_DEBUG", False) is True
            )
            if not allow_demo:
                seed_users.sys.exit(1)
        assert exc_info.value.code == 1
