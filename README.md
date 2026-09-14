# Student Management System

A Flask + Jinja2 + MySQL web application for managing student records, attendance, grades, exams, academic transcripts, fees, notices, student ID cards, audit logs, and analytics — with role-based access control (Admin, Teacher, Student), Two-Factor Authentication, and a full automated test suite.

---

## Features

### 🎓 Student Records
- **CRUD** — create, view, edit, and delete student profiles
- **Search** — live keyword search across the student list
- **Bulk CSV Import** — upload a `.csv` file to create many students at once; performs partial import where valid rows are inserted and invalid rows are skipped with per-row validation feedback
- **CSV Export** — download the current (filtered) student list as a re-importable `.csv` file; phone numbers are wrapped as Excel text-literals (`="digits"`) to prevent scientific-notation rendering
- **Student ID Cards & QR Verification** — generate student ID cards with embedded QR codes; smartphone scans resolve to a public verification page (`/verify/student/<student_id>`) for instant authenticity checks

### 📚 Academic
- **Attendance** — mark daily Present / Absent for each student; attendance is audit-stamped with the recording teacher's username
- **Attendance History** — view a student's complete attendance log
- **Grades** — add subject grades per student; view a grade summary with auto-calculated totals and ordering
- **Exam & Result Management** — schedule and manage exams (Internal 1, Internal 2, Practical, Semester Examination) with dynamic maximum marks and passing marks; auto-provisions BCA subjects for Semesters 1, 2, and 3; validates marks against authoritative exam bounds; computes detailed student result summaries with letter grades (A+ to F) and PASS/FAIL determinations requiring passing every individual subject; generates downloadable ReportLab PDF marksheets
- **Academic Transcript / Academic Record** — complete student academic history grouped semester-wise and exam-wise; calculates cumulative totals across all semesters (total exams, total subjects, marks obtained/max, overall percentage, passed/failed count, and overall grade); generates downloadable ReportLab PDF transcripts
- **Certificates & PDF Exports** — generate student certificates as downloadable PDF files via ReportLab; PDF reports for individual student details and dashboard metrics

### 💰 Financial
- **Fees** — create fee dues, record partial or full payments, view payment history; overpayment is rejected at the database level; fee-section visibility is role-controlled

### 🔐 Roles & Security
- **Role-Based Access Control** — Admin (full access), Teacher (view students, mark attendance, add grades, manage exams, post notices), Student (own record + read-only access)
- **Two-Factor Authentication (TOTP)** — users can enable/disable TOTP-based 2FA; login flow redirects to a verification step when 2FA is active; QR-code provisioning via `qrcode`
- **Rate Limiting & Login Lockout** — `Flask-Limiter` restricts login attempts; 5 consecutive failures lock the account with a clear 429 error page
- **CSRF Protection** — all state-changing POST routes are guarded by Flask-WTF CSRF tokens; invalid or missing tokens return a 400
- **Password Change** — authenticated users can change their own password (requires current password confirmation)
- **Centralized Audit Log** — unified activity log capturing attendance markings, grade entries, and notices stamped with author username and timestamp
- **Custom Error Pages** — styled 403, 404, 429, and 500 pages

### 📢 Communication
- **Notices / Announcements** — Admin and Teacher can post notices visible to all roles; Admin can delete notices
- **Email Notifications** — Admin-triggered batch email sending via Flask-Mail: an admin visits the Notifications panel, reviews the lists of students with overdue fees or low attendance, and clicks a button to dispatch fee-reminder or attendance-alert emails in bulk

### 📊 Reporting & Analytics
- **Analytics Dashboard** — three Chart.js visualisations: Attendance Trend (last 14 days, line chart), Semester Distribution (bar chart), and Fee Status Breakdown (donut chart, admin-only)
- **PDF Generation** — `pdf_generator.py` produces formatted PDF documents (certificates, dashboard exports, marks cards, academic transcripts) using ReportLab

### ⚙️ Operations
- **Docker** — single `docker-compose up --build` spins up the Flask app and a MySQL 8 database; schema migration and user seeding run automatically on start
- **Continuous Integration** — GitHub Actions runs the full pytest suite on every push and pull request to `main`
- **Structured Logging** — Flask app logger and standard logging used throughout for warnings and errors

---

## Tech Stack

| Layer | Library / Tool | Purpose |
|---|---|---|
| Backend | **Flask** | Web framework — routing, sessions, request/response handling |
| Templating | **Jinja2** | HTML templating (bundled with Flask) |
| Database | **mysql-connector-python** | MySQL driver and connection management |
| Config | **python-dotenv** | Loads environment variables from `.env` at startup |
| Security | **Flask-WTF** | CSRF token generation and validation on every POST |
| 2FA | **pyotp** | TOTP secret generation and code verification |
| 2FA QR | **qrcode[pil]** | Generates QR-code images for authenticator-app provisioning and ID cards |
| Email | **Flask-Mail** | SMTP email sending for notifications |
| Rate Limiting | **Flask-Limiter** | Request-rate limits; login-attempt lockout |
| PDF | **reportlab** | PDF generation for marksheets, transcripts, certificates, and student reports |
| Production WSGI | **gunicorn** | WSGI server used inside the Docker container |
| Frontend | Vanilla CSS + JS | Custom "Museum Catalog" design system (Newsreader & IBM Plex Sans typography, terracotta accent) |

---

## Project Structure

```
StudentManagement/
├── app.py                      # Flask routes, auth decorators, validation logic
├── database.py                 # MySQL query helpers and connection management
├── config.py                   # Configuration loader (reads .env via python-dotenv)
├── exam_service.py             # Result calculation, letter grading, academic transcript engine
├── pdf_generator.py            # ReportLab PDF generation for certificates, marksheets, transcripts
├── migrate.py                  # Schema migration script (idempotent, safe to re-run)
├── seed_users.py               # Seeds Admin, Teacher, and Student login accounts
├── schema.sql                  # Full database schema + sample student & subject data
│
├── requirements.txt            # Production Python dependencies
├── requirements-dev.txt        # Dev/test dependencies (pytest, pytest-flask)
│
├── Dockerfile                  # Single-stage Docker image (python:3.12-slim) for the Flask app
├── docker-compose.yml          # Composes Flask app + MySQL 8 service
├── docker-entrypoint.sh        # Container startup: wait for DB → schema → seed → gunicorn
├── .dockerignore               # Files excluded from the Docker build context
│
├── .github/
│   └── workflows/
│       └── ci.yml              # GitHub Actions CI: pytest on every push / PR
│
├── pytest.ini                  # pytest configuration (testpaths, markers)
├── conftest.py                 # Shared test fixtures (Flask test client, DB setup)
│
├── templates/                  # Jinja2 HTML templates
│   ├── base.html               # Shell layout (sidebar, topbar, flash messages)
│   ├── login.html              # Username / password login form
│   ├── 2fa_setup.html          # TOTP 2FA setup (QR code + verification)
│   ├── 2fa_verify.html         # TOTP code entry during login
│   ├── change_password.html    # Authenticated password change form
│   ├── dashboard.html          # Dashboard with summary stats and recent notices
│   ├── students.html           # Student list, search, import/export buttons
│   ├── student_details.html    # Full student profile (attendance, grades, fees, transcripts)
│   ├── add_student.html        # Add new student form
│   ├── edit_student.html       # Edit existing student form
│   ├── students_import.html    # Bulk CSV import upload form + result display
│   ├── attendance.html         # Mark daily attendance form
│   ├── attendance_history.html # Per-student attendance log
│   ├── grades_add.html         # Add subject grade for a student
│   ├── exams.html              # Exam list with filters, create button, and result links
│   ├── exam_create.html        # Create new exam with dynamic max/pass marks
│   ├── exam_marks_entry.html   # Enter student marks per subject with range validation
│   ├── marksheet.html          # Individual student marksheet view with PDF download
│   ├── academic_transcript.html# Student multi-semester academic transcript view with PDF download
│   ├── id_card.html            # Printable student ID card with QR verification code
│   ├── id_card_verify.html     # Public verification response page for scanned ID cards
│   ├── audit_log.html          # Centralized audit log view (admin only)
│   ├── fees_create.html        # Create a fee due for a student
│   ├── fees_pay.html           # Record a fee payment
│   ├── fees_view.html          # View a student's fee history and outstanding dues
│   ├── notices.html            # Notice board (all roles) with delete for admin
│   ├── notice_add.html         # Post a new notice (admin / teacher)
│   ├── notifications.html      # Admin panel to send batch fee-reminder and attendance-alert emails
│   ├── analytics.html          # Analytics charts and summary tables
│   ├── 403.html                # Forbidden error page
│   ├── 404.html                # Not found error page
│   ├── 429.html                # Too many requests / login lockout error page
│   └── 500.html                # Internal server error page
│
├── static/
│   ├── css/style.css           # Design system (CSS variables, components, layout)
│   ├── js/script.js            # Frontend interactivity (search, flash dismissal)
│   └── fonts/                  # Bundled custom fonts (DancingScript for certificates)
│
└── tests/
    ├── __init__.py
    ├── test_2fa.py             # TOTP setup, login flow, disable flow
    ├── test_academic_record.py # Student academic transcript calculations, grouping, PDF export
    ├── test_analytics.py       # Analytics route access and DB query correctness
    ├── test_audit_log.py       # Audit log route access, event unioning, and ordering
    ├── test_auth.py            # Login flow, session contents, audit-trail & _get_user_id regression
    ├── test_bulk_import.py     # CSV import validation, column-order, partial import behavior
    ├── test_certificate_pdf.py # Certificate PDF generation output and content checks
    ├── test_csrf.py            # CSRF enforcement on all POST routes
    ├── test_csv_export.py      # CSV export headers, content, phone formatting
    ├── test_error_handlers.py  # 403/404/429/500 custom error page rendering
    ├── test_exams.py           # Exam CRUD, marks entry, result calculation, marksheets, fallback guards
    ├── test_fees.py            # Dues calculation, partial payments, overpayment guard
    ├── test_grades.py          # Grade insert/query, NULL safety, ordering
    ├── test_id_card.py         # ID card generation, QR code verification route
    ├── test_login_lockout.py   # Rate-limit and account lockout after failed logins
    ├── test_notices.py         # Notice CRUD access matrix, validation
    ├── test_notifications.py   # Email notification triggering and content
    ├── test_password_change.py # Password change flow, wrong-current-password guard
    └── test_permissions.py     # Full route permission matrix for all three roles
```

---

## Complete Setup Guide

Follow these steps in order to set up and run the project locally:

### 1. Clone the repository
```bash
git clone https://github.com/sayanawari12/StudentManagement.git
cd StudentManagement
```

### 2. Set up environment variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Open `.env` in a text editor and fill in your local MySQL credentials and a secure `SECRET_KEY`:
```env
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=your_mysql_password
DB_NAME=student_management
SECRET_KEY=your_random_secret_key
FLASK_DEBUG=false

# Optional public base URL for ID Card QR verification scans
PUBLIC_BASE_URL=https://your-domain.vercel.app

# Optional Seed Passwords (used when bootstrapping users in production)
# SEED_ADMIN_PASSWORD=your_secure_admin_password
# SEED_TEACHER_PASSWORD=your_secure_teacher_password
# SEED_STUDENT_PASSWORD=your_secure_student_password
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Set up the database
- **For a fresh installation** (creates database, tables, sample students, and subjects):
  ```bash
  mysql -u root -p < schema.sql
  ```
- **For an existing installation** (upgrading from an older schema):
  ```bash
  python migrate.py
  ```

### 5. Seed user accounts
Create initial user login accounts for all roles.

- **For local development and testing** (creates demo accounts):
  ```bash
  python seed_users.py --dev
  ```
  > **Demo accounts created:**
  > - **Admin**: `admin` / `admin123` (Full access)
  > - **Teacher**: `teacher` / `teacher123` (View students, mark attendance, exams, post notices)
  > - **Student**: `student` / `student123` (Linked to sample student BCA2401)

- **For production environments**, define your secure passwords via environment variables:
  ```bash
  SEED_ADMIN_PASSWORD="<secure-password>" \
  SEED_TEACHER_PASSWORD="<secure-password>" \
  SEED_STUDENT_PASSWORD="<secure-password>" \
  python seed_users.py
  ```

### 6. Run the application
```bash
python app.py
```
Open your browser and navigate to `http://127.0.0.1:5000` to log in.

---

## Security Note

> **Security Alert:** Development passwords from historical commits must never be reused. Always configure unique, high-entropy passwords in `.env` for production deployments.

---

## Running Tests

The test suite uses **pytest** (303 tests) and targets a separate `student_management_test` database — it never touches your real data.

### 1. Install dev dependencies
```bash
pip install -r requirements-dev.txt
```

### 2. Run the full suite
```bash
pytest
```

The test DB is created and torn down automatically. All tests run against the MySQL credentials configured in `.env`.

### Test coverage

| File | What is tested |
|------|----------------|
| `tests/test_2fa.py` | TOTP setup/enable/disable flows, 2FA login redirect, lockout after 5 wrong codes |
| `tests/test_academic_record.py` | Student academic transcript calculations, multi-semester grouping, dynamic marks handling, PDF export |
| `tests/test_analytics.py` | Analytics route access matrix, underlying DB query correctness |
| `tests/test_audit_log.py` | Audit log route access, event unioning across attendance/grades/notices, ordering |
| `tests/test_auth.py` | Login flow, session contents, audit-trail actor attribution, `_get_user_id` safe resolution |
| `tests/test_bulk_import.py` | CSV upload validation, column-order enforcement, partial import behavior (valid rows inserted, invalid rows skipped with per-row feedback) |
| `tests/test_certificate_pdf.py` | Certificate PDF generation output, file type, and content checks |
| `tests/test_csrf.py` | CSRF enforcement on POST — missing/empty/invalid/valid token cases |
| `tests/test_csv_export.py` | Export headers match `EXPECTED_CSV_HEADERS`, phone Excel text-literal format, filtered export |
| `tests/test_error_handlers.py` | 403/404/429/500 custom error page rendering |
| `tests/test_exams.py` | Exam CRUD, marks entry, validation, letter grades, marksheet generation, fallback hardening, DB startup logging |
| `tests/test_fees.py` | `get_total_dues()` NULL safety, partial payments, overpayment rejection at DB level |
| `tests/test_grades.py` | `get_grade_summary()` NULL safety, grade insert/query correctness, ordering |
| `tests/test_id_card.py` | Student ID card generation, QR code generation, public verification route |
| `tests/test_login_lockout.py` | Rate-limit enforcement, account lockout after 5 failed login attempts |
| `tests/test_notices.py` | Notice CRUD access matrix (admin/teacher/student), validation (empty title/body) |
| `tests/test_notifications.py` | Email notification triggering and content |
| `tests/test_password_change.py` | Password change success/failure, wrong-current-password guard |
| `tests/test_permissions.py` | Full route permission matrix (admin/teacher/student/anon), `_assert_own_record` guard, fees-section visibility per role |

---

## Run with Docker

Docker Compose spins up the Flask app **and** a MySQL 8 database together. Schema migration and user seeding happen automatically on every container start (both are idempotent, so restarts are safe).

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or Docker Engine + Compose plugin on Linux)

### 1. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and set your values (the `DB_HOST` field is overridden automatically to the compose service name — you don't need to change it):

```env
DB_HOST=localhost          # ignored in compose — overridden to "db" automatically
DB_USER=root
DB_PASSWORD=your_mysql_password
DB_NAME=student_management
SECRET_KEY=your_random_secret_key
FLASK_DEBUG=false          # keep false in production / containers
SEED_ALLOW_DEMO=true       # allow demo accounts in local docker environment
```

### 2. Build and start

```bash
docker-compose up --build
```

On first run, Docker will:
1. Pull the `mysql:8` image and start the database
2. Build the Flask app image
3. Wait for MySQL to be healthy (via `mysqladmin ping` healthcheck)
4. Apply `schema.sql` (creates tables + sample students + subjects)
5. Run `seed_users.py` (creates admin/teacher/student accounts)
6. Start `gunicorn` on port 5000

### 3. Open the app

Visit **http://localhost:5000** and log in with one of the seeded accounts:

| Username  | Password     | Role    |
|-----------|--------------|---------|
| `admin`   | `admin123`   | Admin   |
| `teacher` | `teacher123` | Teacher |
| `student` | `student123` | Student |

### Useful commands

```bash
# Start in the background (detached)
docker-compose up -d --build

# View logs
docker-compose logs -f app

# Stop and remove containers (data volume is preserved)
docker-compose down

# Stop and wipe the DB volume (full reset)
docker-compose down -v
```

---

## Continuous Integration

Every push to `main` (and every pull request targeting `main`) automatically runs the **full pytest suite** via GitHub Actions.

The workflow (`.github/workflows/ci.yml`) spins up a MySQL 8 service container using the same credentials as the test fixtures, installs all dependencies, and runs `pytest -v`. The build fails if any test fails.

You can see the live status of the latest run in the **Actions** tab of this repository.
