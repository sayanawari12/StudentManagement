import re
from decimal import Decimal
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from werkzeug.security import check_password_hash
from mysql.connector import Error

import config
import database
from flask_wtf.csrf import CSRFProtect

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
csrf = CSRFProtect(app)

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


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
            session["admin"] = user["username"]          # kept for any legacy checks
            session["role"]  = user["role"]
            session["linked_student_id"] = user["linked_student_id"]  # None for admin/teacher
            return redirect(url_for("dashboard"))

        flash("Invalid username or password.", "error")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


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
        marked_by = session.get("linked_student_id") or _get_user_id()

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


def _get_user_id():
    """Fetch the users.id for the currently logged-in user."""
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
