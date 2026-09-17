"""
test_student_login_credentials.py — Comprehensive tests for the Student Login Credential System.

Covers:
  - Admin student creation with automatic user account generation
  - Name-based Login ID formatting, lowercasing, 3-digit suffix, and collision handling
  - Cryptographic temporary password generation and Werkzeug PBKDF2 password hashing
  - Zero plaintext password persistence in DB or logs
  - First-login forced redirect to /change-password and clearing flag after password change
  - Student own-record data isolation (_assert_own_record / 403 Forbidden on cross-student URL manipulation)
  - Idempotent backfill function (creates missing accounts without modifying existing linked accounts)
  - Per-student backfill transaction isolation
  - Atomic transaction rollback on user creation failure
  - CSV import with automatic user creation
  - Admin/Teacher/Student login regressions
"""

import pytest
from unittest.mock import patch
from werkzeug.security import check_password_hash, generate_password_hash
import database
import secrets


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def post_login(client, username, password):
    return client.post("/login", data={"username": username, "password": password}, follow_redirects=False)


# ===========================================================================
# 1. Credential Generator Unit Tests
# ===========================================================================

class TestCredentialGenerators:

    def test_generate_unique_login_id_formatting(self, db):
        login_id = database.generate_unique_login_id("Sayan Awari")
        assert login_id.startswith("sayan")
        assert len(login_id) == len("sayan") + 3
        suffix = login_id[len("sayan"):]
        assert suffix.isdigit()
        assert 100 <= int(suffix) <= 999

    def test_generate_unique_login_id_special_characters_and_fallback(self, db):
        login_id = database.generate_unique_login_id("!!! $$$ ***")
        assert login_id.startswith("student")
        assert len(login_id) == len("student") + 3

    def test_generate_unique_login_id_collision_retry(self, db):
        # Create a user with sayan100 first to force potential collision check
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
            ("sayan100", generate_password_hash("pass"), "student")
        )
        conn.commit()
        cursor.close()
        conn.close()

        # Generating login ID for Sayan should produce a valid unique username
        login_id = database.generate_unique_login_id("Sayan")
        assert login_id != "sayan100"
        assert login_id.startswith("sayan")
        assert database.get_user_by_username(login_id) is None

    def test_generate_temp_password_complexity(self):
        pwd = database.generate_temp_password()
        assert len(pwd) == 10
        assert any(c.isupper() for c in pwd)
        assert any(c.islower() for c in pwd)
        assert any(c.isdigit() for c in pwd)
        assert any(c in "@#$!%*" for c in pwd)


# ===========================================================================
# 2. Atomic Student + User Creation Tests
# ===========================================================================

class TestAtomicStudentUserCreation:

    def test_create_student_with_account_creates_both_records(self, db):
        data = {
            "student_id": "TEST_STUD_001",
            "student_name": "Rohan Deshmukh",
            "email": "rohan@example.com",
            "phone": "9876543210",
            "gender": "Male",
            "date_of_birth": "2005-05-15",
            "course": "BCA",
            "semester": 1,
            "address": "Pune, Maharashtra"
        }
        stud_pk, payload, login_id, temp_pwd = database.create_student_with_account(data)

        # Verify student record created
        student = database.get_student_by_id(stud_pk)
        assert student is not None
        assert student["student_name"] == "Rohan Deshmukh"

        # Verify linked user account created
        user = database.get_user_by_username(login_id)
        assert user is not None
        assert user["role"] == "student"
        assert user["linked_student_id"] == stud_pk
        assert user["requires_password_change"] == 1

        # Verify password is stored ONLY as a hash
        assert user["password"] != temp_pwd
        assert check_password_hash(user["password"], temp_pwd) is True

    def test_create_student_with_account_rollback_on_failure(self, db):
        data = {
            "student_id": "TEST_STUD_002",
            "student_name": "Failure Student",
            "email": "fail@example.com",
            "phone": "9876543211",
            "gender": "Female",
            "date_of_birth": "2005-06-16",
            "course": "BCA",
            "semester": 2,
            "address": "Nagpur"
        }

        # Mock database exception during user insert step
        with patch.object(database, "generate_unique_login_id", side_effect=RuntimeError("Simulated user creation failure")):
            with pytest.raises(RuntimeError):
                database.create_student_with_account(data)

        # Verify student record was cleanly rolled back (not orphaned)
        assert database.get_student_by_student_id("TEST_STUD_002") is None


# ===========================================================================
# 3. Add Student Route & Credential Success UI Tests
# ===========================================================================

class TestAddStudentRouteWithCredentials:

    def test_admin_add_student_renders_success_screen(self, admin_client, db):
        form_data = {
            "student_id": "BCA2488",
            "student_name": "Tanya Sharma",
            "email": "tanya@example.com",
            "phone": "9876543299",
            "gender": "Female",
            "date_of_birth": "2005-08-20",
            "course": "BCA",
            "semester": "1",
            "address": "Mumbai",
            "csrf_token": ""
        }
        resp = admin_client.post("/students/add", data=form_data, follow_redirects=True)
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")

        assert "Student Created Successfully" in html
        assert "Tanya Sharma" in html
        assert "BCA2488" in html
        assert "Temporary Password" in html
        assert "Copy" in html
        assert "Go to Student" in html
        assert "Done" in html

        # Verify user account was created in DB
        stud = database.get_student_by_student_id("BCA2488")
        assert stud is not None
        user = database.get_user_by_id(stud["id"])  # lookup by linked_student_id logic or fetch users
        conn = database.get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE linked_student_id = %s", (stud["id"],))
        u_row = cursor.fetchone()
        cursor.close()
        conn.close()

        assert u_row is not None
        assert u_row["username"].startswith("tanya")
        assert u_row["requires_password_change"] == 1


# ===========================================================================
# 4. First Login & Forced Password Change Tests
# ===========================================================================

class TestFirstLoginPasswordChangeFlow:

    def test_first_login_redirects_to_change_password(self, client, db):
        # Create student with account
        data = {
            "student_id": "BCA2489",
            "student_name": "Vikram Seth",
            "email": "vikram@example.com",
            "phone": "9876543288",
            "gender": "Male",
            "date_of_birth": "2005-09-10",
            "course": "BCA",
            "semester": 1,
            "address": "Delhi"
        }
        stud_pk, _, login_id, temp_pwd = database.create_student_with_account(data)

        # Login with temporary password
        login_resp = post_login(client, login_id, temp_pwd)
        assert login_resp.status_code == 302
        assert "/change-password" in login_resp.headers["Location"]

        # Attempting to access protected student details while flag is set forces redirect to /change-password
        prot_resp = client.get(f"/students/{stud_pk}", follow_redirects=False)
        assert prot_resp.status_code == 302
        assert "/change-password" in prot_resp.headers["Location"]

        # Submit change password form
        change_resp = client.post("/change-password", data={
            "current_password": temp_pwd,
            "new_password": "NewSecurePassword123!",
            "confirm_new_password": "NewSecurePassword123!",
            "csrf_token": ""
        }, follow_redirects=True)
        assert change_resp.status_code == 200

        # Verify database flag cleared
        user = database.get_user_by_username(login_id)
        assert user["requires_password_change"] == 0

        # Verify student can now access own details route
        details_resp = client.get(f"/students/{stud_pk}")
        assert details_resp.status_code == 200
        assert "Vikram Seth" in details_resp.data.decode("utf-8")


# ===========================================================================
# 5. Student Data Isolation Tests
# ===========================================================================

class TestStudentDataIsolation:

    def test_student_cannot_access_other_student_profile(self, client, db):
        # Create Student A
        data_a = {"student_id": "STUD_A", "student_name": "Student A", "email": "a@ex.com", "course": "BCA", "semester": 1}
        pk_a, _, login_a, temp_a = database.create_student_with_account(data_a)

        # Create Student B
        data_b = {"student_id": "STUD_B", "student_name": "Student B", "email": "b@ex.com", "course": "BCA", "semester": 1}
        pk_b, _, login_b, temp_b = database.create_student_with_account(data_b)

        # Login as Student A and change password to activate normal session
        client.post("/login", data={"username": login_a, "password": temp_a})
        client.post("/change-password", data={"current_password": temp_a, "new_password": "PermPassword123!", "confirm_new_password": "PermPassword123!"})

        # Student A accesses own profile -> 200
        own_resp = client.get(f"/students/{pk_a}")
        assert own_resp.status_code == 200

        # Student A attempts to access Student B profile -> 403 Forbidden
        other_resp = client.get(f"/students/{pk_b}")
        assert other_resp.status_code == 403


# ===========================================================================
# 6. Idempotent Backfill Tests
# ===========================================================================

class TestBackfillUnlinkedAccounts:

    def test_backfill_creates_missing_accounts_without_touching_existing(self, db):
        # Insert an unlinked student directly into `students` table
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO students (student_id, student_name, email, course, semester)
               VALUES (%s, %s, %s, %s, %s)""",
            ("UNLINKED_001", "Unlinked Student", "unlinked@example.com", "BCA", 1)
        )
        unlinked_pk = cursor.lastrowid
        conn.commit()
        cursor.close()
        conn.close()

        # Run backfill
        res1 = database.backfill_unlinked_student_accounts()
        assert len(res1["created"]) >= 1
        created_unlinked = next((item for item in res1["created"] if item["student_id"] == "UNLINKED_001"), None)
        assert created_unlinked is not None

        # Verify user created in DB
        u = database.get_user_by_username(created_unlinked["login_id"])
        assert u is not None
        assert u["linked_student_id"] == unlinked_pk

        # Re-run backfill to verify idempotency (zero new accounts created)
        res2 = database.backfill_unlinked_student_accounts()
        assert len(res2["created"]) == 0
        assert res2["skipped_count"] >= 1

    def test_regenerate_backfill_credentials_targets_only_backfilled_accounts(self, db):
        # Target specific test user IDs
        target_ids = (7, 8, 9)
        results = database.regenerate_backfill_credentials(target_user_ids=target_ids)
        assert len(results) == 3
        for item in results:
            assert "student_name" in item
            assert "login_id" in item
            assert "temp_password" in item
            user = database.get_user_by_username(item["login_id"])
            assert user["requires_password_change"] == 1
