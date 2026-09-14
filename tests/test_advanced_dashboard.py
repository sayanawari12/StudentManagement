"""
test_advanced_dashboard.py — Comprehensive tests for Advanced Student Dashboard analytics & responsiveness.
"""

import pytest
import database

class TestAdvancedStudentDashboard:

    def test_dashboard_renders_for_admin(self, admin_client):
        res = admin_client.get("/dashboard")
        assert res.status_code == 200
        html = res.data.decode("utf-8")
        assert "Student Overview" in html
        assert "Attendance Overview" in html
        assert "Academic Performance" in html
        assert "Fee Collection" in html

    def test_dashboard_renders_for_teacher(self, teacher_client):
        res = teacher_client.get("/dashboard")
        assert res.status_code == 200
        html = res.data.decode("utf-8")
        assert "Student Overview" in html
        assert "Attendance Overview" in html

    def test_dashboard_forbidden_for_student(self, student_client):
        """STUDENT role must NOT have access to /dashboard (returns 403 Forbidden)."""
        res = student_client.get("/dashboard")
        assert res.status_code == 403

    def test_dashboard_analytics_not_executed_for_student(self, student_client, monkeypatch):
        """Dashboard backend database analytics must NOT execute for student requests."""
        called = False
        def mock_get_stats():
            nonlocal called
            called = True
            raise RuntimeError("Database analytics should not be called for student request!")

        monkeypatch.setattr(database, "get_dashboard_stats", mock_get_stats)
        res = student_client.get("/dashboard")
        assert res.status_code == 403
        assert not called, "database.get_dashboard_stats() was executed for student request!"

    def test_dashboard_navigation_visibility_by_role(self, admin_client, teacher_client, student_client, db):
        """Dashboard menu item must be visible to Admin and Teacher, but hidden for Student."""
        admin_res = admin_client.get("/dashboard")
        assert admin_res.status_code == 200
        assert "Dashboard" in admin_res.data.decode("utf-8")

        teacher_res = teacher_client.get("/dashboard")
        assert teacher_res.status_code == 200
        assert "Dashboard" in teacher_res.data.decode("utf-8")

        # Student page — check navigation menu in app shell
        student_pk = db["linked_pk"]
        student_res = student_client.get(f"/students/{student_pk}")
        assert student_res.status_code == 200
        student_html = student_res.data.decode("utf-8")
        # Sidebar/drawer links: 'Dashboard' nav link should NOT be rendered
        assert 'href="/dashboard"' not in student_html

    def test_student_360_profile_access_remains_working(self, student_client, db):
        """Existing Student 360 Profile access must continue working for authorized student."""
        student_pk = db["linked_pk"]
        res = student_client.get(f"/students/{student_pk}")
        assert res.status_code == 200

    def test_unauthenticated_dashboard_redirects_to_login(self, client):
        res = client.get("/dashboard")
        assert res.status_code == 302
        assert "/login" in res.headers["Location"]

    def test_get_dashboard_stats_database_aggregation(self, db):
        stats = database.get_dashboard_stats()
        assert "total_students" in stats
        assert "attendance_today" in stats
        assert "pending_fee_students_count" in stats
        assert "attendance_overview" in stats
        assert "fee_overview" in stats
        assert "academic_performance" in stats
        assert len(stats["academic_performance"]) == 6

    def test_attendance_overview_dynamic_calculation(self, admin_client, db):
        students = database.get_all_students()
        if students:
            s_id = students[0]["id"]
            database.upsert_attendance(s_id, "2026-09-14", "Present", 1)
            database.upsert_attendance(s_id, "2026-09-13", "Absent", 1)

        res = admin_client.get("/dashboard")
        assert res.status_code == 200
        html = res.data.decode("utf-8")
        assert "Attendance Overview" in html
        assert "Overall Attendance" in html

    def test_fee_collection_dynamic_calculation(self, admin_client, db):
        stud_code = "STU_DASH_FEE"
        database.insert_student({
            "student_id": stud_code,
            "student_name": "Dash Fee Student",
            "email": "dashfee@example.com",
            "phone": "9876543210",
            "course": "BCA",
            "semester": 1,
            "gender": "Male",
            "date_of_birth": "2001-01-01",
            "address": "Dash Address"
        })
        s = database.get_student_by_student_id(stud_code)
        if s:
            database.insert_fee_due({
                "stud_id": s["id"],
                "amount_due": 10000.00,
                "due_date": "2026-10-01"
            })

        res = admin_client.get("/dashboard")
        assert res.status_code == 200
        html = res.data.decode("utf-8")
        assert "Fee Collection" in html
        assert "Billed" in html or "Billed:" in html

        # Cleanup
        if s:
            conn = database.get_db_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM fees WHERE stud_id = %s", (s["id"],))
            cursor.execute("DELETE FROM students WHERE id = %s", (s["id"],))
            conn.commit()
            cursor.close()
            conn.close()

    def test_academic_performance_semesters_rendered(self, admin_client):
        res = admin_client.get("/dashboard")
        assert res.status_code == 200
        html = res.data.decode("utf-8")
        assert "Academic Performance" in html
        assert "Sem 1" in html
        assert "Sem 2" in html
        assert "Sem 6" in html

    def test_responsive_grid_classes(self, admin_client):
        res = admin_client.get("/dashboard")
        assert res.status_code == 200
        html = res.data.decode("utf-8")
        assert "dashboard-advanced-grid" in html
        assert "progress-bar-wrap" in html
        assert "sem-perf-row" in html
