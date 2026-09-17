"""
print_backfill_credentials.py — Regenerates temporary passwords for the 15 backfilled student accounts
and outputs the credentials report table directly to stdout for Admin review.
"""

import database


def main():
    print("==========================================================================")
    print("      ONE-TIME REGENERATED CREDENTIALS FOR 15 BACKFILLED STUDENTS         ")
    print("==========================================================================")
    
    credentials = database.regenerate_backfill_credentials()
    
    print(f"{'STUDENT NAME':<30} | {'STUDENT ID':<15} | {'LOGIN ID':<15} | {'TEMP PASSWORD':<15}")
    print("-" * 82)
    for item in credentials:
        print(f"{item['student_name']:<30} | {item['student_id']:<15} | {item['login_id']:<15} | {item['temp_password']:<15}")
    print("-" * 82)
    print(f"\nTotal Target Accounts: {len(credentials)}")
    print("IMPORTANT: Save these temporary credentials now. Plaintext passwords are not saved in the database.")


if __name__ == "__main__":
    main()
