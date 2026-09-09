"""
All MySQL access lives in this file. app.py never writes SQL directly —
it calls these functions instead. That separation is what makes it easy
to explain "how does Flask talk to MySQL" in viva: app.py handles the
web request, this file handles the database.
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
# Admin queries
# ---------------------------------------------------------------------------

def get_admin_by_username(username):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM admins WHERE username = %s", (username,))
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

        cursor.execute("SELECT COUNT(*) AS total FROM students WHERE course = %s", ("BCA",))
        total_bca = cursor.fetchone()["total"]

        cursor.execute(
            "SELECT semester, COUNT(*) AS total FROM students GROUP BY semester ORDER BY semester"
        )
        semester_counts = cursor.fetchall()

        return {
            "total_students": total_students,
            "total_bca": total_bca,
            "semester_counts": semester_counts
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
                      OR student_id LIKE %s
                      OR email LIKE %s
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
    """Look up a student by the human-facing roll number (`student_id`).

    Used to check for duplicates before inserting or updating a record.
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM students WHERE student_id = %s", (student_id,))
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
