"""
test_permissions.py — Route permission matrix, own-record guard, and fees-section guard.
"""

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get(client, url, **kwargs):
    return client.get(url, follow_redirects=False, **kwargs)

def post(client, url, data=None, **kwargs):
    return client.post(url, data=data or {}, follow_redirects=False, **kwargs)


def assert_allowed(resp, description=""):
    """2xx or redirect (not 403)."""
    assert resp.status_code != 403, (
        f"Expected access but got 403 for {description}"
    )

def assert_forbidden(resp, description=""):
    assert resp.status_code == 403, (
        f"Expected 403 but got {resp.status_code} for {description}"
    )

def assert_redirected_to_login(resp):
    """Unauthenticated requests should redirect to /login."""
    assert resp.status_code in (302, 301)
    assert "/login" in resp.headers.get("Location", "")


# ---------------------------------------------------------------------------
# Full route permission matrix (parametrized)
# ---------------------------------------------------------------------------

class TestRoutePermissions:
    """
    For each route, assert:
      - allowed roles → not 403
      - forbidden roles → exactly 403
    """

    def test_students_list_admin_allowed(self, admin_client):
        assert_allowed(get(admin_client, "/students"), "/students as admin")

    def test_students_list_teacher_allowed(self, teacher_client):
        assert_allowed(get(teacher_client, "/students"), "/students as teacher")

    def test_students_list_student_forbidden(self, student_client):
        assert_forbidden(get(student_client, "/students"), "/students as student")

    def test_students_list_anon_redirects(self, client):
        assert_redirected_to_login(get(client, "/students"))

    # /students/add
    def test_students_add_admin_allowed(self, admin_client):
        assert_allowed(get(admin_client, "/students/add"), "/students/add as admin")

    def test_students_add_teacher_forbidden(self, teacher_client):
        assert_forbidden(get(teacher_client, "/students/add"), "/students/add as teacher")

    def test_students_add_student_forbidden(self, student_client):
        assert_forbidden(get(student_client, "/students/add"), "/students/add as student")

    # /students/<id>/edit
    def test_students_edit_admin_allowed(self, admin_client, db):
        stud_id = db["linked_pk"]
        assert_allowed(get(admin_client, f"/students/{stud_id}/edit"), "edit as admin")

    def test_students_edit_teacher_forbidden(self, teacher_client, db):
        stud_id = db["linked_pk"]
        assert_forbidden(get(teacher_client, f"/students/{stud_id}/edit"), "edit as teacher")

    def test_students_edit_student_forbidden(self, student_client, db):
        stud_id = db["linked_pk"]
        assert_forbidden(get(student_client, f"/students/{stud_id}/edit"), "edit as student")

    # /students/<id>/delete (POST only)
    def test_students_delete_admin_allowed(self, admin_client, db):
        # Use other_pk so we don't break the seeded linked student
        stud_id = db["other_pk"]
        resp = post(admin_client, f"/students/{stud_id}/delete")
        assert_allowed(resp, "delete as admin")

    def test_students_delete_teacher_forbidden(self, teacher_client, db):
        stud_id = db["linked_pk"]
        assert_forbidden(post(teacher_client, f"/students/{stud_id}/delete"), "delete as teacher")

    def test_students_delete_student_forbidden(self, student_client, db):
        stud_id = db["linked_pk"]
        assert_forbidden(post(student_client, f"/students/{stud_id}/delete"), "delete as student")

    # /attendance (GET)
    def test_attendance_admin_allowed(self, admin_client):
        assert_allowed(get(admin_client, "/attendance"), "/attendance as admin")

    def test_attendance_teacher_allowed(self, teacher_client):
        assert_allowed(get(teacher_client, "/attendance"), "/attendance as teacher")

    def test_attendance_student_forbidden(self, student_client):
        assert_forbidden(get(student_client, "/attendance"), "/attendance as student")

    # /fees/create/<id>
    def test_fees_create_admin_allowed(self, admin_client, db):
        stud_id = db["linked_pk"]
        assert_allowed(get(admin_client, f"/fees/create/{stud_id}"), "fees_create as admin")

    def test_fees_create_teacher_forbidden(self, teacher_client, db):
        stud_id = db["linked_pk"]
        assert_forbidden(get(teacher_client, f"/fees/create/{stud_id}"), "fees_create as teacher")

    def test_fees_create_student_forbidden(self, student_client, db):
        stud_id = db["linked_pk"]
        assert_forbidden(get(student_client, f"/fees/create/{stud_id}"), "fees_create as student")

    # /fees/pay/<fee_id> — we need an actual fee row for this
    def test_fees_pay_admin_allowed(self, admin_client, db):
        import database
        stud_id = db["linked_pk"]
        database.insert_fee_due({"stud_id": stud_id, "amount_due": "100.00", "due_date": "2025-12-31"})
        fees = database.get_student_fees(stud_id)
        unpaid = [f for f in fees if f["amount_paid"] < f["amount_due"]]
        assert unpaid, "Need an unpaid fee to test /fees/pay"
        fee_id = unpaid[0]["id"]
        assert_allowed(get(admin_client, f"/fees/pay/{fee_id}"), "fees_pay as admin")

    def test_fees_pay_teacher_forbidden(self, teacher_client, db):
        import database
        stud_id = db["linked_pk"]
        fees = database.get_student_fees(stud_id)
        unpaid = [f for f in fees if f["amount_paid"] < f["amount_due"]]
        if not unpaid:
            database.insert_fee_due({"stud_id": stud_id, "amount_due": "50.00", "due_date": "2025-12-31"})
            fees = database.get_student_fees(stud_id)
            unpaid = [f for f in fees if f["amount_paid"] < f["amount_due"]]
        fee_id = unpaid[0]["id"]
        assert_forbidden(get(teacher_client, f"/fees/pay/{fee_id}"), "fees_pay as teacher")

    def test_fees_pay_student_forbidden(self, student_client, db):
        import database
        stud_id = db["linked_pk"]
        fees = database.get_student_fees(stud_id)
        unpaid = [f for f in fees if f["amount_paid"] < f["amount_due"]]
        if not unpaid:
            database.insert_fee_due({"stud_id": stud_id, "amount_due": "50.00", "due_date": "2025-12-31"})
            fees = database.get_student_fees(stud_id)
            unpaid = [f for f in fees if f["amount_paid"] < f["amount_due"]]
        fee_id = unpaid[0]["id"]
        assert_forbidden(get(student_client, f"/fees/pay/{fee_id}"), "fees_pay as student")

    # /grades/add/<id>
    def test_grades_add_admin_allowed(self, admin_client, db):
        stud_id = db["linked_pk"]
        assert_allowed(get(admin_client, f"/grades/add/{stud_id}"), "grades_add as admin")

    def test_grades_add_teacher_allowed(self, teacher_client, db):
        stud_id = db["linked_pk"]
        assert_allowed(get(teacher_client, f"/grades/add/{stud_id}"), "grades_add as teacher")

    def test_grades_add_student_forbidden(self, student_client, db):
        stud_id = db["linked_pk"]
        assert_forbidden(get(student_client, f"/grades/add/{stud_id}"), "grades_add as student")


# ---------------------------------------------------------------------------
# _assert_own_record tests
# ---------------------------------------------------------------------------

class TestOwnRecordGuard:
    """Student-role user can only view their own linked record."""

    def test_student_own_details_allowed(self, student_client, db):
        own_id = db["linked_pk"]
        resp = get(student_client, f"/students/{own_id}")
        assert resp.status_code != 403, f"Student should see own record, got {resp.status_code}"

    def test_student_other_details_forbidden(self, student_client, db):
        other_id = db["other_pk"]
        assert_forbidden(get(student_client, f"/students/{other_id}"), "student viewing other details")

    def test_student_own_attendance_allowed(self, student_client, db):
        own_id = db["linked_pk"]
        resp = get(student_client, f"/attendance/{own_id}")
        assert resp.status_code != 403

    def test_student_other_attendance_forbidden(self, student_client, db):
        other_id = db["other_pk"]
        assert_forbidden(get(student_client, f"/attendance/{other_id}"), "student viewing other attendance")

    def test_student_own_fees_allowed(self, student_client, db):
        own_id = db["linked_pk"]
        resp = get(student_client, f"/fees/{own_id}")
        assert resp.status_code != 403

    def test_student_other_fees_forbidden(self, student_client, db):
        other_id = db["other_pk"]
        assert_forbidden(get(student_client, f"/fees/{other_id}"), "student viewing other fees")

    def test_student_own_grades_redirects(self, student_client, db):
        """GET /grades/<own_id> redirects to student_details (not 403)."""
        own_id = db["linked_pk"]
        resp = get(student_client, f"/grades/{own_id}")
        assert resp.status_code in (200, 302), f"Got {resp.status_code} for own grades"
        assert resp.status_code != 403

    def test_student_other_grades_forbidden(self, student_client, db):
        other_id = db["other_pk"]
        assert_forbidden(get(student_client, f"/grades/{other_id}"), "student viewing other grades")


# ---------------------------------------------------------------------------
# Fees-section visibility guard on student_details
# ---------------------------------------------------------------------------

class TestFeesSectionVisibilityOnStudentDetails:
    """
    /students/<id> for a teacher must NOT include fee amounts.
    Attendance is visible to teachers; Fees are NOT.
    (Regression: this guard was fixed explicitly — keep it fixed.)
    """

    def test_teacher_sees_no_fees_section(self, teacher_client, db, admin_client):
        """
        Ensure a teacher viewing a student's detail page gets the attendance
        section but NOT the fees section (no currency amounts, no fee status).
        """
        stud_id = db["linked_pk"]

        # Seed a fee row so there'd actually be something to leak
        import database
        database.insert_fee_due({
            "stud_id": stud_id,
            "amount_due": "9999.00",
            "due_date":   "2025-12-31",
        })

        resp = get(teacher_client, f"/students/{stud_id}")
        assert resp.status_code == 200

        body = resp.data.decode("utf-8")

        # Teacher should NOT see the Fees section heading or fee amounts
        assert "9999" not in body, (
            "Teacher should not see fee amount '9999' on student details page"
        )
        assert "Amount Due" not in body, (
            "Teacher should not see 'Amount Due' label on student details page"
        )

    def test_admin_sees_fees_section(self, admin_client, db):
        """Admin must be able to see fees on the student details page."""
        import database
        stud_id = db["linked_pk"]
        # Ensure there's at least one fee row
        fees = database.get_student_fees(stud_id)
        if not fees:
            database.insert_fee_due({
                "stud_id":    stud_id,
                "amount_due": "500.00",
                "due_date":   "2025-12-31",
            })

        resp = get(admin_client, f"/students/{stud_id}")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        # Admin should see the Fees section
        assert "Fees" in body

    def test_student_sees_own_fees_section(self, student_client, db):
        """Student must be able to see their own fees on the details page."""
        import database
        own_id = db["linked_pk"]
        fees = database.get_student_fees(own_id)
        if not fees:
            database.insert_fee_due({
                "stud_id":    own_id,
                "amount_due": "200.00",
                "due_date":   "2025-12-31",
            })

        resp = get(student_client, f"/students/{own_id}")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        assert "Fees" in body
