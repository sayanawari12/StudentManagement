"""
backfill_credentials.py — Safe, idempotent migration to generate login accounts for unlinked students.

This script dynamically queries all students who do not currently have a linked user account
in `users`, generates a unique Login ID and temporary password for each unlinked student,
and inserts their user account in an independent transaction.

Existing accounts (such as student1 linked to BCA2401) are strictly untouched.
"""

import sys
import database


def main():
    print("==================================================")
    print("      STUDENT LOGIN ACCOUNT BACKFILL TOOL        ")
    print("==================================================")
    print("Scanning database for unlinked student records...\n")

    res = database.backfill_unlinked_student_accounts()
    created = res["created"]
    skipped_count = res["skipped_count"]
    failed = res["failed"]

    if created:
        print(f"SUCCESS: Created {len(created)} new student login account(s):\n")
        print(f"{'STUDENT ID':<15} | {'STUDENT NAME':<25} | {'LOGIN ID':<15} | {'TEMP PASSWORD':<15}")
        print("-" * 75)
        for item in created:
            print(f"{item['student_id']:<15} | {item['student_name']:<25} | {item['login_id']:<15} | {item['temp_password']:<15}")
        print("-" * 75)
        print("\nIMPORTANT: Save these temporary credentials now. Passwords are not stored in plaintext.")
    else:
        print("No new student accounts needed creation.")

    if skipped_count:
        print(f"\nSkipped: {skipped_count} student(s) already have linked user accounts.")

    if failed:
        print(f"\nWARNING: {len(failed)} student(s) failed during account creation:")
        for item in failed:
            print(f"  - [{item['student_id']}] {item['student_name']}: {item['reason']}")

    print("\nBackfill operation complete.")


if __name__ == "__main__":
    main()
