"""
tests/test_authorization.py — Deep Authorization, RBAC, and IDOR/BOLA security test matrix.

Tests:
  - Anonymous route protection
  - Student role permissions and IDOR/BOLA isolation
  - Teacher role permissions and Admin action protection
  - Admin full access
  - Document & PDF object-level ownership checks
"""

import io
import pytest
import database


class TestAnonymousAccessProtection:
    """Unauthenticated users must be redirected to /login for all protected routes."""

    @pytest.mark.parametrize("url", [
        "/dashboard",
        "/dashboard/export",
        "/analytics",
        "/students",
        "/students/export",
        "/students/add",
        "/students/1",
        "/students/1/edit",
        "/students/1/certificate",
        "/students/1/id-card",
        "/attendance",
        "/attendance/1",
        "/grades/add/1",
        "/fees/create/1",
        "/fees/pay/1",
        "/fees/1",
        "/notices",
        "/notices/1",
        "/notices/add",
        "/audit-log",
        "/notifications",
        "/exams",
        "/exams/create",
        "/exams/1/marks",
        "/students/1/result-history",
        "/students/1/academic-record",
        "/students/1/academic-record/pdf",
        "/rankings",
        "/api/global-search?q=test",
    ])
    def test_anonymous_redirected_to_login(self, client, url):
        resp = client.get(url, follow_redirects=False)
        assert resp.status_code == 302
        assert "/login" in resp.headers.get("Location", "")


class TestStudentAuthorizationIsolation:
    """Student role must access only their own resources and receive 403 on other students' data or admin routes."""

    def test_student_own_profile_allowed(self, student_client, db):
        own_id = db["linked_pk"]
        resp = student_client.get(f"/students/{own_id}")
        assert resp.status_code == 200

    def test_student_other_profile_forbidden(self, student_client, db):
        own_id = db["linked_pk"]
        other_id = own_id + 1 if own_id == 1 else 1
        resp = student_client.get(f"/students/{other_id}")
        assert resp.status_code == 403

    def test_student_own_academic_record_allowed(self, student_client, db):
        own_id = db["linked_pk"]
        resp = student_client.get(f"/students/{own_id}/academic-record")
        assert resp.status_code == 200

    def test_student_other_academic_record_forbidden(self, student_client, db):
        own_id = db["linked_pk"]
        other_id = own_id + 1 if own_id == 1 else 1
        resp = student_client.get(f"/students/{other_id}/academic-record")
        assert resp.status_code == 403

    def test_student_own_pdf_transcript_allowed(self, student_client, db):
        own_id = db["linked_pk"]
        resp = student_client.get(f"/students/{own_id}/academic-record/pdf")
        assert resp.status_code == 200
        assert resp.mimetype == "application/pdf"

    def test_student_other_pdf_transcript_forbidden(self, student_client, db):
        own_id = db["linked_pk"]
        other_id = own_id + 1 if own_id == 1 else 1
        resp = student_client.get(f"/students/{other_id}/academic-record/pdf")
        assert resp.status_code == 403

    def test_student_admin_operations_forbidden(self, student_client, db):
        own_id = db["linked_pk"]
        assert student_client.get("/students/add").status_code == 403
        assert student_client.get(f"/students/{own_id}/edit").status_code == 403
        assert student_client.post(f"/students/{own_id}/delete").status_code == 403
        assert student_client.get("/audit-log").status_code == 403
        assert student_client.get("/notifications").status_code == 403
        assert student_client.get("/students/export").status_code == 403
        assert student_client.get("/dashboard/export").status_code == 403

    def test_student_teacher_write_operations_forbidden(self, student_client, db):
        own_id = db["linked_pk"]
        assert student_client.get("/attendance").status_code == 403
        assert student_client.post("/attendance", data={"date": "2026-09-15"}).status_code == 403
        assert student_client.get(f"/grades/add/{own_id}").status_code == 403
        assert student_client.post(f"/grades/add/{own_id}", data={"subject": "Math", "marks_obtained": "90"}).status_code == 403
        assert student_client.get("/notices/add").status_code == 403

    def test_student_other_fee_forbidden(self, student_client, db):
        own_id = db["linked_pk"]
        other_id = own_id + 1 if own_id == 1 else 1
        resp = student_client.get(f"/fees/{other_id}")
        assert resp.status_code == 403

    def test_student_other_attendance_forbidden(self, student_client, db):
        own_id = db["linked_pk"]
        other_id = own_id + 1 if own_id == 1 else 1
        resp = student_client.get(f"/attendance/{other_id}")
        assert resp.status_code == 403

    def test_student_other_results_history_forbidden(self, student_client, db):
        own_id = db["linked_pk"]
        other_id = own_id + 1 if own_id == 1 else 1
        resp = student_client.get(f"/students/{other_id}/result-history")
        assert resp.status_code == 403

    def test_student_global_search_cannot_see_other_students(self, student_client, db):
        resp = student_client.get("/api/global-search?q=a")
        assert resp.status_code == 200
        data = resp.get_json()
        student_results = data["results"]["students"]
        own_id = db["linked_pk"]
        for s in student_results:
            assert s["id"] == own_id, f"Student global search leaked other student id={s['id']}"


class TestTeacherAuthorizationPermissions:
    """Teacher role has view/mark permissions but is blocked from Admin-only write/config actions."""

    def test_teacher_permitted_routes_allowed(self, teacher_client, db):
        own_id = db["linked_pk"]
        assert teacher_client.get("/students").status_code == 200
        assert teacher_client.get(f"/students/{own_id}").status_code == 200
        assert teacher_client.get("/attendance").status_code == 200
        assert teacher_client.get(f"/grades/add/{own_id}").status_code == 200
        assert teacher_client.get("/exams").status_code == 200
        assert teacher_client.get("/notices").status_code == 200
        assert teacher_client.get("/notices/add").status_code == 200

    def test_teacher_admin_only_operations_forbidden(self, teacher_client, db):
        own_id = db["linked_pk"]
        assert teacher_client.get("/students/add").status_code == 403
        assert teacher_client.get(f"/students/{own_id}/edit").status_code == 403
        assert teacher_client.post(f"/students/{own_id}/delete").status_code == 403
        assert teacher_client.get("/audit-log").status_code == 403
        assert teacher_client.get("/notifications").status_code == 403
        assert teacher_client.get(f"/fees/create/{own_id}").status_code == 403
        assert teacher_client.get("/fees/pay/1").status_code == 403
        assert teacher_client.post("/exams/1/delete").status_code == 403

    def test_teacher_document_writes_forbidden(self, teacher_client, db):
        own_id = db["linked_pk"]
        data = {"doc_type": "Identity Proof", "document_file": (io.BytesIO(b"dummy"), "doc.pdf")}
        assert teacher_client.post(f"/student/{own_id}/documents/upload", data=data).status_code == 403
        assert teacher_client.post(f"/student/{own_id}/documents/1/verify").status_code == 403
        assert teacher_client.post(f"/student/{own_id}/documents/1/reject").status_code == 403
        assert teacher_client.post(f"/student/{own_id}/documents/1/delete").status_code == 403


class TestAdminAuthorizationAccess:
    """Admin role can access all administration endpoints."""

    def test_admin_full_access(self, admin_client, db):
        own_id = db["linked_pk"]
        assert admin_client.get("/students").status_code == 200
        assert admin_client.get(f"/students/{own_id}").status_code == 200
        assert admin_client.get("/students/add").status_code == 200
        assert admin_client.get(f"/students/{own_id}/edit").status_code == 200
        assert admin_client.get("/attendance").status_code == 200
        assert admin_client.get("/fees/create/1").status_code == 200 or admin_client.get(f"/fees/create/{own_id}").status_code == 200
        assert admin_client.get("/audit-log").status_code == 200
        assert admin_client.get("/notifications").status_code == 200
        assert admin_client.get("/exams").status_code == 200
        assert admin_client.get("/notices").status_code == 200


class TestDocumentAndPdfOwnershipChecks:
    """Verify that document preview/download checks both URL student_id and document owner stud_id."""

    def test_student_document_preview_other_student_document_forbidden(self, student_client, db):
        own_id = db["linked_pk"]
        other_id = own_id + 1 if own_id == 1 else 1

        # Create document belonging to other_id
        doc_id = database.insert_student_document(
            stud_id=other_id,
            doc_type="Aadhaar Card",
            custom_doc_name=None,
            original_filename="other.pdf",
            stored_filename="safe_other.pdf",
            mime_type="application/pdf",
            file_size_bytes=100,
            uploaded_by=db["users"]["admin"]["id"],
        )

        # Student A requesting Student B's document via Student A's URL -> 403
        resp1 = student_client.get(f"/student/{own_id}/documents/{doc_id}/preview")
        assert resp1.status_code == 403

        # Student A requesting Student B's document via Student B's URL -> 403
        resp2 = student_client.get(f"/student/{other_id}/documents/{doc_id}/preview")
        assert resp2.status_code == 403
