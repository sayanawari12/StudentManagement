"""
test_analytics.py — Tests for the Analytics page and underlying DB queries.
"""

import pytest
import database


class TestAnalyticsRouteAccess:
    """Route access matrix and role-based data protection tests for /analytics."""

    def test_admin_access_allowed(self, admin_client):
        resp = admin_client.get("/analytics")
        assert resp.status_code == 200
        assert b"Analytics Overview" in resp.data

    def test_teacher_access_allowed(self, teacher_client):
        resp = teacher_client.get("/analytics")
        assert resp.status_code == 200
        assert b"Analytics Overview" in resp.data

    def test_student_access_forbidden(self, student_client):
        resp = student_client.get("/analytics")
        assert resp.status_code == 403

    def test_anonymous_redirects_to_login(self, client):
        resp = client.get("/analytics", follow_redirects=False)
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_teacher_response_contains_no_fee_data(self, teacher_client, db):
        """
        Data-level security: teacher must NOT receive fee JSON keys or fee status markup
        anywhere in the raw response body.
        """
        resp = teacher_client.get("/analytics")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")

        assert "Fee Status Breakdown" not in body, (
            "Teacher response body must not contain 'Fee Status Breakdown'"
        )
        assert "feeData" not in body, (
            "Teacher response body must not contain feeData JS variable"
        )
        assert "feeChart" not in body, (
            "Teacher response body must not contain feeChart canvas ID"
        )

    def test_admin_response_contains_fee_status_section(self, admin_client, db):
        resp = admin_client.get("/analytics")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        assert "Fee Status Breakdown" in body


class TestAnalyticsDatabaseQueries:
    """Tests for database.get_attendance_trend() and database.get_fee_status_breakdown()."""

    def test_get_attendance_trend_returns_14_calendar_days(self, db):
        trend = database.get_attendance_trend(days=14)
        assert trend is not None, "get_attendance_trend() must never return None"
        assert len(trend) == 14, f"Expected 14 calendar days, got {len(trend)}"

        for day in trend:
            assert "date" in day
            assert "present_count" in day
            assert "total_marked" in day
            assert "percentage" in day
            assert isinstance(day["percentage"], (int, float))

    def test_get_fee_status_breakdown_never_none_and_has_required_keys(self, db):
        breakdown = database.get_fee_status_breakdown()
        assert breakdown is not None, "get_fee_status_breakdown() must never return None"
        assert "paid" in breakdown
        assert "partial" in breakdown
        assert "due" in breakdown
        assert isinstance(breakdown["paid"], int)
        assert isinstance(breakdown["partial"], int)
        assert isinstance(breakdown["due"], int)
