"""
tests/test_exams.py — Comprehensive tests for Exam & Result Management system.
"""

import io
from decimal import Decimal
import pytest

import database
import exam_service
from pdf_generator import generate_marksheet_pdf


class TestSemester3Subjects:
    def test_semester3_subjects_creation_and_reuse(self, db):
        """Ensure ensure_semester3_subjects creates and reuses exact 6 subjects."""
        created = database.ensure_semester3_subjects()
        assert len(created) == 6

        subjects = database.get_subjects_by_course_and_semester("Computer Science", 3)
        sub_names = [s["subject_name"] for s in subjects]

        for expected_name in exam_service.SEMESTER_3_SUBJECTS:
            assert expected_name in sub_names

        # Calling it again must reuse and not duplicate subjects
        created_again = database.ensure_semester3_subjects()
        subjects_after = database.get_subjects_by_course_and_semester("Computer Science", 3)
        assert len(subjects_after) == 6


class TestExamManagement:
    def test_create_and_get_exam(self, db):
        admin_id = db["users"]["admin"]["id"]
        exam_id = database.create_exam(
            exam_name="Sem 3 Midterm",
            exam_type="Internal 1",
            course="Computer Science",
            semester=3,
            academic_year="2026-2027",
            status="Scheduled",
            created_by=admin_id
        )
        assert exam_id > 0

        exam = database.get_exam_by_id(exam_id)
        assert exam is not None
        assert exam["exam_name"] == "Sem 3 Midterm"
        assert exam["exam_type"] == "Internal 1"
        assert exam["course"] == "Computer Science"
        assert exam["semester"] == 3
        assert exam["academic_year"] == "2026-2027"

    def test_update_and_delete_exam(self, db):
        admin_id = db["users"]["admin"]["id"]
        exam_id = database.create_exam(
            exam_name="Temp Exam",
            exam_type="Practical",
            course="Computer Science",
            semester=3,
            academic_year="2026-2027",
            status="Draft",
            created_by=admin_id
        )
        database.update_exam(
            exam_id=exam_id,
            exam_name="Updated Temp Exam",
            exam_type="Practical",
            course="Computer Science",
            semester=3,
            academic_year="2026-2027",
            status="Completed"
        )
        updated = database.get_exam_by_id(exam_id)
        assert updated["exam_name"] == "Updated Temp Exam"
        assert updated["status"] == "Completed"

        database.delete_exam(exam_id)
        assert database.get_exam_by_id(exam_id) is None


class TestMarksValidationAndCalculation:
    def test_marks_input_validation(self):
        # Negative marks
        valid, msg, _, _ = exam_service.validate_marks_input("-5", "100")
        assert not valid
        assert "negative" in msg.lower()

        # Obtained > Max
        valid, msg, _, _ = exam_service.validate_marks_input("105", "100")
        assert not valid
        assert "exceed" in msg.lower()

        # Non-numeric
        valid, msg, _, _ = exam_service.validate_marks_input("abc", "100")
        assert not valid

        # Valid marks
        valid, msg, obt, max_m = exam_service.validate_marks_input("85", "100")
        assert valid
        assert obt == Decimal("85")
        assert max_m == Decimal("100")

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
        assert summary["total_obtained"] == Decimal("460")
        assert summary["total_max"] == Decimal("600")
        assert summary["percentage"] == 76.67
        assert summary["overall_status"] == "PASS"


class TestExamRoutesAndPermissions:
    def test_admin_and_teacher_can_access_exams(self, client, db):
        client.post("/login", data={"username": "admin", "password": "AdminPassword123!"})
        res = client.get("/exams")
        assert res.status_code == 200

        client.get("/logout")
        client.post("/login", data={"username": "teacher", "password": "TeacherPassword123!"})
        res = client.get("/exams")
        assert res.status_code == 200

    def test_student_cannot_access_exam_management(self, client, db):
        client.post("/login", data={"username": "student", "password": "StudentPassword123!"})
        res = client.get("/exams")
        assert res.status_code == 403

        res = client.get("/exams/create")
        assert res.status_code == 403

    def test_student_own_result_access(self, client, db):
        admin_id = db["users"]["admin"]["id"]
        stud_id = db["linked_student_id"]
        other_stud_id = db["unlinked_student_id"]

        exam_id = database.create_exam(
            exam_name="Sem 3 Endsem",
            exam_type="Semester Examination",
            course="Computer Science",
            semester=3,
            academic_year="2026-2027",
            status="Completed",
            created_by=admin_id
        )

        subjects = database.get_subjects_by_course_and_semester("Computer Science", 3)
        if not subjects:
            database.ensure_semester3_subjects()
            subjects = database.get_subjects_by_course_and_semester("Computer Science", 3)

        sub_id = subjects[0]["subject_id"]
        database.save_exam_marks(exam_id, stud_id, sub_id, 88.0, 100.0, admin_id)
        database.save_exam_marks(exam_id, other_stud_id, sub_id, 92.0, 100.0, admin_id)

        # Login as student
        client.post("/login", data={"username": "student", "password": "StudentPassword123!"})

        # Can view own result
        res = client.get(f"/exams/{exam_id}/results/{stud_id}")
        assert res.status_code == 200
        assert b"Statement of Marks" in res.data or b"Result" in res.data

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
            course="Computer Science",
            semester=3,
            academic_year="2026-2027",
            status="Scheduled",
            created_by=admin_id
        )

        client.post("/login", data={"username": "teacher", "password": "TeacherPassword123!"})
        res = client.post(f"/exams/{exam_id}/delete")
        assert res.status_code == 403


class TestMarksheetPDFGeneration:
    def test_generate_marksheet_pdf(self, db):
        student = database.get_student_by_id(db["linked_student_id"])
        exam = {
            "exam_name": "Semester 3 Final Exam",
            "exam_type": "Semester Examination",
            "course": "Computer Science",
            "semester": 3,
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
