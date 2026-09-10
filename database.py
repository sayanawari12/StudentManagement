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

import mysql.connector
import config


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


# ---------------------------------------------------------------------------
# Dashboard queries
# ---------------------------------------------------------------------------

def get_dashboard_stats():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT COUNT(*) AS total FROM students")
        total_students = cursor.fetchone()["total"]

        cursor.execute(
            "SELECT COUNT(*) AS total FROM students WHERE course = %s", ("BCA",)
        )
        total_bca = cursor.fetchone()["total"]

        cursor.execute(
            "SELECT semester, COUNT(*) AS total "
            "FROM students GROUP BY semester ORDER BY semester"
        )
        semester_counts = cursor.fetchall()

        # Attendance today (Present count only)
        cursor.execute(
            "SELECT COUNT(*) AS total FROM attendance "
            "WHERE date = CURDATE() AND status = 'Present'"
        )
        attendance_today = cursor.fetchone()["total"]

        # Total outstanding dues — COALESCE prevents NULL on empty table (Fix 8)
        cursor.execute(
            "SELECT COALESCE(SUM(amount_due - amount_paid), 0) AS total_dues "
            "FROM fees WHERE amount_paid < amount_due"
        )
        total_dues = cursor.fetchone()["total_dues"]  # Decimal >= 0, never None

        return {
            "total_students":   total_students,
            "total_bca":        total_bca,
            "semester_counts":  semester_counts,
            "attendance_today": attendance_today,
            "total_dues":       total_dues,
        }
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# Student queries
# ---------------------------------------------------------------------------

def get_all_students(search=None):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        if search:
            like_term = f"%{search}%"
            cursor.execute(
                """SELECT * FROM students
                   WHERE student_name LIKE %s
                      OR student_id   LIKE %s
                      OR email        LIKE %s
                   ORDER BY id DESC""",
                (like_term, like_term, like_term)
            )
        else:
            cursor.execute("SELECT * FROM students ORDER BY id DESC")
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
            "SELECT id, student_name, student_id FROM students ORDER BY student_name"
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
