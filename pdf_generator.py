"""
pdf_generator.py — Pure-Python PDF generation using ReportLab.
Handles Bonafide Certificate and Dashboard PDF exports.
"""

from io import BytesIO
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY


TERRACOTTA = colors.HexColor("#A9714F")
DARK_TEXT  = colors.HexColor("#111111")
MUTED_TEXT = colors.HexColor("#555555")
BG_LIGHT   = colors.HexColor("#F8F7F4")
BORDER_CLR = colors.HexColor("#DDDDDD")


def generate_bonafide_pdf(institution_name, student):
    """
    Generates a Bonafide Certificate PDF for a single student.
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

    # Custom paragraph styles
    inst_style = ParagraphStyle(
        'InstHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        textColor=TERRACOTTA,
        alignment=TA_CENTER,
        spaceAfter=6,
    )

    title_style = ParagraphStyle(
        'CertTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=DARK_TEXT,
        alignment=TA_CENTER,
        spaceAfter=24,
    )

    body_style = ParagraphStyle(
        'CertBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=12,
        leading=20,
        textColor=DARK_TEXT,
        alignment=TA_JUSTIFY,
        spaceAfter=20,
    )

    meta_style = ParagraphStyle(
        'CertMeta',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=11,
        leading=16,
        textColor=MUTED_TEXT,
        alignment=TA_LEFT,
    )

    sig_style = ParagraphStyle(
        'CertSig',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=16,
        textColor=DARK_TEXT,
        alignment=TA_RIGHT,
    )

    today_str = datetime.now().strftime("%B %d, %Y")

    student_name = student.get("student_name", "")
    student_id   = student.get("student_id", "")
    course       = student.get("course", "")
    semester     = student.get("semester", "")

    story = []

    # Institution Header
    story.append(Paragraph(institution_name.upper(), inst_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=TERRACOTTA, spaceAfter=20, spaceBefore=4))

    # Certificate Title
    story.append(Paragraph("BONAFIDE CERTIFICATE", title_style))
    story.append(Spacer(1, 15))

    # Certificate Body Text
    cert_text = (
        f"This is to certify that <b>{student_name}</b> (Roll No. <b>{student_id}</b>) "
        f"is a bonafide student of <b>{course}</b>, currently enrolled in Semester <b>{semester}</b> "
        f"in our institution, as per our official institutional records."
    )
    story.append(Paragraph(cert_text, body_style))
    story.append(Spacer(1, 15))

    cert_text_extra = (
        "This certificate is issued upon the request of the student for official purposes."
    )
    story.append(Paragraph(cert_text_extra, body_style))
    story.append(Spacer(1, 50))

    # Date and Signature Table
    table_data = [
        [
            Paragraph(f"<b>Date of Issue:</b> {today_str}", meta_style),
            Paragraph("____________________________<br/><b>Registrar / Principal</b>", sig_style)
        ]
    ]

    sig_table = Table(table_data, colWidths=[250, 254])
    sig_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
    ]))

    story.append(sig_table)

    doc.build(story)
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
