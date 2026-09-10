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
