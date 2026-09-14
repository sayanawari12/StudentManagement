"""
tests/test_academic_record.py — Tests for Student Academic Transcript / Academic Record feature.
"""

from decimal import Decimal
import pytest
import database
import exam_service
from pdf_generator import generate_academic_transcript_pdf


class TestAcademicTranscriptService:
    """Unit tests for exam_service.compute_academic_transcript"""

    def test_compute_academic_transcript_empty(self, db):
        """Test transcript calculation when student has no recorded exam history."""
        student = {"id": 999, "student_id": "TEST999", "student_name": "No Exam Student", "course": "BCA", "semester": 1}
        transcript = exam_service.compute_academic_transcript(student, [])

        assert transcript["student"] == student
        assert transcript["semesters"] == {}
        assert transcript["ordered_semesters"] == []
        assert transcript["overall"]["has_data"] is False
        assert transcript["overall"]["total_semesters"] == 0
        assert transcript["overall"]["total_exams"] == 0
        assert transcript["overall"]["total_subjects"] == 0
        assert transcript["overall"]["overall_result"] == "N/A"
        assert transcript["overall"]["overall_grade"] == "N/A"

    def test_compute_academic_transcript_semester_and_exam_grouping(self, db):
        """Verify semester-wise and exam-wise grouping and dynamic max/pass marks."""
        student = {"id": 1, "student_id": "BCA2401", "student_name": "Test Student", "course": "BCA", "semester": 2}
        
        raw_history = [
            {
                "exam": {
                    "id": 101,
                    "exam_name": "Mid-Term Exam Sem 1",
                    "exam_type": "Mid-Term",
                    "semester": 1,
                    "academic_year": "2025-26",
                    "max_marks": Decimal("50.00"),
                    "pass_marks": Decimal("15.00"),
                },
                "marks": [
                    {
                        "subject_id": 1,
                        "subject_name": "Problem Solving Using C",
                        "subject_code": "PSC101",
                        "obtained_marks": Decimal("40.00"),
                        "max_marks": Decimal("50.00"),
                        "pass_marks": Decimal("15.00"),
                    }
                ]
            },
            {
                "exam": {
                    "id": 102,
                    "exam_name": "End Semester Exam Sem 1",
                    "exam_type": "End-Sem",
                    "semester": 1,
                    "academic_year": "2025-26",
                    "max_marks": Decimal("100.00"),
                    "pass_marks": Decimal("35.00"),
                },
                "marks": [
                    {
                        "subject_id": 1,
                        "subject_name": "Problem Solving Using C",
                        "subject_code": "PSC101",
                        "obtained_marks": Decimal("85.00"),
                        "max_marks": Decimal("100.00"),
                        "pass_marks": Decimal("35.00"),
                    }
                ]
            },
            {
                "exam": {
                    "id": 103,
                    "exam_name": "Semester 2 Main Exam",
                    "exam_type": "End-Sem",
                    "semester": 2,
                    "academic_year": "2025-26",
                    "max_marks": Decimal("70.00"),
                    "pass_marks": Decimal("28.00"),
                },
                "marks": [
                    {
                        "subject_id": 2,
                        "subject_name": "Data Structures",
                        "subject_code": "DS201",
                        "obtained_marks": Decimal("56.00"),
                        "max_marks": Decimal("70.00"),
                        "pass_marks": Decimal("28.00"),
                    }
                ]
            }
        ]

        transcript = exam_service.compute_academic_transcript(student, raw_history)

        assert transcript["overall"]["has_data"] is True
        assert transcript["overall"]["total_semesters"] == 2
        assert transcript["overall"]["total_exams"] == 3
        assert transcript["overall"]["total_subjects"] == 3
        assert transcript["ordered_semesters"] == [1, 2]

        # Verify Sem 1 has 2 separate exams preserved
        sem1_exams = transcript["semesters"][1]["exams"]
        assert len(sem1_exams) == 2
        assert sem1_exams[0]["exam"]["exam_name"] == "Mid-Term Exam Sem 1"
        assert sem1_exams[1]["exam"]["exam_name"] == "End Semester Exam Sem 1"

        # Verify dynamic max and pass marks are preserved
        ex1_sub = sem1_exams[0]["summary"]["subject_results"][0]
        assert ex1_sub["max_marks"] == 50.0
        assert ex1_sub["pass_marks"] == 15.0
        assert ex1_sub["percentage"] == 80.0
        assert ex1_sub["status"] == "PASS"

        ex2_sub = sem1_exams[1]["summary"]["subject_results"][0]
        assert ex2_sub["max_marks"] == 100.0
        assert ex2_sub["pass_marks"] == 35.0
        assert ex2_sub["percentage"] == 85.0
        assert ex2_sub["status"] == "PASS"

        # Verify Sem 2 exam
        sem2_exams = transcript["semesters"][2]["exams"]
        assert len(sem2_exams) == 1
        ex3_sub = sem2_exams[0]["summary"]["subject_results"][0]
        assert ex3_sub["max_marks"] == 70.0
        assert ex3_sub["pass_marks"] == 28.0
        assert ex3_sub["percentage"] == 80.0
        assert ex3_sub["status"] == "PASS"

        # Overall summary assertions
        assert transcript["overall"]["total_obtained"] == 40.0 + 85.0 + 56.0
        assert transcript["overall"]["total_max"] == 50.0 + 100.0 + 70.0
        assert transcript["overall"]["passed_subjects"] == 3
        assert transcript["overall"]["failed_subjects"] == 0
        assert transcript["overall"]["overall_result"] == "PASS"

    def test_compute_academic_transcript_zero_pass_and_obtained_marks(self, db):
        """Verify obtained_marks=0 and pass_marks=0 evaluate correctly as PASS."""
        student = {"id": 1, "student_id": "BCA2401", "student_name": "Test Student"}
        raw_history = [
            {
                "exam": {
                    "id": 201,
                    "exam_name": "Special Zero Pass Exam",
                    "semester": 1,
                    "max_marks": Decimal("100.00"),
                    "pass_marks": Decimal("0.00"),
                },
                "marks": [
                    {
                        "subject_id": 1,
                        "subject_name": "Experimental Subject",
                        "subject_code": "EXP101",
                        "obtained_marks": Decimal("0.00"),
                        "max_marks": Decimal("100.00"),
                        "pass_marks": Decimal("0.00"),
                    }
                ]
            }
        ]

        transcript = exam_service.compute_academic_transcript(student, raw_history)
        sub = transcript["semesters"][1]["exams"][0]["summary"]["subject_results"][0]

        assert sub["obtained_marks"] == 0.0
        assert sub["pass_marks"] == 0.0
        assert sub["status"] == "PASS"
        assert transcript["overall"]["overall_result"] == "PASS"


class TestAcademicTranscriptRoutes:
    """Route and authorization tests for /students/<student_id>/academic-record"""

    def test_admin_can_access_academic_record(self, admin_client, db):
        """Admin can view any student's academic record page."""
        resp = admin_client.get("/students/BCA2401/academic-record")
        assert resp.status_code == 200
        assert b"Student Academic Transcript" in resp.data

    def test_teacher_can_access_academic_record(self, teacher_client, db):
        """Teacher can view student's academic record page."""
        resp = teacher_client.get("/students/BCA2401/academic-record")
        assert resp.status_code == 200
        assert b"Student Academic Transcript" in resp.data

    def test_student_can_access_own_academic_record(self, student_client, db):
        """Logged-in student can access their own academic record."""
        # student fixture is linked to BCA2401
        resp = student_client.get("/students/BCA2401/academic-record")
        assert resp.status_code == 200
        assert b"Student Academic Transcript" in resp.data

    def test_student_cannot_access_other_academic_record(self, student_client, db):
        """Logged-in student CANNOT access another student's academic record (returns 403)."""
        conn = database.get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT student_id FROM students WHERE student_id != 'BCA2401' LIMIT 1")
            other_student = cursor.fetchone()
        finally:
            cursor.close()
            conn.close()
        
        if other_student:
            other_id = other_student["student_id"]
            resp = student_client.get(f"/students/{other_id}/academic-record")
            assert resp.status_code == 403

    def test_non_existent_student_returns_404(self, admin_client, db):
        """Requesting transcript for non-existent student returns 404."""
        resp = admin_client.get("/students/NONEXISTENT999/academic-record")
        assert resp.status_code == 404


class TestAcademicTranscriptPDF:
    """PDF generation and route tests for academic transcripts."""

    def test_admin_can_download_pdf_transcript(self, admin_client, db):
        """Admin can download academic transcript PDF."""
        resp = admin_client.get("/students/BCA2401/academic-record/pdf")
        assert resp.status_code == 200
        assert resp.mimetype == "application/pdf"
        assert resp.data.startswith(b"%PDF")

    def test_student_can_download_own_pdf_transcript(self, student_client, db):
        """Logged-in student can download their own PDF transcript."""
        resp = student_client.get("/students/BCA2401/academic-record/pdf")
        assert resp.status_code == 200
        assert resp.mimetype == "application/pdf"
        assert resp.data.startswith(b"%PDF")

    def test_student_cannot_download_other_pdf_transcript(self, student_client, db):
        """Logged-in student CANNOT download another student's PDF transcript (returns 403)."""
        conn = database.get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT student_id FROM students WHERE student_id != 'BCA2401' LIMIT 1")
            other_student = cursor.fetchone()
        finally:
            cursor.close()
            conn.close()
        
        if other_student:
            other_id = other_student["student_id"]
            resp = student_client.get(f"/students/{other_id}/academic-record/pdf")
            assert resp.status_code == 403

    def test_direct_pdf_generator_function(self, db):
        """Direct call to generate_academic_transcript_pdf generates valid PDF bytes."""
        student = {"student_id": "BCA2401", "student_name": "Test Student", "course": "BCA", "semester": 1}
        transcript = exam_service.compute_academic_transcript(student, [])
        pdf_bytes = generate_academic_transcript_pdf(student, transcript)
        assert isinstance(pdf_bytes, bytes)
        assert pdf_bytes.startswith(b"%PDF")


class TestAcademicRecordHardenAndOptimize:
    """Regression tests for Issue 1 (zero marks & dynamic bounds) and Issue 2 (batch history queries)."""

    def test_zero_obtained_and_forty_pass_marks_fail(self):
        """obtained_marks = 0, pass_marks = 40 MUST yield FAIL."""
        marks = [{"subject_name": "Physics", "obtained_marks": 0.0, "max_marks": 100.0, "pass_marks": 40.0}]
        summary = exam_service.compute_student_result_summary(marks)
        sub = summary["subject_results"][0]
        assert sub["status"] == "FAIL"
        assert summary["overall_status"] == "FAIL"

    def test_dynamic_marks_custom_exam_bounds(self):
        """Verify dynamic custom exam bounds (80/32 and 50/20) are respected without hardcoded 40/100 defaults."""
        exam1 = {"max_marks": 80.0, "pass_marks": 32.0}
        marks1 = [{"subject_name": "Paper 1", "obtained_marks": 32.0}]
        sum1 = exam_service.compute_student_result_summary(None, exam1, marks1)
        assert sum1["subject_results"][0]["max_marks"] == 80.0
        assert sum1["subject_results"][0]["pass_marks"] == 32.0
        assert sum1["subject_results"][0]["status"] == "PASS"

        exam2 = {"max_marks": 50.0, "pass_marks": 20.0}
        marks2 = [{"subject_name": "Paper 2", "obtained_marks": 19.99}]
        sum2 = exam_service.compute_student_result_summary(None, exam2, marks2)
        assert sum2["subject_results"][0]["max_marks"] == 50.0
        assert sum2["subject_results"][0]["pass_marks"] == 20.0
        assert sum2["subject_results"][0]["status"] == "FAIL"

    def test_optimized_academic_history_retrieval(self, db):
        """Verify get_student_exam_history batch query structure and data integrity."""
        stud_obj = database.get_student_by_id(db["linked_pk"])
        stud_id = stud_obj["student_id"]
        admin_id = db["users"]["admin"]["id"]

        # Create two separate exams
        ex1_id = database.create_exam("Batch Test Exam 1", "Internal 1", stud_obj["course"], 1, "2025-26", admin_id, status="Completed", max_marks=50.0, pass_marks=20.0)
        ex2_id = database.create_exam("Batch Test Exam 2", "Semester Examination", stud_obj["course"], 2, "2025-26", admin_id, status="Completed", max_marks=80.0, pass_marks=32.0)

        subjects1 = database.ensure_semester1_subjects(stud_obj["course"])
        subjects2 = database.ensure_semester2_subjects(stud_obj["course"])

        database.save_exam_marks(ex1_id, stud_id, subjects1[0]["id"], 25.0, 50.0, admin_id)
        database.save_exam_marks(ex2_id, stud_id, subjects2[0]["id"], 40.0, 80.0, admin_id)

        history = database.get_student_exam_history(stud_id)
        assert len(history) >= 2

        # Verify returned structure
        for item in history:
            assert "exam" in item
            assert "marks" in item
            assert isinstance(item["marks"], list)
            if item["exam"]["id"] == ex1_id:
                assert len(item["marks"]) == 1
                assert float(item["marks"][0]["max_marks"]) == 50.0
                assert float(item["marks"][0]["pass_marks"]) == 20.0
            elif item["exam"]["id"] == ex2_id:
                assert len(item["marks"]) == 1
                assert float(item["marks"][0]["max_marks"]) == 80.0
                assert float(item["marks"][0]["pass_marks"]) == 32.0

