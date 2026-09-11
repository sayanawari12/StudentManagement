# Student Management System

A Flask + Jinja2 + MySQL web application for managing student records, attendance tracking, and fee collections with role-based access control (Admin, Teacher, Student).

---

## Tech Stack

- **Backend**: Python, Flask, Jinja2
- **Database**: MySQL (`mysql-connector-python`)
- **Security**: Flask-WTF (CSRF Protection), `python-dotenv` (Environment Secrets management), Werkzeug password hashing
- **Frontend**: Vanilla CSS with custom Museum Catalog design system (Newsreader & IBM Plex Sans typography)

---

## Project Structure

```
StudentManagement/
├── app.py                 # Flask application routes, auth decorators & validation
├── database.py            # MySQL database connection helpers & queries
├── config.py              # Configuration loader (reads .env via python-dotenv)
├── .env.example           # Template for local environment variables
├── schema.sql             # Full database schema and initial sample data
├── migrate.py            # Migration script for existing database installs
├── seed_users.py          # User seeding script (Admin, Teacher, Student)
├── requirements.txt       # Python package dependencies
├── templates/             # Jinja2 HTML templates
│   ├── base.html          # Shell layout (sidebar + topbar)
│   ├── dashboard.html     # Dashboard with stats overview
│   ├── students.html      # Student list & search
│   ├── student_details.html # Detailed view (profile, attendance, fees)
│   ├── add_student.html   # Add new student form
│   ├── edit_student.html  # Edit student details form
│   ├── attendance.html    # Mark daily attendance form
│   ├── fees_create.html   # Create fee due form
│   ├── fees_pay.html      # Record fee payment form
│   └── login.html         # User authentication form
└── static/                # Static assets (CSS styling & JS scripts)
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
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Set up the database
- **For a fresh installation** (creates database, tables, and sample students):
  ```bash
  mysql -u root -p < schema.sql
  ```
- **For an existing installation** (upgrading from an older schema):
  ```bash
  python migrate.py
  ```

### 5. Seed user accounts
Create initial user login accounts for all roles:
```bash
python seed_users.py
```
> **Default accounts created by seed script:**
> - **Admin**: `admin` / `admin123` (Full access)
> - **Teacher**: `teacher` / `teacher123` (View students, mark attendance)
> - **Student**: `student` / `student123` (Linked to sample student BCA2401)

### 6. Run the application
```bash
python app.py
```
Open your browser and navigate to `http://127.0.0.1:5000` to log in.

---

## Security Note

> **Security Alert:** The initial development password (`root123`) was committed to this repository in earlier git history. Removing secrets from `config.py` does not remove them from past commits. It is strongly recommended to change the actual MySQL root password used on your database server going forward.

---

## Running Tests

The test suite uses **pytest** and targets a separate `student_management_test` database — it never touches your real data.

### 1. Install dev dependencies
```bash
pip install -r requirements-dev.txt
```

### 2. Run the full suite
```bash
pytest
```

The test DB is created and torn down automatically. All tests run against the same MySQL credentials configured in `.env`.

### Test coverage

| File | What is tested |
|------|----------------|
| `tests/test_auth.py` | Login flow, session contents after login, `marked_by`/`recorded_by` audit trail regression |
| `tests/test_permissions.py` | Full route permission matrix (admin/teacher/student/anon), `_assert_own_record` guard, fees-section visibility per role |
| `tests/test_fees.py` | `get_total_dues()` NULL safety, partial payments, overpayment rejection at DB level |
| `tests/test_grades.py` | `get_grade_summary()` NULL safety, grade insert/query correctness, ordering |
| `tests/test_csrf.py` | CSRF enforcement on POST — missing/empty/invalid/valid token cases |

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
```

### 2. Build and start

```bash
docker-compose up --build
```

On first run, Docker will:
1. Pull the `mysql:8` image and start the database
2. Build the Flask app image
3. Wait for MySQL to be healthy (via `mysqladmin ping` healthcheck)
4. Apply `schema.sql` (creates tables + sample students)
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

