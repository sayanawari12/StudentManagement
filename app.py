import base64
import csv
import datetime
import io
import logging
import math
import os
import re
from decimal import Decimal
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, flash, abort, send_file
from werkzeug.security import check_password_hash, generate_password_hash
from mysql.connector import Error
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

import pyotp
import qrcode
import qrcode.image.svg

import config
import database
import exam_service
from pdf_generator import (
    generate_bonafide_pdf,
    generate_dashboard_pdf,
    generate_id_card_pdf,
    generate_marksheet_pdf,
    generate_academic_transcript_pdf,
)
from flask_wtf.csrf import CSRFProtect
from flask_mail import Mail, Message

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
csrf = CSRFProtect(app)

# IP-based rate limiting (per-process in-memory storage)
# NOTE: memory:// storage is per-process and resets on restart; it will NOT
# be shared correctly across multiple gunicorn worker processes in Docker/production.
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    storage_uri="memory://",
    enabled=lambda: not app.config.get("TESTING", False) and app.config.get("RATELIMIT_ENABLED", True)
)

app.config["MAIL_SERVER"] = config.MAIL_SERVER
app.config["MAIL_PORT"] = config.MAIL_PORT
app.config["MAIL_USE_TLS"] = config.MAIL_USE_TLS
app.config["MAIL_USERNAME"] = config.MAIL_USERNAME
app.config["MAIL_PASSWORD"] = config.MAIL_PASSWORD
app.config["MAIL_DEFAULT_SENDER"] = config.MAIL_DEFAULT_SENDER or config.MAIL_USERNAME or "noreply@institution.edu"
mail = Mail(app)


def _email_configured():
    """Return True if both MAIL_SERVER and MAIL_USERNAME are configured in app.config."""
    return bool(app.config.get("MAIL_SERVER")) and bool(app.config.get("MAIL_USERNAME"))

# ---------------------------------------------------------------------------
# Logging — only configure when not in debug mode; Flask's dev server already
# handles log output in debug mode.
# ---------------------------------------------------------------------------
if not config.FLASK_DEBUG:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

# ---------------------------------------------------------------------------
# Session cookie hardening (Task 4)
# ---------------------------------------------------------------------------
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
# Secure flag requires HTTPS — only enforce when not in local debug mode.
app.config["SESSION_COOKIE_SECURE"] = not config.FLASK_DEBUG

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
INSTITUTION_NAME        = "Sushganga Institute, Wani"
INSTITUTION_LOCATION    = "Wani, Dist. Yavatmal, Maharashtra – 445304"
INSTITUTION_AFFILIATION = "Affiliated to Sant Gadge Baba Amravati University, Amravati"
ATTENDANCE_TREND_DAYS = 14
NOTICES_LIMIT_DASH = 3    # recent notices shown on dashboard
NOTICES_LIMIT_FULL = 50   # cap for the full /notices page
AUDIT_LOG_LIMIT    = 100  # most recent combined events shown on /audit-log
EXPECTED_CSV_HEADERS = [
    "student_id", "student_name", "email", "phone",
    "gender", "date_of_birth", "course", "semester", "address"
]

# Ensure database tables for exams & subjects exist on application load
try:
    database.ensure_exam_tables_exist()
except Exception as _e:
    app.logger.warning("Could not initialize exam tables on application startup: %s", _e)


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def role_required(*roles):
    """Decorator factory — allows access only to users whose session role is
    in the given roles tuple.  Redirects to login if no session exists.

    Usage:
        @role_required('admin', 'teacher')
        def some_view(): ...

    login_required is an alias that accepts all three roles.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            if "role" not in session:
                flash("Please log in to continue.", "error")
                return redirect(url_for("login"))
            if session["role"] not in roles:
                abort(403)
            return view_func(*args, **kwargs)
        return wrapped
    return decorator


# Convenience alias — any logged-in user (admin, teacher, or student)
def login_required(view_func):
    return role_required("admin", "teacher", "student")(view_func)


def _assert_own_record(record_id):
    """For student-role users: abort 403 if record_id is not their linked student."""
    if str(session.get("role")).lower() == "student":
        linked_pk = session.get("linked_student_id")
        record_pk = database._resolve_student_pk(record_id)
        if str(record_pk) != str(linked_pk):
            abort(403)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def validate_student_form(form):
    """Server-side validation. Runs even if browser JS validation passed."""
    errors = []
    required_fields = {
        "student_id":   "Student ID",
        "student_name": "Student name",
        "email":        "Email",
        "course":       "Course",
        "semester":     "Semester",
    }
    for field, label in required_fields.items():
        if not form.get(field, "").strip():
            errors.append(f"{label} is required.")

    email = form.get("email", "").strip()
    if email and not EMAIL_REGEX.match(email):
        errors.append("Please enter a valid email address.")

    phone = form.get("phone", "").strip()
    if phone and (not phone.isdigit() or len(phone) not in (10, 11, 12)):
        errors.append("Please enter a valid phone number.")

    semester = form.get("semester", "").strip()
    if semester and (not semester.isdigit() or not (1 <= int(semester) <= 6)):
        errors.append("Semester must be a number between 1 and 6.")

    return errors


def validate_password_change_form(form, user):
    """Validates current_password, new_password, and confirm_new_password."""
    errors = []
    current_password = form.get("current_password", "")
    new_password = form.get("new_password", "")
    confirm_new_password = form.get("confirm_new_password", "")

    if not current_password or not check_password_hash(user["password"], current_password):
        errors.append("Current password is incorrect.")

    if len(new_password) < 8:
        errors.append("New password must be at least 8 characters long.")

    if new_password != confirm_new_password:
        errors.append("New password and confirmation do not match.")

    if current_password and new_password and current_password == new_password:
        errors.append("New password must be different from current password.")

    return errors


def student_payload(form):
    """Turns a submitted form into the dict shape database.py expects."""
    return {
        "student_id":    form.get("student_id", "").strip(),
        "student_name":  form.get("student_name", "").strip(),
        "email":         form.get("email", "").strip(),
        "phone":         form.get("phone", "").strip(),
        "gender":        form.get("gender", ""),
        "date_of_birth": form.get("date_of_birth") or None,
        "course":        form.get("course", "").strip(),
        "semester":      int(form.get("semester")),
        "address":       form.get("address", "").strip(),
    }


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    if "role" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


MAX_FAILED_ATTEMPTS = 5    # defined near login(), easy to change
LOCKOUT_MINUTES = 15


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        try:
            user = database.get_user_by_username(username)
        except Error as e:
            app.logger.warning("DB error during login for user %r from %s: %s", username, request.remote_addr, e)
            flash("Could not reach the database. Please check MySQL is running.", "error")
            return render_template("login.html")

        # 1. Account Lockout check (if account exists and is locked)
        if user and database.is_account_locked(user):
            locked_until = user["locked_until"]
            diff = locked_until - datetime.datetime.now()
            remaining_minutes = max(1, math.ceil(diff.total_seconds() / 60))
            flash(f"Account locked. Try again in {remaining_minutes} minutes.", "error")
            return render_template("login.html")

        # 2. Check password
        if user and check_password_hash(user["password"], password):
            try:
                database.reset_failed_login(user["id"])
            except Error as e:
                app.logger.warning("DB error resetting failed login attempts for user %s: %s", user["id"], e)

            if user.get("totp_enabled"):
                # 2FA is enabled — set a temporary pending marker and redirect
                # to the code-entry step. Full session is NOT set yet.
                session.clear()
                session["pending_2fa_user_id"] = user["id"]
                session["pending_2fa_attempts"] = 0
                return redirect(url_for("login_2fa"))
            # No 2FA — proceed as normal
            session["user_id"] = user["id"]
            session["admin"]   = user["username"]          # kept for any legacy checks
            session["role"]    = user["role"]
            session["linked_student_id"] = user["linked_student_id"]  # None for admin/teacher
            return redirect(url_for("dashboard"))

        # 3. Failed password or invalid user
        app.logger.warning("Failed login attempt for user %r from %s", username, request.remote_addr)

        if user:
            try:
                res = database.increment_failed_login(user["id"], MAX_FAILED_ATTEMPTS, LOCKOUT_MINUTES)
                if res and res.get("failed_login_attempts", 0) >= MAX_FAILED_ATTEMPTS:
                    flash(f"Too many failed attempts. Account locked for {LOCKOUT_MINUTES} minutes.", "error")
                else:
                    flash("Invalid username or password.", "error")
            except Error as e:
                app.logger.warning("DB error updating failed login attempts for user %s: %s", user["id"], e)
                flash("Invalid username or password.", "error")
        else:
            flash("Invalid username or password.", "error")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


@app.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    user_id = _get_user_id()
    if not user_id:
        flash("User session invalid. Please log in again.", "error")
        return redirect(url_for("logout"))
    try:
        user = database.get_user_by_id(user_id)
    except Error as e:
        app.logger.warning("DB error fetching user %s in change_password: %s", user_id, e)
        flash("Could not reach the database.", "error")
        return redirect(url_for("dashboard"))

    if not user:
        flash("User not found.", "error")
        return redirect(url_for("logout"))

    if request.method == "POST":
        errors = validate_password_change_form(request.form, user)

        if errors:
            for error in errors:
                flash(error, "error")
            return render_template("change_password.html")

        new_hashed = generate_password_hash(request.form.get("new_password"))
        try:
            database.update_user_password(user_id, new_hashed)
            flash("Password updated.", "success")
            return redirect(url_for("dashboard"))
        except Error as e:
            app.logger.warning("DB error updating password for user %s: %s", user_id, e)
            flash(f"Database error: {e}", "error")
            return render_template("change_password.html")

    return render_template("change_password.html")


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.route("/dashboard")
@login_required
def dashboard():
    try:
        stats = database.get_dashboard_stats()
    except Error as e:
        app.logger.warning("DB error loading dashboard stats: %s", e)
        flash("Could not load dashboard stats from the database.", "error")
        stats = {
            "total_students":   0,
            "total_bca":        0,
            "semester_counts":  [],
            "attendance_today": 0,
            "total_dues":       Decimal("0"),
        }

    try:
        recent_notices = database.get_all_notices(limit=NOTICES_LIMIT_DASH)
    except Error as e:
        app.logger.warning("DB error loading recent notices for dashboard: %s", e)
        recent_notices = []

    return render_template("dashboard.html", stats=stats, recent_notices=recent_notices)


@app.route("/dashboard/export")
@role_required("admin")
def dashboard_export():
    from datetime import date as dt_date
    try:
        stats = database.get_dashboard_stats()
    except Error as e:
        app.logger.warning("DB error loading stats for dashboard export: %s", e)
        flash("Could not load dashboard stats from the database.", "error")
        return redirect(url_for("dashboard"))

    today_str = dt_date.today().isoformat()
    pdf_buffer = generate_dashboard_pdf(INSTITUTION_NAME, stats, today_str)
    return send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"dashboard_report_{today_str}.pdf",
    )


@app.route("/analytics")
@role_required("admin", "teacher")
def analytics():
    try:
        attendance_trend = database.get_attendance_trend(ATTENDANCE_TREND_DAYS)
    except Error as e:
        app.logger.warning("DB error loading attendance trend: %s", e)
        flash("Could not load attendance trend from the database.", "error")
        attendance_trend = []

    try:
        stats = database.get_dashboard_stats()
        semester_counts = stats.get("semester_counts", [])
    except Error as e:
        app.logger.warning("DB error loading semester distribution: %s", e)
        flash("Could not load semester distribution stats.", "error")
        semester_counts = []

    fee_status = None
    if session.get("role") == "admin":
        try:
            fee_status = database.get_fee_status_breakdown()
        except Error as e:
            app.logger.warning("DB error loading fee status breakdown: %s", e)
            flash("Could not load fee status breakdown.", "error")
            fee_status = {"paid": 0, "partial": 0, "due": 0}

    return render_template(
        "analytics.html",
        attendance_trend=attendance_trend,
        semester_counts=semester_counts,
        fee_status=fee_status,
    )


# ---------------------------------------------------------------------------
# Student routes
# ---------------------------------------------------------------------------

@app.route("/students")
@role_required("admin", "teacher")       # Fix 7: students cannot list all records
def students():
    search = request.args.get("search", "").strip()
    try:
        student_list = database.get_all_students(search if search else None)
    except Error as e:
        app.logger.warning("DB error loading student list: %s", e)
        flash("Could not load students from the database.", "error")
        student_list = []
    return render_template("students.html", students=student_list, search=search)


def sanitize_csv_value(val):
    """
    Safely neutralize spreadsheet formulas for CSV export.
    Values starting with =, +, -, @, \t, or \r are prefixed with a single quote (')
    so spreadsheet software (Excel, LibreOffice) treats them as plain text literals.
    Normal text strings and data remain untouched.
    """
    if val is None:
        return ""
    val_str = str(val)
    if val_str and val_str[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + val_str
    return val_str


@app.route("/students/export")
@role_required("admin", "teacher")
def students_export():
    """Download the student list (respecting the current search filter) as a CSV.

    The produced file uses EXPECTED_CSV_HEADERS in the exact order required by
    the bulk-import feature, so it can be re-imported without column changes.
    """
    search = request.args.get("search", "").strip()
    try:
        student_list = database.get_all_students(search if search else None)
    except Error as e:
        app.logger.warning("DB error during CSV export: %s", e)
        flash("Could not export students: database error.", "error")
        return redirect(url_for("students", search=search))

    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=EXPECTED_CSV_HEADERS,
        extrasaction="ignore",          # drop any extra DB columns (e.g. id)
        lineterminator="\r\n",          # RFC 4180 line endings
    )
    writer.writeheader()
    for student in student_list:
        # Normalise date_of_birth to a plain string (MySQL returns datetime.date)
        row = dict(student)
        if row.get("date_of_birth") and hasattr(row["date_of_birth"], "isoformat"):
            row["date_of_birth"] = row["date_of_birth"].isoformat()

        # Sanitize text fields against spreadsheet formula injection while preserving phone Excel text literal format
        for k in list(row.keys()):
            if k == "phone" and row.get("phone"):
                raw_phone = str(row["phone"]).strip()
                sanitized_phone = sanitize_csv_value(raw_phone)
                row["phone"] = f'="{sanitized_phone}"'
            elif row.get(k) is not None:
                row[k] = sanitize_csv_value(row[k])

        writer.writerow(row)

    output.seek(0)
    filename = "students_export.csv"
    return send_file(
        io.BytesIO(output.getvalue().encode("utf-8-sig")),   # BOM for Excel compat
        mimetype="text/csv",
        as_attachment=True,
        download_name=filename,
    )



@app.route("/students/add", methods=["GET", "POST"])
@role_required("admin")                  # Fix 7: admin only
def add_student():
    if request.method == "POST":
        form = request.form
        errors = validate_student_form(form)

        if not errors:
            try:
                existing = database.get_student_by_student_id(form.get("student_id").strip())
            except Error as e:
                app.logger.warning("DB error checking duplicate student_id in add_student: %s", e)
                flash("Could not reach the database. Please try again.", "error")
                return render_template("add_student.html", form=form)
            if existing:
                errors.append("Student ID already exists.")

        if errors:
            for error in errors:
                flash(error, "error")
            return render_template("add_student.html", form=form)

        try:
            database.insert_student(student_payload(form))
            flash("Student added successfully.", "success")
            return redirect(url_for("students"))
        except Error as e:
            app.logger.warning("DB error inserting student: %s", e)
            flash(f"Database error: {e}", "error")
            return render_template("add_student.html", form=form)

    return render_template("add_student.html", form={})


@app.route("/students/import/sample")
@role_required("admin")
def students_import_sample():
    sample_csv = (
        "student_id,student_name,email,phone,gender,date_of_birth,course,semester,address\n"
        "BCA2499,Demo Student,demo@example.com,9876543219,Male,2005-01-01,BCA,1,Mumbai\n"
    )
    buffer = io.BytesIO(sample_csv.encode("utf-8"))
    return send_file(
        buffer,
        mimetype="text/csv",
        as_attachment=True,
        download_name="sample_students.csv",
    )


@app.route("/students/import", methods=["GET", "POST"])
@role_required("admin")
def students_import():
    if request.method == "POST":
        if "file" not in request.files:
            flash("Please select a CSV file to upload.", "error")
            return render_template("students_import.html")

        file = request.files["file"]
        if not file or not file.filename:
            flash("Please select a CSV file to upload.", "error")
            return render_template("students_import.html")

        filename = file.filename
        if not filename.lower().endswith(".csv"):
            flash("Only .csv files are supported.", "error")
            return render_template("students_import.html")

        file_bytes = file.read()
        if len(file_bytes) > 1 * 1024 * 1024:
            flash("File size exceeds maximum allowed limit of 1MB.", "error")
            return render_template("students_import.html")

        try:
            text_content = file_bytes.decode("utf-8-sig", errors="replace")
        except Exception:
            flash("Could not read CSV file. Please ensure it is UTF-8 encoded.", "error")
            return render_template("students_import.html")

        reader = csv.DictReader(io.StringIO(text_content))

        # Header check
        raw_headers = reader.fieldnames
        if raw_headers is None:
            flash("CSV file is empty or missing headers.", "error")
            return render_template("students_import.html")

        found_headers = [h.strip() for h in raw_headers if h is not None]
        if found_headers != EXPECTED_CSV_HEADERS:
            flash(
                f"Invalid CSV headers. Expected: {', '.join(EXPECTED_CSV_HEADERS)} | Found: {', '.join(found_headers)}",
                "error",
            )
            return render_template("students_import.html")

        imported_count = 0
        skipped_rows = []
        seen_student_ids = set()

        for row_index, raw_row in enumerate(reader, start=1):
            # Normalize row: replace None with empty string (handles short rows)
            row = {
                k: (v.strip() if isinstance(v, str) else (v if v is not None else ""))
                for k, v in (raw_row or {}).items()
            }

            # Strip Excel text-literal wrapper from phone if present.
            # Our export writes phone as =" digits " so that Excel doesn't
            # auto-convert it to scientific notation.  Before validation we
            # recover the plain digit string so the round-trip is transparent.
            phone_val = row.get("phone", "")
            if phone_val.startswith('="') and phone_val.endswith('"'):
                row["phone"] = phone_val[2:-1]

            student_id = row.get("student_id", "").strip()
            student_name = row.get("student_name", "").strip() or f"Row {row_index}"
            row_errors = []

            # Check in-file duplicate first
            if student_id and student_id in seen_student_ids:
                row_errors.append("Student ID is duplicate within this file.")

            # Validate using validate_student_form
            form_errors = validate_student_form(row)
            row_errors.extend(form_errors)

            # Check DB duplicate if student_id is provided and no in-file duplicate error yet
            if student_id and "Student ID is duplicate within this file." not in row_errors:
                try:
                    existing = database.get_student_by_student_id(student_id)
                    if existing:
                        row_errors.append("Student ID already exists in database.")
                except Error as e:
                    row_errors.append(f"Database lookup error: {e}")

            if not row_errors:
                try:
                    payload = student_payload(row)
                    database.insert_student(payload)
                    seen_student_ids.add(student_id)
                    imported_count += 1
                except Error as e:
                    row_errors.append(f"Database insertion error: {e}")
                    skipped_rows.append({
                        "row_num": row_index,
                        "name": student_name,
                        "reasons": row_errors,
                    })
            else:
                skipped_rows.append({
                    "row_num": row_index,
                    "name": student_name,
                    "reasons": row_errors,
                })

        return render_template(
            "students_import.html",
            processed=True,
            imported_count=imported_count,
            skipped_rows=skipped_rows,
        )

    return render_template("students_import.html", processed=False)


@app.route("/students/<int:record_id>")
@role_required("admin", "teacher", "student")
def student_details(record_id):
    _assert_own_record(record_id)        # Fix 5: applied here (not on edit)

    try:
        student = database.get_student_by_id(record_id)
    except Error as e:
        app.logger.warning("DB error fetching student %s in student_details: %s", record_id, e)
        flash("Could not reach the database.", "error")
        return redirect(url_for("students"))

    if not student:
        flash("Student not found.", "error")
        return redirect(url_for("students"))

    # Attendance section data
    try:
        attendance_records = database.get_student_attendance(record_id)
    except Error as e:
        app.logger.warning("DB error fetching attendance for student %s in student_details: %s", record_id, e)
        attendance_records = []

    attendance_pct = None
    if attendance_records:
        present_count = sum(1 for r in attendance_records if r["status"] == "Present")
        attendance_pct = round(present_count / len(attendance_records) * 100)

    # Grades section data
    PASSING_THRESHOLD = 40.0  # Defined here for easy modification
    try:
        grade_records = database.get_student_grades(record_id)
        raw_grade_pct = database.get_grade_summary(record_id)
        grade_summary_pct = round(float(raw_grade_pct), 1) if raw_grade_pct else 0.0
    except Error as e:
        app.logger.warning("DB error fetching grades for student %s in student_details: %s", record_id, e)
        grade_records = []
        grade_summary_pct = 0.0

    for g in grade_records:
        obtained = float(g["marks_obtained"])
        maximum = float(g["max_marks"]) if g["max_marks"] and float(g["max_marks"]) > 0 else 100.0
        pct = (obtained / maximum) * 100.0
        g["percentage"] = round(pct, 1)
        g["passed"] = (pct >= PASSING_THRESHOLD)

    # Fees section data
    try:
        fee_records = database.get_student_fees(record_id)
    except Error as e:
        app.logger.warning("DB error fetching fees for student %s in student_details: %s", record_id, e)
        fee_records = []

    # Compute derived status for each fee row
    for fee in fee_records:
        paid = fee["amount_paid"]
        due  = fee["amount_due"]
        if paid >= due:
            fee["status"] = "Paid"
        elif paid > 0:
            fee["status"] = "Partial"
        else:
            fee["status"] = "Due"
        fee["remaining"] = due - paid

    return render_template(
        "student_details.html",
        student=student,
        attendance_records=attendance_records,
        attendance_pct=attendance_pct,
        grade_records=grade_records,
        grade_summary_pct=grade_summary_pct,
        passing_threshold=PASSING_THRESHOLD,
        fee_records=fee_records,
    )


@app.route("/students/<int:record_id>/edit", methods=["GET", "POST"])
@role_required("admin")
def edit_student(record_id):
    try:
        student = database.get_student_by_id(record_id)
    except Error as e:
        app.logger.warning("DB error fetching student %s in edit_student: %s", record_id, e)
        flash("Could not reach the database.", "error")
        return redirect(url_for("students"))

    if not student:
        flash("Student not found.", "error")
        return redirect(url_for("students"))

    if request.method == "POST":
        form = request.form
        errors = validate_student_form(form)

        if not errors:
            try:
                existing = database.get_student_by_student_id(form.get("student_id").strip())
            except Error as e:
                app.logger.warning("DB error checking duplicate student_id in edit_student: %s", e)
                flash("Could not reach the database. Please try again.", "error")
                return render_template("edit_student.html", student={**student, **form})
            if existing and existing["id"] != record_id:
                errors.append("Student ID already exists.")

        if errors:
            for error in errors:
                flash(error, "error")
            return render_template("edit_student.html", student={**student, **form})

        try:
            database.update_student(record_id, student_payload(form))
            flash("Student updated successfully.", "success")
            return redirect(url_for("student_details", record_id=record_id))
        except Error as e:
            app.logger.warning("DB error updating student %s: %s", record_id, e)
            flash(f"Database error: {e}", "error")
            return render_template("edit_student.html", student={**student, **form})

    return render_template("edit_student.html", student=student)


@app.route("/students/<int:record_id>/delete", methods=["POST"])
@role_required("admin")
def delete_student(record_id):
    try:
        database.delete_student(record_id)
        flash("Student deleted successfully.", "success")
    except Error as e:
        app.logger.warning("DB error deleting student %s: %s", record_id, e)
        flash(f"Database error: {e}", "error")
    return redirect(url_for("students"))


@app.route("/students/<int:record_id>/certificate")
@role_required("admin", "student")
def student_certificate(record_id):
    _assert_own_record(record_id)
    try:
        student = database.get_student_by_id(record_id)
    except Error as e:
        app.logger.warning("DB error fetching student %s for certificate: %s", record_id, e)
        flash("Could not reach the database.", "error")
        return redirect(url_for("students"))

    if not student:
        flash("Student not found.", "error")
        return redirect(url_for("students"))

    # Validate that all certificate-required fields are present and non-empty.
    missing = [
        field for field in ("student_name", "student_id", "course", "semester")
        if not student.get(field)
    ]
    if missing:
        flash(
            f"Cannot generate certificate: the following required fields are missing "
            f"for this student: {', '.join(missing)}. Please update the student record first.",
            "error",
        )
        return redirect(url_for("student_details", record_id=record_id))

    pdf_buffer = generate_bonafide_pdf(
        INSTITUTION_NAME,
        student,
        institution_location=INSTITUTION_LOCATION,
        institution_affiliation=INSTITUTION_AFFILIATION,
    )
    return send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"certificate_{student['student_id']}.pdf",
    )


# ---------------------------------------------------------------------------
# Student ID Card routes
# ---------------------------------------------------------------------------

def _get_id_card_student_or_abort(record_id):
    """
    Shared helper for ID card routes: fetch student from DB and
    apply own-record guard for student role.  Returns the student dict
    or redirects/aborts.  Raises TypeError if called with a bad record_id.
    """
    _assert_own_record(record_id)
    try:
        student = database.get_student_by_id(record_id)
    except Error as e:
        app.logger.warning("DB error fetching student %s for ID card: %s", record_id, e)
        flash("Could not reach the database.", "error")
        return None, redirect(url_for("students"))

    if not student:
        flash("Student not found.", "error")
        return None, redirect(url_for("students"))

    # Validate required fields
    missing = [
        field for field in ("student_name", "student_id", "course", "semester")
        if not student.get(field)
    ]
    if missing:
        flash(
            f"Cannot generate ID card: the following required fields are missing "
            f"for this student: {', '.join(missing)}. Please update the student record first.",
            "error",
        )
        return None, redirect(url_for("student_details", record_id=record_id))

    return student, None


def _get_student_photo_url(student):
    """
    Returns static URL for the student photo:
    1. If student has custom 'photo' column and file exists -> return photo URL
    2. Else if gender is female/girl/f -> id-card-default-female.jpg
    3. Else -> id-card-default-male.jpg
    """
    if not student or not isinstance(student, dict):
        return url_for("static", filename="images/id-card-default-male.jpg")

    custom_photo = student.get("photo")
    if custom_photo and isinstance(custom_photo, str) and custom_photo.strip():
        rel_path = custom_photo.strip().lstrip("/")
        full_path = os.path.join(app.root_path, rel_path)
        if os.path.isfile(full_path):
            return "/" + rel_path

    gender = str(student.get("gender") or "").strip().lower()
    if gender in ("female", "girl", "f"):
        return url_for("static", filename="images/id-card-default-female.jpg")
    else:
        return url_for("static", filename="images/id-card-default-male.jpg")


@app.context_processor
def inject_student_photo_helper():
    return {
        "get_student_photo_url": _get_student_photo_url
    }


@app.template_filter("student_photo_url")
def student_photo_url_filter(student):
    return _get_student_photo_url(student)


def _get_verification_url(student):
    """
    Builds full public verification URL for QR code scanning.
    Format required:
        PUBLIC_BASE_URL + /verify/student/<student_id>
    
    If PUBLIC_BASE_URL is configured (e.g. "https://studentmanagement.vercel.app"),
    returns: f"{config.PUBLIC_BASE_URL}/verify/student/{student['student_id']}"
    """
    student_id_str = str(student.get("student_id") or student.get("id")).strip()
    pub_base = (getattr(config, "PUBLIC_BASE_URL", "") or os.environ.get("PUBLIC_BASE_URL", "")).strip().rstrip("/")
    if pub_base:
        return f"{pub_base}/verify/student/{student_id_str}"

    try:
        return url_for("public_student_verify", student_id=student_id_str, _external=True)
    except Exception:
        return f"/verify/student/{student_id_str}"


def _generate_qr_data_uri(text_data):
    """Generate a high-contrast base64 PNG data URI for embedding directly in HTML <img> tags."""
    try:
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=3,
        )
        qr.add_data(text_data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/png;base64,{b64}"
    except Exception as e:
        app.logger.warning("QR Data URI generation failed: %s", e)
        return ""


@app.route("/students/<int:record_id>/id-card")
@role_required("admin", "teacher", "student")
def student_id_card_preview(record_id):
    """HTML preview page showing the ID card design + download/print buttons."""
    student, err_redirect = _get_id_card_student_or_abort(record_id)
    if err_redirect:
        return err_redirect

    # Academic year (dynamic)
    curr_year = datetime.datetime.now().year
    acad_year = f"{curr_year}\u2013{str(curr_year + 1)[-2:]}"

    verify_url = _get_verification_url(student)
    qr_data_uri = _generate_qr_data_uri(verify_url)
    photo_url = _get_student_photo_url(student)

    return render_template(
        "id_card_preview.html",
        student=student,
        institution_name=INSTITUTION_NAME,
        institution_location=INSTITUTION_LOCATION,
        institution_affiliation=INSTITUTION_AFFILIATION,
        acad_year=acad_year,
        photo_url=photo_url,
        qr_data_uri=qr_data_uri,
        verify_url=verify_url,
    )


@app.route("/students/<int:record_id>/id-card/download")
@role_required("admin", "teacher", "student")
def student_id_card_download(record_id):
    """Return the CR80 ID card PDF as a file download."""
    student, err_redirect = _get_id_card_student_or_abort(record_id)
    if err_redirect:
        return err_redirect

    verify_url = _get_verification_url(student)

    try:
        pdf_buffer = generate_id_card_pdf(
            INSTITUTION_NAME,
            student,
            verification_url=verify_url,
            institution_location=INSTITUTION_LOCATION,
            institution_affiliation=INSTITUTION_AFFILIATION,
        )
    except Exception as e:
        app.logger.warning("PDF generation error for ID card student %s: %s", record_id, e)
        flash("Could not generate the ID card PDF. Please try again.", "error")
        return redirect(url_for("student_id_card_preview", record_id=record_id))

    return send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"student_id_card_{student['student_id']}.pdf",
    )


@app.route("/verify/student/<student_id>")
def public_student_verify(student_id):
    """
    Public QR code verification page (no login required).
    Accepts ONLY the VARCHAR roll number (student_id) — NEVER a raw integer PK.
    Sequential integer enumeration (1, 2, 3...) is blocked by design:
    get_student_by_student_id() only matches the VARCHAR roll column, which is
    non-sequential and institution-specific (e.g. 'BCA2401').
    Shows ONLY safe public details:
    - Student Name
    - Student ID / Roll Number
    - Course
    - Semester
    - Academic Year
    - Student Status
    Does NOT expose passwords, tokens, phone numbers, email, address, or private fields.
    """
    # SECURITY: reject bare integers immediately — do NOT fall back to get_student_by_id().
    # This closes the enumeration vector where /verify/student/1, /2, /3... revealed real data.
    if str(student_id).isdigit():
        return render_template("id_card_verify.html", student=None, error="Student record not found.")

    student = None
    try:
        student = database.get_student_by_student_id(student_id)
    except Error as e:
        app.logger.warning("DB error fetching student %s for QR verify: %s", student_id, e)
        return render_template("id_card_verify.html", student=None, error="Database unavailable.")

    if not student:
        return render_template("id_card_verify.html", student=None, error="Student record not found.")

    curr_year = datetime.datetime.now().year
    acad_year = f"{curr_year}\u2013{str(curr_year + 1)[-2:]}"

    safe_student = {
        "id": student["id"],
        "student_id": student["student_id"],
        "student_name": student["student_name"],
        "course": student.get("course", ""),
        "semester": student.get("semester", ""),
        "gender": student.get("gender", ""),
        "acad_year": acad_year,
        "status": "Active",
    }

    return render_template(
        "id_card_verify.html",
        student=safe_student,
        error=None,
        institution_name=INSTITUTION_NAME,
        institution_location=INSTITUTION_LOCATION,
        institution_affiliation=INSTITUTION_AFFILIATION,
    )


@app.route("/students/<int:record_id>/id-card/verify")
def student_id_card_verify(record_id):
    """
    Backwards-compatibility alias — always redirects to the canonical
    /verify/student/<roll_number> URL using the REAL roll number.
    SECURITY: never echoes the raw integer PK back to public_student_verify.
    If the record doesn't exist, renders the not-found page directly.
    """
    try:
        student = database.get_student_by_id(record_id)
        if student:
            # Redirect to the canonical roll-number URL (not the raw PK)
            return redirect(
                url_for("public_student_verify", student_id=student["student_id"]),
                code=301
            )
    except Exception as e:
        app.logger.warning("DB error in id-card/verify alias for pk=%s: %s", record_id, e)
    # Student not found — render not-found page, do NOT forward the integer to public_student_verify
    return render_template("id_card_verify.html", student=None, error="Student record not found.")

# ---------------------------------------------------------------------------
# Attendance routes
# ---------------------------------------------------------------------------

@app.route("/attendance", methods=["GET", "POST"])
@role_required("admin", "teacher")
def attendance():
    from datetime import date as dt_date
    today = dt_date.today().isoformat()
    selected_date = request.args.get("date", today)

    if request.method == "POST":
        post_date = request.form.get("date", "").strip()
        if not post_date:
            flash("Date is required.", "error")
            return redirect(url_for("attendance"))

        students_list = database.get_all_students_for_attendance()
        marked_by = _get_user_id()
        if not marked_by:
            flash("Could not identify current user. Please log in again.", "error")
            return redirect(url_for("attendance", date=post_date))

        for s in students_list:
            status = request.form.get(f"status_{s['id']}", "")
            if status in ("Present", "Absent"):
                try:
                    database.upsert_attendance(s["id"], post_date, status, marked_by)
                except Error as e:
                    app.logger.warning("DB error saving attendance for student %s on %s: %s", s['id'], post_date, e)
                    flash(f"Database error saving attendance: {e}", "error")
                    return redirect(url_for("attendance", date=post_date))

        flash("Attendance saved.", "success")
        return redirect(url_for("attendance", date=post_date))

    # GET — load students + today's existing marks
    try:
        students_list    = database.get_all_students_for_attendance()
        existing_marks   = database.get_attendance_by_date(selected_date)
    except Error as e:
        app.logger.warning("DB error loading attendance page: %s", e)
        flash("Could not load attendance data.", "error")
        students_list  = []
        existing_marks = {}

    return render_template(
        "attendance.html",
        students=students_list,
        existing_marks=existing_marks,
        selected_date=selected_date,
    )


@app.route("/attendance/<int:record_id>")
@role_required("admin", "teacher", "student")
def attendance_history(record_id):
    _assert_own_record(record_id)

    try:
        student = database.get_student_by_id(record_id)
    except Error as e:
        app.logger.warning("DB error fetching student %s in attendance_history: %s", record_id, e)
        flash("Could not reach the database.", "error")
        return redirect(url_for("students"))

    if not student:
        flash("Student not found.", "error")
        return redirect(url_for("students"))

    try:
        records = database.get_student_attendance(record_id)
    except Error as e:
        app.logger.warning("DB error loading attendance history for student %s: %s", record_id, e)
        flash("Could not load attendance records.", "error")
        records = []

    pct = None
    if records:
        present = sum(1 for r in records if r["status"] == "Present")
        pct = round(present / len(records) * 100)

    return render_template(
        "attendance_history.html",
        student=student,
        records=records,
        pct=pct,
    )


# ---------------------------------------------------------------------------
# Grades routes
# ---------------------------------------------------------------------------

def validate_grade_form(form):
    """Server-side validation for grade entry."""
    errors = []
    subject = form.get("subject", "").strip()
    exam_type = form.get("exam_type", "").strip()
    marks_obtained_str = form.get("marks_obtained", "").strip()
    max_marks_str = form.get("max_marks", "100").strip()
    semester_str = form.get("semester", "").strip()

    if not subject:
        errors.append("Subject name is required.")
    elif len(subject) > 100:
        errors.append("Subject name must be 100 characters or fewer.")

    valid_exam_types = ("Internal", "Mid-term", "Final")
    if not exam_type:
        errors.append("Exam type is required.")
    elif exam_type not in valid_exam_types:
        errors.append("Invalid exam type selected.")

    marks_obtained = None
    if not marks_obtained_str:
        errors.append("Marks obtained is required.")
    else:
        try:
            marks_obtained = Decimal(marks_obtained_str)
            if marks_obtained < 0:
                errors.append("Marks obtained cannot be negative.")
        except Exception:
            errors.append("Marks obtained must be a valid number.")

    max_marks = None
    if not max_marks_str:
        errors.append("Maximum marks is required.")
    else:
        try:
            max_marks = Decimal(max_marks_str)
            if max_marks <= 0:
                errors.append("Maximum marks must be greater than zero.")
        except Exception:
            errors.append("Maximum marks must be a valid number.")

    if marks_obtained is not None and max_marks is not None:
        if marks_obtained > max_marks:
            errors.append("Marks obtained cannot exceed maximum marks.")

    if not semester_str:
        errors.append("Semester is required.")
    elif not semester_str.isdigit() or not (1 <= int(semester_str) <= 6):
        errors.append("Semester must be a number between 1 and 6.")

    return errors


@app.route("/grades/add/<int:record_id>", methods=["GET", "POST"])
@role_required("admin", "teacher")
def grades_add(record_id):
    try:
        student = database.get_student_by_id(record_id)
    except Error as e:
        app.logger.warning("DB error fetching student %s in grades_add: %s", record_id, e)
        flash("Could not reach the database.", "error")
        return redirect(url_for("students"))

    if not student:
        flash("Student not found.", "error")
        return redirect(url_for("students"))

    if request.method == "POST":
        form = request.form
        errors = validate_grade_form(form)

        if errors:
            for error in errors:
                flash(error, "error")
            return render_template("grades_add.html", student=student, form=form)

        recorded_by = _get_user_id()
        if not recorded_by:
            flash("Could not identify current user. Please log in again.", "error")
            return render_template("grades_add.html", student=student, form=form)

        try:
            database.insert_grade({
                "stud_id":        record_id,
                "subject":        form.get("subject", "").strip(),
                "exam_type":      form.get("exam_type", "").strip(),
                "marks_obtained": Decimal(form.get("marks_obtained", "").strip()),
                "max_marks":       Decimal(form.get("max_marks", "100").strip()),
                "semester":       int(form.get("semester", "").strip()),
                "recorded_by":    recorded_by,
            })
            flash("Grade recorded successfully.", "success")
            return redirect(url_for("student_details", record_id=record_id))
        except Error as e:
            app.logger.warning("DB error inserting grade for student %s: %s", record_id, e)
            flash(f"Database error: {e}", "error")
            return render_template("grades_add.html", student=student, form=form)

    return render_template("grades_add.html", student=student, form={"max_marks": "100.00"})


@app.route("/grades/<int:record_id>")
@role_required("admin", "teacher", "student")
def grades_view(record_id):
    _assert_own_record(record_id)
    return redirect(url_for("student_details", record_id=record_id))


def _get_user_id():
    """Fetch the users.id for the currently logged-in user. Returns None if unresolvable."""
    if "user_id" in session:
        return session["user_id"]
    username = session.get("admin", "")
    if not username:
        return None
    try:
        user = database.get_user_by_username(username)
        if user:
            session["user_id"] = user["id"]
            return user["id"]
        return None
    except Error as e:
        app.logger.error("DB error fetching user_id in _get_user_id: %s", e)
        return None


# ---------------------------------------------------------------------------
# Fees routes
# ---------------------------------------------------------------------------

@app.route("/fees/create/<int:record_id>", methods=["GET", "POST"])
@role_required("admin")
def fees_create(record_id):
    try:
        student = database.get_student_by_id(record_id)
    except Error as e:
        app.logger.warning("DB error fetching student %s in fees_create: %s", record_id, e)
        flash("Could not reach the database.", "error")
        return redirect(url_for("students"))

    if not student:
        flash("Student not found.", "error")
        return redirect(url_for("students"))

    if request.method == "POST":
        errors = []
        amount_due_str = request.form.get("amount_due", "").strip()
        due_date       = request.form.get("due_date", "").strip()

        if not amount_due_str:
            errors.append("Amount due is required.")
        else:
            try:
                amount_due = Decimal(amount_due_str)
                if amount_due <= 0:
                    errors.append("Amount due must be greater than zero.")
            except Exception:
                errors.append("Amount due must be a valid number.")
                amount_due = None

        if not due_date:
            errors.append("Due date is required.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("fees_create.html", student=student, form=request.form)

        try:
            database.insert_fee_due({
                "stud_id":    record_id,
                "amount_due": amount_due,
                "due_date":   due_date,
            })
            flash("Fee due created successfully.", "success")
            return redirect(url_for("student_details", record_id=record_id))
        except Error as e:
            app.logger.warning("DB error creating fee due for student %s: %s", record_id, e)
            flash(f"Database error: {e}", "error")
            return render_template("fees_create.html", student=student, form=request.form)

    return render_template("fees_create.html", student=student, form={})


@app.route("/fees/pay/<int:fee_id>", methods=["GET", "POST"])
@role_required("admin")
def fees_pay(fee_id):
    try:
        fee = database.get_fee_by_id(fee_id)
    except Error as e:
        app.logger.warning("DB error fetching fee %s in fees_pay: %s", fee_id, e)
        flash("Could not reach the database.", "error")
        return redirect(url_for("students"))

    if not fee:
        flash("Fee record not found.", "error")
        return redirect(url_for("students"))

    remaining = fee["amount_due"] - fee["amount_paid"]
    record_id = fee["stud_id"]

    try:
        student = database.get_student_by_id(record_id)
    except Error as e:
        app.logger.warning("DB error fetching student %s in fees_pay: %s", record_id, e)
        student = None

    if request.method == "POST":
        errors = []
        payment_str = request.form.get("payment_amount", "").strip()

        if not payment_str:
            errors.append("Payment amount is required.")
        else:
            try:
                payment = Decimal(payment_str)
                if payment <= 0:
                    errors.append("Payment must be greater than zero.")
                elif payment > remaining:
                    errors.append(
                        f"Payment (₹{payment}) exceeds the remaining balance (₹{remaining})."
                    )
            except Exception:
                errors.append("Payment amount must be a valid number.")
                payment = None

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template(
                "fees_pay.html", fee=fee, student=student, remaining=remaining, form=request.form
            )

        try:
            rows = database.update_fee_payment(fee_id, payment)
            if rows == 0:
                flash("Payment rejected — amount would exceed the balance due.", "error")
            else:
                flash("Payment recorded successfully.", "success")
            return redirect(url_for("student_details", record_id=record_id))
        except Error as e:
            app.logger.warning("DB error recording payment for fee %s: %s", fee_id, e)
            flash(f"Database error: {e}", "error")
            return render_template(
                "fees_pay.html", fee=fee, student=student, remaining=remaining, form=request.form
            )

    return render_template(
        "fees_pay.html", fee=fee, student=student, remaining=remaining, form={}
    )


@app.route("/fees/<int:record_id>")
@role_required("admin", "student")
def fees_view(record_id):
    _assert_own_record(record_id)

    try:
        student = database.get_student_by_id(record_id)
    except Error as e:
        app.logger.warning("DB error fetching student %s in fees_view: %s", record_id, e)
        flash("Could not reach the database.", "error")
        return redirect(url_for("students"))

    if not student:
        flash("Student not found.", "error")
        return redirect(url_for("students"))

    try:
        fee_records = database.get_student_fees(record_id)
    except Error as e:
        app.logger.warning("DB error loading fee records for student %s: %s", record_id, e)
        flash("Could not load fee records.", "error")
        fee_records = []

    for fee in fee_records:
        paid = fee["amount_paid"]
        due  = fee["amount_due"]
        if paid >= due:
            fee["status"] = "Paid"
        elif paid > 0:
            fee["status"] = "Partial"
        else:
            fee["status"] = "Due"
        fee["remaining"] = due - paid

    return render_template("fees_view.html", student=student, fee_records=fee_records)



# ---------------------------------------------------------------------------
# 2FA routes  (TOTP — opt-in, all roles)
# ---------------------------------------------------------------------------

MAX_2FA_ATTEMPTS = 5  # consecutive wrong codes before the pending session is cleared


@app.route("/login/2fa", methods=["GET", "POST"])
def login_2fa():
    """Second step of login for users who have TOTP enabled.

    A pending_2fa_user_id in the session (set by login()) is required to
    reach this route. The full session (role, user_id, …) is set only on
    successful code verification.
    """
    pending_user_id = session.get("pending_2fa_user_id")
    if not pending_user_id:
        return redirect(url_for("login"))

    if request.method == "POST":
        code = request.form.get("code", "").strip()
        attempts = session.get("pending_2fa_attempts", 0)

        try:
            user = database.get_user_by_id(pending_user_id)
        except Error as e:
            app.logger.warning("DB error fetching user %s in login_2fa: %s", pending_user_id, e)
            flash("Could not reach the database. Please try again.", "error")
            return render_template("2fa_verify.html")

        if not user or not user.get("totp_secret"):
            session.clear()
            flash("2FA configuration error. Please log in again.", "error")
            return redirect(url_for("login"))

        totp = pyotp.TOTP(user["totp_secret"])
        if totp.verify(code, valid_window=1):
            # Success — establish the full session
            session.pop("pending_2fa_user_id", None)
            session.pop("pending_2fa_attempts", None)
            session["user_id"] = user["id"]
            session["admin"]   = user["username"]
            session["role"]    = user["role"]
            session["linked_student_id"] = user["linked_student_id"]
            return redirect(url_for("dashboard"))

        # Wrong code
        attempts += 1
        if attempts >= MAX_2FA_ATTEMPTS:
            app.logger.warning(
                "2FA attempt cap reached for user_id=%s — clearing pending session", pending_user_id
            )
            session.clear()
            flash("Too many incorrect codes. Please log in again.", "error")
            return redirect(url_for("login"))

        session["pending_2fa_attempts"] = attempts
        flash(f"Incorrect code. {MAX_2FA_ATTEMPTS - attempts} attempt(s) remaining.", "error")

    return render_template("2fa_verify.html")


@app.route("/2fa/setup", methods=["GET", "POST"])
@login_required
def totp_setup():
    """GET/POST /2fa/setup — opt-in TOTP setup for any logged-in user.

    GET:
      - If already enabled: show "disable" state.
      - Otherwise: generate a new secret (stored with enabled=False),
        render a QR code + raw secret + confirmation form.

    POST:
      - Verify the submitted code against the stored (not-yet-enabled) secret.
      - On success: enable_user_totp, flash, redirect.
      - On failure: re-render with the same QR/secret, do NOT regenerate.
    """
    user_id = _get_user_id()
    if not user_id:
        flash("User session invalid. Please log in again.", "error")
        return redirect(url_for("logout"))

    try:
        user = database.get_user_by_id(user_id)
    except Error as e:
        app.logger.warning("DB error fetching user %s in totp_setup: %s", user_id, e)
        flash("Could not reach the database.", "error")
        return redirect(url_for("dashboard"))

    if not user:
        flash("User not found.", "error")
        return redirect(url_for("logout"))

    if request.method == "POST":
        code = request.form.get("code", "").strip()
        secret = user.get("totp_secret")
        if not secret:
            flash("No pending 2FA secret found. Please reload and try again.", "error")
            return redirect(url_for("totp_setup"))

        totp = pyotp.TOTP(secret)
        if totp.verify(code, valid_window=1):
            try:
                database.enable_user_totp(user_id)
                flash("Two-factor authentication enabled.", "success")
                return redirect(url_for("dashboard"))
            except Error as e:
                app.logger.warning("DB error enabling TOTP for user %s: %s", user_id, e)
                flash(f"Database error: {e}", "error")
        else:
            flash("Incorrect code — please try again with a fresh code from your app.", "error")

        # Re-render with the same secret (don't regenerate on a failed attempt)
        return render_template("2fa_setup.html", user=user, qr_data_uri=_totp_qr_uri(user))

    # GET
    if user.get("totp_enabled"):
        # Already set up — show the "disable" state; no new QR generated
        return render_template("2fa_setup.html", user=user, qr_data_uri=None)

    # Not yet set up — generate a fresh secret, store it, show QR
    secret = pyotp.random_base32()
    try:
        database.set_user_totp_secret(user_id, secret)
    except Error as e:
        app.logger.warning("DB error storing TOTP secret for user %s: %s", user_id, e)
        flash("Could not save 2FA secret. Please try again.", "error")
        return redirect(url_for("dashboard"))

    # Reload user so the template sees the new secret
    user["totp_secret"] = secret
    return render_template("2fa_setup.html", user=user, qr_data_uri=_totp_qr_uri(user))


def _totp_qr_uri(user):
    """Return a data: URI (PNG, base64) of the TOTP provisioning QR code."""
    secret = user["totp_secret"]
    username = user.get("username", "user")
    provisioning_uri = pyotp.totp.TOTP(secret).provisioning_uri(
        name=username,
        issuer_name="Student MS"
    )
    img = qrcode.make(provisioning_uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


@app.route("/2fa/disable", methods=["POST"])
@login_required
def totp_disable():
    """Disable TOTP for the current user, requiring current password as confirmation."""
    user_id = _get_user_id()
    if not user_id:
        flash("User session invalid. Please log in again.", "error")
        return redirect(url_for("logout"))

    try:
        user = database.get_user_by_id(user_id)
    except Error as e:
        app.logger.warning("DB error fetching user %s in totp_disable: %s", user_id, e)
        flash("Could not reach the database.", "error")
        return redirect(url_for("totp_setup"))

    if not user:
        flash("User not found.", "error")
        return redirect(url_for("logout"))

    current_password = request.form.get("current_password", "")
    if not check_password_hash(user["password"], current_password):
        flash("Incorrect password. 2FA was not disabled.", "error")
        return redirect(url_for("totp_setup"))

    try:
        database.disable_user_totp(user_id)
        flash("Two-factor authentication disabled.", "success")
    except Error as e:
        app.logger.warning("DB error disabling TOTP for user %s: %s", user_id, e)
        flash(f"Database error: {e}", "error")

    return redirect(url_for("dashboard"))


# ---------------------------------------------------------------------------
# Notices routes
# ---------------------------------------------------------------------------


@app.route("/notices")
@login_required
def notices():
    try:
        notice_list = database.get_all_notices(limit=NOTICES_LIMIT_FULL)
    except Error as e:
        app.logger.warning("DB error loading notices list: %s", e)
        flash("Could not load notices from the database.", "error")
        notice_list = []
    return render_template("notices.html", notices=notice_list)


@app.route("/notices/add", methods=["GET", "POST"])
@role_required("admin", "teacher")
def notice_add():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        body  = request.form.get("body", "").strip()
        errors = []
        if not title:
            errors.append("Title is required.")
        elif len(title) > 150:
            errors.append("Title must be 150 characters or fewer.")
        if not body:
            errors.append("Body is required.")

        if errors:
            for error in errors:
                flash(error, "error")
            return render_template("notice_add.html", form=request.form)

        posted_by = _get_user_id()
        if not posted_by:
            flash("Could not identify current user. Please log in again.", "error")
            return render_template("notice_add.html", form=request.form)
        try:
            database.insert_notice(title, body, posted_by)
            flash("Notice posted successfully.", "success")
            return redirect(url_for("notices"))
        except Error as e:
            app.logger.warning("DB error inserting notice (posted_by=%s): %s", posted_by, e)
            flash(f"Database error: {e}", "error")
            return render_template("notice_add.html", form=request.form)

    return render_template("notice_add.html", form={})


@app.route("/notices/<int:notice_id>/delete", methods=["POST"])
@role_required("admin")
def notice_delete(notice_id):
    try:
        database.delete_notice(notice_id)
        flash("Notice deleted.", "success")
    except Error as e:
        app.logger.warning("DB error deleting notice %s: %s", notice_id, e)
        flash("Could not delete the notice.", "error")
    return redirect(url_for("notices"))


# ---------------------------------------------------------------------------
# Audit Log route
# ---------------------------------------------------------------------------


@app.route("/audit-log")
@role_required("admin")
def audit_log():
    """Display a combined, newest-first activity log across attendance, grades, and notices.

    Admin-only: reveals who marked attendance, recorded grades, and posted
    notices across the whole system.  Capped at AUDIT_LOG_LIMIT rows.
    """
    try:
        events = database.get_audit_log(AUDIT_LOG_LIMIT)
    except Error as e:
        app.logger.warning("DB error loading audit log: %s", e)
        flash("Could not load the audit log from the database.", "error")
        events = []
    return render_template("audit_log.html", events=events)


# ---------------------------------------------------------------------------
# Notifications routes
# ---------------------------------------------------------------------------

LOW_ATTENDANCE_THRESHOLD = 75.0  # Defined here for easy modification


@app.route("/notifications", methods=["GET"])
@role_required("admin")
def notifications():
    try:
        overdue_fees = database.get_students_with_overdue_fees()
        for fee in overdue_fees:
            paid = fee["amount_paid"]
            due = fee["amount_due"]
            if paid >= due:
                fee["status"] = "Paid"
            elif paid > 0:
                fee["status"] = "Partial"
            else:
                fee["status"] = "Due"
            fee["remaining"] = due - paid
    except Error as e:
        app.logger.warning("DB error fetching overdue fees for notifications: %s", e)
        flash("Could not load overdue fees.", "error")
        overdue_fees = []

    try:
        low_attendance = database.get_students_with_low_attendance(LOW_ATTENDANCE_THRESHOLD)
    except Error as e:
        app.logger.warning("DB error fetching low attendance for notifications: %s", e)
        flash("Could not load low attendance records.", "error")
        low_attendance = []

    return render_template(
        "notifications.html",
        overdue_fees=overdue_fees,
        low_attendance=low_attendance,
        low_attendance_threshold=LOW_ATTENDANCE_THRESHOLD,
        email_configured=_email_configured()
    )


@app.route("/notifications/send-fee-reminders", methods=["POST"])
@role_required("admin")
def send_fee_reminders():
    if not _email_configured():
        flash("Email is not configured.", "error")
        return redirect(url_for("notifications"))

    try:
        overdue_fees = database.get_students_with_overdue_fees()
    except Error as e:
        app.logger.warning("DB error fetching overdue fees for reminders: %s", e)
        flash("Could not load overdue fees to send reminders.", "error")
        return redirect(url_for("notifications"))

    sent_count = 0
    fail_count = 0

    for fee in overdue_fees:
        recipient = fee.get("email")
        if not recipient:
            fail_count += 1
            continue

        try:
            remaining = fee["amount_due"] - fee["amount_paid"]
            due_date_str = fee["due_date"].strftime("%d %b %Y") if fee.get("due_date") else "N/A"
            body = (
                f"Dear {fee['student_name']},\n\n"
                f"This is a reminder from {INSTITUTION_NAME} that you have an outstanding fee balance of "
                f"₹{remaining:.2f} (Due Date: {due_date_str}).\n\n"
                f"Please clear your dues at the earliest.\n\n"
                f"Regards,\n"
                f"{INSTITUTION_NAME}"
            )
            msg = Message(
                subject="Fee Payment Reminder",
                recipients=[recipient],
                body=body
            )
            mail.send(msg)
            sent_count += 1
        except Exception as e:
            app.logger.warning("Failed to send fee reminder email to %s: %s", recipient, e)
            fail_count += 1

    flash(f"Sent {sent_count} reminders, {fail_count} failed.", "success" if sent_count > 0 or fail_count == 0 else "error")
    return redirect(url_for("notifications"))


@app.route("/notifications/send-attendance-alerts", methods=["POST"])
@role_required("admin")
def send_attendance_alerts():
    if not _email_configured():
        flash("Email is not configured.", "error")
        return redirect(url_for("notifications"))

    try:
        low_attendance = database.get_students_with_low_attendance(LOW_ATTENDANCE_THRESHOLD)
    except Error as e:
        app.logger.warning("DB error fetching low attendance for alerts: %s", e)
        flash("Could not load low attendance records to send alerts.", "error")
        return redirect(url_for("notifications"))

    sent_count = 0
    fail_count = 0

    for student in low_attendance:
        recipient = student.get("email")
        if not recipient:
            fail_count += 1
            continue

        try:
            pct = student["percentage"]
            body = (
                f"Dear {student['student_name']},\n\n"
                f"This is an alert from {INSTITUTION_NAME} regarding your attendance.\n"
                f"Your current overall attendance is {pct:.1f}%, which is below the required threshold of "
                f"{LOW_ATTENDANCE_THRESHOLD}%.\n\n"
                f"Please ensure regular attendance in your upcoming classes.\n\n"
                f"Regards,\n"
                f"{INSTITUTION_NAME}"
            )
            msg = Message(
                subject="Attendance Alert",
                recipients=[recipient],
                body=body
            )
            mail.send(msg)
            sent_count += 1
        except Exception as e:
            app.logger.warning("Failed to send attendance alert email to %s: %s", recipient, e)
            fail_count += 1

    flash(f"Sent {sent_count} reminders, {fail_count} failed.", "success" if sent_count > 0 or fail_count == 0 else "error")
    return redirect(url_for("notifications"))


# ---------------------------------------------------------------------------
# Exam & Result Management Routes
# ---------------------------------------------------------------------------

@app.route("/exams")
@role_required("admin", "teacher")
def list_exams_route():
    course = request.args.get("course", "").strip() or None
    semester = request.args.get("semester", "").strip() or None
    academic_year = request.args.get("academic_year", "").strip() or None
    
    if semester and semester.isdigit():
        semester = int(semester)
    else:
        semester = None

    try:
        exams = database.get_all_exams(course=course, semester=semester, academic_year=academic_year)
    except Error as e:
        app.logger.error("DB error listing exams: %s", e)
        flash("Database error loading exams.", "error")
        exams = []

    return render_template("exams.html", exams=exams, selected_course=course or "", selected_semester=semester or "", selected_year=academic_year or "")


@app.route("/exams/create", methods=["GET", "POST"])
@role_required("admin", "teacher")
def create_exam_route():
    if request.method == "POST":
        exam_name = request.form.get("exam_name", "").strip()
        exam_type = request.form.get("exam_type", "").strip()
        course = request.form.get("course", "").strip()
        semester_str = request.form.get("semester", "").strip()
        academic_year = request.form.get("academic_year", "").strip()
        status = request.form.get("status", "Scheduled").strip()
        max_marks_str = request.form.get("max_marks", "").strip()
        pass_marks_str = request.form.get("pass_marks", "").strip()

        errors = []
        if not exam_name:
            errors.append("Exam name is required.")
        if not exam_type:
            errors.append("Exam type is required.")
        if not course:
            errors.append("Course is required.")
        if not semester_str or not semester_str.isdigit() or not (1 <= int(semester_str) <= 6):
            errors.append("Semester must be between 1 and 6.")
        if not academic_year:
            errors.append("Academic year is required.")
        if not max_marks_str:
            errors.append("Maximum marks is required.")
        if not pass_marks_str:
            errors.append("Passing marks is required.")

        # Validate max_marks and pass_marks
        max_marks_f, pass_marks_f = None, None
        if max_marks_str and pass_marks_str:
            cfg_valid, cfg_err, max_marks_f, pass_marks_f = exam_service.validate_exam_marks_config(
                max_marks_str, pass_marks_str
            )
            if not cfg_valid:
                errors.append(cfg_err)

        if errors:
            for err in errors:
                flash(err, "error")
            return render_template("exam_form.html", exam=request.form, is_edit=False)

        try:
            created_by = session.get("user_id")
            database.create_exam(
                exam_name=exam_name,
                exam_type=exam_type,
                course=course,
                semester=int(semester_str),
                academic_year=academic_year,
                status=status,
                max_marks=max_marks_f,
                pass_marks=pass_marks_f,
                created_by=created_by
            )
            flash(f"Exam '{exam_name}' created successfully.", "success")
            return redirect(url_for("list_exams_route"))
        except Error as e:
            app.logger.error("DB error creating exam: %s", e)
            flash("Failed to create exam in database.", "error")

    return render_template("exam_form.html", exam={}, is_edit=False)


@app.route("/exams/<int:exam_id>/edit", methods=["GET", "POST"])
@role_required("admin", "teacher")
def edit_exam_route(exam_id):
    exam = database.get_exam_by_id(exam_id)
    if not exam:
        abort(404)

    has_marks = database.has_exam_marks(exam_id)

    if request.method == "POST":
        exam_name = request.form.get("exam_name", "").strip()
        exam_type = request.form.get("exam_type", "").strip()
        course = request.form.get("course", "").strip()
        semester_str = request.form.get("semester", "").strip()
        academic_year = request.form.get("academic_year", "").strip()
        status = request.form.get("status", "Scheduled").strip()
        max_marks_str = request.form.get("max_marks", "").strip()
        pass_marks_str = request.form.get("pass_marks", "").strip()

        errors = []
        if not exam_name:
            errors.append("Exam name is required.")
        if not academic_year:
            errors.append("Academic year is required.")

        # Task 1: If marks exist, academic configuration fields are locked server-side.
        if has_marks:
            orig_type = str(exam.get("exam_type") or "").strip()
            orig_course = str(exam.get("course") or "").strip()
            orig_sem = int(exam.get("semester")) if exam.get("semester") is not None else None
            orig_max = float(exam.get("max_marks")) if exam.get("max_marks") is not None else 100.0
            orig_pass = float(exam.get("pass_marks")) if exam.get("pass_marks") is not None else 40.0

            locked_changed = False
            if exam_type and exam_type != orig_type:
                locked_changed = True
            if course and course != orig_course:
                locked_changed = True
            if semester_str and semester_str.isdigit() and int(semester_str) != orig_sem:
                locked_changed = True
            if max_marks_str:
                try:
                    if abs(float(max_marks_str) - orig_max) > 1e-6:
                        locked_changed = True
                except ValueError:
                    locked_changed = True
            if pass_marks_str:
                try:
                    if abs(float(pass_marks_str) - orig_pass) > 1e-6:
                        locked_changed = True
                except ValueError:
                    locked_changed = True

            if locked_changed:
                errors.append("Exam configuration cannot be changed after marks have been entered.")

            exam_type = orig_type
            course = orig_course
            semester_str = str(orig_sem) if orig_sem is not None else "1"
            max_marks_f = orig_max
            pass_marks_f = orig_pass
        else:
            if not exam_type:
                errors.append("Exam type is required.")
            if not course:
                errors.append("Course is required.")
            if not semester_str or not semester_str.isdigit() or not (1 <= int(semester_str) <= 6):
                errors.append("Semester must be between 1 and 6.")
            if not max_marks_str:
                errors.append("Maximum marks is required.")
            if not pass_marks_str:
                errors.append("Passing marks is required.")

            max_marks_f, pass_marks_f = None, None
            if max_marks_str and pass_marks_str:
                cfg_valid, cfg_err, max_marks_f, pass_marks_f = exam_service.validate_exam_marks_config(
                    max_marks_str, pass_marks_str
                )
                if not cfg_valid:
                    errors.append(cfg_err)

        if errors:
            for err in errors:
                flash(err, "error")
            return render_template("exam_form.html", exam=request.form, is_edit=True, exam_id=exam_id, has_marks=has_marks)

        try:
            database.update_exam(
                exam_id=exam_id,
                exam_name=exam_name,
                exam_type=exam_type,
                course=course,
                semester=int(semester_str),
                academic_year=academic_year,
                status=status,
                max_marks=max_marks_f,
                pass_marks=pass_marks_f
            )
            flash(f"Exam '{exam_name}' updated successfully.", "success")
            return redirect(url_for("list_exams_route"))
        except Error as e:
            app.logger.error("DB error updating exam: %s", e)
            flash("Failed to update exam in database.", "error")

    return render_template("exam_form.html", exam=exam, is_edit=True, exam_id=exam_id, has_marks=has_marks)



@app.route("/exams/<int:exam_id>/delete", methods=["POST"])
@role_required("admin")
def delete_exam_route(exam_id):
    try:
        database.delete_exam(exam_id)
        flash("Exam deleted successfully.", "success")
    except Error as e:
        app.logger.error("DB error deleting exam: %s", e)
        flash("Failed to delete exam.", "error")
    return redirect(url_for("list_exams_route"))


@app.route("/exams/<int:exam_id>/marks", methods=["GET", "POST"])
@role_required("admin", "teacher")
def enter_exam_marks_route(exam_id):
    exam = database.get_exam_by_id(exam_id)
    if not exam:
        abort(404)

    if exam["semester"] == 1:
        database.ensure_semester1_subjects(exam["course"])
    elif exam["semester"] == 2:
        database.ensure_semester2_subjects(exam["course"])
    elif exam["semester"] == 3:
        database.ensure_semester3_subjects(exam["course"])

    subjects = database.get_subjects_by_course_and_semester(exam["course"], exam["semester"])
    students = database.get_all_students(course_filter=exam["course"], semester_filter=exam["semester"])

    if request.method == "POST":
        all_marks_valid = True
        recorded_by = _get_user_id()
        if not recorded_by:
            flash("Could not identify current user. Please log in again.", "error")
            return redirect(url_for("list_exams_route"))

        for student in students:
            roll_no = student["student_id"]   # varchar roll number (used in field names)
            stud_pk = student["id"]           # integer PK (used for DB saves)
            for sub in subjects:
                sub_id = sub["id"]            # subjects.id (integer PK)
                obt_key = f"obt_{roll_no}_{sub_id}"

                obt_val = request.form.get(obt_key, "").strip()

                if obt_val:
                    # Ignore any max_marks submitted in form payload. Always use the unalterable exam-level max_marks!
                    exam_max = float(exam.get("max_marks") if exam.get("max_marks") is not None else sub.get("max_marks", 100.0))
                    valid, err_msg, obt_f, max_f = exam_service.validate_marks_input(obt_val, exam_max)
                    if not valid:
                        flash(f"Student {roll_no} - {sub['subject_name']}: {err_msg}", "error")
                        all_marks_valid = False
                    else:
                        try:
                            database.save_exam_marks(
                                exam_id=exam_id,
                                stud_id=stud_pk,
                                subject_id=sub_id,
                                obtained_marks=obt_f,
                                max_marks=exam_max,
                                recorded_by=recorded_by
                            )
                        except Error as e:
                            app.logger.error("DB error saving marks: %s", e)
                            flash(f"Database error saving marks for {roll_no}", "error")
                            all_marks_valid = False

        if all_marks_valid:
            flash("Exam marks saved successfully.", "success")
            return redirect(url_for("list_exams_route"))

    existing_marks = database.get_all_marks_for_exam(exam_id)
    # Key: (student_pk: int, subject_id: int) → mark row
    marks_map = {}
    for m in existing_marks:
        marks_map[(m["stud_id"], m["subject_id"])] = m

    return render_template(
        "exam_marks_entry.html",
        exam=exam,
        subjects=subjects,
        students=students,
        marks_map=marks_map
    )


@app.route("/exams/<int:exam_id>/results/<student_id>")
@role_required("admin", "teacher", "student")
def view_exam_results_route(exam_id, student_id):
    _assert_own_record(student_id)

    exam = database.get_exam_by_id(exam_id)
    if not exam:
        abort(404)

    student = database.get_student_by_id(student_id)
    if not student:
        student = database.get_student_by_student_id(student_id)
    if not student:
        abort(404)

    raw_marks = database.get_exam_marks_for_student(exam_id, student_id)
    result_summary = exam_service.compute_student_result_summary(student=student, exam=exam, raw_marks_list=raw_marks)

    return render_template(
        "student_result.html",
        summary=result_summary,
        exam=exam,
        student=student,
        subject_results=result_summary["subject_results"],
        total_obtained=result_summary["total_obtained"],
        total_max=result_summary["total_max"],
        percentage=result_summary["percentage"],
        overall_grade=result_summary["overall_grade"],
        overall_status=result_summary["overall_status"]
    )


@app.route("/students/<student_id>/result-history")
@role_required("admin", "teacher", "student")
def student_result_history_route(student_id):
    _assert_own_record(student_id)

    student = database.get_student_by_id(student_id)
    if not student:
        student = database.get_student_by_student_id(student_id)
    if not student:
        abort(404)

    raw_history = database.get_student_exam_history(student_id)

    semester_groups = {}
    for item in raw_history:
        sem = item["exam"]["semester"]
        if sem not in semester_groups:
            semester_groups[sem] = {"semester": sem, "exams": []}
        
        summary = exam_service.compute_student_result_summary(item["marks"])
        semester_groups[sem]["exams"].append({
            "exam": item["exam"],
            "marks": item["marks"],
            "summary": summary
        })

    return render_template(
        "student_result_history.html",
        student=student,
        semester_groups=semester_groups
    )


@app.route("/students/<student_id>/academic-record")
@role_required("admin", "teacher", "student")
def student_academic_record_route(student_id):
    _assert_own_record(student_id)

    student = database.get_student_by_id(student_id)
    if not student:
        student = database.get_student_by_student_id(student_id)
    if not student:
        abort(404)

    raw_history = database.get_student_exam_history(student_id)
    transcript = exam_service.compute_academic_transcript(student, raw_history)

    return render_template(
        "academic_record.html",
        student=student,
        transcript=transcript
    )


@app.route("/students/<student_id>/academic-record/pdf")
@role_required("admin", "teacher", "student")
def download_academic_record_pdf_route(student_id):
    _assert_own_record(student_id)

    student = database.get_student_by_id(student_id)
    if not student:
        student = database.get_student_by_student_id(student_id)
    if not student:
        abort(404)

    raw_history = database.get_student_exam_history(student_id)
    transcript = exam_service.compute_academic_transcript(student, raw_history)

    pdf_bytes = generate_academic_transcript_pdf(
        student=student,
        transcript_data=transcript
    )

    filename = f"Academic_Transcript_{student.get('student_id', student_id)}.pdf"
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename
    )



@app.route("/exams/<int:exam_id>/marksheet/<student_id>/pdf")
@role_required("admin", "teacher", "student")
def download_marksheet_pdf_route(exam_id, student_id):
    _assert_own_record(student_id)

    exam = database.get_exam_by_id(exam_id)
    if not exam:
        abort(404)

    student = database.get_student_by_id(student_id)
    if not student:
        student = database.get_student_by_student_id(student_id)
    if not student:
        abort(404)

    raw_marks = database.get_exam_marks_for_student(exam_id, student_id)
    result_summary = exam_service.compute_student_result_summary(raw_marks)

    pdf_bytes = generate_marksheet_pdf(
        student=student,
        exam=exam,
        marks=raw_marks,
        result_summary=result_summary
    )

    filename = f"result_{student_id}_{exam_id}.pdf"
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename
    )


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------

@app.errorhandler(403)
def forbidden(e):
    return render_template("403.html"), 403


@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404


@app.errorhandler(429)
def ratelimit_handler(e):
    return render_template("429.html"), 429


@app.errorhandler(500)
def server_error(e):
    app.logger.error("Unhandled server error: %s", e, exc_info=True)
    return render_template("500.html"), 500


if __name__ == "__main__":
    app.run(debug=config.FLASK_DEBUG)
