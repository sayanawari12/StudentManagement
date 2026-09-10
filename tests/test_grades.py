"""
test_grades.py — Grades database function tests.
"""

from decimal import Decimal

import pytest
import database


class TestGetGradeSummary:
    """get_grade_summary() must never return None or raise."""

    def test_zero_grade_rows_returns_zero(self, db):
        """
        Regression (mirrors Fix 8 for fees): SUM() on zero rows yields NULL.
        get_grade_summary() must use COALESCE/NULLIF and return 0, not None.
        """
        # Use a non-existent student ID to guarantee zero rows
        result = database.get_grade_summary(999_999)
        assert result is not None, "get_grade_summary() must never return None"
        assert result == 0 or result == Decimal("0")


class TestGradeInsertAndQuery:
    """insert_grade + get_student_grades + get_grade_summary correctness."""

    def _insert(self, stud_id, subject, marks_obtained, max_marks=100.0,
                exam_type="Internal", semester=3, recorded_by=1):
        database.insert_grade({
            "stud_id":        stud_id,
            "subject":        subject,
            "exam_type":      exam_type,
            "marks_obtained": Decimal(str(marks_obtained)),
            "max_marks":      Decimal(str(max_marks)),
            "semester":       semester,
            "recorded_by":    recorded_by,
        })

    def test_insert_two_grades_both_returned(self, db):
        """Both inserted grades must appear in get_student_grades()."""
        stud_id = db["linked_pk"]
        recorded_by = db["users"]["admin"]["id"]

        before = database.get_student_grades(stud_id)
        self._insert(stud_id, "Math",    80, recorded_by=recorded_by)
        self._insert(stud_id, "English", 30, recorded_by=recorded_by)

        after = database.get_student_grades(stud_id)
        assert len(after) == len(before) + 2

    def test_passing_grade_percentage_correct(self, db):
        stud_id = db["linked_pk"]
        recorded_by = db["users"]["admin"]["id"]

        self._insert(stud_id, "Physics", 75, max_marks=100, recorded_by=recorded_by)

        grades = database.get_student_grades(stud_id)
        physics = next((g for g in grades if g["subject"] == "Physics"), None)
        assert physics is not None

        pct = float(physics["marks_obtained"]) / float(physics["max_marks"]) * 100
        assert abs(pct - 75.0) < 0.01, f"Expected ~75%, got {pct}"

    def test_failing_grade_percentage_correct(self, db):
        stud_id = db["linked_pk"]
        recorded_by = db["users"]["admin"]["id"]

        self._insert(stud_id, "Chemistry", 20, max_marks=100, recorded_by=recorded_by)

        grades = database.get_student_grades(stud_id)
        chem = next((g for g in grades if g["subject"] == "Chemistry"), None)
        assert chem is not None

        pct = float(chem["marks_obtained"]) / float(chem["max_marks"]) * 100
        assert pct < 40.0, f"Chemistry (20/100) should be failing, got {pct}%"

    def test_grade_summary_matches_combined_ratio(self, db):
        """
        Insert two grades with known marks and verify the summary percentage
        matches SUM(marks_obtained) / SUM(max_marks) * 100 exactly.
        """
        # Use other_pk for isolation (so prior test data doesn't skew result)
        stud_id = db["other_pk"]
        recorded_by = db["users"]["admin"]["id"]

        # Insert fresh, known grades
        self._insert(stud_id, "SubjectA", 60, max_marks=100, recorded_by=recorded_by)
        self._insert(stud_id, "SubjectB", 40, max_marks=100, recorded_by=recorded_by)

        summary = database.get_grade_summary(stud_id)
        assert summary is not None

        # All grades for other_pk (may include earlier inserts by other tests)
        grades = database.get_student_grades(stud_id)
        total_obtained = sum(float(g["marks_obtained"]) for g in grades)
        total_max      = sum(float(g["max_marks"])      for g in grades)
        expected_pct   = (total_obtained / total_max) * 100.0

        assert abs(float(summary) - expected_pct) < 0.1, (
            f"get_grade_summary returned {summary}, expected ~{expected_pct:.2f}"
        )

    def test_grade_summary_never_none_with_grades(self, db):
        """Even when grades exist, get_grade_summary must never return None."""
        stud_id = db["linked_pk"]
        recorded_by = db["users"]["admin"]["id"]
        self._insert(stud_id, "History", 55, recorded_by=recorded_by)

        result = database.get_grade_summary(stud_id)
        assert result is not None

    def test_grades_ordered_by_semester_then_subject(self, db):
        """get_student_grades must return rows ordered semester ASC, subject ASC."""
        # Use a fresh student to get clean ordering
        stud_id = db["other_pk"]
        recorded_by = db["users"]["admin"]["id"]

        # Clear existing from this student by checking current count
        before = database.get_student_grades(stud_id)

        self._insert(stud_id, "Zebra",   50, semester=2, recorded_by=recorded_by)
        self._insert(stud_id, "Apple",   60, semester=2, recorded_by=recorded_by)
        self._insert(stud_id, "Mango",   70, semester=1, recorded_by=recorded_by)

        after = database.get_student_grades(stud_id)
        # The new rows we care about
        new_rows = after[len(before):]

        # Find Mango — should come before Zebra and Apple (semester 1 < semester 2)
        subjects_in_order = [g["subject"] for g in after]
        mango_idx = next(i for i, g in enumerate(after) if g["subject"] == "Mango" and g["semester"] == 1)
        apple_idx = next(i for i, g in enumerate(after) if g["subject"] == "Apple" and g["semester"] == 2)
        zebra_idx = next(i for i, g in enumerate(after) if g["subject"] == "Zebra" and g["semester"] == 2)

        assert mango_idx < apple_idx, "Semester 1 (Mango) should come before semester 2 (Apple)"
        assert mango_idx < zebra_idx, "Semester 1 (Mango) should come before semester 2 (Zebra)"
        assert apple_idx < zebra_idx, "Apple should come before Zebra (alphabetical within same semester)"
