"""
All MySQL access lives in this file. app.py never writes SQL directly —
it calls these functions instead. That separation is what makes it easy
to explain "how does Flask talk to MySQL" in viva: app.py handles the
web request, this file handles the database.

Column naming note:
  attendance.stud_id  and  fees.stud_id  are INT FKs → students.id (PK).
  students.student_id is a VARCHAR roll number (e.g. 'BCA2401').
  These are different columns; never conflate them in JOINs or queries.
"""

import datetime
import logging
import mysql.connector
from mysql.connector import Error
import config

logger = logging.getLogger(__name__)


def get_db_connection():
    """Opens a fresh MySQL connection using the credentials in config.py.

    A new connection is opened per call and closed right after use
    (see the try/finally blocks below). For a project this size that's
    simpler to reason about than keeping one connection alive for the
    whole app.
    """
    return mysql.connector.connect(
        host=config.DB_HOST,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        database=config.DB_NAME
    )


# ---------------------------------------------------------------------------
# User / auth queries  (users table replaces the old admins table)
# ---------------------------------------------------------------------------

def get_user_by_username(username):
    """Return the users row matching username, or None."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()


def get_user_by_id(user_id):
    """Return the users row matching primary key user_id, or None."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()


def update_user_password(user_id, new_hashed_password):
    """Update the password hash for user_id."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE users SET password = %s WHERE id = %s",
            (new_hashed_password, user_id)
        )
        conn.commit()
        return cursor.rowcount
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# TOTP / 2FA mutators
# NOTE: get_user_by_id already returns SELECT * so totp_secret / totp_enabled
#       are already available through that function — no new getter needed.
# KNOWN LIMITATION: backup/recovery codes are not implemented. If a user loses
#   their authenticator device they must contact an admin to disable 2FA via
#   direct DB access until a recovery-code feature is added.
# ---------------------------------------------------------------------------

def set_user_totp_secret(user_id, secret):
    """Store a freshly generated TOTP secret for user_id (totp_enabled stays FALSE).

    Called during the setup flow before the user proves they can generate codes.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE users SET totp_secret = %s, totp_enabled = FALSE WHERE id = %s",
            (secret, user_id)
        )
        conn.commit()
        return cursor.rowcount
    finally:
        cursor.close()
        conn.close()


def enable_user_totp(user_id):
    """Flip totp_enabled = TRUE once the user has confirmed a valid code."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE users SET totp_enabled = TRUE WHERE id = %s",
            (user_id,)
        )
        conn.commit()
        return cursor.rowcount
    finally:
        cursor.close()
        conn.close()


def disable_user_totp(user_id):
    """Clear totp_secret and set totp_enabled = FALSE (2FA removed for user)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE users SET totp_secret = NULL, totp_enabled = FALSE WHERE id = %s",
            (user_id,)
        )
        conn.commit()
        return cursor.rowcount
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# Dashboard queries
# ---------------------------------------------------------------------------

def get_dashboard_stats():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # 1. Total Students
        cursor.execute("SELECT COUNT(*) AS total FROM students")
        total_students = cursor.fetchone()["total"]

        # 2. Total BCA Students
        cursor.execute(
            "SELECT COUNT(*) AS total FROM students WHERE course = %s", ("BCA",)
        )
        total_bca = cursor.fetchone()["total"]

        # 3. Semester Breakdown
        cursor.execute(
            "SELECT semester, COUNT(*) AS total "
            "FROM students GROUP BY semester ORDER BY semester"
        )
        semester_counts = cursor.fetchall()

        # 4. Attendance today (Present count)
        cursor.execute(
            "SELECT COUNT(*) AS total FROM attendance "
            "WHERE date = CURDATE() AND status = 'Present'"
        )
        attendance_today = cursor.fetchone()["total"]

        # 5. Students with Pending/Overdue Fees Count
        cursor.execute(
            "SELECT COUNT(DISTINCT stud_id) AS total FROM fees WHERE amount_paid < amount_due"
        )
        pending_fee_students_count = cursor.fetchone()["total"]

        # 6. Total Outstanding Dues Amount
        cursor.execute(
            "SELECT COALESCE(SUM(amount_due - amount_paid), 0) AS total_dues "
            "FROM fees WHERE amount_paid < amount_due"
        )
        total_dues = cursor.fetchone()["total_dues"]

        # 7. Overall Attendance Overview stats
        cursor.execute(
            "SELECT "
            "COALESCE(SUM(CASE WHEN status = 'Present' THEN 1 ELSE 0 END), 0) AS total_present, "
            "COALESCE(SUM(CASE WHEN status = 'Absent' THEN 1 ELSE 0 END), 0) AS total_absent, "
            "COUNT(*) AS total_marked "
            "FROM attendance"
        )
        att_row = cursor.fetchone()
        tot_present = int(att_row["total_present"] or 0)
        tot_absent = int(att_row["total_absent"] or 0)
        tot_marked = int(att_row["total_marked"] or 0)
        att_pct = round((tot_present / tot_marked * 100.0), 1) if tot_marked > 0 else None

        attendance_overview = {
            "total_present": tot_present,
            "total_absent": tot_absent,
            "total_marked": tot_marked,
            "percentage": att_pct
        }

        # 8. Fee Collection Overview stats
        cursor.execute(
            "SELECT "
            "COALESCE(SUM(amount_due), 0) AS total_billed, "
            "COALESCE(SUM(amount_paid), 0) AS total_collected, "
            "COALESCE(SUM(CASE WHEN amount_paid < amount_due THEN (amount_due - amount_paid) ELSE 0 END), 0) AS total_pending, "
            "COUNT(*) AS record_count "
            "FROM fees"
        )
        fee_row = cursor.fetchone()
        total_billed = float(fee_row["total_billed"] or 0)
        total_collected = float(fee_row["total_collected"] or 0)
        total_pending = float(fee_row["total_pending"] or 0)
        fee_count = int(fee_row["record_count"] or 0)
        fee_pct = round((total_collected / total_billed * 100.0), 1) if total_billed > 0 else (0.0 if fee_count > 0 else None)

        fee_overview = {
            "total_billed": total_billed,
            "total_collected": total_collected,
            "total_pending": total_pending,
            "record_count": fee_count,
            "percentage": fee_pct
        }

        # 9. Semester-Wise Academic Performance (Semesters 1-6)
        cursor.execute(
            """
            SELECT e.semester,
                   SUM(em.obtained_marks) AS total_obtained,
                   SUM(COALESCE(e.max_marks, 100.0)) AS total_max,
                   COUNT(em.id) AS marks_count
            FROM exam_marks em
            JOIN exams e ON e.id = em.exam_id
            GROUP BY e.semester
            """
        )
        exam_rows = cursor.fetchall()
        sem_map = {}
        for r in exam_rows:
            sem = r["semester"]
            obtained = float(r["total_obtained"] or 0)
            maximum = float(r["total_max"] or 0)
            if maximum > 0:
                sem_map[sem] = round((obtained / maximum * 100.0), 1)

        # Fallback/supplement with grades table if any semester missing in exam_marks
        cursor.execute(
            """
            SELECT g.semester,
                   SUM(g.marks_obtained) AS total_obtained,
                   SUM(COALESCE(g.max_marks, 100.0)) AS total_max,
                   COUNT(g.id) AS grade_count
            FROM grades g
            GROUP BY g.semester
            """
        )
        grade_rows = cursor.fetchall()
        for r in grade_rows:
            sem = r["semester"]
            if sem not in sem_map:
                obtained = float(r["total_obtained"] or 0)
                maximum = float(r["total_max"] or 0)
                if maximum > 0:
                    sem_map[sem] = round((obtained / maximum * 100.0), 1)

        academic_performance = []
        for s in range(1, 7):
            academic_performance.append({
                "semester": s,
                "percentage": sem_map.get(s, None)
            })

        return {
            "total_students":             total_students,
            "total_bca":                  total_bca,
            "semester_counts":            semester_counts,
            "attendance_today":           attendance_today,
            "pending_fee_students_count": pending_fee_students_count,
            "total_dues":                 total_dues,
            "attendance_overview":        attendance_overview,
            "fee_overview":               fee_overview,
            "academic_performance":       academic_performance,
        }
    finally:
        cursor.close()
        conn.close()


def get_attendance_trend(days=14):
    """
    Returns attendance trend for the last `days` calendar days (today-13 to today).
    Guarantees one row per calendar day with keys:
    { 'date': 'YYYY-MM-DD', 'present_count': int, 'total_marked': int, 'percentage': float }
    """
    from datetime import date, timedelta
    today = date.today()
    start_date = today - timedelta(days=days - 1)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT date, "
            "SUM(CASE WHEN status = 'Present' THEN 1 ELSE 0 END) AS present_count, "
            "COUNT(*) AS total_marked "
            "FROM attendance "
            "WHERE date >= %s AND date <= %s "
            "GROUP BY date ORDER BY date",
            (start_date.isoformat(), today.isoformat())
        )
        db_rows = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    db_map = {
        (row["date"].isoformat() if hasattr(row["date"], "isoformat") else str(row["date"])): row
        for row in db_rows
    }

    results = []
    for i in range(days):
        day_date = start_date + timedelta(days=i)
        day_str = day_date.isoformat()
        if day_str in db_map:
            row = db_map[day_str]
            present = int(row["present_count"] or 0)
            total   = int(row["total_marked"] or 0)
            pct     = round((present / total) * 100.0, 1) if total > 0 else 0.0
        else:
            present = 0
            total   = 0
            pct     = 0.0

        results.append({
            "date":          day_str,
            "present_count": present,
            "total_marked":  total,
            "percentage":    pct,
        })

    return results


def get_fee_status_breakdown():
    """
    Returns counts of {paid, partial, due} fee records.
    Uses the exact status logic of student_details.html & fees_view.html:
      - paid: amount_paid >= amount_due
      - partial: amount_paid > 0 and amount_paid < amount_due
      - due: amount_paid == 0
    Returns {'paid': int, 'partial': int, 'due': int}. Never returns None.
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT "
            "COALESCE(SUM(CASE WHEN amount_paid >= amount_due THEN 1 ELSE 0 END), 0) AS paid, "
            "COALESCE(SUM(CASE WHEN amount_paid > 0 AND amount_paid < amount_due THEN 1 ELSE 0 END), 0) AS partial, "
            "COALESCE(SUM(CASE WHEN amount_paid = 0 THEN 1 ELSE 0 END), 0) AS due "
            "FROM fees"
        )
        row = cursor.fetchone()
        if not row:
            return {"paid": 0, "partial": 0, "due": 0}
        return {
            "paid":    int(row["paid"] or 0),
            "partial": int(row["partial"] or 0),
            "due":     int(row["due"] or 0),
        }
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# Student queries
# ---------------------------------------------------------------------------

def get_all_students(search=None, course_filter=None, semester_filter=None):
    """Fetch all students with optional search, course_filter, and semester_filter."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        query = "SELECT * FROM students WHERE 1=1"
        params = []

        if search:
            search_str = str(search).strip()
            if search_str:
                like_term = f"%{search_str}%"
                query += " AND (student_name LIKE %s OR student_id LIKE %s OR email LIKE %s OR phone LIKE %s)"
                params.extend([like_term, like_term, like_term, like_term])

        if course_filter:
            query += " AND course = %s"
            params.append(course_filter)

        if semester_filter is not None and str(semester_filter).strip() != "":
            query += " AND semester = %s"
            params.append(int(semester_filter))

        query += " ORDER BY student_id ASC"
        cursor.execute(query, params)
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def get_student_by_id(record_id):
    """Look up a student by the internal primary key (`id`)."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM students WHERE id = %s", (record_id,))
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()


def get_student_by_student_id(student_id):
    """Look up a student by the human-facing roll number (`student_id` VARCHAR).

    Used to check for duplicates before inserting or updating a record.
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT * FROM students WHERE student_id = %s", (student_id,)
        )
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()


def insert_student(data):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT INTO students
                   (student_id, student_name, email, phone, gender,
                    date_of_birth, course, semester, address)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (data["student_id"], data["student_name"], data["email"], data["phone"],
             data["gender"], data["date_of_birth"], data["course"],
             data["semester"], data["address"])
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def update_student(record_id, data):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """UPDATE students SET
                   student_id = %s, student_name = %s, email = %s, phone = %s,
                   gender = %s, date_of_birth = %s, course = %s,
                   semester = %s, address = %s
               WHERE id = %s""",
            (data["student_id"], data["student_name"], data["email"], data["phone"],
             data["gender"], data["date_of_birth"], data["course"],
             data["semester"], data["address"], record_id)
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def delete_student(record_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM students WHERE id = %s", (record_id,))
        conn.commit()
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# Attendance queries
# NOTE: stud_id = students.id (INT PK), NOT students.student_id (VARCHAR roll)
# ---------------------------------------------------------------------------

def get_all_students_for_attendance():
    """Return list of all students for the attendance marking page."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT id, student_name, student_id, gender FROM students ORDER BY student_name"
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def get_attendance_by_date(date):
    """Return dict keyed by students.id (INT PK) → status for a given date."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT stud_id, status FROM attendance WHERE date = %s", (date,)
        )
        return {row["stud_id"]: row["status"] for row in cursor.fetchall()}
    finally:
        cursor.close()
        conn.close()


def upsert_attendance(stud_id, date, status, marked_by):
    """Insert or update a single attendance record.
    UNIQUE(stud_id, date) ensures only one record per student per day.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT INTO attendance (stud_id, date, status, marked_by)
               VALUES (%s, %s, %s, %s)
               ON DUPLICATE KEY UPDATE status = VALUES(status),
                                       marked_by = VALUES(marked_by)""",
            (stud_id, date, status, marked_by)
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def get_student_attendance(stud_id):
    """Return attendance history for one student, newest first."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT date, status FROM attendance "
            "WHERE stud_id = %s ORDER BY date DESC",
            (stud_id,)
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def get_attendance_stats_today():
    """Count of Present records for today (used on dashboard)."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT COUNT(*) AS total FROM attendance "
            "WHERE date = CURDATE() AND status = 'Present'"
        )
        return cursor.fetchone()["total"]
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# Fees queries
# NOTE: stud_id = students.id (INT PK), NOT students.student_id (VARCHAR roll)
# ---------------------------------------------------------------------------

def get_student_fees(stud_id):
    """Return all fee rows for a student, newest first."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT id, amount_due, amount_paid, due_date "
            "FROM fees WHERE stud_id = %s ORDER BY due_date DESC",
            (stud_id,)
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def get_fee_by_id(fee_id):
    """Return a single fee row (used to pre-fill fees_pay.html)."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT id, stud_id, amount_due, amount_paid, due_date "
            "FROM fees WHERE id = %s",
            (fee_id,)
        )
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()


def insert_fee_due(data):
    """Create a new billing-period row. amount_paid starts at 0."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT INTO fees (stud_id, amount_due, amount_paid, due_date)
               VALUES (%s, %s, 0.00, %s)""",
            (data["stud_id"], data["amount_due"], data["due_date"])
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def update_fee_payment(fee_id, payment_amount):
    """Add payment_amount to an existing fee row's amount_paid.

    The WHERE clause guards against overpayment at the DB level:
    if amount_paid + payment > amount_due, zero rows are affected.
    Returns the number of affected rows (0 = overpayment rejected).
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """UPDATE fees
               SET amount_paid = amount_paid + %s
               WHERE id = %s
                 AND amount_paid + %s <= amount_due""",
            (payment_amount, fee_id, payment_amount)
        )
        conn.commit()
        return cursor.rowcount
    finally:
        cursor.close()
        conn.close()


def get_total_dues():
    """Sum of outstanding balances across all fee rows.

    Uses COALESCE so an empty fees table returns Decimal('0'), never None.
    (Fix 8: SUM() returns NULL on zero rows.)
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT COALESCE(SUM(amount_due - amount_paid), 0) AS total_dues "
            "FROM fees WHERE amount_paid < amount_due"
        )
        return cursor.fetchone()["total_dues"]
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# Grades queries
# NOTE: stud_id = students.id (INT PK), NOT students.student_id (VARCHAR roll)
# ---------------------------------------------------------------------------

def insert_grade(data):
    """Insert a new grade record for a student."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT INTO grades
                   (stud_id, subject, exam_type, marks_obtained, max_marks, semester, recorded_by)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (data["stud_id"], data["subject"], data["exam_type"],
             data["marks_obtained"], data["max_marks"], data["semester"],
             data["recorded_by"])
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def get_student_grades(stud_id):
    """Return all grade records for a student ordered by semester, then subject."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """SELECT id, stud_id, subject, exam_type, marks_obtained, max_marks,
                      semester, recorded_by, created_at
               FROM grades
               WHERE stud_id = %s
               ORDER BY semester ASC, subject ASC""",
            (stud_id,)
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def get_grade_summary(stud_id):
    """Calculate overall percentage across all grade rows for a student.
    Returns 0 instead of NULL when the student has no grades yet.
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """SELECT COALESCE(SUM(marks_obtained) / NULLIF(SUM(max_marks), 0) * 100, 0) AS overall_percentage
               FROM grades
               WHERE stud_id = %s""",
            (stud_id,)
        )
        row = cursor.fetchone()
        return row["overall_percentage"] if row else 0
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# Notices queries
# ---------------------------------------------------------------------------

def insert_notice(title, body, posted_by):
    """Insert a new notice row. Returns the new row's auto-increment id."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO notices (title, body, posted_by) VALUES (%s, %s, %s)",
            (title, body, posted_by)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        cursor.close()
        conn.close()


def get_all_notices(limit=10):
    """Return the most recent notices joined with the poster's username.

    Each row has: id, title, body, posted_by (user id), created_at, username.
    Ordered newest-first and capped at `limit` rows.
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """SELECT n.id, n.title, n.body, n.posted_by, n.created_at,
                      u.username
               FROM notices n
               JOIN users u ON u.id = n.posted_by
               ORDER BY n.created_at DESC
               LIMIT %s""",
            (limit,)
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def delete_notice(notice_id):
    """Delete a notice by primary key. Returns affected row count (0 = not found)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM notices WHERE id = %s", (notice_id,))
        conn.commit()
        return cursor.rowcount
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# Notifications queries
# ---------------------------------------------------------------------------

def get_students_with_overdue_fees():
    """Return fee records that are overdue or partially paid and due_date <= CURDATE().

    Returns a list of dicts:
      {student_id, student_name, email, gender, amount_due, amount_paid, due_date}
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """SELECT s.id AS student_id, s.student_name, s.email, s.gender,
                      f.amount_due, f.amount_paid, f.due_date
               FROM fees f
               JOIN students s ON f.stud_id = s.id
               WHERE f.amount_paid < f.amount_due
                 AND f.due_date <= CURDATE()
               ORDER BY f.due_date ASC"""
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def get_students_with_low_attendance(threshold):
    """Return students whose attendance percentage is strictly below threshold.

    Excludes students with zero attendance records.
    Returns a list of dicts:
      {student_id, student_name, email, gender, percentage}
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """SELECT s.id AS student_id, s.student_name, s.email, s.gender,
                      ROUND(COALESCE(SUM(CASE WHEN a.status = 'Present' THEN 1 ELSE 0 END) / NULLIF(COUNT(a.id), 0) * 100, 0), 1) AS percentage
               FROM students s
               JOIN attendance a ON a.stud_id = s.id
               GROUP BY s.id, s.student_name, s.email, s.gender
               HAVING percentage < %s
               ORDER BY percentage ASC""",
            (threshold,)
        )
        rows = cursor.fetchall()
        for row in rows:
            if row["percentage"] is not None:
                row["percentage"] = float(row["percentage"])
        return rows
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# Account Lockout queries
# ---------------------------------------------------------------------------

def increment_failed_login(user_id, max_attempts=5, lockout_minutes=15):
    """Atomically increment failed_login_attempts by 1.

    If the new count reaches max_attempts, sets locked_until = NOW() + INTERVAL lockout_minutes MINUTE
    in the same single UPDATE statement to avoid race conditions.

    Returns dict: {"failed_login_attempts": count, "locked_until": datetime_or_None}
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """UPDATE users
               SET locked_until = CASE
                       WHEN failed_login_attempts + 1 >= %s THEN NOW() + INTERVAL %s MINUTE
                       ELSE locked_until
                   END,
                   failed_login_attempts = failed_login_attempts + 1
               WHERE id = %s""",
            (max_attempts, lockout_minutes, user_id)
        )
        conn.commit()

        cursor.execute(
            "SELECT failed_login_attempts, locked_until FROM users WHERE id = %s",
            (user_id,)
        )
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()


def reset_failed_login(user_id):
    """Reset failed_login_attempts to 0 and clear locked_until timestamp."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """UPDATE users
               SET failed_login_attempts = 0,
                   locked_until = NULL
               WHERE id = %s""",
            (user_id,)
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()



# ---------------------------------------------------------------------------
# Audit log query
# ---------------------------------------------------------------------------

def get_audit_log(limit=100):
    """Return the most recent combined activity across attendance, grades, and notices.

    Each row has the same shape:
        event_type  — 'attendance' | 'grade' | 'notice'
        event_time  — datetime-like value (date for attendance, DATETIME for the rest)
        actor       — username of the staff member who performed the action
        description — human-readable summary of the event

    Ordered newest-first and capped at `limit` rows.
    Returns an empty list (never None, never raises) when there is no data.
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT event_type, event_time, actor, description
            FROM (
                SELECT 'attendance' AS event_type,
                       a.date       AS event_time,
                       u.username   AS actor,
                       CONCAT('Marked ', a.status, ' for ', s.student_name) AS description
                FROM attendance a
                JOIN users    u ON u.id = a.marked_by
                JOIN students s ON s.id = a.stud_id

                UNION ALL

                SELECT 'grade'      AS event_type,
                       g.created_at AS event_time,
                       u.username   AS actor,
                       CONCAT('Recorded ', g.subject, ' (', g.exam_type, ') for ', s.student_name) AS description
                FROM grades g
                JOIN users    u ON u.id = g.recorded_by
                JOIN students s ON s.id = g.stud_id

                UNION ALL

                SELECT 'notice'     AS event_type,
                       n.created_at AS event_time,
                       u.username   AS actor,
                       CONCAT('Posted notice: ', n.title) AS description
                FROM notices n
                JOIN users u ON u.id = n.posted_by
            ) AS audit_union
            ORDER BY event_time DESC
            LIMIT %s
            """,
            (limit,)
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def get_student_audit_log(stud_id, limit=5):
    """Return student-specific activity across attendance, grades, fees, and documents."""
    pk_id = _resolve_student_pk(stud_id)
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT event_type, event_time, actor, description
            FROM (
                SELECT 'attendance' AS event_type,
                       a.date       AS event_time,
                       COALESCE(u.username, 'System') AS actor,
                       CONCAT('Attendance marked: ', a.status) AS description
                FROM attendance a
                LEFT JOIN users u ON u.id = a.marked_by
                WHERE a.stud_id = %s

                UNION ALL

                SELECT 'grade'      AS event_type,
                       g.created_at AS event_time,
                       COALESCE(u.username, 'System') AS actor,
                       CONCAT('Grade recorded for ', g.subject, ' (', g.marks_obtained, '/', g.max_marks, ')') AS description
                FROM grades g
                LEFT JOIN users u ON u.id = g.recorded_by
                WHERE g.stud_id = %s

                UNION ALL

                SELECT 'fee'        AS event_type,
                       f.due_date   AS event_time,
                       'Finance'    AS actor,
                       CONCAT('Fee record: ₹', f.amount_due, ' (Paid: ₹', f.amount_paid, ')') AS description
                FROM fees f
                WHERE f.stud_id = %s

                UNION ALL

                SELECT 'document'    AS event_type,
                       d.created_at  AS event_time,
                       COALESCE(u.username, 'System') AS actor,
                       CONCAT('Document ', d.doc_type, ' (', d.status, ')') AS description
                FROM student_documents d
                LEFT JOIN users u ON u.id = d.uploaded_by
                WHERE d.stud_id = %s
            ) AS student_audit
            ORDER BY event_time DESC
            LIMIT %s
            """,
            (pk_id, pk_id, pk_id, pk_id, limit)
        )
        return cursor.fetchall()
    except Exception as e:
        return []
    finally:
        cursor.close()
        conn.close()



def is_account_locked(user):

    """Return True if user's locked_until is set and is in the future."""
    if not user or not user.get("locked_until"):
        return False
    locked_until = user["locked_until"]
    if isinstance(locked_until, str):
        try:
            locked_until = datetime.datetime.fromisoformat(locked_until)
        except ValueError:
            return False
    if isinstance(locked_until, datetime.datetime):
        return locked_until > datetime.datetime.now()
    return False


# ---------------------------------------------------------------------------
# Subject query helpers
# ---------------------------------------------------------------------------

def ensure_semester1_subjects(course="BCA"):
    """
    Ensure that Semester 1 has all 6 mandated subjects in the database.
    Idempotent (uses INSERT IGNORE).
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        sem1_subjects = [
            ("PSC101", "Problem Solving Using C"),
            ("MFCS102", "Mathematics Foundation to Computer Science"),
            ("CA103", "Computer Architecture"),
            ("EVS104", "Environmental Studies (EVS)"),
            ("IKS105", "Indian Knowledge System (IKS)"),
            ("ENG106", "General English"),
        ]
        for code, name in sem1_subjects:
            cursor.execute(
                """
                INSERT IGNORE INTO subjects (course, semester, subject_code, subject_name, max_marks, pass_marks)
                VALUES (%s, 1, %s, %s, 100.00, 40.00)
                """,
                (course, code, name)
            )
        conn.commit()

        cursor.execute("SELECT * FROM subjects WHERE course = %s AND semester = 1 ORDER BY id ASC", (course,))
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def ensure_semester2_subjects(course="BCA"):
    """
    Ensure that Semester 2 has all 6 mandated subjects in the database.
    Idempotent (uses INSERT IGNORE).
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        sem2_subjects = [
            ("DS201", "Data Structures"),
            ("OOPC202", "Object Oriented Programming Using C++ (OOP C++)"),
            ("OOPJ203", "Object Oriented Programming Using Java (OOP Java)"),
            ("OS204", "Operating System"),
            ("WT205", "Web Technology"),
            ("IC206", "Indian Constitution"),
        ]
        for code, name in sem2_subjects:
            cursor.execute(
                """
                INSERT IGNORE INTO subjects (course, semester, subject_code, subject_name, max_marks, pass_marks)
                VALUES (%s, 2, %s, %s, 100.00, 40.00)
                """,
                (course, code, name)
            )
        conn.commit()

        cursor.execute("SELECT * FROM subjects WHERE course = %s AND semester = 2 ORDER BY id ASC", (course,))
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def ensure_semester3_subjects(course="BCA"):
    """
    Ensure that Semester 3 has all 6 mandated subjects in the database.
    Idempotent (uses INSERT IGNORE).
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        sem3_subjects = [
            ("SE301", "Software Engineering (SE)"),
            ("DBMS302", "Database Management System (DBMS)"),
            ("PY303", "Python"),
            ("PS304", "Probability and Statistics"),
            ("FE305", "Future Engineering"),
            ("BDA306", "Basics of Data Analytics Using Spreadsheet"),
        ]
        for code, name in sem3_subjects:
            cursor.execute(
                """
                INSERT IGNORE INTO subjects (course, semester, subject_code, subject_name, max_marks, pass_marks)
                VALUES (%s, 3, %s, %s, 100.00, 40.00)
                """,
                (course, code, name)
            )
        conn.commit()

        cursor.execute("SELECT * FROM subjects WHERE course = %s AND semester = 3 ORDER BY id ASC", (course,))
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def get_subjects_by_course_and_semester(course, semester):
    """Fetch all subjects for a given course and semester."""
    sem_str = str(semester)
    if sem_str == "1":
        ensure_semester1_subjects(course)
    elif sem_str == "2":
        ensure_semester2_subjects(course)
    elif sem_str == "3":
        ensure_semester3_subjects(course)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT * FROM subjects WHERE course = %s AND semester = %s ORDER BY id ASC",
            (course, semester)
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def get_subject_by_id(subject_id):
    """Fetch a single subject by ID."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM subjects WHERE id = %s", (subject_id,))
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# Exam query helpers
# ---------------------------------------------------------------------------

def create_exam(exam_name, exam_type, course, semester, academic_year, created_by,
                status="Scheduled", max_marks=None, pass_marks=None):
    """Insert a new exam into the database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    mx = float(max_marks) if max_marks is not None else None
    pm = float(pass_marks) if pass_marks is not None else None
    try:
        cursor.execute(
            """
            INSERT INTO exams (exam_name, exam_type, course, semester, academic_year, status, max_marks, pass_marks, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (exam_name, exam_type, course, semester, academic_year, status, mx, pm, created_by)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        cursor.close()
        conn.close()


def ensure_exam_tables_exist():
    """
    Ensure that subjects, exams, and exam_marks tables exist in the database.
    Idempotent and safe to run on every app startup or on demand.
    """
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS subjects (
                id            INT AUTO_INCREMENT PRIMARY KEY,
                course        VARCHAR(50)  NOT NULL,
                semester      INT          NOT NULL,
                subject_code  VARCHAR(20)  NULL,
                subject_name  VARCHAR(150) NOT NULL,
                max_marks     DECIMAL(5,2) NOT NULL DEFAULT 100.00,
                pass_marks    DECIMAL(5,2) NOT NULL DEFAULT 40.00,
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY uq_course_sem_subject (course, semester, subject_name)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS exams (
                id            INT AUTO_INCREMENT PRIMARY KEY,
                exam_name     VARCHAR(150) NOT NULL,
                exam_type     ENUM('Internal 1','Internal 2','Practical','Semester Examination') NOT NULL,
                course        VARCHAR(50)  NOT NULL,
                semester      INT          NOT NULL,
                academic_year VARCHAR(20)  NOT NULL,
                status        VARCHAR(50)  NOT NULL DEFAULT 'Scheduled',
                max_marks     DECIMAL(5,2) NULL,
                pass_marks    DECIMAL(5,2) NULL,
                created_by    INT          NOT NULL,
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (created_by) REFERENCES users(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS exam_marks (
                id             INT AUTO_INCREMENT PRIMARY KEY,
                exam_id        INT          NOT NULL,
                stud_id        INT          NOT NULL,
                subject_id     INT          NOT NULL,
                obtained_marks DECIMAL(5,2) NOT NULL,
                max_marks      DECIMAL(5,2) NOT NULL DEFAULT 100.00,
                recorded_by    INT          NOT NULL,
                created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uq_exam_student_subject (exam_id, stud_id, subject_id),
                FOREIGN KEY (exam_id)    REFERENCES exams(id) ON DELETE CASCADE,
                FOREIGN KEY (stud_id)    REFERENCES students(id) ON DELETE CASCADE,
                FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE,
                FOREIGN KEY (recorded_by) REFERENCES users(id)
            )
        """)

        sem1_subjects = [
            ("PSC101", "Problem Solving Using C"),
            ("MFCS102", "Mathematics Foundation to Computer Science"),
            ("CA103", "Computer Architecture"),
            ("EVS104", "Environmental Studies (EVS)"),
            ("IKS105", "Indian Knowledge System (IKS)"),
            ("ENG106", "General English"),
        ]
        for code, name in sem1_subjects:
            cursor.execute(
                """
                INSERT IGNORE INTO subjects (course, semester, subject_code, subject_name, max_marks, pass_marks)
                VALUES ('BCA', 1, %s, %s, 100.00, 40.00)
                """,
                (code, name)
            )

        sem2_subjects = [
            ("DS201", "Data Structures"),
            ("OOPC202", "Object Oriented Programming Using C++ (OOP C++)"),
            ("OOPJ203", "Object Oriented Programming Using Java (OOP Java)"),
            ("OS204", "Operating System"),
            ("WT205", "Web Technology"),
            ("IC206", "Indian Constitution"),
        ]
        for code, name in sem2_subjects:
            cursor.execute(
                """
                INSERT IGNORE INTO subjects (course, semester, subject_code, subject_name, max_marks, pass_marks)
                VALUES ('BCA', 2, %s, %s, 100.00, 40.00)
                """,
                (code, name)
            )

        sem3_subjects = [
            ("SE301", "Software Engineering (SE)"),
            ("DBMS302", "Database Management System (DBMS)"),
            ("PY303", "Python"),
            ("PS304", "Probability and Statistics"),
            ("FE305", "Future Engineering"),
            ("BDA306", "Basics of Data Analytics Using Spreadsheet"),
        ]
        for code, name in sem3_subjects:
            cursor.execute(
                """
                INSERT IGNORE INTO subjects (course, semester, subject_code, subject_name, max_marks, pass_marks)
                VALUES ('BCA', 3, %s, %s, 100.00, 40.00)
                """,
                (code, name)
            )

        conn.commit()
    except Error as e:
        logger.warning("Database error during ensure_exam_tables_exist: %s", e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    # Idempotent migrations: add max_marks and pass_marks to exams if missing
    _migrate_add_exam_max_marks()
    _migrate_add_exam_pass_marks()


def _migrate_add_exam_max_marks():
    """
    Idempotent ALTER TABLE: adds max_marks column to the exams table if it does not yet exist.
    Safe to run multiple times. Existing data is not affected.
    """
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT COUNT(*) FROM information_schema.columns
            WHERE table_schema = DATABASE()
              AND table_name = 'exams'
              AND column_name = 'max_marks'
            """
        )
        if cursor.fetchone()[0] == 0:
            cursor.execute(
                "ALTER TABLE exams ADD COLUMN max_marks DECIMAL(5,2) NULL"
            )
            conn.commit()
    except Error as e:
        logger.warning("Database error in _migrate_add_exam_max_marks: %s", e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def _migrate_add_exam_pass_marks():
    """
    Idempotent ALTER TABLE: adds pass_marks column to the exams table if it does not yet exist.
    Safe to run multiple times. Existing data is not affected.
    """
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Check if column already exists
        cursor.execute(
            """
            SELECT COUNT(*) FROM information_schema.columns
            WHERE table_schema = DATABASE()
              AND table_name = 'exams'
              AND column_name = 'pass_marks'
            """
        )
        if cursor.fetchone()[0] == 0:
            cursor.execute(
                "ALTER TABLE exams ADD COLUMN pass_marks DECIMAL(5,2) NULL"
            )
            conn.commit()
    except Error as e:
        logger.warning("Database error in _migrate_add_exam_pass_marks: %s", e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def _fetch_all_exams_query(course=None, semester=None, academic_year=None, status=None):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        query = """
            SELECT e.*, COALESCE(u.username, 'Admin') as creator_name
            FROM exams e
            LEFT JOIN users u ON u.id = e.created_by
            WHERE 1=1
        """
        params = []
        if course:
            query += " AND e.course = %s"
            params.append(course)
        if semester:
            query += " AND e.semester = %s"
            params.append(semester)
        if academic_year:
            query += " AND e.academic_year = %s"
            params.append(academic_year)
        if status:
            query += " AND e.status = %s"
            params.append(status)
        query += " ORDER BY e.created_at DESC"
        cursor.execute(query, params)
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def get_all_exams(course=None, semester=None, academic_year=None, status=None):
    """Fetch exams with optional filtering, auto-creating tables if missing."""
    try:
        return _fetch_all_exams_query(course, semester, academic_year, status)
    except Error as e:
        if getattr(e, 'errno', None) == 1146 or "doesn't exist" in str(e).lower():
            ensure_exam_tables_exist()
            return _fetch_all_exams_query(course, semester, academic_year, status)
        raise e


def get_exam_by_id(exam_id):
    """Fetch a single exam record by ID."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT e.*, COALESCE(u.username, 'Admin') as creator_name
            FROM exams e
            LEFT JOIN users u ON u.id = e.created_by
            WHERE e.id = %s
            """,
            (exam_id,)
        )
        return cursor.fetchone()
    except Error as e:
        if getattr(e, 'errno', None) == 1146 or "doesn't exist" in str(e).lower():
            ensure_exam_tables_exist()
            cursor.execute(
                """
                SELECT e.*, COALESCE(u.username, 'Admin') as creator_name
                FROM exams e
                LEFT JOIN users u ON u.id = e.created_by
                WHERE e.id = %s
                """,
                (exam_id,)
            )
            return cursor.fetchone()
        raise e
    finally:
        cursor.close()
        conn.close()


def update_exam(exam_id, exam_name, exam_type, course, semester, academic_year, status,
                max_marks=None, pass_marks=None):
    """Update an existing exam record."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        fields = ["exam_name = %s", "exam_type = %s", "course = %s", "semester = %s", "academic_year = %s", "status = %s"]
        params = [exam_name, exam_type, course, semester, academic_year, status]
        if max_marks is not None:
            fields.append("max_marks = %s")
            params.append(float(max_marks))
        if pass_marks is not None:
            fields.append("pass_marks = %s")
            params.append(float(pass_marks))
        params.append(exam_id)

        sql = f"UPDATE exams SET {', '.join(fields)} WHERE id = %s"
        cursor.execute(sql, params)
        conn.commit()
        return cursor.rowcount
    finally:
        cursor.close()
        conn.close()


def delete_exam(exam_id):
    """Delete an exam record and all associated marks."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM exams WHERE id = %s", (exam_id,))
        conn.commit()
        return cursor.rowcount
    finally:
        cursor.close()
        conn.close()


def has_exam_marks(exam_id):
    """Check if any marks have been recorded for an exam."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT 1 FROM exam_marks WHERE exam_id = %s LIMIT 1", (exam_id,))
        return cursor.fetchone() is not None
    finally:
        cursor.close()
        conn.close()



# ---------------------------------------------------------------------------
# Exam Marks / Results query helpers
# ---------------------------------------------------------------------------

def _resolve_student_pk(stud_id):
    """If stud_id is a string like 'BCA2401', lookup the integer PK 'id' from students table."""
    if isinstance(stud_id, int):
        return stud_id
    if isinstance(stud_id, str):
        if stud_id.isdigit():
            return int(stud_id)
        student = get_student_by_student_id(stud_id)
        if student and "id" in student:
            return student["id"]
        student = get_student_by_id(stud_id)
        if student and "id" in student:
            return student["id"]
    return stud_id


def save_exam_marks(exam_id, stud_id, subject_id, obtained_marks, max_marks, recorded_by):
    """
    Insert or update a student's marks for a subject in an exam.
    Prevents duplicate entries via ON DUPLICATE KEY UPDATE.
    """
    pk_id = _resolve_student_pk(stud_id)
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO exam_marks (exam_id, stud_id, subject_id, obtained_marks, max_marks, recorded_by)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                obtained_marks = VALUES(obtained_marks),
                max_marks = VALUES(max_marks),
                recorded_by = VALUES(recorded_by)
            """,
            (exam_id, pk_id, subject_id, obtained_marks, max_marks, recorded_by)
        )
        conn.commit()
        return cursor.lastrowid or cursor.rowcount
    finally:
        cursor.close()
        conn.close()


def get_exam_marks_for_student(exam_id, stud_id):
    """Fetch all subject marks recorded for a specific student in an exam.
    The pass_marks returned in each row reflects the exam-level configured passing mark
    (if set on the exam), falling back to the subject-level pass_marks otherwise.
    """
    pk_id = _resolve_student_pk(stud_id)
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT m.id, m.exam_id, m.stud_id, m.subject_id, m.obtained_marks, m.recorded_by, m.created_at, m.updated_at,
                   sub.subject_name,
                   sub.subject_code,
                   COALESCE(e.max_marks, m.max_marks, sub.max_marks) AS max_marks,
                   COALESCE(e.pass_marks, sub.pass_marks) AS pass_marks
            FROM exam_marks m
            JOIN subjects sub ON sub.id = m.subject_id
            JOIN exams    e   ON e.id  = m.exam_id
            WHERE m.exam_id = %s AND m.stud_id = %s
            ORDER BY sub.id ASC
            """,
            (exam_id, pk_id)
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def get_all_marks_for_exam(exam_id):
    """Fetch all recorded marks for an exam grouped by student."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT m.id, m.exam_id, m.stud_id, m.subject_id, m.obtained_marks, m.recorded_by, m.created_at, m.updated_at,
                   s.student_name, s.student_id as roll_no, sub.subject_name, sub.subject_code,
                   COALESCE(e.max_marks, m.max_marks, sub.max_marks) AS max_marks
            FROM exam_marks m
            JOIN students s ON s.id = m.stud_id
            JOIN subjects sub ON sub.id = m.subject_id
            JOIN exams e ON e.id = m.exam_id
            WHERE m.exam_id = %s
            ORDER BY s.student_name ASC, sub.id ASC
            """,
            (exam_id,)
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def get_student_exam_history(stud_id):
    """Fetch all exam results recorded for a student across all semesters.
    Uses 2 batch database queries instead of 1 + N queries to eliminate the N+1 query pattern.
    """
    pk_id = _resolve_student_pk(stud_id)
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT DISTINCT e.*
            FROM exams e
            JOIN exam_marks m ON m.exam_id = e.id
            WHERE m.stud_id = %s
            ORDER BY e.academic_year DESC, e.semester DESC, e.created_at DESC
            """,
            (pk_id,)
        )
        exam_list = cursor.fetchall()
        if not exam_list:
            return []

        cursor.execute(
            """
            SELECT m.id, m.exam_id, m.stud_id, m.subject_id, m.obtained_marks, m.recorded_by, m.created_at, m.updated_at,
                   sub.subject_name,
                   sub.subject_code,
                   COALESCE(e.max_marks, m.max_marks, sub.max_marks) AS max_marks,
                   COALESCE(e.pass_marks, sub.pass_marks) AS pass_marks
            FROM exam_marks m
            JOIN subjects sub ON sub.id = m.subject_id
            JOIN exams    e   ON e.id  = m.exam_id
            WHERE m.stud_id = %s
            ORDER BY sub.id ASC
            """,
            (pk_id,)
        )
        all_marks = cursor.fetchall()

        marks_by_exam = {}
        for m_row in all_marks:
            ex_id = m_row["exam_id"]
            if ex_id not in marks_by_exam:
                marks_by_exam[ex_id] = []
            marks_by_exam[ex_id].append(m_row)

        history = []
        for exam in exam_list:
            e_id = exam["id"]
            history.append({
                "exam": exam,
                "marks": marks_by_exam.get(e_id, [])
            })
        return history
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# Student Document Management Query Helpers
# ---------------------------------------------------------------------------

def ensure_document_table_exists():
    """
    Ensure student_documents table exists in the database.
    Idempotent and safe to run on app startup.
    """
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS student_documents (
                id                INT AUTO_INCREMENT PRIMARY KEY,
                stud_id           INT          NOT NULL,
                doc_type          ENUM('Aadhaar Card','Marksheet','Caste Certificate','Caste Validity','Leaving Certificate','Bonafide','Passport Photo','Other') NOT NULL,
                custom_doc_name   VARCHAR(150) NULL,
                original_filename VARCHAR(255) NOT NULL,
                stored_filename   VARCHAR(255) NOT NULL,
                mime_type         VARCHAR(100) NOT NULL,
                file_size_bytes   INT          NOT NULL,
                status            ENUM('Pending','Verified','Rejected') NOT NULL DEFAULT 'Pending',
                rejection_reason  TEXT         NULL,
                uploaded_by       INT          NOT NULL,
                verified_by       INT          NULL,
                verified_at       DATETIME     NULL,
                created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (stud_id)     REFERENCES students(id) ON DELETE CASCADE,
                FOREIGN KEY (uploaded_by) REFERENCES users(id),
                FOREIGN KEY (verified_by) REFERENCES users(id)
            )
        """)
        conn.commit()
    except Exception as e:
        logger.warning("Database error during ensure_document_table_exists: %s", e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def insert_student_document(stud_id, doc_type, custom_doc_name, original_filename, stored_filename, mime_type, file_size_bytes, uploaded_by):
    """Insert a new document record for a student."""
    pk_id = _resolve_student_pk(stud_id)
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO student_documents
                (stud_id, doc_type, custom_doc_name, original_filename, stored_filename, mime_type, file_size_bytes, status, uploaded_by)
            VALUES
                (%s, %s, %s, %s, %s, %s, %s, 'Pending', %s)
        """, (pk_id, doc_type, custom_doc_name, original_filename, stored_filename, mime_type, file_size_bytes, uploaded_by))
        conn.commit()
        return cursor.lastrowid
    finally:
        cursor.close()
        conn.close()


def get_student_documents(stud_id):
    """Fetch all documents for a specific student, ordered newest first."""
    pk_id = _resolve_student_pk(stud_id)
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT d.*, 
                   u1.username AS uploader_username,
                   u2.username AS verifier_username
            FROM student_documents d
            LEFT JOIN users u1 ON u1.id = d.uploaded_by
            LEFT JOIN users u2 ON u2.id = d.verified_by
            WHERE d.stud_id = %s
            ORDER BY d.created_at DESC
        """, (pk_id,))
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def get_document_by_id(doc_id):
    """Fetch a single document by document ID."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT d.*, 
                   u1.username AS uploader_username,
                   u2.username AS verifier_username
            FROM student_documents d
            LEFT JOIN users u1 ON u1.id = d.uploaded_by
            LEFT JOIN users u2 ON u2.id = d.verified_by
            WHERE d.id = %s
        """, (doc_id,))
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()


def update_document_status(doc_id, status, verifier_user_id, rejection_reason=None):
    """Update document status (Verified or Rejected). Sets verified_by and verified_at."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE student_documents
            SET status = %s,
                verified_by = %s,
                verified_at = NOW(),
                rejection_reason = %s
            WHERE id = %s
        """, (status, verifier_user_id, rejection_reason if status == 'Rejected' else None, doc_id))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        cursor.close()
        conn.close()


def delete_student_document(doc_id):
    """Delete a document record by ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM student_documents WHERE id = %s", (doc_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        cursor.close()
        conn.close()


def get_document_stats_for_student(stud_id):
    """Return summary document statistics for a student (total, verified, pending, rejected)."""
    pk_id = _resolve_student_pk(stud_id)
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT 
                COUNT(*) AS total,
                SUM(CASE WHEN status = 'Verified' THEN 1 ELSE 0 END) AS verified,
                SUM(CASE WHEN status = 'Pending' THEN 1 ELSE 0 END) AS pending,
                SUM(CASE WHEN status = 'Rejected' THEN 1 ELSE 0 END) AS rejected
            FROM student_documents
            WHERE stud_id = %s
        """, (pk_id,))
        row = cursor.fetchone()
        if not row or row["total"] == 0:
            return {"total": 0, "verified": 0, "pending": 0, "rejected": 0}
        return {
            "total": int(row["total"] or 0),
            "verified": int(row["verified"] or 0),
            "pending": int(row["pending"] or 0),
            "rejected": int(row["rejected"] or 0)
        }
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# Global Search Service
# ---------------------------------------------------------------------------

def _escape_like_query(search_str):
    """Escape % and _ for safe literal matching in SQL LIKE statements."""
    if not search_str:
        return ""
    return search_str.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def global_search(query, user_role, user_id, linked_student_id=None, limit=10):
    """
    Executes a role-restricted parameterized global search across 7 modules:
    Students, Exams, Results, Fees, Notices, Certificates, Audit Logs.
    
    Returns a dictionary of category result lists.
    """
    empty_response = {
        "query": query.strip() if query and isinstance(query, str) else "",
        "results": {
            "students": [],
            "exams": [],
            "results": [],
            "fees": [],
            "notices": [],
            "certificates": [],
            "audit_logs": []
        }
    }

    if not query or not isinstance(query, str):
        return empty_response

    q_trimmed = query.strip()
    if len(q_trimmed) < 2:
        return empty_response

    safe_like = f"%{_escape_like_query(q_trimmed)}%"
    role = (user_role or "").lower()
    student_pk = _resolve_student_pk(linked_student_id) if linked_student_id else None

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    results = {
        "students": [],
        "exams": [],
        "results": [],
        "fees": [],
        "notices": [],
        "certificates": [],
        "audit_logs": []
    }

    try:
        # 1. STUDENTS SEARCH
        if role in ("admin", "teacher"):
            cursor.execute("""
                SELECT id, student_id, student_name, course, semester, email, phone
                FROM students
                WHERE student_name LIKE %s ESCAPE '\\\\'
                   OR student_id LIKE %s ESCAPE '\\\\'
                   OR email LIKE %s ESCAPE '\\\\'
                   OR phone LIKE %s ESCAPE '\\\\'
                ORDER BY (CASE WHEN student_id = %s THEN 0 WHEN student_id LIKE %s ESCAPE '\\\\' THEN 1 ELSE 2 END), student_name ASC
                LIMIT %s
            """, (safe_like, safe_like, safe_like, safe_like, q_trimmed, f"{_escape_like_query(q_trimmed)}%", limit))
            s_rows = cursor.fetchall()
            for r in s_rows:
                results["students"].append({
                    "id": r["id"],
                    "student_id": r["student_id"],
                    "title": r["student_name"],
                    "subtitle": f"{r['student_id']} • {r['course']} Sem {r['semester']}",
                    "detail": r["email"] or "",
                    "url": f"/students/{r['id']}",
                    "action_text": "View Student"
                })
        elif role == "student" and student_pk:
            cursor.execute("""
                SELECT id, student_id, student_name, course, semester, email, phone
                FROM students
                WHERE id = %s AND (
                    student_name LIKE %s ESCAPE '\\\\'
                 OR student_id LIKE %s ESCAPE '\\\\'
                 OR email LIKE %s ESCAPE '\\\\'
                 OR phone LIKE %s ESCAPE '\\\\'
                )
                LIMIT 1
            """, (student_pk, safe_like, safe_like, safe_like, safe_like))
            s_rows = cursor.fetchall()
            for r in s_rows:
                results["students"].append({
                    "id": r["id"],
                    "student_id": r["student_id"],
                    "title": r["student_name"],
                    "subtitle": f"{r['student_id']} • {r['course']} Sem {r['semester']}",
                    "detail": r["email"] or "",
                    "url": f"/students/{r['id']}",
                    "action_text": "View Student"
                })

        # 2. EXAMS SEARCH
        if role in ("admin", "teacher"):
            cursor.execute("""
                SELECT e.id, e.exam_name, e.exam_type, e.course, e.semester, e.academic_year, e.status
                FROM exams e
                WHERE e.exam_name LIKE %s ESCAPE '\\\\'
                   OR e.course LIKE %s ESCAPE '\\\\'
                   OR e.academic_year LIKE %s ESCAPE '\\\\'
                   OR e.exam_type LIKE %s ESCAPE '\\\\'
                ORDER BY e.created_at DESC
                LIMIT %s
            """, (safe_like, safe_like, safe_like, safe_like, limit))
            e_rows = cursor.fetchall()
            for r in e_rows:
                results["exams"].append({
                    "id": r["id"],
                    "title": r["exam_name"],
                    "subtitle": f"{r['exam_type']} • {r['course']} Sem {r['semester']} ({r['academic_year']})",
                    "detail": f"Status: {r['status']}",
                    "url": f"/exams/{r['id']}/marks",
                    "action_text": "View Exam"
                })

        # 3. RESULTS SEARCH
        if role in ("admin", "teacher"):
            cursor.execute("""
                SELECT e.id AS exam_id, e.exam_name, s.id AS stud_pk, s.student_id, s.student_name, sub.subject_name, MAX(m.created_at) AS latest_created
                FROM exam_marks m
                JOIN exams e ON e.id = m.exam_id
                JOIN students s ON s.id = m.stud_id
                JOIN subjects sub ON sub.id = m.subject_id
                WHERE s.student_name LIKE %s ESCAPE '\\\\'
                   OR s.student_id LIKE %s ESCAPE '\\\\'
                   OR sub.subject_name LIKE %s ESCAPE '\\\\'
                   OR sub.subject_code LIKE %s ESCAPE '\\\\'
                   OR e.exam_name LIKE %s ESCAPE '\\\\'
                GROUP BY e.id, e.exam_name, s.id, s.student_id, s.student_name, sub.subject_name
                ORDER BY latest_created DESC
                LIMIT %s
            """, (safe_like, safe_like, safe_like, safe_like, safe_like, limit))
            r_rows = cursor.fetchall()
            for r in r_rows:
                results["results"].append({
                    "id": r["exam_id"],
                    "title": f"Result: {r['student_name']} ({r['student_id']})",
                    "subtitle": f"{r['exam_name']} • {r['subject_name']}",
                    "detail": f"Student Roll: {r['student_id']}",
                    "url": f"/students/{r['student_id']}/result-history",
                    "action_text": "View Result"
                })
        elif role == "student" and student_pk:
            cursor.execute("""
                SELECT e.id AS exam_id, e.exam_name, s.id AS stud_pk, s.student_id, s.student_name, sub.subject_name, MAX(m.created_at) AS latest_created
                FROM exam_marks m
                JOIN exams e ON e.id = m.exam_id
                JOIN students s ON s.id = m.stud_id
                JOIN subjects sub ON sub.id = m.subject_id
                WHERE s.id = %s AND (
                      sub.subject_name LIKE %s ESCAPE '\\\\'
                   OR sub.subject_code LIKE %s ESCAPE '\\\\'
                   OR e.exam_name LIKE %s ESCAPE '\\\\'
                   OR s.student_name LIKE %s ESCAPE '\\\\'
                   OR s.student_id LIKE %s ESCAPE '\\\\'
                )
                GROUP BY e.id, e.exam_name, s.id, s.student_id, s.student_name, sub.subject_name
                ORDER BY latest_created DESC
                LIMIT %s
            """, (student_pk, safe_like, safe_like, safe_like, safe_like, safe_like, limit))
            r_rows = cursor.fetchall()
            for r in r_rows:
                results["results"].append({
                    "id": r["exam_id"],
                    "title": f"My Result: {r['exam_name']}",
                    "subtitle": f"{r['subject_name']}",
                    "detail": f"Student ID: {r['student_id']}",
                    "url": f"/students/{r['student_id']}/result-history",
                    "action_text": "View Result"
                })


        # 4. FEES SEARCH (ADMIN & STUDENT OWN)
        if role == "admin":
            cursor.execute("""
                SELECT f.id, f.amount_due, f.amount_paid, f.due_date, s.id AS stud_pk, s.student_id, s.student_name
                FROM fees f
                JOIN students s ON s.id = f.stud_id
                WHERE s.student_name LIKE %s ESCAPE '\\\\'
                   OR s.student_id LIKE %s ESCAPE '\\\\'
                   OR CAST(f.amount_due AS CHAR) LIKE %s ESCAPE '\\\\'
                   OR CAST(f.amount_paid AS CHAR) LIKE %s ESCAPE '\\\\'
                ORDER BY f.created_at DESC
                LIMIT %s
            """, (safe_like, safe_like, safe_like, safe_like, limit))
            f_rows = cursor.fetchall()
            for r in f_rows:
                paid = float(r["amount_paid"])
                due = float(r["amount_due"])
                st = "Paid" if paid >= due else ("Partial" if paid > 0 else "Due")
                results["fees"].append({
                    "id": r["id"],
                    "title": f"Fee Record: {r['student_name']} ({r['student_id']})",
                    "subtitle": f"Status: {st} • Due: ₹{due:.0f} • Paid: ₹{paid:.0f}",
                    "detail": f"Due Date: {r['due_date']}",
                    "url": f"/students/{r['stud_pk']}",
                    "action_text": "View Fees"
                })
        elif role == "student" and student_pk:
            cursor.execute("""
                SELECT f.id, f.amount_due, f.amount_paid, f.due_date, s.id AS stud_pk, s.student_id, s.student_name
                FROM fees f
                JOIN students s ON s.id = f.stud_id
                WHERE s.id = %s AND (
                      CAST(f.amount_due AS CHAR) LIKE %s ESCAPE '\\\\'
                   OR CAST(f.amount_paid AS CHAR) LIKE %s ESCAPE '\\\\'
                   OR s.student_name LIKE %s ESCAPE '\\\\'
                   OR s.student_id LIKE %s ESCAPE '\\\\'
                )
                ORDER BY f.created_at DESC
                LIMIT %s
            """, (student_pk, safe_like, safe_like, safe_like, safe_like, limit))
            f_rows = cursor.fetchall()
            for r in f_rows:
                paid = float(r["amount_paid"])
                due = float(r["amount_due"])
                st = "Paid" if paid >= due else ("Partial" if paid > 0 else "Due")
                results["fees"].append({
                    "id": r["id"],
                    "title": f"My Fee Record",
                    "subtitle": f"Status: {st} • Due: ₹{due:.0f} • Paid: ₹{paid:.0f}",
                    "detail": f"Due Date: {r['due_date']}",
                    "url": f"/students/{r['stud_pk']}",
                    "action_text": "View Fees"
                })

        # 5. NOTICES SEARCH (ALL LOGGED-IN ROLES)
        if role in ("admin", "teacher", "student"):
            cursor.execute("""
                SELECT n.id, n.title, n.body, n.created_at, u.username
                FROM notices n
                LEFT JOIN users u ON u.id = n.posted_by
                WHERE n.title LIKE %s ESCAPE '\\\\'
                   OR n.body LIKE %s ESCAPE '\\\\'
                ORDER BY n.created_at DESC
                LIMIT %s
            """, (safe_like, safe_like, limit))
            n_rows = cursor.fetchall()
            for r in n_rows:
                body_snippet = (r["body"] or "")[:80] + ("..." if len(r["body"] or "") > 80 else "")
                results["notices"].append({
                    "id": r["id"],
                    "title": r["title"],
                    "subtitle": f"Posted by {r['username'] or 'System'} on {r['created_at']}",
                    "detail": body_snippet,
                    "url": "/notices",
                    "action_text": "View Notice"
                })

        # 6. CERTIFICATES SEARCH
        if role in ("admin", "teacher"):
            cursor.execute("""
                SELECT s.id, s.student_id, s.student_name, s.course, s.semester
                FROM students s
                WHERE s.student_name LIKE %s ESCAPE '\\\\'
                   OR s.student_id LIKE %s ESCAPE '\\\\'
                   OR s.course LIKE %s ESCAPE '\\\\'
                ORDER BY s.student_name ASC
                LIMIT %s
            """, (safe_like, safe_like, safe_like, limit))
            c_rows = cursor.fetchall()
            for r in c_rows:
                results["certificates"].append({
                    "id": r["id"],
                    "title": f"Bonafide Certificate: {r['student_name']}",
                    "subtitle": f"ID: {r['student_id']} • {r['course']} Sem {r['semester']}",
                    "detail": "Enrollment & Bonafide Certificate",
                    "url": f"/students/{r['id']}/certificate",
                    "action_text": "View Certificate"
                })
        elif role == "student" and student_pk:
            cursor.execute("""
                SELECT s.id, s.student_id, s.student_name, s.course, s.semester
                FROM students s
                WHERE s.id = %s AND (
                      s.student_name LIKE %s ESCAPE '\\\\'
                   OR s.student_id LIKE %s ESCAPE '\\\\'
                   OR s.course LIKE %s ESCAPE '\\\\'
                )
                LIMIT 1
            """, (student_pk, safe_like, safe_like, safe_like))
            c_rows = cursor.fetchall()
            for r in c_rows:
                results["certificates"].append({
                    "id": r["id"],
                    "title": "My Bonafide Certificate",
                    "subtitle": f"ID: {r['student_id']} • {r['course']} Sem {r['semester']}",
                    "detail": "Enrollment & Bonafide Certificate",
                    "url": f"/students/{r['id']}/certificate",
                    "action_text": "View Certificate"
                })

        # 7. AUDIT LOGS SEARCH (ADMIN ONLY or STUDENT OWN)
        if role == "admin":
            all_audit = get_audit_log(limit=100)
            q_lower = q_trimmed.lower()
            matching_audit = []
            for item in all_audit:
                desc = str(item.get("description", ""))
                actor = str(item.get("actor", ""))
                etype = str(item.get("event_type", ""))
                if q_lower in desc.lower() or q_lower in actor.lower() or q_lower in etype.lower():
                    matching_audit.append({
                        "id": len(matching_audit) + 1,
                        "title": desc,
                        "subtitle": f"By {actor} • {etype.capitalize()}",
                        "detail": f"Time: {item.get('event_time')}",
                        "url": "/audit-log",
                        "action_text": "View Audit Log"
                    })
                    if len(matching_audit) >= limit:
                        break
            results["audit_logs"] = matching_audit
        elif role == "student" and student_pk:
            student_audit = get_student_audit_log(student_pk, limit=20)
            q_lower = q_trimmed.lower()
            matching_audit = []
            for item in student_audit:
                desc = str(item.get("description", ""))
                actor = str(item.get("actor", ""))
                etype = str(item.get("event_type", ""))
                if q_lower in desc.lower() or q_lower in actor.lower() or q_lower in etype.lower():
                    matching_audit.append({
                        "id": len(matching_audit) + 1,
                        "title": desc,
                        "subtitle": f"By {actor} • {etype.capitalize()}",
                        "detail": f"Time: {item.get('event_time')}",
                        "url": f"/students/{student_pk}",
                        "action_text": "View Audit Log"
                    })
                    if len(matching_audit) >= limit:
                        break
            results["audit_logs"] = matching_audit

        return {
            "query": q_trimmed,
            "results": results
        }
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# Student Performance & Ranking Helpers
# ---------------------------------------------------------------------------

def get_semester_rankings(semester):
    """
    Calculates student rankings for a given semester strictly following Data Integrity Rules:
      1. Exam & Result Management (exam_marks + exams + subjects) is authoritative.
      2. Maximum marks resolution chain: exam.max_marks -> exam_marks.max_marks -> subject.max_marks.
         No hardcoded fallback (100, 500, 600, etc.) is assumed if unresolvable.
      3. Percentage = (Total Obtained Marks / Total Maximum Marks) * 100. No CGPA.
      4. Deterministic competition ranking (1, 2, 2, 4) for equal percentages.
      5. Displayed Obtained/Total marks and Percentage are derived from the exact same records.
      6. Grades table is used as fallback ONLY when no exam_marks record exists for the student.
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        try:
            sem_int = int(semester)
        except (ValueError, TypeError):
            sem_int = 1

        # Query exam_marks with strict 3-tier max_marks resolution (e.max_marks -> m.max_marks -> sub.max_marks)
        cursor.execute(
            """
            SELECT 
                s.id AS record_id,
                s.student_id,
                s.student_name,
                s.course,
                SUM(m.obtained_marks) AS total_obtained,
                SUM(COALESCE(e.max_marks, m.max_marks, sub.max_marks)) AS total_max,
                COUNT(m.id) AS marks_count
            FROM exam_marks m
            JOIN students s ON s.id = m.stud_id
            JOIN exams e ON e.id = m.exam_id
            JOIN subjects sub ON sub.id = m.subject_id
            WHERE e.semester = %s
              AND m.obtained_marks >= 0
              AND COALESCE(e.max_marks, m.max_marks, sub.max_marks) IS NOT NULL
              AND COALESCE(e.max_marks, m.max_marks, sub.max_marks) > 0
            GROUP BY s.id, s.student_id, s.student_name, s.course
            HAVING total_max IS NOT NULL AND total_max > 0 AND total_obtained >= 0
            """,
            (sem_int,)
        )
        exam_rows = cursor.fetchall()

        student_data = {}
        for r in exam_rows:
            sid = r["record_id"]
            obt = float(r["total_obtained"] or 0)
            mx = float(r["total_max"] or 0)
            if mx > 0 and obt >= 0:
                student_data[sid] = {
                    "record_id": sid,
                    "student_id": r["student_id"],
                    "student_name": r["student_name"],
                    "course": r["course"],
                    "total_obtained": obt,
                    "total_max": mx
                }

        # Fallback to grades table ONLY for students without any exam_marks records in this semester
        cursor.execute(
            """
            SELECT 
                s.id AS record_id,
                s.student_id,
                s.student_name,
                s.course,
                SUM(g.marks_obtained) AS total_obtained,
                SUM(g.max_marks) AS total_max,
                COUNT(g.id) AS grade_count
            FROM grades g
            JOIN students s ON s.id = g.stud_id
            WHERE g.semester = %s
              AND g.marks_obtained >= 0
              AND g.max_marks IS NOT NULL
              AND g.max_marks > 0
            GROUP BY s.id, s.student_id, s.student_name, s.course
            HAVING total_max IS NOT NULL AND total_max > 0 AND total_obtained >= 0
            """,
            (sem_int,)
        )
        grade_rows = cursor.fetchall()
        for r in grade_rows:
            sid = r["record_id"]
            if sid not in student_data:
                obt = float(r["total_obtained"] or 0)
                mx = float(r["total_max"] or 0)
                if mx > 0 and obt >= 0:
                    student_data[sid] = {
                        "record_id": sid,
                        "student_id": r["student_id"],
                        "student_name": r["student_name"],
                        "course": r["course"],
                        "total_obtained": obt,
                        "total_max": mx
                    }

        if not student_data:
            return []

        rank_list = []
        for sid, item in student_data.items():
            obt = item["total_obtained"]
            mx = item["total_max"]
            if mx <= 0 or obt < 0:
                continue

            pct = round((obt / mx * 100.0), 2)
            fmt_obt = f"{int(obt)}" if obt.is_integer() else f"{obt:.2f}"
            fmt_mx = f"{int(mx)}" if mx.is_integer() else f"{mx:.2f}"

            rank_list.append({
                "record_id": item["record_id"],
                "student_id": item["student_id"],
                "student_name": item["student_name"],
                "course": item["course"],
                "total_obtained": round(obt, 2),
                "total_max": round(mx, 2),
                "percentage": pct,
                "formatted_marks": f"{fmt_obt} / {fmt_mx}",
                "formatted_percentage": f"{pct:.2f}%"
            })

        # Sort descending by percentage, then total_obtained, then student_name
        rank_list.sort(key=lambda x: (-x["percentage"], -x["total_obtained"], x["student_name"]))

        # Competition ranking (1, 2, 2, 4)
        for i, item in enumerate(rank_list):
            if i > 0:
                prev_item = rank_list[i - 1]
                if item["percentage"] == prev_item["percentage"]:
                    item["rank"] = prev_item["rank"]
                else:
                    item["rank"] = i + 1
            else:
                item["rank"] = 1

        return rank_list
    finally:
        cursor.close()
        conn.close()




