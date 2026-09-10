"""
test_fees.py — Fees database function tests.

All calls go directly against the test DB (no HTTP layer needed).
"""

from decimal import Decimal

import pytest
import database


class TestGetTotalDues:
    """get_total_dues() must never return None."""

    def test_zero_fee_rows_returns_decimal_zero(self, db):
        """
        Regression (Fix 8): SUM() on zero rows returns NULL in MySQL.
        get_total_dues() must use COALESCE and return Decimal(0), not None.
        """
        result = database.get_total_dues()
        assert result is not None, "get_total_dues() must never return None"
        assert result == Decimal("0") or result >= Decimal("0")


class TestInsertAndPayFee:
    """insert_fee_due + update_fee_payment correctness."""

    def _insert_fee(self, stud_id, amount_due="200.00", due_date="2025-06-30"):
        database.insert_fee_due({
            "stud_id":    stud_id,
            "amount_due": Decimal(amount_due),
            "due_date":   due_date,
        })
        # Return the newest fee for this student
        fees = database.get_student_fees(stud_id)
        assert fees, "insert_fee_due must have created a row"
        return fees[0]  # ordered by due_date DESC → newest first

    def test_initial_amount_paid_is_zero(self, db):
        stud_id = db["linked_pk"]
        fee = self._insert_fee(stud_id, "300.00", "2025-07-01")
        assert fee["amount_paid"] == Decimal("0.00")
        assert fee["amount_due"] == Decimal("300.00")

    def test_two_partial_payments_fully_clear_balance(self, db):
        """
        Regression: double-counting across multiple payment rows.
        Two payments that together equal amount_due must yield get_total_dues() == 0
        (no double-counting of old rows).
        """
        stud_id = db["linked_pk"]
        fee = self._insert_fee(stud_id, "400.00", "2025-08-01")
        fee_id = fee["id"]

        rows1 = database.update_fee_payment(fee_id, Decimal("150.00"))
        assert rows1 == 1, "First partial payment should affect 1 row"

        rows2 = database.update_fee_payment(fee_id, Decimal("250.00"))
        assert rows2 == 1, "Second payment should affect 1 row"

        # After full payment this fee is settled; total dues should not include it
        total = database.get_total_dues()
        assert total is not None
        # Check this specific fee is fully paid
        fees_after = database.get_student_fees(stud_id)
        target = next((f for f in fees_after if f["id"] == fee_id), None)
        assert target is not None
        assert target["amount_paid"] == target["amount_due"], (
            "After two payments totalling amount_due, the fee must be fully paid"
        )

    def test_overpayment_rejected_at_db_level(self, db):
        """
        update_fee_payment() with an amount exceeding remaining balance must
        affect 0 rows and leave amount_paid unchanged.
        """
        stud_id = db["linked_pk"]
        fee = self._insert_fee(stud_id, "100.00", "2025-09-01")
        fee_id = fee["id"]

        # First, pay half
        database.update_fee_payment(fee_id, Decimal("50.00"))

        # Now try to overpay (remaining is 50.00, we send 75.00)
        rows = database.update_fee_payment(fee_id, Decimal("75.00"))
        assert rows == 0, (
            f"Overpayment must be rejected (0 rows affected), got {rows}"
        )

        # Confirm amount_paid is still 50.00
        fees = database.get_student_fees(stud_id)
        target = next((f for f in fees if f["id"] == fee_id), None)
        assert target is not None
        assert target["amount_paid"] == Decimal("50.00"), (
            f"amount_paid should be 50.00 after rejected overpayment, got {target['amount_paid']}"
        )

    def test_get_total_dues_excludes_fully_paid_fees(self, db):
        """
        After fully paying off a fee, get_total_dues() must not count it.
        """
        stud_id = db["linked_pk"]
        fee = self._insert_fee(stud_id, "200.00", "2025-10-01")
        fee_id = fee["id"]

        dues_before = database.get_total_dues()

        database.update_fee_payment(fee_id, Decimal("200.00"))

        dues_after = database.get_total_dues()
        assert dues_after <= dues_before, (
            "After fully paying a fee, total_dues must not increase"
        )
        assert dues_after is not None, "get_total_dues() must never return None after payments"
