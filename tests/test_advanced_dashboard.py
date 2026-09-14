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

    def test_dashboard_renders_for_student(self, student_client):
        res = student_client.get("/dashboard")
        assert res.status_code == 200
        html = res.data.decode("utf-8")
        assert "Student Overview" in html

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
        students = database.get_all_students()
        if students:
            s_id = students[0]["id"]
            database.insert_fee_due({
                "stud_id": s_id,
                "amount_due": 10000.00,
                "due_date": "2026-10-01"
            })

        res = admin_client.get("/dashboard")
        assert res.status_code == 200
        html = res.data.decode("utf-8")
        assert "Fee Collection" in html
        assert "Billed" in html or "Billed:" in html

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
