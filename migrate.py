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

    # 4b — add requires_password_change column
    run(cursor,
        "ALTER TABLE users ADD COLUMN requires_password_change BOOLEAN NOT NULL DEFAULT FALSE",
        "ADD COLUMN users.requires_password_change")

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

    # 7 — grades table
    run(cursor, """
        CREATE TABLE IF NOT EXISTS grades (
            id              INT AUTO_INCREMENT PRIMARY KEY,
            stud_id         INT            NOT NULL,
            subject         VARCHAR(100)   NOT NULL,
            exam_type       ENUM('Internal','Mid-term','Final') NOT NULL,
            marks_obtained  DECIMAL(5,2)   NOT NULL,
            max_marks       DECIMAL(5,2)   NOT NULL DEFAULT 100.00,
            semester        INT            NOT NULL,
            recorded_by     INT            NOT NULL,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (stud_id)     REFERENCES students(id) ON DELETE CASCADE,
            FOREIGN KEY (recorded_by) REFERENCES users(id)
        )
    """, "CREATE TABLE grades")

    # 8 — notices table
    run(cursor, """
        CREATE TABLE IF NOT EXISTS notices (
            id              INT AUTO_INCREMENT PRIMARY KEY,
            title           VARCHAR(150) NOT NULL,
            body            TEXT NOT NULL,
            category        VARCHAR(50) NOT NULL DEFAULT 'General',
            priority        VARCHAR(20) NOT NULL DEFAULT 'Normal',
            target_course   VARCHAR(50) NULL,
            target_semester INT NULL,
            status          VARCHAR(20) NOT NULL DEFAULT 'Published',
            posted_by       INT NOT NULL,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (posted_by) REFERENCES users(id)
        )
    """, "CREATE TABLE notices")

    # 8b — notices table column extensions
    run(cursor, "ALTER TABLE notices ADD COLUMN category VARCHAR(50) NOT NULL DEFAULT 'General'", "ADD COLUMN notices.category")
    run(cursor, "ALTER TABLE notices ADD COLUMN priority VARCHAR(20) NOT NULL DEFAULT 'Normal'", "ADD COLUMN notices.priority")
    run(cursor, "ALTER TABLE notices ADD COLUMN target_course VARCHAR(50) NULL", "ADD COLUMN notices.target_course")
    run(cursor, "ALTER TABLE notices ADD COLUMN target_semester INT NULL", "ADD COLUMN notices.target_semester")
    run(cursor, "ALTER TABLE notices ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'Published'", "ADD COLUMN notices.status")


    # 9 — users.totp_secret column (2FA)
    run(cursor,
        "ALTER TABLE users ADD COLUMN totp_secret VARCHAR(32) NULL",
        "ADD COLUMN users.totp_secret")

    # 10 — users.totp_enabled column (2FA)
    run(cursor,
        "ALTER TABLE users ADD COLUMN totp_enabled BOOLEAN NOT NULL DEFAULT FALSE",
        "ADD COLUMN users.totp_enabled")

    # 11 — users.failed_login_attempts column (lockout)
    run(cursor,
        "ALTER TABLE users ADD COLUMN failed_login_attempts INT NOT NULL DEFAULT 0",
        "ADD COLUMN users.failed_login_attempts")

    # 12 — users.locked_until column (lockout)
    run(cursor,
        "ALTER TABLE users ADD COLUMN locked_until DATETIME NULL",
        "ADD COLUMN users.locked_until")

    # 13 — subjects table
    run(cursor, """
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
    """, "CREATE TABLE subjects")

    # 14 — exams table
    run(cursor, """
        CREATE TABLE IF NOT EXISTS exams (
            id            INT AUTO_INCREMENT PRIMARY KEY,
            exam_name     VARCHAR(150) NOT NULL,
            exam_type     ENUM('Internal 1','Internal 2','Practical','Semester Examination') NOT NULL,
            course        VARCHAR(50)  NOT NULL,
            semester      INT          NOT NULL,
            academic_year VARCHAR(20)  NOT NULL,
            status        VARCHAR(50)  NOT NULL DEFAULT 'Scheduled',
            created_by    INT          NOT NULL,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (created_by) REFERENCES users(id)
        )
    """, "CREATE TABLE exams")

    # 15 — exam_marks table
    run(cursor, """
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
    """, "CREATE TABLE exam_marks")

    # 16 — Seed default BCA subjects (Semesters 1, 2, and 3)
    run(cursor, """
        INSERT IGNORE INTO subjects (course, semester, subject_code, subject_name, max_marks, pass_marks) VALUES
            ('BCA', 1, 'PSC101', 'Problem Solving Using C', 100.00, 40.00),
            ('BCA', 1, 'MFCS102', 'Mathematics Foundation to Computer Science', 100.00, 40.00),
            ('BCA', 1, 'CA103', 'Computer Architecture', 100.00, 40.00),
            ('BCA', 1, 'EVS104', 'Environmental Studies (EVS)', 100.00, 40.00),
            ('BCA', 1, 'IKS105', 'Indian Knowledge System (IKS)', 100.00, 40.00),
            ('BCA', 1, 'ENG106', 'General English', 100.00, 40.00),
            ('BCA', 2, 'DS201', 'Data Structures', 100.00, 40.00),
            ('BCA', 2, 'OOPC202', 'Object Oriented Programming Using C++ (OOP C++)', 100.00, 40.00),
            ('BCA', 2, 'OOPJ203', 'Object Oriented Programming Using Java (OOP Java)', 100.00, 40.00),
            ('BCA', 2, 'OS204', 'Operating System', 100.00, 40.00),
            ('BCA', 2, 'WT205', 'Web Technology', 100.00, 40.00),
            ('BCA', 2, 'IC206', 'Indian Constitution', 100.00, 40.00),
            ('BCA', 3, 'SE301', 'Software Engineering (SE)', 100.00, 40.00),
            ('BCA', 3, 'DBMS302', 'Database Management System (DBMS)', 100.00, 40.00),
            ('BCA', 3, 'PY303', 'Python', 100.00, 40.00),
            ('BCA', 3, 'PS304', 'Probability and Statistics', 100.00, 40.00),
            ('BCA', 3, 'FE305', 'Future Engineering', 100.00, 40.00),
            ('BCA', 3, 'BDA306', 'Basics of Data Analytics Using Spreadsheet', 100.00, 40.00)
    """, "SEED Semester 1, 2, and 3 subjects")

    # 17 — student_documents table
    run(cursor, """
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
    """, "CREATE TABLE student_documents")

    # 13. Create timetable table
    run_migration(cursor, """
        CREATE TABLE IF NOT EXISTS timetable (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            semester    INT          NOT NULL,
            subject_id  INT          NOT NULL,
            teacher_id  INT          NOT NULL,
            day_of_week VARCHAR(20)  NOT NULL,
            start_time  TIME         NOT NULL,
            end_time    TIME         NOT NULL,
            room        VARCHAR(50)  NOT NULL,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE,
            FOREIGN KEY (teacher_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """, "CREATE TABLE timetable")

    conn.commit()
    cursor.close()
    conn.close()
    print("Done. Now run: python seed_users.py")



if __name__ == "__main__":
    migrate()
