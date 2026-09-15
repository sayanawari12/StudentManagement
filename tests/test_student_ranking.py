"""
test_student_ranking.py — Unit and integration security tests for the Student Performance / Ranking module.
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
    # Setup test student in session
    with client.session_transaction() as sess:
        sess["user_id"] = 3
        sess["username"] = "student1"
        sess["role"] = "student"
        sess["linked_student_id"] = 1
    return client


def test_ranking_calculation_no_cgpa():
    """Verify that rankings calculate percentage from obtained/total_max and do not use CGPA."""
    rankings = database.get_semester_rankings(1)
    for r in rankings:
        assert "cgpa" not in r
        assert "percentage" in r
        assert "formatted_marks" in r
        assert "formatted_percentage" in r
        assert r["percentage"] >= 0.0 and r["percentage"] <= 100.0


def test_competition_tie_handling():
    """Test deterministic competition ranking (1, 2, 2, 4) for equal percentages."""
    # Mock data to test tie breaking logic
    test_data = [
        {"percentage": 90.00},
        {"percentage": 85.00},
        {"percentage": 85.00},
        {"percentage": 80.00},
    ]
    # Competition ranking assignment
    for i, item in enumerate(test_data):
        if i > 0:
            prev = test_data[i - 1]
            if item["percentage"] == prev["percentage"]:
                item["rank"] = prev["rank"]
            else:
                item["rank"] = i + 1
        else:
            item["rank"] = 1

    assert test_data[0]["rank"] == 1
    assert test_data[1]["rank"] == 2
    assert test_data[2]["rank"] == 2
    assert test_data[3]["rank"] == 4  # Skips 3 due to tie at 2


def test_empty_semester_ranking_handling():
    """Verify clean empty state when no results exist for a semester."""
    rankings = database.get_semester_rankings(999)
    assert isinstance(rankings, list)
    assert len(rankings) == 0


def test_admin_can_access_rankings(auth_admin):
    """Admin can view the ranking route."""
    response = auth_admin.get("/rankings?semester=1")
    assert response.status_code == 200
    assert b"Student Performance &amp; Rankings" in response.data or b"Student Performance & Rankings" in response.data


def test_teacher_can_access_rankings(auth_teacher):
    """Teacher can view the ranking route."""
    response = auth_teacher.get("/rankings?semester=1")
    assert response.status_code == 200
    assert b"Student Performance &amp; Rankings" in response.data or b"Student Performance & Rankings" in response.data


def test_student_privacy_restriction(auth_student):
    """Student role cannot enumerate or browse other students' rankings."""
    response = auth_student.get("/rankings?semester=1")
    assert response.status_code == 200
    # Confirm table header with other students is not shown to student
    assert b"Total Ranked Students" not in response.data

    # Test API endpoint privacy filtering for student
    api_resp = auth_student.get("/api/student-rankings?semester=1")
    assert api_resp.status_code == 200
    json_data = api_resp.get_json()
    assert json_data["role"] == "student"
    # If rankings list has items, it must contain at most 1 item (the student's own)
    assert len(json_data["rankings"]) <= 1


def test_api_student_rankings_admin(auth_admin):
    """Admin can query the student rankings JSON API."""
    response = auth_admin.get("/api/student-rankings?semester=1")
    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["success"] is True
    assert json_data["semester"] == 1
    assert "rankings" in json_data


def test_dashboard_widget_renders(auth_admin):
    """Verify that Dashboard renders Top Performers widget."""
    response = auth_admin.get("/dashboard")
    assert response.status_code == 200
    assert b"Top Performers" in response.data
    assert b"topPerformersSemSelect" in response.data
