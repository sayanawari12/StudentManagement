"""
migrate.py — run this ONCE on an existing install that already has an `admins` table.

Steps performed (idempotent — safe to re-run):
  1. RENAME TABLE admins → users
  2. ADD COLUMN role  ENUM('admin','teacher','student') DEFAULT 'admin'
  3. ADD COLUMN linked_student_id INT NULL (FK to students.id)
  4. CREATE TABLE attendance (if not exists)
  5. CREATE TABLE fees       (if not exists)

After running this, run:
    python seed_users.py
to add teacher + student login accounts.
"""

import mysql.connector
from mysql.connector import Error
import config


def run(cursor, sql, description):
    try:
        cursor.execute(sql)
        print(f"  OK  {description}")
    except Error as e:
        # 1060 = duplicate column, 1050 = table already exists,
        # 1146 = table doesn't exist (rename already done), etc.
        print(f"  SKIP ({e.errno}): {description} — {e.msg}")


def migrate():
    conn = mysql.connector.connect(
        host=config.DB_HOST,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        database=config.DB_NAME,
    )
    cursor = conn.cursor()

    print("Running migrations…")

    # 1 — rename admins → users
    run(cursor, "RENAME TABLE admins TO users",
        "RENAME TABLE admins -> users")

    # 2 — add role column
    run(cursor,
        "ALTER TABLE users ADD COLUMN role "
        "ENUM('admin','teacher','student') NOT NULL DEFAULT 'admin'",
        "ADD COLUMN users.role")

    # 3 — add linked_student_id column
    run(cursor,
        "ALTER TABLE users ADD COLUMN linked_student_id INT NULL",
        "ADD COLUMN users.linked_student_id")

    # 4 — add FK constraint (skip if already present)
    run(cursor,
        "ALTER TABLE users ADD CONSTRAINT fk_users_student "
        "FOREIGN KEY (linked_student_id) REFERENCES students(id) ON DELETE SET NULL",
        "ADD FK users.linked_student_id -> students.id")

    # 5 — attendance table
    run(cursor, """
        CREATE TABLE IF NOT EXISTS attendance (
            id        INT AUTO_INCREMENT PRIMARY KEY,
            stud_id   INT  NOT NULL,
            date      DATE NOT NULL,
            status    ENUM('Present','Absent') NOT NULL,
            marked_by INT  NOT NULL,
            UNIQUE KEY uq_attendance (stud_id, date),
            FOREIGN KEY (stud_id)   REFERENCES students(id) ON DELETE CASCADE,
            FOREIGN KEY (marked_by) REFERENCES users(id)
        )
    """, "CREATE TABLE attendance")

    # 6 — fees table
    run(cursor, """
        CREATE TABLE IF NOT EXISTS fees (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            stud_id     INT            NOT NULL,
            amount_due  DECIMAL(10,2)  NOT NULL,
            amount_paid DECIMAL(10,2)  NOT NULL DEFAULT 0.00,
            due_date    DATE           NOT NULL,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (stud_id) REFERENCES students(id) ON DELETE CASCADE
        )
    """, "CREATE TABLE fees")

    conn.commit()
    cursor.close()
    conn.close()
    print("Done. Now run: python seed_users.py")


if __name__ == "__main__":
    migrate()
