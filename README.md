# Student Management System

A BCA 3rd Semester mini project: a Flask + MySQL admin panel for managing
student records (add, view, search, edit, delete), behind a simple
session-based admin login.

## Tech stack

- **Frontend:** HTML5, CSS3, vanilla JavaScript (Jinja2 templates)
- **Backend:** Python, Flask
- **Database:** MySQL, via `mysql-connector-python`

## Project structure

```
StudentManagement/
├── app.py                # Flask routes
├── database.py            # All SQL queries
├── config.py               # DB credentials + secret key
├── seed_admin.py            # One-off script to create the first admin login
├── schema.sql                # Run this in MySQL Workbench first
├── requirements.txt
│
├── templates/
│   ├── base.html              # Shared sidebar layout
│   ├── login.html
│   ├── dashboard.html
│   ├── students.html
│   ├── add_student.html
│   ├── edit_student.html
│   └── student_details.html
│
└── static/
    ├── css/style.css
    └── js/script.js
```

## Setup

1. **Create a virtual environment and install dependencies**

   ```bash
   python -m venv venv
   venv\Scripts\activate        # Windows
   source venv/bin/activate     # macOS / Linux

   pip install -r requirements.txt
   ```

2. **Create the database**

   Open MySQL Workbench (or the `mysql` CLI) and run `schema.sql`. This
   creates the `student_management` database, the `students` and `admins`
   tables, and inserts four sample students so the dashboard isn't empty
   on first run.

   ```bash
   mysql -u root -p < schema.sql
   ```

3. **Set your database credentials**

   Open `config.py` and update `DB_PASSWORD` (and `DB_USER`/`DB_HOST` if
   different from the defaults) to match your local MySQL setup. Also
   change `SECRET_KEY` to any random string.

4. **Create the first admin login**

   `schema.sql` only creates the `admins` table — it doesn't insert an
   admin, since the password needs to be hashed by the app itself. Run:

   ```bash
   python seed_admin.py
   ```

   This creates a login with username `admin` and password `admin123`.
   Open `seed_admin.py` and change the password before running it if
   you'd like something else. You can re-run this script with different
   arguments to add more admins later.

5. **Run the app**

   ```bash
   python app.py
   ```

   Then open `http://127.0.0.1:5000` in a browser and log in.

## Notes

- Passwords are stored as hashes (via `werkzeug.security`), never in
  plain text.
- All SQL queries use parameterized statements (`%s` placeholders) to
  avoid SQL injection.
- Every route except `/login` is protected by a `login_required`
  decorator that checks the session.
- Set `debug=False` in `app.py`'s last line before running this
  anywhere other than your own machine.
