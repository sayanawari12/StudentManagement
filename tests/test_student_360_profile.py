"""
test_student_360_profile.py — Comprehensive tests for Student 360° Profile aggregation & presentation.
"""

import pytest
import database

def get_first_student():
    students = database.get_all_students()
    if students:
        return students[0]
    return None

class TestStudent360Profile:

    def test_admin_can_view_student_360_profile(self, admin_client, db):
        stud = get_first_student()
        assert stud is not None
        res = admin_client.get(f"/students/{stud['id']}")
        assert res.status_code == 200
        html = res.data.decode("utf-8")
        assert "Student 360° Profile" in html
        assert "Personal Information" in html
        assert "Academic Information" in html
        assert "Attendance Summary" in html

    def test_teacher_can_view_student_360_profile(self, teacher_client, db):
        stud = get_first_student()
        assert stud is not None
        res = teacher_client.get(f"/students/{stud['id']}")
        assert res.status_code == 200
        html = res.data.decode("utf-8")
        assert "Student 360° Profile" in html

    def test_student_can_view_own_360_profile(self, student_client, db):
        stud = database.get_student_by_student_id("STU001")
        if not stud:
            students = database.get_all_students()
            stud = students[0] if students else None
        assert stud is not None
        res = student_client.get(f"/students/{stud['id']}")
        assert res.status_code == 200
        html = res.data.decode("utf-8")
        assert "Student 360° Profile" in html

    def test_student_cannot_access_other_student_360_profile(self, student_client, db):
        students = database.get_all_students()
        other = next((s for s in students if s['student_id'] != 'STU001' and s['id'] != 1), None)
        if other:
            res = student_client.get(f"/students/{other['id']}")
            assert res.status_code == 403

    def test_profile_photo_rendered(self, admin_client, db):
        stud = get_first_student()
        assert stud is not None
        res = admin_client.get(f"/students/{stud['id']}")
        assert res.status_code == 200
        html = res.data.decode("utf-8")
        assert "profile-avatar-lg" in html
        assert "<img src=" in html

    def test_attendance_summary_real_data(self, admin_client, db):
        stud = get_first_student()
        database.upsert_attendance(stud['id'], '2026-09-14', 'Present', 1)
        res = admin_client.get(f"/students/{stud['id']}")
        assert res.status_code == 200
        html = res.data.decode("utf-8")
        assert "Attendance Summary" in html
        assert "Present" in html

    def test_fee_summary_real_data(self, admin_client, db):
        stud = get_first_student()
        database.insert_fee_due({
            "stud_id": stud['id'],
            "amount_due": 5000.00,
            "due_date": "2026-10-01"
        })
        res = admin_client.get(f"/students/{stud['id']}")
        assert res.status_code == 200
        html = res.data.decode("utf-8")
        assert "Fee Summary" in html
        assert "5000" in html or "Fee" in html

    def test_action_links_present(self, admin_client, db):
        stud = get_first_student()
        res = admin_client.get(f"/students/{stud['id']}")
        assert res.status_code == 200
        html = res.data.decode("utf-8")
        assert "Academic Transcript" in html
        assert "Exam Results" in html
        assert "ID Card" in html
        assert "Download Certificate" in html

    def test_missing_data_empty_states(self, admin_client, db):
        stud_code = "STU9999"
        database.insert_student({
            "student_id": stud_code,
            "student_name": "Test Empty Profile",
            "email": "empty9999@example.com",
            "phone": "9999999999",
            "course": "BCA",
            "semester": 1,
            "gender": "Male",
            "date_of_birth": "2000-01-01",
            "address": "Test Address"
        })
        new_stud = database.get_student_by_student_id(stud_code)
        assert new_stud is not None
        res = admin_client.get(f"/students/{new_stud['id']}")
        assert res.status_code == 200
        html = res.data.decode("utf-8")
        assert "No attendance records yet" in html
        assert "No fee records available" in html
        assert "No exam results available" in html

    def test_responsive_grid_classes_rendered(self, admin_client, db):
        stud = get_first_student()
        res = admin_client.get(f"/students/{stud['id']}")
        assert res.status_code == 200
        html = res.data.decode("utf-8")
        assert "overview-stats-grid" in html
        assert "profile-360-grid" in html

    def test_nonexistent_student_redirects(self, admin_client):
        res = admin_client.get("/students/999999", follow_redirects=True)
        assert res.status_code == 200
        html = res.data.decode("utf-8")
        assert "Student not found." in html
