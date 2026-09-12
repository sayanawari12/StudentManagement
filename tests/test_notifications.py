"""
tests/test_notifications.py — Tests for Email Notifications (admin-triggered).

Covers:
  - GET /notifications: admin -> 200, teacher/student -> 403, anonymous -> redirect to /login
  - Unconfigured mail: POST to send routes flashes "Email is not configured.", 0 emails sent, no crash
  - Fee reminders: POST /notifications/send-fee-reminders dispatches email to students with overdue/partial fees
  - Low attendance:
      * Student with zero attendance records excluded from get_students_with_low_attendance()
      * Student below 75% attendance included and receives alert email via POST /notifications/send-attendance-alerts
"""

import datetime
import pytest
from app import mail
import database


# ---------------------------------------------------------------------------
# Test GET /notifications route permissions
# ---------------------------------------------------------------------------

class TestNotificationsPermissions:
    def test_admin_access_allowed(self, admin_client):
        resp = admin_client.get("/notifications")
        assert resp.status_code == 200
        assert b"Notifications" in resp.data

    def test_teacher_access_forbidden(self, teacher_client):
        resp = teacher_client.get("/notifications")
        assert resp.status_code == 403

    def test_student_access_forbidden(self, student_client):
        resp = student_client.get("/notifications")
        assert resp.status_code == 403

    def test_anonymous_redirects_to_login(self, client):
        resp = client.get("/notifications", follow_redirects=False)
        assert resp.status_code in (301, 302)
        assert "/login" in resp.headers.get("Location", "")


# ---------------------------------------------------------------------------
# Test Unconfigured Mail Behavior
# ---------------------------------------------------------------------------

class TestUnconfiguredMail:
    def test_send_fee_reminders_unconfigured(self, app, admin_client):
        app.config["MAIL_SERVER"] = None
        app.config["MAIL_USERNAME"] = None
        app.config["MAIL_SUPPRESS_SEND"] = True
        mail.init_app(app)

        with mail.record_messages() as out:
            resp = admin_client.post("/notifications/send-fee-reminders", follow_redirects=True)
            assert resp.status_code == 200
            assert b"Email is not configured." in resp.data
            assert len(out) == 0

    def test_send_attendance_alerts_unconfigured(self, app, admin_client):
        app.config["MAIL_SERVER"] = None
        app.config["MAIL_USERNAME"] = None
        app.config["MAIL_SUPPRESS_SEND"] = True
        mail.init_app(app)

        with mail.record_messages() as out:
            resp = admin_client.post("/notifications/send-attendance-alerts", follow_redirects=True)
            assert resp.status_code == 200
            assert b"Email is not configured." in resp.data
            assert len(out) == 0


# ---------------------------------------------------------------------------
# Test Fee Reminders Dispatch
# ---------------------------------------------------------------------------

class TestFeeRemindersDispatch:
    def test_send_fee_reminders_dispatches_email(self, app, admin_client, db):
        app.config["MAIL_SERVER"] = "localhost"
        app.config["MAIL_PORT"] = 25
        app.config["MAIL_USE_TLS"] = False
        app.config["MAIL_USERNAME"] = "admin@test.com"
        app.config["MAIL_DEFAULT_SENDER"] = "admin@test.com"
        app.config["MAIL_SUPPRESS_SEND"] = True
        app.config["TESTING"] = True
        mail.init_app(app)

        student_pk = db["linked_pk"]
        # Ensure student has known email
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE students SET email = 'student_fee_test@example.com' WHERE id = %s",
            (student_pk,)
        )
        # Add an overdue fee row
        yesterday = datetime.date.today() - datetime.timedelta(days=1)
        cursor.execute(
            "INSERT INTO fees (stud_id, amount_due, amount_paid, due_date) VALUES (%s, %s, %s, %s)",
            (student_pk, 5000.00, 1000.00, yesterday)
        )
        conn.commit()
        cursor.close()
        conn.close()

        with mail.record_messages() as out:
            resp = admin_client.post("/notifications/send-fee-reminders", follow_redirects=True)
            assert resp.status_code == 200
            assert b"reminders" in resp.data.lower()
            assert len(out) >= 1
            sent_to_student = [m for m in out if "student_fee_test@example.com" in m.recipients]
            assert len(sent_to_student) >= 1
            msg = sent_to_student[0]
            assert msg.subject == "Fee Payment Reminder"
            assert "outstanding fee balance" in msg.body
            assert "Your College Name Here" in msg.body


# ---------------------------------------------------------------------------
# Test Low Attendance Filtering & Alerts Dispatch
# ---------------------------------------------------------------------------

class TestLowAttendance:
    def test_student_with_zero_attendance_records_excluded(self, db):
        # Create a new student with zero attendance records
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO students (student_id, student_name, email, phone, gender, date_of_birth, course, semester) "
            "VALUES ('TEST999', 'No Attendance Student', 'no_att@example.com', '9999999999', 'Other', '2000-01-01', 'BCA', 1)"
        )
        conn.commit()
        new_stud_pk = cursor.lastrowid
        cursor.close()
        conn.close()

        low_att_list = database.get_students_with_low_attendance(75.0)
        pks = [s["student_id"] for s in low_att_list]
        assert new_stud_pk not in pks

    def test_student_below_threshold_included_and_alerted(self, app, admin_client, db):
        app.config["MAIL_SERVER"] = "localhost"
        app.config["MAIL_PORT"] = 25
        app.config["MAIL_USE_TLS"] = False
        app.config["MAIL_USERNAME"] = "admin@test.com"
        app.config["MAIL_DEFAULT_SENDER"] = "admin@test.com"
        app.config["MAIL_SUPPRESS_SEND"] = True
        app.config["TESTING"] = True
        mail.init_app(app)

        student_pk = db["other_pk"]
        admin_user_id = db["users"]["admin"]["id"]
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE students SET email = 'low_att_test@example.com' WHERE id = %s",
            (student_pk,)
        )
        # Clear existing attendance for this student and insert 1 Present, 3 Absent (25% attendance)
        cursor.execute("DELETE FROM attendance WHERE stud_id = %s", (student_pk,))
        today = datetime.date.today()
        cursor.execute(
            "INSERT INTO attendance (stud_id, date, status, marked_by) VALUES (%s, %s, 'Present', %s)",
            (student_pk, today, admin_user_id)
        )
        cursor.execute(
            "INSERT INTO attendance (stud_id, date, status, marked_by) VALUES (%s, %s, 'Absent', %s)",
            (student_pk, today - datetime.timedelta(days=1), admin_user_id)
        )
        cursor.execute(
            "INSERT INTO attendance (stud_id, date, status, marked_by) VALUES (%s, %s, 'Absent', %s)",
            (student_pk, today - datetime.timedelta(days=2), admin_user_id)
        )
        cursor.execute(
            "INSERT INTO attendance (stud_id, date, status, marked_by) VALUES (%s, %s, 'Absent', %s)",
            (student_pk, today - datetime.timedelta(days=3), admin_user_id)
        )
        conn.commit()
        cursor.close()
        conn.close()

        # Check DB function includes student
        low_att_list = database.get_students_with_low_attendance(75.0)
        low_att_pks = [s["student_id"] for s in low_att_list]
        assert student_pk in low_att_pks

        # Check email dispatch
        with mail.record_messages() as out:
            resp = admin_client.post("/notifications/send-attendance-alerts", follow_redirects=True)
            assert resp.status_code == 200
            sent_to_student = [m for m in out if "low_att_test@example.com" in m.recipients]
            assert len(sent_to_student) == 1
            msg = sent_to_student[0]
            assert msg.subject == "Attendance Alert"
            assert "25.0%" in msg.body
