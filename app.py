import re
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import check_password_hash
from mysql.connector import Error

import config
import database

app = Flask(__name__)
app.secret_key = config.SECRET_KEY

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------

def login_required(view_func):
    """Redirects to the login page if there is no admin in the session.
    Applied to every route below except /login itself.
    """
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if "admin" not in session:
            flash("Please log in to continue.", "error")
            return redirect(url_for("login"))
        return view_func(*args, **kwargs)
    return wrapped_view


# ---------------------------------------------------------------------------
# Validation helper
# ---------------------------------------------------------------------------

def validate_student_form(form):
    """Server-side validation. Runs even if the browser's JS validation
    already passed, since JS can always be bypassed.
    """
    errors = []

    required_fields = {
        "student_id": "Student ID",
        "student_name": "Student name",
        "email": "Email",
        "course": "Course",
        "semester": "Semester",
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
        "student_id": form.get("student_id", "").strip(),
        "student_name": form.get("student_name", "").strip(),
        "email": form.get("email", "").strip(),
        "phone": form.get("phone", "").strip(),
        "gender": form.get("gender", ""),
        "date_of_birth": form.get("date_of_birth") or None,
        "course": form.get("course", "").strip(),
        "semester": int(form.get("semester")),
        "address": form.get("address", "").strip(),
    }


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    if "admin" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        try:
            admin = database.get_admin_by_username(username)
        except Error:
            flash("Could not reach the database. Please check MySQL is running.", "error")
            return render_template("login.html")

        if admin and check_password_hash(admin["password"], password):
            session["admin"] = admin["username"]
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
        stats = {"total_students": 0, "total_bca": 0, "semester_counts": []}
    return render_template("dashboard.html", stats=stats)


# ---------------------------------------------------------------------------
# Student routes
# ---------------------------------------------------------------------------

@app.route("/students")
@login_required
def students():
    search = request.args.get("search", "").strip()
    try:
        student_list = database.get_all_students(search if search else None)
    except Error:
        flash("Could not load students from the database.", "error")
        student_list = []
    return render_template("students.html", students=student_list, search=search)


@app.route("/students/add", methods=["GET", "POST"])
@login_required
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
@login_required
def student_details(record_id):
    try:
        student = database.get_student_by_id(record_id)
    except Error:
        flash("Could not reach the database.", "error")
        return redirect(url_for("students"))

    if not student:
        flash("Student not found.", "error")
        return redirect(url_for("students"))

    return render_template("student_details.html", student=student)


@app.route("/students/<int:record_id>/edit", methods=["GET", "POST"])
@login_required
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
@login_required
def delete_student(record_id):
    try:
        database.delete_student(record_id)
        flash("Student deleted successfully.", "success")
    except Error as e:
        flash(f"Database error: {e}", "error")
    return redirect(url_for("students"))


if __name__ == "__main__":
    app.run(debug=True)
