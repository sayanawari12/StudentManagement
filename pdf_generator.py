import os
from io import BytesIO
from datetime import datetime
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


TERRACOTTA = colors.HexColor("#A9714F")
DARK_TEXT  = colors.HexColor("#111111")
MUTED_TEXT = colors.HexColor("#555555")
BG_LIGHT   = colors.HexColor("#F8F7F4")
BORDER_CLR = colors.HexColor("#DDDDDD")

_FONT_REGISTERED = False


def _register_cursive_font():
    global _FONT_REGISTERED
    if not _FONT_REGISTERED:
        font_path = os.path.join(os.path.dirname(__file__), "static", "fonts", "DancingScript-Variable.ttf")
        if os.path.exists(font_path):
            pdfmetrics.registerFont(TTFont("DancingScript", font_path))
            _FONT_REGISTERED = True


def _draw_certificate_border(canvas, doc):
    canvas.saveState()
    # Outer thin border frame (A4 portrait)
    canvas.setLineWidth(1.5)
    canvas.setStrokeColor(colors.HexColor("#222222"))
    canvas.rect(30, 30, doc.pagesize[0] - 60, doc.pagesize[1] - 60)
    # Inner accent border line
    canvas.setLineWidth(0.5)
    canvas.setStrokeColor(colors.HexColor("#555555"))
    canvas.rect(34, 34, doc.pagesize[0] - 68, doc.pagesize[1] - 68)
    canvas.restoreState()


def generate_bonafide_pdf(institution_name, student):
    """
    Generates a professional Bonafide Certificate PDF for a single student.
    Matches exact college certificate structure with Helvetica standard typography
    and DancingScript cursive font exclusively for Student Name and Principal Signature.
    Returns a BytesIO buffer containing the PDF bytes.
    """
    _register_cursive_font()

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=54,
        leftMargin=54,
        topMargin=54,
        bottomMargin=54,
    )

    styles = getSampleStyleSheet()

    # Cursive font fallback
    cursive_font = "DancingScript" if _FONT_REGISTERED else "Helvetica-Bold"

    # Header & Typography Styles
    college_name_style = ParagraphStyle(
        'CollegeHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=17,
        leading=21,
        textColor=DARK_TEXT,
        alignment=TA_CENTER,
        spaceAfter=4,
    )

    college_location_style = ParagraphStyle(
        'CollegeLocation',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=11,
        leading=14,
        textColor=DARK_TEXT,
        alignment=TA_CENTER,
        spaceAfter=2,
    )

    college_affiliation_style = ParagraphStyle(
        'CollegeAffiliation',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=13,
        textColor=MUTED_TEXT,
        alignment=TA_CENTER,
        spaceAfter=12,
    )

    cert_title_style = ParagraphStyle(
        'CertTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=19,
        leading=23,
        textColor=DARK_TEXT,
        alignment=TA_CENTER,
        spaceAfter=12,
    )

    meta_left_style = ParagraphStyle(
        'MetaLeft',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=11,
        leading=14,
        textColor=DARK_TEXT,
        alignment=TA_LEFT,
    )

    meta_right_style = ParagraphStyle(
        'MetaRight',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=11,
        leading=14,
        textColor=DARK_TEXT,
        alignment=TA_RIGHT,
    )

    body_style = ParagraphStyle(
        'CertBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=12,
        leading=22,
        textColor=DARK_TEXT,
        alignment=TA_JUSTIFY,
        spaceAfter=14,
    )

    place_style = ParagraphStyle(
        'CertPlace',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=11,
        leading=15,
        textColor=DARK_TEXT,
        alignment=TA_LEFT,
        spaceBefore=10,
        spaceAfter=35,
    )

    sig_style = ParagraphStyle(
        'CertSigStyle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=11,
        leading=16,
        textColor=DARK_TEXT,
        alignment=TA_LEFT,
    )

    # Dynamic Student Data Extraction
    student_name = student.get("student_name", "")
    student_id   = student.get("student_id", "")
    course       = student.get("course", "")
    semester     = student.get("semester", "")
    gender       = student.get("gender", "")
    pk_id        = student.get("id", 1)

    # Dynamic Pronouns & Salutation
    salutation   = "Mr." if gender == "Male" else ("Ms." if gender == "Female" else "Mr./Ms.")
    pronoun_subj = "He" if gender == "Male" else ("She" if gender == "Female" else "He/She")

    # Dynamic Dates & Certificate Number
    curr_date    = datetime.now()
    curr_year    = curr_date.year
    next_year_short = str(curr_year + 1)[-2:]
    academic_year = f"{curr_year}–{next_year_short}"
    issue_date   = curr_date.strftime("%d %B %Y")

    course_code  = "BCA" if "BCA" in str(course).upper() else "CERT"
    cert_no      = f"{course_code}/{curr_year}/{pk_id:03d}"

    story = []

    # 1. College Header — driven by institution_name parameter
    header_text = institution_name.upper() if institution_name else "YOUR COLLEGE NAME HERE"
    story.append(Paragraph(header_text, college_name_style))

    # Divider line 1
    story.append(HRFlowable(width="100%", thickness=1, color=DARK_TEXT, spaceBefore=8, spaceAfter=14))

    # 2. Bonafide Certificate Title
    story.append(Paragraph("BONAFIDE CERTIFICATE", cert_title_style))

    # Divider line 2
    story.append(HRFlowable(width="100%", thickness=1, color=DARK_TEXT, spaceBefore=0, spaceAfter=18))

    # 3. Certificate Number & Date Line
    meta_table = Table([
        [
            Paragraph(f"Certificate No.: <b>{cert_no}</b>", meta_left_style),
            Paragraph(f"Date: <b>{issue_date}</b>", meta_right_style)
        ]
    ], colWidths=[240, 247.27])
    meta_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 18))

    # 4. Certificate Body Paragraphs
    salut_prefix = f"{salutation} " if salutation else ""
    p1 = (
        f"This is to certify that {salut_prefix}"
        f"<font fontName=\"{cursive_font}\" size=\"20\"><b>{student_name}</b></font>, "
        f"Roll No. <b>{student_id}</b>, is a bonafide student of <b>{course}</b> in our institution."
    )
    story.append(Paragraph(p1, body_style))

    p2 = (
        f"{pronoun_subj} is currently studying in <b>Semester {semester}</b> during the "
        f"Academic Year <b>{academic_year}</b>, as per the official records of the institution."
    )
    story.append(Paragraph(p2, body_style))

    p3 = "This certificate is issued at the request of the student for official purposes."
    story.append(Paragraph(p3, body_style))

    # 5. Place
    story.append(Paragraph("Place: Wani, Maharashtra", place_style))

    # 6. Principal Signature Section (Bottom Right)
    sig_cell = (
        "______________________<br/><br/>"
        "Principal<br/>"
        "(Authorised Signatory)"
    )
    sig_table = Table([
        ["", Paragraph(sig_cell, sig_style)]
    ], colWidths=[240, 247.27])
    sig_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(sig_table)

    doc.build(story, onFirstPage=_draw_certificate_border)
    buffer.seek(0)
    return buffer


def generate_dashboard_pdf(institution_name, stats, today_date_str):
    """
    Generates a Dashboard Overview Report PDF mirroring the live dashboard stats.
    Returns a BytesIO buffer containing the PDF bytes.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=54,
        leftMargin=54,
        topMargin=54,
        bottomMargin=54,
    )

    styles = getSampleStyleSheet()

    header_style = ParagraphStyle(
        'DashHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=16,
        leading=20,
        textColor=TERRACOTTA,
        alignment=TA_LEFT,
        spaceAfter=4,
    )

    title_style = ParagraphStyle(
        'DashTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        textColor=DARK_TEXT,
        alignment=TA_LEFT,
        spaceAfter=4,
    )

    meta_style = ParagraphStyle(
        'DashMeta',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=MUTED_TEXT,
        alignment=TA_LEFT,
        spaceAfter=16,
    )

    section_style = ParagraphStyle(
        'DashSection',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=17,
        textColor=DARK_TEXT,
        spaceBefore=14,
        spaceAfter=8,
    )

    card_label_style = ParagraphStyle(
        'CardLabel',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=12,
        textColor=MUTED_TEXT,
        alignment=TA_CENTER,
    )

    card_val_style = ParagraphStyle(
        'CardVal',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=16,
        leading=20,
        textColor=TERRACOTTA,
        alignment=TA_CENTER,
    )

    cell_style = ParagraphStyle(
        'Cell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=DARK_TEXT,
        alignment=TA_LEFT,
    )

    cell_bold_style = ParagraphStyle(
        'CellBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=14,
        textColor=DARK_TEXT,
        alignment=TA_LEFT,
    )

    story = []

    # Header
    story.append(Paragraph(institution_name.upper(), header_style))
    story.append(Paragraph("Dashboard Overview Report", title_style))
    story.append(Paragraph(f"Generated on {today_date_str}", meta_style))
    story.append(HRFlowable(width="100%", thickness=1, color=TERRACOTTA, spaceAfter=16, spaceBefore=0))

    # Summary Stats Cards (2x2 grid table)
    tot_students = stats.get("total_students", 0)
    tot_bca      = stats.get("total_bca", 0)
    att_today    = stats.get("attendance_today", 0)
    tot_dues     = stats.get("total_dues", 0)

    card_data = [
        [
            [
                Paragraph("NO. 01 — TOTAL STUDENTS", card_label_style),
                Spacer(1, 4),
                Paragraph(str(tot_students), card_val_style)
            ],
            [
                Paragraph("NO. 02 — BCA ENROLLED", card_label_style),
                Spacer(1, 4),
                Paragraph(str(tot_bca), card_val_style)
            ]
        ],
        [
            [
                Paragraph("NO. 03 — ATTENDANCE TODAY", card_label_style),
                Spacer(1, 4),
                Paragraph(str(att_today), card_val_style)
            ],
            [
                Paragraph("NO. 04 — TOTAL DUES OUTSTANDING", card_label_style),
                Spacer(1, 4),
                Paragraph(f"Rs. {tot_dues:,.2f}" if isinstance(tot_dues, (int, float)) or hasattr(tot_dues, 'as_tuple') else f"Rs. {tot_dues}", card_val_style)
            ]
        ]
    ]

    cards_table = Table(card_data, colWidths=[246, 246])
    cards_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), BG_LIGHT),
        ('BOX', (0, 0), (-1, -1), 0.5, BORDER_CLR),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, BORDER_CLR),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
    ]))

    story.append(cards_table)
    story.append(Spacer(1, 16))

    # Semester Breakdown Section
    story.append(Paragraph("Semester Breakdown", section_style))

    sem_counts = stats.get("semester_counts", [])
    table_rows = [
        [Paragraph("<b>Semester</b>", cell_bold_style), Paragraph("<b>Student Count</b>", cell_bold_style)]
    ]

    if sem_counts:
        for row in sem_counts:
            sem_num = row.get("semester", "-")
            count   = row.get("total", 0)
            table_rows.append([
                Paragraph(f"Semester {sem_num}", cell_style),
                Paragraph(str(count), cell_style)
            ])
    else:
        table_rows.append([Paragraph("No student data available", cell_style), Paragraph("0", cell_style)])

    sem_table = Table(table_rows, colWidths=[250, 242])
    sem_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), BG_LIGHT),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('LINEBELOW', (0, 0), (-1, 0), 1, TERRACOTTA),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, BORDER_CLR),
        ('BOX', (0, 0), (-1, -1), 0.5, BORDER_CLR),
    ]))

    story.append(sem_table)

    doc.build(story)
    buffer.seek(0)
    return buffer
