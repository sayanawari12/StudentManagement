"""
test_notices.py — Tests for the Notices / Announcements feature.

Covers:
  - GET /notices: all three roles → 200, anonymous → redirect to login
  - GET/POST /notices/add: admin → 200/302, teacher → 200/302, student → 403
  - POST /notices/<id>/delete: admin → row removed, teacher → 403, student → 403
  - Validation: empty title / empty body → flash error, no row inserted
  - Dashboard: Recent Notices card visible to student role (not role-gated)
"""

import pytest
import database


# ---------------------------------------------------------------------------
# Helpers (mirror the pattern from test_permissions.py)
# ---------------------------------------------------------------------------

def get(client, url, **kwargs):
    return client.get(url, follow_redirects=False, **kwargs)


def post(client, url, data=None, **kwargs):
    return client.post(url, data=data or {}, follow_redirects=False, **kwargs)


def assert_redirected_to_login(resp):
    assert resp.status_code in (301, 302)
    assert "/login" in resp.headers.get("Location", "")


# ---------------------------------------------------------------------------
# Helper: insert a notice directly via database.py for test setup
# ---------------------------------------------------------------------------

def _seed_notice(title="Test Notice", body="Test body", db_info=None):
    """Insert a notice using the admin user's id (id=1 in test seed)."""
    admin_id = db_info["users"]["admin"]["id"]
    return database.insert_notice(title, body, admin_id)


# ===========================================================================
# GET /notices  — access control
# ===========================================================================

class TestNoticesListAccess:

    def test_admin_can_view_notices(self, admin_client):
        resp = get(admin_client, "/notices")
        assert resp.status_code == 200

    def test_teacher_can_view_notices(self, teacher_client):
        resp = get(teacher_client, "/notices")
        assert resp.status_code == 200

    def test_student_can_view_notices(self, student_client):
        resp = get(student_client, "/notices")
        assert resp.status_code == 200

    def test_anonymous_redirected_to_login(self, client):
        assert_redirected_to_login(get(client, "/notices"))


# ===========================================================================
# GET /notices/add  — access control
# ===========================================================================

class TestNoticeAddAccess:

    def test_admin_can_get_add_form(self, admin_client):
        resp = get(admin_client, "/notices/add")
        assert resp.status_code == 200

    def test_teacher_can_get_add_form(self, teacher_client):
        resp = get(teacher_client, "/notices/add")
        assert resp.status_code == 200

    def test_student_add_forbidden(self, student_client):
        resp = get(student_client, "/notices/add")
        assert resp.status_code == 403

    def test_anonymous_add_redirects_to_login(self, client):
        assert_redirected_to_login(get(client, "/notices/add"))


# ===========================================================================
# POST /notices/add  — valid submissions
# ===========================================================================

class TestNoticeAddPost:

    def test_admin_post_valid_notice_redirects(self, admin_client):
        resp = post(admin_client, "/notices/add", data={
            "title": "Admin Notice",
            "body":  "This is the body text.",
        })
        assert resp.status_code == 302
        assert "/notices" in resp.headers.get("Location", "")

    def test_teacher_post_valid_notice_redirects(self, teacher_client):
        resp = post(teacher_client, "/notices/add", data={
            "title": "Teacher Notice",
            "body":  "Posted by a teacher.",
        })
        assert resp.status_code == 302

    def test_student_post_notice_forbidden(self, student_client):
        resp = post(student_client, "/notices/add", data={
            "title": "Student Notice",
            "body":  "Should be rejected.",
        })
        assert resp.status_code == 403

    def test_notice_actually_stored_in_db(self, admin_client, db):
        unique_title = "Stored Notice XYZ-Unique"
        post(admin_client, "/notices/add", data={
            "title": unique_title,
            "body":  "Some content here.",
        })
        notices = database.get_all_notices(limit=50)
        titles = [n["title"] for n in notices]
        assert unique_title in titles


# ===========================================================================
# POST /notices/add  — validation failures
# ===========================================================================

class TestNoticeAddValidation:

    def test_empty_title_rejected(self, admin_client, db):
        count_before = len(database.get_all_notices(limit=100))
        resp = post(admin_client, "/notices/add", data={
            "title": "",
            "body":  "Has a body but no title.",
        })
        # Should re-render the form (200), not redirect
        assert resp.status_code == 200
        count_after = len(database.get_all_notices(limit=100))
        assert count_after == count_before, "No row should be inserted when title is empty"

    def test_empty_body_rejected(self, admin_client, db):
        count_before = len(database.get_all_notices(limit=100))
        resp = post(admin_client, "/notices/add", data={
            "title": "Has Title",
            "body":  "",
        })
        assert resp.status_code == 200
        count_after = len(database.get_all_notices(limit=100))
        assert count_after == count_before, "No row should be inserted when body is empty"

    def test_both_empty_rejected(self, admin_client, db):
        count_before = len(database.get_all_notices(limit=100))
        resp = post(admin_client, "/notices/add", data={
            "title": "",
            "body":  "",
        })
        assert resp.status_code == 200
        count_after = len(database.get_all_notices(limit=100))
        assert count_after == count_before

    def test_title_too_long_rejected(self, admin_client, db):
        count_before = len(database.get_all_notices(limit=100))
        resp = post(admin_client, "/notices/add", data={
            "title": "X" * 151,
            "body":  "Body text is fine.",
        })
        assert resp.status_code == 200
        count_after = len(database.get_all_notices(limit=100))
        assert count_after == count_before


# ===========================================================================
# POST /notices/<id>/delete  — access control and actual deletion
# ===========================================================================

class TestNoticeDelete:

    def test_admin_can_delete_notice(self, admin_client, db):
        notice_id = _seed_notice(title="To Be Deleted", db_info=db)
        resp = post(admin_client, f"/notices/{notice_id}/delete")
        assert resp.status_code == 302

        # Confirm it's actually gone from the DB
        notices = database.get_all_notices(limit=100)
        ids = [n["id"] for n in notices]
        assert notice_id not in ids

    def test_teacher_delete_forbidden(self, teacher_client, db):
        notice_id = _seed_notice(title="Teacher Cannot Delete", db_info=db)
        resp = post(teacher_client, f"/notices/{notice_id}/delete")
        assert resp.status_code == 403

        # Notice still exists
        notices = database.get_all_notices(limit=100)
        ids = [n["id"] for n in notices]
        assert notice_id in ids

    def test_student_delete_forbidden(self, student_client, db):
        notice_id = _seed_notice(title="Student Cannot Delete", db_info=db)
        resp = post(student_client, f"/notices/{notice_id}/delete")
        assert resp.status_code == 403

        notices = database.get_all_notices(limit=100)
        ids = [n["id"] for n in notices]
        assert notice_id in ids


# ===========================================================================
# Dashboard Recent Notices card — visible to ALL roles (not role-gated)
# ===========================================================================

class TestDashboardNoticesCard:

    def test_student_sees_notices_section_on_dashboard(self, student_client, db):
        """The 'Recent Notices' card must appear for student role — it is NOT role-gated."""
        # Seed a notice so the card has content to render
        _seed_notice(title="Visible To Student", body="All roles see this.", db_info=db)

        resp = get(student_client, "/dashboard")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        # The section heading should appear regardless of role
        assert "Recent Notices" in body

    def test_admin_sees_notices_section_on_dashboard(self, admin_client, db):
        _seed_notice(title="Admin Dashboard Notice", db_info=db)
        resp = get(admin_client, "/dashboard")
        assert resp.status_code == 200
        assert "Recent Notices" in resp.data.decode("utf-8")

    def test_teacher_sees_notices_section_on_dashboard(self, teacher_client, db):
        _seed_notice(title="Teacher Dashboard Notice", db_info=db)
        resp = get(teacher_client, "/dashboard")
        assert resp.status_code == 200
        assert "Recent Notices" in resp.data.decode("utf-8")

    def test_dashboard_has_view_all_link(self, student_client):
        resp = get(student_client, "/dashboard")
        assert resp.status_code == 200
        assert "/notices" in resp.data.decode("utf-8")


# ===========================================================================
# database.py unit tests  (no HTTP)
# ===========================================================================

class TestDatabaseNoticesFunctions:

    def test_insert_and_retrieve_notice(self, db):
        admin_id = db["users"]["admin"]["id"]
        nid = database.insert_notice("DB Test Title", "DB Test Body", admin_id)
        assert isinstance(nid, int) and nid > 0

        notices = database.get_all_notices(limit=50)
        ids = [n["id"] for n in notices]
        assert nid in ids

    def test_get_all_notices_includes_username(self, db):
        admin_id = db["users"]["admin"]["id"]
        database.insert_notice("Username Test", "Body", admin_id)
        notices = database.get_all_notices(limit=50)
        assert all("username" in n for n in notices)

    def test_get_all_notices_order_newest_first(self, db):
        admin_id = db["users"]["admin"]["id"]
        database.insert_notice("First", "body", admin_id)
        database.insert_notice("Second", "body", admin_id)
        notices = database.get_all_notices(limit=50)
        # created_at of first item should be >= second item (newest-first)
        if len(notices) >= 2:
            assert notices[0]["created_at"] >= notices[1]["created_at"]

    def test_delete_notice_returns_1_on_success(self, db):
        admin_id = db["users"]["admin"]["id"]
        nid = database.insert_notice("To Delete", "Body", admin_id)
        affected = database.delete_notice(nid)
        assert affected == 1

    def test_delete_notice_returns_0_for_missing_id(self, db):
        affected = database.delete_notice(999999)
        assert affected == 0

    def test_limit_parameter_respected(self, db):
        admin_id = db["users"]["admin"]["id"]
        for i in range(5):
            database.insert_notice(f"Limit Test {i}", "body", admin_id)
        notices = database.get_all_notices(limit=2)
        assert len(notices) <= 2
