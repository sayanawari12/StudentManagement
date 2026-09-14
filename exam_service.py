"""
exam_service.py — Business logic and result calculation engine for the Exam & Result Management system.

Handles:
  - Subject grade and overall result calculations
  - Marks validation (range, non-negative, max limit)
  - Semester 3 subject specifications
  - Result summary formatting for HTML UI and PDF Marksheet generation
"""

# Mandated 6 subjects for Semester 1
SEMESTER_1_SUBJECTS = [
    {"code": "PSC101", "name": "Problem Solving Using C"},
    {"code": "MFCS102", "name": "Mathematics Foundation to Computer Science"},
    {"code": "CA103", "name": "Computer Architecture"},
    {"code": "EVS104", "name": "Environmental Studies (EVS)"},
    {"code": "IKS105", "name": "Indian Knowledge System (IKS)"},
    {"code": "ENG106", "name": "General English"},
]

# Mandated 6 subjects for Semester 2
SEMESTER_2_SUBJECTS = [
    {"code": "DS201", "name": "Data Structures"},
    {"code": "OOPC202", "name": "Object Oriented Programming Using C++ (OOP C++)"},
    {"code": "OOPJ203", "name": "Object Oriented Programming Using Java (OOP Java)"},
    {"code": "OS204", "name": "Operating System"},
    {"code": "WT205", "name": "Web Technology"},
    {"code": "IC206", "name": "Indian Constitution"},
]

# Mandated 6 subjects for Semester 3
SEMESTER_3_SUBJECTS = [
    {"code": "SE301", "name": "Software Engineering (SE)"},
    {"code": "DBMS302", "name": "Database Management System (DBMS)"},
    {"code": "PY303", "name": "Python"},
    {"code": "PS304", "name": "Probability and Statistics"},
    {"code": "FE305", "name": "Future Engineering"},
    {"code": "BDA306", "name": "Basics of Data Analytics Using Spreadsheet"},
]


def calculate_subject_grade(percentage: float) -> str:
    """
    Calculate letter grade based on percentage:
      90% - 100%: A+
      80% - 89.9%: A
      70% - 79.9%: B+
      60% - 69.9%: B
      50% - 59.9%: C
      40% - 49.9%: D
      < 40%:      F
    """
    if percentage >= 90.0:
        return "A+"
    elif percentage >= 80.0:
        return "A"
    elif percentage >= 70.0:
        return "B+"
    elif percentage >= 60.0:
        return "B"
    elif percentage >= 50.0:
        return "C"
    elif percentage >= 40.0:
        return "D"
    else:
        return "F"


def validate_marks_input(obtained_marks: float, max_marks: float) -> tuple:
    """
    Validates entered marks:
      - non-negative
      - max_marks > 0
      - obtained_marks <= max_marks
    Returns (is_valid, error_message, obtained_float, max_float).
    """
    try:
        obt = float(obtained_marks)
        mx = float(max_marks)
    except (ValueError, TypeError):
        return False, "Marks must be valid numbers.", 0.0, 0.0

    if obt < 0:
        return False, "Obtained marks cannot be negative.", obt, mx
    if mx <= 0:
        return False, "Maximum marks must be greater than zero.", obt, mx
    if obt > mx:
        return False, f"Obtained marks ({obt:.2f}) cannot exceed maximum marks ({mx:.2f}).", obt, mx

    return True, "", obt, mx


def validate_pass_marks(pass_marks, max_marks: float) -> tuple:
    """
    Validates a configured passing-marks value:
      - Must be a valid number
      - Must be >= 0
      - Must not exceed max_marks
    Returns (is_valid, error_message, pass_marks_float).
    """
    try:
        pm = float(pass_marks)
        mx = float(max_marks)
    except (ValueError, TypeError):
        return False, "Passing marks must be a valid number.", 0.0

    if mx <= 0:
        return False, "Maximum marks must be greater than zero.", 0.0
    if pm < 0:
        return False, "Passing marks cannot be negative.", pm
    if pm > mx:
        return False, (
            f"Passing marks ({pm:.2f}) cannot exceed maximum marks ({mx:.2f})."
        ), pm

    return True, "", pm


def validate_exam_marks_config(max_marks, pass_marks) -> tuple:
    """
    Validates an exam's configured maximum marks and passing marks:
      - max_marks must be a number > 0
      - pass_marks must be a number >= 0
      - pass_marks must not exceed max_marks
    Returns (is_valid, error_message, max_marks_float, pass_marks_float).
    """
    try:
        mx = float(max_marks)
    except (ValueError, TypeError):
        return False, "Maximum marks must be a valid number.", 0.0, 0.0

    try:
        pm = float(pass_marks)
    except (ValueError, TypeError):
        return False, "Passing marks must be a valid number.", mx, 0.0

    if mx <= 0:
        return False, "Maximum marks must be greater than zero.", mx, pm
    if pm < 0:
        return False, "Passing marks cannot be negative.", mx, pm
    if pm > mx:
        return False, f"Passing marks ({pm:.2f}) cannot exceed maximum marks ({mx:.2f}).", mx, pm

    return True, "", mx, pm



def compute_student_result_summary(*args, **kwargs) -> dict:
    """
    Calculates detailed result summary for a student's exam.
    Accepts:
      - compute_student_result_summary(raw_marks_list)
      - compute_student_result_summary(student, exam, raw_marks_list)
      - compute_student_result_summary(raw_marks_list=...)
    """
    student = kwargs.get("student")
    exam = kwargs.get("exam")
    raw_marks_list = kwargs.get("raw_marks_list") or kwargs.get("marks")

    if args:
        if len(args) == 1:
            raw_marks_list = args[0]
        elif len(args) == 3:
            student = args[0]
            exam = args[1]
            raw_marks_list = args[2]

    if raw_marks_list is None:
        raw_marks_list = []

    subject_results = []
    total_obtained = 0.0
    total_max = 0.0
    all_passed = True

    for row in raw_marks_list:
        obt = float(row.get("obtained_marks", 0.0))
        mx = float(row.get("max_marks", 100.0))
        pass_val = row.get("pass_marks")
        pass_cutoff = float(pass_val) if pass_val is not None else 40.0

        pct = (obt / mx * 100.0) if mx > 0 else 0.0
        grade = calculate_subject_grade(pct)
        # A student passes a subject if and only if their obtained marks meet the
        # configured passing mark for that subject. No secondary percentage gate.
        passed = obt >= pass_cutoff

        if not passed:
            all_passed = False

        total_obtained += obt
        total_max += mx

        subject_results.append({
            "subject_id": row.get("subject_id"),
            "subject_name": row.get("subject_name", "Subject"),
            "subject_code": row.get("subject_code", ""),
            "obtained_marks": obt,
            "max_marks": mx,
            "pass_marks": pass_cutoff,
            "percentage": round(pct, 2),
            "grade": grade,
            "status": "PASS" if passed else "FAIL",
        })

    overall_pct = (total_obtained / total_max * 100.0) if total_max > 0 else 0.0
    # Overall result: student must pass every individual subject (no hardcoded overall floor).
    overall_status = "PASS" if (all_passed and len(subject_results) > 0) else "FAIL"
    overall_grade = calculate_subject_grade(overall_pct) if overall_status == "PASS" else "F"

    return {
        "student": student,
        "exam": exam,
        "subject_results": subject_results,
        "total_obtained": round(total_obtained, 2),
        "total_max": round(total_max, 2),
        "percentage": round(overall_pct, 2),
        "overall_percentage": round(overall_pct, 2),
        "overall_grade": overall_grade,
        "overall_status": overall_status,
        "total_subjects": len(subject_results),
    }
