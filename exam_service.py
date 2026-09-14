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
        obt_val = row.get("obtained_marks")
        obt = float(obt_val) if obt_val is not None else 0.0

        # Resolve max_marks: check row first, then exam configuration
        mx_val = row.get("max_marks")
        if mx_val is None and isinstance(exam, dict):
            mx_val = exam.get("max_marks")
        mx = float(mx_val) if mx_val is not None else 100.0

        # Resolve pass_marks: check row first, then exam configuration
        pass_val = row.get("pass_marks")
        if pass_val is None and isinstance(exam, dict):
            pass_val = exam.get("pass_marks")

        # Explicit check: if pass_marks is specified (including 0 or 0.0), respect it.
        # If pass_marks is unspecified in row & exam, use relative 40% of max_marks.
        if pass_val is not None:
            pass_cutoff = float(pass_val)
        else:
            pass_cutoff = 40.0 if mx == 100.0 else (0.4 * mx)

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


def compute_academic_transcript(student: dict, raw_history: list) -> dict:
    """
    Calculates full academic transcript data for a student structured
    semester-wise and exam-wise.

    Reuses existing exam calculation logic without duplicating marks rules.
    """
    if raw_history is None:
        raw_history = []

    semesters = {}
    total_exams = 0
    total_subjects = 0
    total_obtained = 0.0
    total_max = 0.0
    passed_subjects = 0
    failed_subjects = 0

    for item in raw_history:
        exam = item.get("exam", {})
        marks = item.get("marks", [])
        
        # Calculate summary for this exam
        summary = compute_student_result_summary(student, exam, marks)
        
        sem_val = exam.get("semester", 1)
        try:
            sem_key = int(sem_val)
        except (ValueError, TypeError):
            sem_key = sem_val

        if sem_key not in semesters:
            semesters[sem_key] = {
                "semester": sem_key,
                "exams": []
            }

        semesters[sem_key]["exams"].append({
            "exam": exam,
            "marks": marks,
            "summary": summary
        })

        total_exams += 1
        for sub in summary.get("subject_results", []):
            total_subjects += 1
            total_obtained += sub.get("obtained_marks", 0.0)
            total_max += sub.get("max_marks", 0.0)
            if sub.get("status") == "PASS":
                passed_subjects += 1
            else:
                failed_subjects += 1

    # Sort semester keys numerically if possible, otherwise string sort
    def sem_sort_key(k):
        try:
            return (0, int(k))
        except (ValueError, TypeError):
            return (1, str(k))

    ordered_semesters = sorted(list(semesters.keys()), key=sem_sort_key)

    has_data = total_subjects > 0
    if has_data:
        overall_pct = (total_obtained / total_max * 100.0) if total_max > 0 else 0.0
        overall_result = "PASS" if failed_subjects == 0 else "FAIL"
        overall_grade = calculate_subject_grade(overall_pct) if overall_result == "PASS" else "F"
    else:
        overall_pct = 0.0
        overall_result = "N/A"
        overall_grade = "N/A"

    overall_summary = {
        "total_semesters": len(semesters),
        "total_exams": total_exams,
        "total_subjects": total_subjects,
        "total_obtained": round(total_obtained, 2),
        "total_max": round(total_max, 2),
        "overall_percentage": round(overall_pct, 2),
        "passed_subjects": passed_subjects,
        "failed_subjects": failed_subjects,
        "overall_result": overall_result,
        "overall_grade": overall_grade,
        "has_data": has_data
    }

    return {
        "student": student or {},
        "semesters": semesters,
        "ordered_semesters": ordered_semesters,
        "overall": overall_summary
    }

