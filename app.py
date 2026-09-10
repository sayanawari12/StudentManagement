import csv
import io
import re
from decimal import Decimal
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, flash, abort, send_file
from werkzeug.security import check_password_hash, generate_password_hash
from mysql.connector import Error

import config
import database
from pdf_generator import generate_bonafide_pdf, generate_dashboard_pdf
from flask_wtf.csrf import CSRFProtect

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
csrf = CSRFProtect(app)

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
INSTITUTION_NAME = "SUSHGANGA INSTITUTE OF COMPUTER APPLICATIONS"
ATTENDANCE_TREND_DAYS = 14
EXPECTED_CSV_HEADERS = [
    "student_id", "student_name", "email", "phone",
    "gender", "date_of_birth", "course", "semester", "address"
]


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
    """For student-role users: abort 403 if record_id is not their linked student.

    Applied only to routes reachable by students:
      student_details, attendance/<record_id>, fees/<record_id>
    NOT applied to edit_student (already admin-only via role_required).
    """
    if session.get("role") == "student":
        if record_id != session.get("linked_student_id"):
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


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        try:
            user = database.get_user_by_username(username)
        except Error:
            flash("Could not reach the database. Please check MySQL is running.", "error")
            return render_template("login.html")

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["admin"]   = user["username"]          # kept for any legacy checks
            session["role"]    = user["role"]
            session["linked_student_id"] = user["linked_student_id"]  # None for admin/teacher
            return redirect(url_for("dashboard"))

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
    try:
        user = database.get_user_by_id(user_id)
    except Error:
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
    except Error:
        flash("Could not load dashboard stats from the database.", "error")
        stats = {
            "total_students":   0,
            "total_bca":        0,
            "semester_counts":  [],
            "attendance_today": 0,
            "total_dues":       Decimal("0"),
        }
    return render_template("dashboard.html", stats=stats)


@app.route("/dashboard/export")
@role_required("admin")
def dashboard_export():
    from datetime import date as dt_date
    try:
        stats = database.get_dashboard_stats()
    except Error:
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
    except Error:
        flash("Could not load attendance trend from the database.", "error")
        attendance_trend = []

    try:
        stats = database.get_dashboard_stats()
        semester_counts = stats.get("semester_counts", [])
    except Error:
        flash("Could not load semester distribution stats.", "error")
        semester_counts = []

    fee_status = None
    if session.get("role") == "admin":
        try:
            fee_status = database.get_fee_status_breakdown()
        except Error:
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
    except Error:
        flash("Could not load students from the database.", "error")
        student_list = []
    return render_template("students.html", students=student_list, search=search)


@app.route("/students/add", methods=["GET", "POST"])
@role_required("admin")                  # Fix 7: admin only
def add_student():
    if request.method == "POST":
        form = request.form
        errors = validate_student_form(form)

        if not errors:
            try:
                existing = database.get_student_by_student_id(form.get("student_id").strip())
            except Error:
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
    except Error:
        flash("Could not reach the database.", "error")
        return redirect(url_for("students"))

    if not student:
        flash("Student not found.", "error")
        return redirect(url_for("students"))

    # Attendance section data
    try:
        attendance_records = database.get_student_attendance(record_id)
    except Error:
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
    except Error:
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
    except Error:
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
    except Error:
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
            except Error:
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
        flash(f"Database error: {e}", "error")
    return redirect(url_for("students"))


@app.route("/students/<int:record_id>/certificate")
@role_required("admin", "student")
def student_certificate(record_id):
    _assert_own_record(record_id)
    try:
        student = database.get_student_by_id(record_id)
    except Error:
        flash("Could not reach the database.", "error")
        return redirect(url_for("students"))

    if not student:
        flash("Student not found.", "error")
        return redirect(url_for("students"))

    pdf_buffer = generate_bonafide_pdf(INSTITUTION_NAME, student)
    return send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"certificate_{student['student_id']}.pdf",
    )


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

        for s in students_list:
            status = request.form.get(f"status_{s['id']}", "")
            if status in ("Present", "Absent"):
                try:
                    database.upsert_attendance(s["id"], post_date, status, marked_by)
                except Error as e:
                    flash(f"Database error saving attendance: {e}", "error")
                    return redirect(url_for("attendance", date=post_date))

        flash("Attendance saved.", "success")
        return redirect(url_for("attendance", date=post_date))

    # GET — load students + today's existing marks
    try:
        students_list    = database.get_all_students_for_attendance()
        existing_marks   = database.get_attendance_by_date(selected_date)
    except Error:
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
    except Error:
        flash("Could not reach the database.", "error")
        return redirect(url_for("students"))

    if not student:
        flash("Student not found.", "error")
        return redirect(url_for("students"))

    try:
        records = database.get_student_attendance(record_id)
    except Error:
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
    except Error:
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
            flash(f"Database error: {e}", "error")
            return render_template("grades_add.html", student=student, form=form)

    return render_template("grades_add.html", student=student, form={"max_marks": "100.00"})


@app.route("/grades/<int:record_id>")
@role_required("admin", "teacher", "student")
def grades_view(record_id):
    _assert_own_record(record_id)
    return redirect(url_for("student_details", record_id=record_id))


def _get_user_id():
    """Fetch the users.id for the currently logged-in user."""
    if "user_id" in session:
        return session["user_id"]
    try:
        user = database.get_user_by_username(session.get("admin", ""))
        return user["id"] if user else 1
    except Error:
        return 1


# ---------------------------------------------------------------------------
# Fees routes
# ---------------------------------------------------------------------------

@app.route("/fees/create/<int:record_id>", methods=["GET", "POST"])
@role_required("admin")
def fees_create(record_id):
    try:
        student = database.get_student_by_id(record_id)
    except Error:
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
            flash(f"Database error: {e}", "error")
            return render_template("fees_create.html", student=student, form=request.form)

    return render_template("fees_create.html", student=student, form={})


@app.route("/fees/pay/<int:fee_id>", methods=["GET", "POST"])
@role_required("admin")
def fees_pay(fee_id):
    try:
        fee = database.get_fee_by_id(fee_id)
    except Error:
        flash("Could not reach the database.", "error")
        return redirect(url_for("students"))

    if not fee:
        flash("Fee record not found.", "error")
        return redirect(url_for("students"))

    remaining = fee["amount_due"] - fee["amount_paid"]
    record_id = fee["stud_id"]

    try:
        student = database.get_student_by_id(record_id)
    except Error:
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
    except Error:
        flash("Could not reach the database.", "error")
        return redirect(url_for("students"))

    if not student:
        flash("Student not found.", "error")
        return redirect(url_for("students"))

    try:
        fee_records = database.get_student_fees(record_id)
    except Error:
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
# Error handlers
# ---------------------------------------------------------------------------

@app.errorhandler(403)
def forbidden(e):
    return render_template("403.html"), 403


if __name__ == "__main__":
    app.run(debug=True)
