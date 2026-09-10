-- ============================================================
-- Student Management System -- full schema
-- Run on a fresh MySQL install:  mysql -u root -p < schema.sql
-- For existing installs that already have tables,
-- run migrate.py first.
--
-- Table creation order matters for FK constraints:
--   1. students  (no dependencies)
--   2. users     (FK -> students.id)
--   3. attendance (FK -> students.id, users.id)
--   4. fees       (FK -> students.id)
-- ============================================================

CREATE DATABASE IF NOT EXISTS student_management;
USE student_management;

-- ----------------------------------------------------------------
-- 1. Students  (created first -- no foreign key dependencies)
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS students (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    student_id     VARCHAR(20)  NOT NULL UNIQUE,   -- VARCHAR roll number e.g. 'BCA2401'
    student_name   VARCHAR(100) NOT NULL,
    email          VARCHAR(100) NOT NULL,
    phone          VARCHAR(15),
    gender         ENUM('Male','Female','Other'),
    date_of_birth  DATE,
    course         VARCHAR(50)  NOT NULL,
    semester       INT          NOT NULL,
    address        TEXT,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ----------------------------------------------------------------
-- 2. Users  (after students, so the FK to students.id is valid)
-- linked_student_id is NULL for admin/teacher, set for student role
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id                 INT AUTO_INCREMENT PRIMARY KEY,
    username           VARCHAR(50)  NOT NULL UNIQUE,
    password           VARCHAR(255) NOT NULL,          -- hashed, never plain text
    role               ENUM('admin','teacher','student') NOT NULL DEFAULT 'admin',
    linked_student_id  INT NULL,
    FOREIGN KEY (linked_student_id) REFERENCES students(id) ON DELETE SET NULL
);

-- ----------------------------------------------------------------
-- 3. Attendance
-- stud_id  = FK -> students.id  (INT primary key)
--            NOT students.student_id which is a VARCHAR roll number
-- marked_by = FK -> users.id
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS attendance (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    stud_id    INT  NOT NULL,
    date       DATE NOT NULL,
    status     ENUM('Present','Absent') NOT NULL,
    marked_by  INT  NOT NULL,
    UNIQUE KEY uq_attendance (stud_id, date),
    FOREIGN KEY (stud_id)   REFERENCES students(id) ON DELETE CASCADE,
    FOREIGN KEY (marked_by) REFERENCES users(id)
);

-- ----------------------------------------------------------------
-- 4. Fees
-- stud_id = FK -> students.id  (INT primary key)
-- One row per billing period. amount_paid is updated incrementally
-- via update_fee_payment(); never insert a new row for a payment.
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fees (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    stud_id      INT            NOT NULL,
    amount_due   DECIMAL(10,2)  NOT NULL,
    amount_paid  DECIMAL(10,2)  NOT NULL DEFAULT 0.00,
    due_date     DATE           NOT NULL,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (stud_id) REFERENCES students(id) ON DELETE CASCADE
);

-- ----------------------------------------------------------------
-- 5. Grades
-- stud_id = FK -> students.id (INT primary key)
-- recorded_by = FK -> users.id
-- ----------------------------------------------------------------
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
);

-- ----------------------------------------------------------------
-- Sample student data (INSERT IGNORE = safe to re-run)
-- ----------------------------------------------------------------
INSERT IGNORE INTO students
    (student_id, student_name, email, phone, gender, date_of_birth, course, semester, address)
VALUES
    ('BCA2401', 'Aarav Sharma',   'aarav.sharma@example.com',   '9876543210', 'Male',   '2005-04-12', 'BCA', 3, 'Aurangabad, Maharashtra'),
    ('BCA2402', 'Priya Deshmukh', 'priya.deshmukh@example.com', '9876543211', 'Female', '2005-08-23', 'BCA', 3, 'Pune, Maharashtra'),
    ('BCA2403', 'Rohan Patil',    'rohan.patil@example.com',    '9876543212', 'Male',   '2004-11-02', 'BCA', 5, 'Nashik, Maharashtra'),
    ('BCA2404', 'Sneha Kulkarni', 'sneha.kulkarni@example.com', '9876543213', 'Female', '2005-01-17', 'BCA', 1, 'Aurangabad, Maharashtra');
