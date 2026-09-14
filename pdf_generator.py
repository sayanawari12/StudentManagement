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


def generate_bonafide_pdf(institution_name, student,
                          institution_location="", institution_affiliation=""):
    """
    Generates a professional Bonafide Certificate PDF for a single student.
    Matches exact college certificate structure with Helvetica standard typography
    and DancingScript cursive font exclusively for Student Name and Principal Signature.

    Args:
        institution_name (str): College / institute name shown at the top.
        student (dict): Student record from the database (must contain student_name,
                        student_id, course, semester; gender is optional).
        institution_location (str): Address line, e.g. "Wani, Dist. Yavatmal…"
        institution_affiliation (str): Affiliation line shown below the address.

    Returns:
        BytesIO: Buffer containing the generated PDF bytes.
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
    academic_year = f"{curr_year}\u2013{next_year_short}"
    issue_date   = curr_date.strftime("%d %B %Y")

    course_code  = "BCA" if "BCA" in str(course).upper() else "CERT"
    cert_no      = f"{course_code}/{curr_year}/{pk_id:03d}"

    story = []

    # 1. College Header — driven by institution_name parameter
    header_text = institution_name.upper() if institution_name else "YOUR COLLEGE NAME HERE"
    story.append(Paragraph(header_text, college_name_style))

    # 1a. Optional location sub-line
    if institution_location:
        story.append(Paragraph(institution_location, college_location_style))

    # 1b. Optional affiliation sub-line
    if institution_affiliation:
        story.append(Paragraph(institution_affiliation, college_affiliation_style))

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


# ---------------------------------------------------------------------------
# ID Card PDF  (CR80 size: 85.6 mm × 54 mm ≈ 242.6 pt × 153.1 pt)
# ---------------------------------------------------------------------------

# CR80 dimensions in points (1 pt = 1/72 inch; 1 mm = 2.8346 pt)
_CR80_W = 85.6 * 2.8346   # ≈ 242.6 pt
_CR80_H = 54.0 * 2.8346   # ≈ 153.1 pt

# Accent colours (reuse module-level constants where possible)
_ID_ACCENT      = colors.HexColor("#A9714F")   # terracotta — matches CSS :root --accent
_ID_ACCENT_DARK = colors.HexColor("#7A4E35")
_ID_WHITE       = colors.white
_ID_DARK        = colors.HexColor("#111111")
_ID_MUTED       = colors.HexColor("#555555")
_ID_LIGHT_BG    = colors.HexColor("#F8F7F4")
_ID_BORDER      = colors.HexColor("#222222")


def _draw_id_card_frame(canvas, doc):
    """Draw the ID card outer double border and header accent band."""
    w, h = _CR80_W, _CR80_H
    margin = 3

    canvas.saveState()

    # Outer border
    canvas.setLineWidth(1.0)
    canvas.setStrokeColor(_ID_BORDER)
    canvas.rect(margin, margin, w - 2 * margin, h - 2 * margin)

    # Inner border (inset 2 pt)
    canvas.setLineWidth(0.4)
    canvas.setStrokeColor(_ID_MUTED)
    canvas.rect(margin + 2, margin + 2, w - 2 * (margin + 2), h - 2 * (margin + 2))

    # Header accent band (top strip)
    band_h = 30
    canvas.setFillColor(_ID_ACCENT)
    canvas.setStrokeColor(_ID_ACCENT)
    canvas.rect(margin, h - margin - band_h, w - 2 * margin, band_h, fill=1, stroke=0)

    # Thin separator below header band
    canvas.setLineWidth(0.6)
    canvas.setStrokeColor(_ID_ACCENT_DARK)
    canvas.line(margin, h - margin - band_h, w - margin, h - margin - band_h)

    canvas.restoreState()


def _qr_image_flowable(data_str, size_pt):
    """
    Generate a QR code for *data_str* and return a ReportLab Image flowable
    sized to *size_pt* × *size_pt* points.  Requires the 'qrcode[pil]' package
    which is already listed in requirements.txt.
    """
    import qrcode as qr_lib
    from PIL import Image as PilImage
    from reportlab.platypus import Image as RLImage

    qr = qr_lib.QRCode(
        version=None,
        error_correction=qr_lib.constants.ERROR_CORRECT_M,
        box_size=12,
        border=3,
    )
    qr.add_data(data_str)
    qr.make(fit=True)
    pil_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    img_buf = BytesIO()
    pil_img.save(img_buf, format="PNG")
    img_buf.seek(0)
    return RLImage(img_buf, width=size_pt, height=size_pt)


def resolve_student_photo_path(student, root_dir=None):
    """
    Returns absolute file path to the student's photo image:
    1. If student has 'photo' column and file exists on disk -> return custom photo path.
    2. Else check student's 'gender' field:
       - If gender is 'female' / 'girl' / 'f' -> static/images/id-card-default-female.jpg
       - Else -> static/images/id-card-default-male.jpg
    """
    if root_dir is None:
        root_dir = os.path.dirname(os.path.abspath(__file__))

    custom_photo = student.get("photo")
    if custom_photo and isinstance(custom_photo, str) and custom_photo.strip():
        p = custom_photo.strip().lstrip("/")
        full = os.path.join(root_dir, p) if not os.path.isabs(custom_photo) else custom_photo
        if os.path.isfile(full):
            return full

    gender = str(student.get("gender") or "").strip().lower()
    if gender in ("female", "girl", "f"):
        filename = "id-card-default-female.jpg"
    else:
        filename = "id-card-default-male.jpg"

    default_path = os.path.join(root_dir, "static", "images", filename)
    if os.path.isfile(default_path):
        return default_path
    return None


def generate_id_card_pdf(institution_name, student,
                         verification_url="",
                         institution_location="",
                         institution_affiliation=""):
    """
    Generates a professional CR80-sized (85.6 × 54 mm) Student ID Card PDF.

    Args:
        institution_name (str): College name — printed in the header band.
        student (dict): Student record from the database.
        verification_url (str): URL encoded in the QR code.
        institution_location (str): Address line shown under the college name.
        institution_affiliation (str): Affiliation line.

    Returns:
        BytesIO: Buffer containing the PDF bytes.
    """
    buffer = BytesIO()

    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.lib.utils import ImageReader

    c = rl_canvas.Canvas(buffer, pagesize=(_CR80_W, _CR80_H))

    # ── 1. Structural frame & background ─────────────────────────────────
    _draw_id_card_frame(c, None)

    card_w, card_h = _CR80_W, _CR80_H
    margin     = 5
    band_h     = 30
    content_y  = card_h - margin - band_h

    # ── 2. Header band text ───────────────────────────────────────────────
    c.setFillColor(_ID_WHITE)
    inst_text = (institution_name or "SUSHGANGA INSTITUTE, WANI").upper()
    c.setFont("Helvetica-Bold", 6.5)
    c.drawCentredString(card_w / 2, card_h - margin - 10, inst_text)

    if institution_location:
        c.setFont("Helvetica-Oblique", 4.2)
        c.drawCentredString(card_w / 2, card_h - margin - 17, institution_location)

    c.setFont("Helvetica-Bold", 4.8)
    c.drawCentredString(card_w / 2, card_h - margin - 25, "STUDENT  ID  CARD")

    # ── 3. Left column — Student Photo & Status Badge ─────────────────────
    photo_x = margin + 3
    photo_w = 40
    photo_h = 50
    photo_y = content_y - photo_h - 6

    photo_path = resolve_student_photo_path(student)
    if photo_path and os.path.isfile(photo_path):
        try:
            photo_img = ImageReader(photo_path)
            c.drawImage(photo_img, photo_x, photo_y, width=photo_w, height=photo_h, preserveAspectRatio=True, anchor='c')
            # Outer border for photo
            c.setLineWidth(0.6)
            c.setStrokeColor(_ID_ACCENT)
            c.rect(photo_x, photo_y, photo_w, photo_h, fill=0, stroke=1)
        except Exception:
            c.setFillColor(_ID_LIGHT_BG)
            c.setStrokeColor(_ID_MUTED)
            c.rect(photo_x, photo_y, photo_w, photo_h, fill=1, stroke=1)
            c.setFillColor(_ID_MUTED)
            c.setFont("Helvetica", 4)
            c.drawCentredString(photo_x + photo_w / 2, photo_y + photo_h / 2, "PHOTO")
    else:
        c.setFillColor(_ID_LIGHT_BG)
        c.setStrokeColor(_ID_MUTED)
        c.rect(photo_x, photo_y, photo_w, photo_h, fill=1, stroke=1)
        c.setFillColor(_ID_MUTED)
        c.setFont("Helvetica", 4)
        c.drawCentredString(photo_x + photo_w / 2, photo_y + photo_h / 2, "PHOTO")

    # Status Pill Badge below Photo
    status_w = photo_w
    status_h = 8
    status_y = photo_y - 10
    c.setFillColor(colors.HexColor("#EBF5EC"))
    c.setStrokeColor(colors.HexColor("#3A7D44"))
    c.setLineWidth(0.4)
    c.rect(photo_x, status_y, status_w, status_h, fill=1, stroke=1)
    c.setFillColor(colors.HexColor("#3A7D44"))
    c.setFont("Helvetica-Bold", 3.8)
    c.drawCentredString(photo_x + status_w / 2, status_y + 2.5, "ACTIVE STUDENT")

    # ── 4. Middle column — Student Details ────────────────────────────────
    detail_x   = photo_x + photo_w + 6
    detail_top = content_y - 6

    student_name  = str(student.get("student_name") or "").strip()
    student_id    = str(student.get("student_id")   or "").strip()
    course        = str(student.get("course")        or "").strip()
    semester      = str(student.get("semester")      or "").strip()
    gender        = str(student.get("gender")        or "").strip()

    curr_year       = datetime.now().year
    next_year_short = str(curr_year + 1)[-2:]
    acad_year       = f"{curr_year}\u2013{next_year_short}"

    # Name
    c.setFillColor(_ID_DARK)
    c.setFont("Helvetica-Bold", 7.5)
    disp_name = student_name[:24] + "\u2026" if len(student_name) > 26 else student_name
    c.drawString(detail_x, detail_top, disp_name)

    # Key-value detail rows
    sem_str = f"Sem {semester}" if semester else ""
    rows = [
        ("Student ID", student_id),
        ("Course", course),
    ]
    if sem_str:
        rows.append(("Semester", sem_str))
    rows.append(("Acad. Year", acad_year))
    if gender:
        rows.append(("Gender", gender))

    row_y    = detail_top - 10
    line_gap = 8.5
    for label, value in rows:
        c.setFillColor(_ID_MUTED)
        c.setFont("Helvetica", 4.5)
        c.drawString(detail_x, row_y, label + ":")

        c.setFillColor(_ID_DARK)
        c.setFont("Helvetica-Bold", 4.8)
        disp_val = str(value)[:20] if len(str(value)) > 20 else str(value)
        c.drawString(detail_x + 36, row_y, disp_val)
        row_y -= line_gap

    # ── 5. Right column — QR code ─────────────────────────────────────────
    qr_size = 38
    qr_x    = card_w - margin - qr_size - 3
    qr_y    = content_y - qr_size - 8

    if verification_url:
        try:
            qr_flow = _qr_image_flowable(verification_url, qr_size)
            qr_flow.drawOn(c, qr_x, qr_y)
            c.setLineWidth(0.4)
            c.setStrokeColor(_ID_BORDER)
            c.rect(qr_x - 1, qr_y - 1, qr_size + 2, qr_size + 2, fill=0, stroke=1)
        except Exception:
            c.setFillColor(_ID_LIGHT_BG)
            c.setStrokeColor(_ID_MUTED)
            c.rect(qr_x, qr_y, qr_size, qr_size, fill=1, stroke=1)

    c.setFillColor(_ID_MUTED)
    c.setFont("Helvetica-Bold", 3.6)
    c.drawCentredString(qr_x + qr_size / 2, qr_y - 6, "SCAN TO VERIFY")

    # ── 6. Footer strip ───────────────────────────────────────────────────
    footer_y = margin + 3
    c.setFillColor(_ID_MUTED)
    c.setFont("Helvetica", 3.8)
    footer_text = institution_affiliation or "Sushganga Institute, Wani • Official Student Identity Document"
    if len(footer_text) > 65:
        footer_text = footer_text[:63] + "\u2026"
    c.drawCentredString(card_w / 2, footer_y, footer_text)

    c.setStrokeColor(_ID_BORDER)
    c.setLineWidth(0.3)
    c.line(margin, footer_y + 6, card_w - margin, footer_y + 6)

    c.save()
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


def generate_marksheet_pdf(*args, **kwargs):
    """
    Generates a professional downloadable Marksheet / Result PDF for a student.
    Flexible signature:
      generate_marksheet_pdf(student, exam, marks, result_summary=...)
      or
      generate_marksheet_pdf(institution_name, student, exam, result_summary, ...)
    """
    institution_name = kwargs.get("institution_name") or "SUSHGANGA INSTITUTE, WANI"
    institution_location = kwargs.get("institution_location") or "Wani, Dist. Yavatmal, Maharashtra – 445304"
    institution_affiliation = kwargs.get("institution_affiliation") or "Affiliated to Sant Gadge Baba Amravati University, Amravati"

    student = kwargs.get("student")
    exam = kwargs.get("exam")
    marks = kwargs.get("marks")
    result_summary = kwargs.get("result_summary")

    if args:
        if isinstance(args[0], dict) and ("student_id" in args[0] or "student_name" in args[0] or "id" in args[0]):
            student = args[0]
            if len(args) > 1: exam = args[1]
            if len(args) > 2:
                if isinstance(args[2], list): marks = args[2]
                elif isinstance(args[2], dict): result_summary = args[2]
            if len(args) > 3 and isinstance(args[3], dict): result_summary = args[3]
        elif isinstance(args[0], str):
            institution_name = args[0]
            if len(args) > 1: student = args[1]
            if len(args) > 2: exam = args[2]
            if len(args) > 3: result_summary = args[3]

    if not isinstance(institution_name, str):
        institution_name = "SUSHGANGA INSTITUTE, WANI"

    if student is None: student = {}
    if exam is None: exam = {}
    if result_summary is None:
        import exam_service
        raw_list = marks if isinstance(marks, list) else []
        result_summary = exam_service.compute_student_result_summary(raw_list)

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'HeaderTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        alignment=TA_CENTER,
        textColor=TERRACOTTA,
    )
    subtitle_style = ParagraphStyle(
        'HeaderSub',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=9,
        leading=12,
        alignment=TA_CENTER,
        textColor=MUTED_TEXT,
    )
    doc_title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=18,
        alignment=TA_CENTER,
        textColor=DARK_TEXT,
        spaceAfter=12,
    )
    label_style = ParagraphStyle(
        'LabelStyle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=12,
        textColor=MUTED_TEXT,
    )
    val_style = ParagraphStyle(
        'ValStyle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=12,
        textColor=DARK_TEXT,
    )
    cell_head_style = ParagraphStyle(
        'CellHead',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=12,
        textColor=DARK_TEXT,
    )
    cell_body_style = ParagraphStyle(
        'CellBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=12,
        textColor=DARK_TEXT,
    )

    story = []

    # 1. Institution Header
    inst_title = (institution_name or "SUSHGANGA INSTITUTE, WANI").upper()
    story.append(Paragraph(inst_title, title_style))

    sub_lines = []
    if institution_location:
        sub_lines.append(institution_location)
    if institution_affiliation:
        sub_lines.append(institution_affiliation)
    if sub_lines:
        story.append(Paragraph(" &bull; ".join(sub_lines), subtitle_style))

    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=1.5, color=TERRACOTTA, spaceBefore=0, spaceAfter=12))

    # 2. Document Title
    exam_title = f"OFFICIAL MARKSHEET — {exam.get('exam_name', 'EXAMINATION')}"
    story.append(Paragraph(exam_title, doc_title_style))

    # 3. Student Details Block
    curr_year = datetime.now().year
    next_year_short = str(curr_year + 1)[-2:]
    acad_year = exam.get("academic_year") or f"{curr_year}\u2013{next_year_short}"

    details_data = [
        [Paragraph("Student Name:", label_style), Paragraph(str(student.get("student_name", "")), val_style),
         Paragraph("Student ID / Roll:", label_style), Paragraph(str(student.get("student_id", "")), val_style)],
        [Paragraph("Course:", label_style), Paragraph(str(student.get("course", "")), val_style),
         Paragraph("Semester:", label_style), Paragraph(f"Semester {student.get('semester', '')}", val_style)],
        [Paragraph("Exam Type:", label_style), Paragraph(str(exam.get("exam_type", "")), val_style),
         Paragraph("Academic Year:", label_style), Paragraph(str(acad_year), val_style)],
    ]

    details_table = Table(details_data, colWidths=[90, 170, 100, 160])
    details_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('BACKGROUND', (0, 0), (-1, -1), BG_LIGHT),
        ('BOX', (0, 0), (-1, -1), 0.5, BORDER_CLR),
    ]))
    story.append(details_table)
    story.append(Spacer(1, 14))

    # 4. Subject-wise Result Table
    table_data = [
        [
            Paragraph("<b>Subject Code</b>", cell_head_style),
            Paragraph("<b>Subject Name</b>", cell_head_style),
            Paragraph("<b>Max Marks</b>", cell_head_style),
            Paragraph("<b>Obtained Marks</b>", cell_head_style),
            Paragraph("<b>Percentage</b>", cell_head_style),
            Paragraph("<b>Grade</b>", cell_head_style),
            Paragraph("<b>Status</b>", cell_head_style),
        ]
    ]

    for item in result_summary.get("subject_results", []):
        status_clr = "#3A7D44" if item["status"] == "PASS" else "#9C3B2E"
        status_p = Paragraph(f"<font color='{status_clr}'><b>{item['status']}</b></font>", cell_body_style)
        table_data.append([
            Paragraph(item.get("subject_code", "-"), cell_body_style),
            Paragraph(item.get("subject_name", ""), cell_body_style),
            Paragraph(f"{item['max_marks']:.2f}", cell_body_style),
            Paragraph(f"{item['obtained_marks']:.2f}", cell_body_style),
            Paragraph(f"{item['percentage']:.1f}%", cell_body_style),
            Paragraph(item['grade'], cell_body_style),
            status_p,
        ])

    res_table = Table(table_data, colWidths=[75, 185, 55, 65, 55, 40, 45])
    res_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), BG_LIGHT),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('ALIGN', (2, 0), (-1, -1), 'CENTER'),
        ('LINEBELOW', (0, 0), (-1, 0), 1.2, TERRACOTTA),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, BORDER_CLR),
        ('BOX', (0, 0), (-1, -1), 0.5, BORDER_CLR),
    ]))
    story.append(res_table)
    story.append(Spacer(1, 14))

    # 5. Overall Summary Table
    overall_status = result_summary.get("overall_status", "FAIL")
    overall_clr = "#3A7D44" if overall_status == "PASS" else "#9C3B2E"
    overall_p = Paragraph(f"<font color='{overall_clr}'><b>{overall_status}</b></font>", cell_head_style)

    summary_data = [
        [
            Paragraph("Total Obtained", label_style),
            Paragraph(f"<b>{result_summary.get('total_obtained', 0):.2f} / {result_summary.get('total_max', 0):.2f}</b>", val_style),
            Paragraph("Percentage", label_style),
            Paragraph(f"<b>{result_summary.get('overall_percentage', 0):.2f}%</b>", val_style),
        ],
        [
            Paragraph("Overall Grade", label_style),
            Paragraph(f"<b>{result_summary.get('overall_grade', 'F')}</b>", val_style),
            Paragraph("Result Status", label_style),
            overall_p,
        ]
    ]

    summary_table = Table(summary_data, colWidths=[100, 160, 100, 160])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), BG_LIGHT),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('BOX', (0, 0), (-1, -1), 1, TERRACOTTA),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, BORDER_CLR),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 24))

    # 6. Issue Date & Signatures Block
    issue_date = datetime.now().strftime("%d %B %Y")
    sig_data = [
        [
            Paragraph(f"<b>Date of Issue:</b> {issue_date}", val_style),
            Paragraph("<b>Controller of Examinations</b>", ParagraphStyle('RightSig', parent=val_style, alignment=TA_RIGHT)),
        ]
    ]
    sig_table = Table(sig_data, colWidths=[260, 260])
    sig_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
    ]))
    story.append(sig_table)

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def generate_academic_transcript_pdf(student, transcript_data, institution_name=None, institution_location=None, institution_affiliation=None):
    """
    Generates a professional downloadable Academic Transcript / Cumulative Record PDF for a student.
    Returns bytes of PDF.
    """
    if institution_name is None: institution_name = "SUSHGANGA INSTITUTE, WANI"
    if institution_location is None: institution_location = "Wani, Dist. Yavatmal, Maharashtra – 445304"
    if institution_affiliation is None: institution_affiliation = "Affiliated to Sant Gadge Baba Amravati University, Amravati"

    if student is None: student = {}
    if transcript_data is None: transcript_data = {}

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'TranscriptInstTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        alignment=TA_CENTER,
        textColor=TERRACOTTA,
    )
    subtitle_style = ParagraphStyle(
        'TranscriptSub',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=9,
        leading=12,
        alignment=TA_CENTER,
        textColor=MUTED_TEXT,
    )
    doc_title_style = ParagraphStyle(
        'TranscriptDocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=18,
        alignment=TA_CENTER,
        textColor=DARK_TEXT,
        spaceAfter=12,
    )
    section_head_style = ParagraphStyle(
        'TranscriptSectionHead',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=14,
        textColor=TERRACOTTA,
        spaceBefore=10,
        spaceAfter=6,
    )
    sub_head_style = ParagraphStyle(
        'TranscriptSubHead',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9.5,
        leading=13,
        textColor=DARK_TEXT,
        spaceBefore=6,
        spaceAfter=4,
    )
    label_style = ParagraphStyle(
        'TLabelStyle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=12,
        textColor=MUTED_TEXT,
    )
    val_style = ParagraphStyle(
        'TValStyle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=12,
        textColor=DARK_TEXT,
    )
    tbl_hdr_style = ParagraphStyle(
        'TTblHdr',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11,
        textColor=DARK_TEXT,
        alignment=TA_CENTER,
    )
    tbl_body_style = ParagraphStyle(
        'TTblBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11,
        textColor=DARK_TEXT,
    )
    tbl_body_center = ParagraphStyle(
        'TTblBodyCenter',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11,
        textColor=DARK_TEXT,
        alignment=TA_CENTER,
    )

    story = []

    # 1. Institution Header
    inst_title = str(institution_name).upper()
    story.append(Paragraph(inst_title, title_style))

    sub_lines = []
    if institution_location: sub_lines.append(institution_location)
    if institution_affiliation: sub_lines.append(institution_affiliation)
    if sub_lines:
        story.append(Paragraph(" &bull; ".join(sub_lines), subtitle_style))

    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=1.5, color=TERRACOTTA, spaceBefore=0, spaceAfter=10))

    # 2. Document Title
    story.append(Paragraph("OFFICIAL ACADEMIC TRANSCRIPT", doc_title_style))

    # 3. Student Information Block
    curr_year = datetime.now().year
    next_year_short = str(curr_year + 1)[-2:]
    acad_year = student.get("academic_year") or f"{curr_year}\u2013{next_year_short}"

    details_data = [
        [Paragraph("Student Name:", label_style), Paragraph(str(student.get("student_name", "")), val_style),
         Paragraph("Student ID / Roll:", label_style), Paragraph(str(student.get("student_id", "")), val_style)],
        [Paragraph("Course:", label_style), Paragraph(str(student.get("course", "")), val_style),
         Paragraph("Current Semester:", label_style), Paragraph(f"Semester {student.get('semester', '')}", val_style)],
        [Paragraph("Academic Year:", label_style), Paragraph(str(acad_year), val_style),
         Paragraph("Date of Issue:", label_style), Paragraph(datetime.now().strftime("%d %B %Y"), val_style)],
    ]
    details_table = Table(details_data, colWidths=[90, 170, 90, 170])
    details_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), BG_LIGHT),
        ('BOX', (0, 0), (-1, -1), 1, TERRACOTTA),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, BORDER_CLR),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(details_table)
    story.append(Spacer(1, 10))

    overall = transcript_data.get("overall", {})
    semesters = transcript_data.get("semesters", {})
    ordered_semesters = transcript_data.get("ordered_semesters", [])

    # 4. Overall Academic Summary Card Table (if data exists)
    if overall.get("has_data"):
        story.append(Paragraph("CUMULATIVE ACADEMIC SUMMARY", section_head_style))
        ov_status = overall.get("overall_result", "N/A")
        ov_clr = "#3A7D44" if ov_status == "PASS" else ("#9C3B2E" if ov_status == "FAIL" else "#111111")
        ov_status_p = Paragraph(f"<font color='{ov_clr}'><b>{ov_status}</b></font>", val_style)

        summary_data = [
            [
                Paragraph("Total Semesters", label_style), Paragraph(str(overall.get("total_semesters", 0)), val_style),
                Paragraph("Total Exams", label_style), Paragraph(str(overall.get("total_exams", 0)), val_style),
            ],
            [
                Paragraph("Total Subjects", label_style), Paragraph(f"{overall.get('passed_subjects', 0)} Passed / {overall.get('total_subjects', 0)} Total", val_style),
                Paragraph("Marks Obtained", label_style), Paragraph(f"<b>{overall.get('total_obtained', 0):.2f} / {overall.get('total_max', 0):.2f}</b>", val_style),
            ],
            [
                Paragraph("Overall Percentage", label_style), Paragraph(f"<b>{overall.get('overall_percentage', 0):.2f}%</b>", val_style),
                Paragraph("Overall Grade", label_style), Paragraph(f"<b>{overall.get('overall_grade', 'N/A')}</b>", val_style),
            ],
            [
                Paragraph("Cumulative Status", label_style), ov_status_p,
                Paragraph("", label_style), Paragraph("", val_style),
            ]
        ]
        summary_table = Table(summary_data, colWidths=[100, 160, 100, 160])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), BG_LIGHT),
            ('BOX', (0, 0), (-1, -1), 1, TERRACOTTA),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, BORDER_CLR),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(summary_table)
        story.append(Spacer(1, 10))

    if not overall.get("has_data") or not ordered_semesters:
        no_data_p = Paragraph("<i>No academic records available yet.</i>", val_style)
        story.append(no_data_p)
    else:
        # 5. Semester-wise & Exam-wise Breakdown
        for sem_key in ordered_semesters:
            sem_data = semesters.get(sem_key, {})
            story.append(Paragraph(f"SEMESTER {sem_key}", section_head_style))

            exams_list = sem_data.get("exams", [])
            for ex_item in exams_list:
                ex = ex_item.get("exam", {})
                ex_summary = ex_item.get("summary", {})
                ex_name = ex.get("exam_name", "Examination")
                ex_year = ex.get("academic_year", "")
                ex_date = ex.get("created_at", "")
                if hasattr(ex_date, "strftime"):
                    ex_date = ex_date.strftime("%Y-%m-%d")

                sub_info = f"Exam: <b>{ex_name}</b>"
                if ex_year: sub_info += f" &bull; Academic Year: {ex_year}"
                if ex_date: sub_info += f" &bull; Date: {ex_date}"

                story.append(Paragraph(sub_info, sub_head_style))

                table_data = [
                    [
                        Paragraph("Subject Code", tbl_hdr_style),
                        Paragraph("Subject Name", tbl_hdr_style),
                        Paragraph("Max Marks", tbl_hdr_style),
                        Paragraph("Pass Marks", tbl_hdr_style),
                        Paragraph("Obtained", tbl_hdr_style),
                        Paragraph("%", tbl_hdr_style),
                        Paragraph("Grade", tbl_hdr_style),
                        Paragraph("Result", tbl_hdr_style),
                    ]
                ]

                for sub in ex_summary.get("subject_results", []):
                    st = sub.get("status", "FAIL")
                    st_clr = "#3A7D44" if st == "PASS" else "#9C3B2E"
                    res_p = Paragraph(f"<font color='{st_clr}'><b>{st}</b></font>", tbl_body_center)
                    code_val = sub.get("subject_code") or "--"

                    table_data.append([
                        Paragraph(str(code_val), tbl_body_style),
                        Paragraph(str(sub.get("subject_name", "")), tbl_body_style),
                        Paragraph(f"{sub.get('max_marks', 0):.2f}", tbl_body_center),
                        Paragraph(f"{sub.get('pass_marks', 0):.2f}", tbl_body_center),
                        Paragraph(f"{sub.get('obtained_marks', 0):.2f}", tbl_body_center),
                        Paragraph(f"{sub.get('percentage', 0):.2f}%", tbl_body_center),
                        Paragraph(str(sub.get("grade", "F")), tbl_body_center),
                        res_p,
                    ])

                col_widths = [65, 175, 45, 45, 45, 45, 40, 60]
                marks_table = Table(table_data, colWidths=col_widths)
                marks_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), BG_LIGHT),
                    ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('GRID', (0, 0), (-1, -1), 0.5, BORDER_CLR),
                    ('TOPPADDING', (0, 0), (-1, -1), 3),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ]))
                story.append(marks_table)

                ex_tot_obt = ex_summary.get("total_obtained", 0)
                ex_tot_mx = ex_summary.get("total_max", 0)
                ex_pct = ex_summary.get("percentage", 0)
                ex_status = ex_summary.get("overall_status", "FAIL")
                ex_grade = ex_summary.get("overall_grade", "F")

                summary_str = f"Exam Summary: Total <b>{ex_tot_obt:.2f} / {ex_tot_mx:.2f}</b> &bull; Percentage: <b>{ex_pct:.2f}%</b> &bull; Grade: <b>{ex_grade}</b> &bull; Result: <b>{ex_status}</b>"
                story.append(Paragraph(summary_str, val_style))
                story.append(Spacer(1, 8))

    story.append(Spacer(1, 14))

    sig_data = [
        [
            Paragraph(f"<b>Date:</b> {datetime.now().strftime('%d %B %Y')}", val_style),
            Paragraph("<b>Controller of Examinations</b>", ParagraphStyle('RightSig', parent=val_style, alignment=TA_RIGHT)),
        ]
    ]
    sig_table = Table(sig_data, colWidths=[260, 260])
    sig_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
    ]))
    story.append(sig_table)

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

