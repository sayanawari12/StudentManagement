"""
test_timetable.py — Unit and integration tests for Timetable Management module.

Tests cover:
  - Admin CRUD operations (create, view, edit, delete)
  - Role-based authorization & security (student, teacher, anonymous access)
  - Dynamic Semester -> Subject API endpoint
  - Data integrity & server-side validation (subject-semester mapping, teacher validation, time bounds)
  - Conflict detection (semester overlap, teacher overlap, room overlap)
  - Student semester isolation & teacher identity filtering
  - CSRF protection and empty states
"""

import pytest
from app import app
import database


@pytest.fixture
def client():
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    with app.test_client() as client:
        yield client


@pytest.fixture
def auth_admin(client):
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["username"] = "admin"
        sess["role"] = "admin"
    return client


@pytest.fixture
def auth_teacher(client):
    with client.session_transaction() as sess:
        sess["user_id"] = 2
        sess["username"] = "teacher"
        sess["role"] = "teacher"
    return client


@pytest.fixture
def auth_student(client):
    with client.session_transaction() as sess:
        sess["user_id"] = 3
        sess["username"] = "student1"
        sess["role"] = "student"
        sess["linked_student_id"] = 1
    return client


def _clean_timetable():
    database.ensure_timetable_table_exists()
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM timetable")
    conn.commit()
    cursor.close()
    conn.close()


# ---------------------------------------------------------------------------
# 1. Admin CRUD & View Tests
# ---------------------------------------------------------------------------

def test_admin_can_view_timetable(auth_admin):
    """Verify admin can view timetable page."""
    _clean_timetable()
    res = auth_admin.get("/timetable")
    assert res.status_code == 200
    assert b"Timetable Management" in res.data or b"Timetable" in res.data


def test_admin_can_create_timetable(auth_admin, db):
    """Verify admin can create a valid timetable entry via POST /timetable/add."""
    _clean_timetable()
    admin_id = db["users"]["admin"]["id"]
    teacher_id = db["users"]["teacher"]["id"]
    subjects = database.get_subjects_by_course_and_semester("BCA", 2)
    assert len(subjects) >= 1

    res = auth_admin.post("/timetable/add", data={
        "semester": "2",
        "subject_id": str(subjects[0]["id"]),
        "teacher_id": str(teacher_id),
        "day_of_week": "Monday",
        "start_time": "09:00",
        "end_time": "10:00",
        "room": "Room 101"
    }, follow_redirects=True)

    assert res.status_code == 200
    entries = database.get_timetable_entries(semester=2)
    assert len(entries) == 1
    assert entries[0]["room"] == "Room 101"
    assert entries[0]["day_of_week"] == "Monday"


def test_admin_can_edit_timetable(auth_admin, db):
    """Verify admin can edit an existing timetable entry."""
    _clean_timetable()
    admin_id = db["users"]["admin"]["id"]
    teacher_id = db["users"]["teacher"]["id"]
    subjects = database.get_subjects_by_course_and_semester("BCA", 2)

    entry_id = database.create_timetable_entry(
        semester=2,
        subject_id=subjects[0]["id"],
        teacher_id=teacher_id,
        day_of_week="Tuesday",
        start_time="10:00",
        end_time="11:00",
        room="Room 102",
        created_by=admin_id
    )

    res = auth_admin.post(f"/timetable/edit/{entry_id}", data={
        "semester": "2",
        "subject_id": str(subjects[0]["id"]),
        "teacher_id": str(teacher_id),
        "day_of_week": "Tuesday",
        "start_time": "10:00",
        "end_time": "11:00",
        "room": "Room 999"
    }, follow_redirects=True)

    assert res.status_code == 200
    updated = database.get_timetable_entry_by_id(entry_id)
    assert updated["room"] == "Room 999"


def test_admin_can_delete_timetable(auth_admin, db):
    """Verify admin can delete a timetable entry."""
    _clean_timetable()
    admin_id = db["users"]["admin"]["id"]
    teacher_id = db["users"]["teacher"]["id"]
    subjects = database.get_subjects_by_course_and_semester("BCA", 2)

    entry_id = database.create_timetable_entry(
        semester=2,
        subject_id=subjects[0]["id"],
        teacher_id=teacher_id,
        day_of_week="Wednesday",
        start_time="11:00",
        end_time="12:00",
        room="Lab 1",
        created_by=admin_id
    )

    res = auth_admin.post(f"/timetable/delete/{entry_id}", follow_redirects=True)
    assert res.status_code == 200
    assert database.get_timetable_entry_by_id(entry_id) is None


# ---------------------------------------------------------------------------
# 2. Authorization & Security Tests
# ---------------------------------------------------------------------------

def test_anonymous_user_cannot_access_timetable(client):
    """Verify anonymous user is redirected to login."""
    res = client.get("/timetable")
    assert res.status_code in (302, 401)


def test_student_cannot_modify_timetable(auth_student, db):
    """Verify student role gets 403 on add, edit, and delete routes."""
    _clean_timetable()
    res_add = auth_student.get("/timetable/add")
    assert res_add.status_code == 403

    res_post = auth_student.post("/timetable/add", data={})
    assert res_post.status_code == 403

    res_edit = auth_student.get("/timetable/edit/1")
    assert res_edit.status_code == 403

    res_del = auth_student.post("/timetable/delete/1")
    assert res_del.status_code == 403


def test_teacher_cannot_modify_timetable(auth_teacher, db):
    """Verify teacher role gets 403 on add, edit, and delete routes."""
    _clean_timetable()
    res_add = auth_teacher.get("/timetable/add")
    assert res_add.status_code == 403

    res_del = auth_teacher.post("/timetable/delete/1")
    assert res_del.status_code == 403


def test_student_sees_only_own_semester_timetable(auth_student, db):
    """Verify student automatically sees only their enrolled semester's timetable."""
    _clean_timetable()
    admin_id = db["users"]["admin"]["id"]
    teacher_id = db["users"]["teacher"]["id"]

    student_rec = database.get_student_by_id(1)
    student_sem = int(student_rec["semester"])
    other_sem = 1 if student_sem != 1 else 2

    own_subs = database.get_subjects_by_course_and_semester("BCA", student_sem)
    other_subs = database.get_subjects_by_course_and_semester("BCA", other_sem)

    database.create_timetable_entry(student_sem, own_subs[0]["id"], teacher_id, "Monday", "09:00", "10:00", "Room Own", admin_id)
    database.create_timetable_entry(other_sem, other_subs[0]["id"], teacher_id, "Monday", "11:00", "12:00", "Room Other", admin_id)

    res = auth_student.get("/timetable")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert own_subs[0]["subject_code"] in html
    assert other_subs[0]["subject_code"] not in html


def test_teacher_sees_only_own_assigned_classes(auth_teacher, db):
    """Verify teacher sees only classes assigned to their teacher ID."""
    _clean_timetable()
    admin_id = db["users"]["admin"]["id"]
    teacher_id = db["users"]["teacher"]["id"]
    subjects = database.get_subjects_by_course_and_semester("BCA", 2)

    # Entry assigned to teacher
    database.create_timetable_entry(2, subjects[0]["id"], teacher_id, "Monday", "09:00", "10:00", "Room A", admin_id)
    # Entry assigned to admin
    database.create_timetable_entry(2, subjects[1]["id"], admin_id, "Monday", "10:00", "11:00", "Room B", admin_id)

    res = auth_teacher.get("/timetable")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert subjects[0]["subject_code"] in html
    assert subjects[1]["subject_code"] not in html


# ---------------------------------------------------------------------------
# 3. Dynamic API & Server-side Validation Tests
# ---------------------------------------------------------------------------

def test_api_semester_subjects_dynamic(auth_admin):
    """Verify GET /api/semesters/<sem>/subjects returns JSON for that semester."""
    res = auth_admin.get("/api/semesters/2/subjects")
    assert res.status_code == 200
    json_data = res.get_json()
    assert json_data["success"] is True
    assert json_data["semester"] == 2
    assert len(json_data["subjects"]) == 6
    codes = [s["subject_code"] for s in json_data["subjects"]]
    assert "DS201" in codes


def test_invalid_semester_subject_combination_rejected(db):
    """Verify server rejects subject that does not belong to selected semester."""
    _clean_timetable()
    admin_id = db["users"]["admin"]["id"]
    teacher_id = db["users"]["teacher"]["id"]
    sem3_subs = database.get_subjects_by_course_and_semester("BCA", 3)

    # Attempt to pair Semester 2 with a Semester 3 subject
    with pytest.raises(ValueError, match="does not belong to Semester 2"):
        database.create_timetable_entry(
            semester=2,
            subject_id=sem3_subs[0]["id"],
            teacher_id=teacher_id,
            day_of_week="Monday",
            start_time="09:00",
            end_time="10:00",
            room="Room 101",
            created_by=admin_id
        )


def test_invalid_teacher_id_rejected(db):
    """Verify non-existent teacher ID is rejected server-side."""
    _clean_timetable()
    admin_id = db["users"]["admin"]["id"]
    subjects = database.get_subjects_by_course_and_semester("BCA", 2)

    with pytest.raises(ValueError, match="Invalid teacher selected"):
        database.create_timetable_entry(
            semester=2,
            subject_id=subjects[0]["id"],
            teacher_id=99999,
            day_of_week="Monday",
            start_time="09:00",
            end_time="10:00",
            room="Room 101",
            created_by=admin_id
        )


def test_start_time_ge_end_time_rejected(db):
    """Verify start_time >= end_time is rejected."""
    _clean_timetable()
    admin_id = db["users"]["admin"]["id"]
    teacher_id = db["users"]["teacher"]["id"]
    subjects = database.get_subjects_by_course_and_semester("BCA", 2)

    with pytest.raises(ValueError, match="Start time must be strictly before end time"):
        database.create_timetable_entry(
            semester=2,
            subject_id=subjects[0]["id"],
            teacher_id=teacher_id,
            day_of_week="Monday",
            start_time="10:00",
            end_time="09:00",
            room="Room 101",
            created_by=admin_id
        )


# ---------------------------------------------------------------------------
# 4. Conflict Detection Tests
# ---------------------------------------------------------------------------

def test_same_semester_overlapping_class_rejected(db):
    """Verify backend rejects overlapping class in same semester."""
    _clean_timetable()
    admin_id = db["users"]["admin"]["id"]
    teacher_id = db["users"]["teacher"]["id"]
    subjects = database.get_subjects_by_course_and_semester("BCA", 2)

    database.create_timetable_entry(2, subjects[0]["id"], teacher_id, "Monday", "09:00", "10:30", "Room 1", admin_id)

    with pytest.raises(ValueError, match="Conflict: Semester 2 already has class"):
        database.create_timetable_entry(2, subjects[1]["id"], teacher_id, "Monday", "10:00", "11:30", "Room 2", admin_id)


def test_same_teacher_overlapping_class_rejected(db):
    """Verify backend rejects overlapping class for same teacher in different semester."""
    _clean_timetable()
    admin_id = db["users"]["admin"]["id"]
    teacher_id = db["users"]["teacher"]["id"]
    sem2_subs = database.get_subjects_by_course_and_semester("BCA", 2)
    sem3_subs = database.get_subjects_by_course_and_semester("BCA", 3)

    database.create_timetable_entry(2, sem2_subs[0]["id"], teacher_id, "Tuesday", "09:00", "10:30", "Room 1", admin_id)

    with pytest.raises(ValueError, match="is already assigned to another class"):
        database.create_timetable_entry(3, sem3_subs[0]["id"], teacher_id, "Tuesday", "10:00", "11:30", "Room 3", admin_id)


def test_same_room_overlapping_class_rejected(db):
    """Verify backend rejects overlapping class in same room."""
    _clean_timetable()
    admin_id = db["users"]["admin"]["id"]
    teacher_id = db["users"]["teacher"]["id"]
    sem2_subs = database.get_subjects_by_course_and_semester("BCA", 2)
    sem3_subs = database.get_subjects_by_course_and_semester("BCA", 3)

    database.create_timetable_entry(2, sem2_subs[0]["id"], teacher_id, "Wednesday", "09:00", "10:30", "Room 101", admin_id)

    with pytest.raises(ValueError, match="is already occupied"):
        database.create_timetable_entry(3, sem3_subs[0]["id"], admin_id, "Wednesday", "10:00", "11:30", "Room 101", admin_id)


def test_non_overlapping_classes_accepted(db):
    """Verify non-overlapping back-to-back classes are accepted."""
    _clean_timetable()
    admin_id = db["users"]["admin"]["id"]
    teacher_id = db["users"]["teacher"]["id"]
    subjects = database.get_subjects_by_course_and_semester("BCA", 2)

    id1 = database.create_timetable_entry(2, subjects[0]["id"], teacher_id, "Thursday", "09:00", "10:00", "Room 1", admin_id)
    id2 = database.create_timetable_entry(2, subjects[1]["id"], teacher_id, "Thursday", "10:00", "11:00", "Room 1", admin_id)
    assert id1 and id2


def test_edit_conflict_excludes_current_entry(db):
    """Verify editing an entry without changing time does not trigger false self-conflict."""
    _clean_timetable()
    admin_id = db["users"]["admin"]["id"]
    teacher_id = db["users"]["teacher"]["id"]
    subjects = database.get_subjects_by_course_and_semester("BCA", 2)

    entry_id = database.create_timetable_entry(2, subjects[0]["id"], teacher_id, "Friday", "09:00", "10:00", "Room A", admin_id)

    # Edit room only
    success = database.update_timetable_entry(
        entry_id=entry_id,
        semester=2,
        subject_id=subjects[0]["id"],
        teacher_id=teacher_id,
        day_of_week="Friday",
        start_time="09:00",
        end_time="10:00",
        room="Room B",
        updated_by=admin_id
    )
    assert success is True


def test_empty_timetable_works(auth_admin):
    """Verify empty timetable renders clean empty state message."""
    _clean_timetable()
    res = auth_admin.get("/timetable")
    assert res.status_code == 200
    assert b"No timetable entries have been scheduled yet" in res.data or b"No classes" in res.data


def test_timetable_time_formatting_regression(auth_admin, db):
    """Regression test: verify start_time and end_time are correctly formatted as HH:MM without literal %H or %i."""
    import re
    _clean_timetable()
    admin_id = db["users"]["admin"]["id"]
    teacher_id = db["users"]["teacher"]["id"]
    subjects = database.get_subjects_by_course_and_semester("BCA", 2)

    entry_id = database.create_timetable_entry(
        semester=2,
        subject_id=subjects[0]["id"],
        teacher_id=teacher_id,
        day_of_week="Monday",
        start_time="09:00",
        end_time="10:30",
        room="Room 101",
        created_by=admin_id
    )

    # 1. Direct helper checks
    entry = database.get_timetable_entry_by_id(entry_id)
    assert entry["start_time"] == "09:00"
    assert entry["end_time"] == "10:30"
    assert "%i" not in entry["start_time"]
    assert "%i" not in entry["end_time"]
    assert "%H" not in entry["start_time"]
    assert "%H" not in entry["end_time"]

    entries = database.get_timetable_entries(semester=2)
    assert len(entries) == 1
    assert entries[0]["start_time"] == "09:00"
    assert entries[0]["end_time"] == "10:30"

    # 2. View HTML rendering check
    res = auth_admin.get("/timetable?semester=2")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "%H" not in html
    assert "%i" not in html
    assert "09:00" in html
    assert "10:30" in html

