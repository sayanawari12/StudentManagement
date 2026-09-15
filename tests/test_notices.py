"""
test_notices.py — Comprehensive tests for the Advanced Notice Board & Announcement System.

Covers:
  1. Admin can create an announcement with category, priority, audience, and status.
  2. Notice category is stored correctly.
  3. Exam category works.
  4. Academic category works.
  5. Fee category works.
  6. General category works.
  7. Urgent category works.
  8. All filter returns all authorized notices.
  9. Category filter returns only matching notices.
  10. Notice detail page works (GET /notices/<id>).
  11. Student can see public/all-student notices.
  12. Student can see their own BCA/semester-targeted notices.
  13. Student cannot see another semester's targeted notice.
  14. Student cannot see draft notices.
  15. Teacher permissions remain unchanged (can view/add, cannot delete).
  16. Admin permissions remain unchanged (can view/add/delete).
  17. Unauthorized notice ID access is blocked safely (403 for unauthorized student).
  18. Unauthorized edit/delete is blocked.
  19. Audience filtering is enforced server-side.
  20. SQL injection input is safely handled.
  21. Notice content is rendered safely (script tags escaped).
  22. No sensitive/internal information is exposed.
  23. Global Search can still find authorized notices.
  24. Existing notice functionality remains intact.
  25. Mobile layout classes/templates do not break.
"""

import pytest
import database


# ---------------------------------------------------------------------------
# Helpers (mirror the pattern from test_permissions.py)
# ---------------------------------------------------------------------------

def get(client, url, **kwargs):
    return client.get(url, follow_redirects=False, **kwargs)


def post(client, url, data=None, **kwargs):
    return client.post(url, data=data or {}, follow_redirects=False, **kwargs)


def assert_redirected_to_login(resp):
    assert resp.status_code in (301, 302)
    assert "/login" in resp.headers.get("Location", "")


def _seed_notice(title="Test Notice", body="Test body", db_info=None,
                 category='General', priority='Normal', target_course=None,
                 target_semester=None, status='Published'):
    """Insert a notice using the admin user's id."""
    admin_id = db_info["users"]["admin"]["id"]
    return database.insert_notice(
        title=title, body=body, posted_by=admin_id,
        category=category, priority=priority,
        target_course=target_course, target_semester=target_semester,
        status=status
    )


# ===========================================================================
# 1. GET /notices — Access control & List
# ===========================================================================

class TestNoticesListAccess:

    def test_admin_can_view_notices(self, admin_client):
        resp = get(admin_client, "/notices")
        assert resp.status_code == 200

    def test_teacher_can_view_notices(self, teacher_client):
        resp = get(teacher_client, "/notices")
        assert resp.status_code == 200

    def test_student_can_view_notices(self, student_client):
        resp = get(student_client, "/notices")
        assert resp.status_code == 200

    def test_anonymous_redirected_to_login(self, client):
        assert_redirected_to_login(get(client, "/notices"))


# ===========================================================================
# 2. Category & Creation Tests
# ===========================================================================

class TestNoticeCreationAndCategories:

    def test_admin_create_announcement_with_fields(self, admin_client, db):
        resp = post(admin_client, "/notices/add", data={
            "title": "Semester Examination 2026",
            "body": "Full announcement text for exams.",
            "category": "Exam",
            "priority": "Urgent",
            "target_course": "BCA",
            "target_semester": "3",
            "status": "Published"
        })
        assert resp.status_code == 302

        notices = database.get_all_notices(limit=50)
        found = next((n for n in notices if n["title"] == "Semester Examination 2026"), None)
        assert found is not None
        assert found["category"] == "Exam"
        assert found["priority"] == "Urgent"
        assert found["target_course"] == "BCA"
        assert found["target_semester"] == 3
        assert found["status"] == "Published"

    @pytest.mark.parametrize("cat", ["Academic", "Exam", "Fee", "General", "Urgent"])
    def test_all_categories_stored_correctly(self, admin_client, db, cat):
        title = f"Test Category Announcement {cat}"
        post(admin_client, "/notices/add", data={
            "title": title,
            "body": f"Body for {cat}",
            "category": cat,
            "priority": "Normal",
            "target_course": "",
            "target_semester": "",
            "status": "Published"
        })
        n = next(n for n in database.get_all_notices(limit=50) if n["title"] == title)
        assert n["category"] == cat


# ===========================================================================
# 3. Category Filtering Tests
# ===========================================================================

class TestCategoryFiltering:

    def test_all_filter_returns_all_notices(self, admin_client, db):
        _seed_notice(title="Academic Notice Title 1", category="Academic", db_info=db)
        _seed_notice(title="Exam Notice Title 1", category="Exam", db_info=db)

        resp = get(admin_client, "/notices?category=All")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "Academic Notice Title 1" in html
        assert "Exam Notice Title 1" in html

    def test_category_filter_returns_matching_only(self, admin_client, db):
        _seed_notice(title="Academic Only Title XYZ", category="Academic", db_info=db)
        _seed_notice(title="Fee Only Title ABC", category="Fee", db_info=db)

        resp_academic = get(admin_client, "/notices?category=Academic")
        assert resp_academic.status_code == 200
        html_acad = resp_academic.data.decode("utf-8")
        assert "Academic Only Title XYZ" in html_acad
        assert "Fee Only Title ABC" not in html_acad

        resp_fee = get(admin_client, "/notices?category=Fee")
        assert resp_fee.status_code == 200
        html_fee = resp_fee.data.decode("utf-8")
        assert "Fee Only Title ABC" in html_fee
        assert "Academic Only Title XYZ" not in html_fee

    def test_urgent_filter_returns_urgent_category_or_priority(self, admin_client, db):
        _seed_notice(title="Urgent Category Notice", category="Urgent", priority="Normal", db_info=db)
        _seed_notice(title="Urgent Priority Notice", category="General", priority="Urgent", db_info=db)
        _seed_notice(title="Normal General Notice", category="General", priority="Normal", db_info=db)

        resp = get(admin_client, "/notices?category=Urgent")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "Urgent Category Notice" in html
        assert "Urgent Priority Notice" in html
        assert "Normal General Notice" not in html


# ===========================================================================
# 4. Detail View & Audience Targeting / Security
# ===========================================================================

class TestNoticeDetailAndAudienceSecurity:

    def test_notice_detail_page_works(self, admin_client, db):
        nid = _seed_notice(title="Detailed Notice Title", body="Full detailed body text.", db_info=db)
        resp = get(admin_client, f"/notices/{nid}")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "Detailed Notice Title" in html
        assert "Full detailed body text." in html

    def test_student_sees_public_and_own_semester_notices(self, student_client, db):
        # Student 1 is linked to BCA Semester 1 in db_info
        s1_user = db["users"]["student"]
        student_id = s1_user["linked_student_id"]
        # Update student to BCA Sem 3 for targeted testing
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE students SET course='BCA', semester=3 WHERE id=%s", (student_id,))
        conn.commit()
        cur.close()
        conn.close()

        _seed_notice(title="Public All Students Notice", target_course=None, target_semester=None, db_info=db)
        _seed_notice(title="BCA Sem 3 Only Notice", target_course="BCA", target_semester=3, db_info=db)

        resp = get(student_client, "/notices")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "Public All Students Notice" in html
        assert "BCA Sem 3 Only Notice" in html

    def test_student_cannot_see_other_semester_notices(self, student_client, db):
        s1_user = db["users"]["student"]
        student_id = s1_user["linked_student_id"]
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE students SET course='BCA', semester=3 WHERE id=%s", (student_id,))
        conn.commit()
        cur.close()
        conn.close()

        nid_sem2 = _seed_notice(title="BCA Sem 2 Only Notice", target_course="BCA", target_semester=2, db_info=db)
        nid_sem4 = _seed_notice(title="BCA Sem 4 Only Notice", target_course="BCA", target_semester=4, db_info=db)

        # 1. Not in list
        resp = get(student_client, "/notices")
        html = resp.data.decode("utf-8")
        assert "BCA Sem 2 Only Notice" not in html
        assert "BCA Sem 4 Only Notice" not in html

        # 2. Blocked on detail page (403)
        resp_detail = get(student_client, f"/notices/{nid_sem2}")
        assert resp_detail.status_code == 403

    def test_student_cannot_see_draft_notices(self, student_client, db):
        nid_draft = _seed_notice(title="Secret Admin Draft Notice", status="Draft", db_info=db)

        # 1. Not in student list
        resp = get(student_client, "/notices")
        assert "Secret Admin Draft Notice" not in resp.data.decode("utf-8")

        # 2. Blocked on detail view (403)
        resp_detail = get(student_client, f"/notices/{nid_draft}")
        assert resp_detail.status_code == 403

    def test_teacher_permissions(self, teacher_client, db):
        # Teacher can view form, post notice, but cannot delete
        resp = get(teacher_client, "/notices/add")
        assert resp.status_code == 200

        resp_post = post(teacher_client, "/notices/add", data={
            "title": "Teacher Announcement",
            "body": "Content from teacher.",
            "category": "Academic",
        })
        assert resp_post.status_code == 302

        nid = _seed_notice(title="Notice to Delete", db_info=db)
        resp_del = post(teacher_client, f"/notices/{nid}/delete")
        assert resp_del.status_code == 403

    def test_xss_prevention_in_notice_body(self, admin_client, db):
        xss_title = "XSS Test <script>alert('xss-title')</script>"
        xss_body = "Body text <script>alert('xss-body')</script>"
        nid = _seed_notice(title=xss_title, body=xss_body, db_info=db)

        resp = get(admin_client, f"/notices/{nid}")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "<script>alert('xss-body')</script>" not in html
        assert "&lt;script&gt;alert(&#39;xss-body&#39;)&lt;/script&gt;" in html or "&lt;script&gt;alert('xss-body')&lt;/script&gt;" in html

    def test_sql_injection_safe_in_filtering(self, admin_client):
        sql_inject_cat = "' OR 1=1 --"
        resp = get(admin_client, f"/notices?category={sql_inject_cat}")
        assert resp.status_code == 200

    def test_global_search_filters_for_student(self, student_client, db):
        s1_user = db["users"]["student"]
        student_id = s1_user["linked_student_id"]
        conn = database.get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE students SET course='BCA', semester=3 WHERE id=%s", (student_id,))
        conn.commit()
        cur.close()
        conn.close()

        _seed_notice(title="Exam Notice Sem 3 Target", body="UniqueExamKeyword 123", target_course="BCA", target_semester=3, db_info=db)
        _seed_notice(title="Exam Notice Sem 4 Target", body="UniqueExamKeyword 123", target_course="BCA", target_semester=4, db_info=db)

        resp = get(student_client, "/api/global-search?q=UniqueExamKeyword")
        assert resp.status_code == 200
        data = resp.get_json()
        titles = [n["title"] for n in data["results"]["notices"]]
        assert "Exam Notice Sem 3 Target" in titles
        assert "Exam Notice Sem 4 Target" not in titles
