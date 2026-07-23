"""
prepare_queue.py
=================
THE ONLY SCRIPT YOU RUN ON YOUR LAPTOP.

Flow:
  1. Reads leads.csv → auto-picks next 60 pending rows
     (30 for acc1, 30 for acc2, alternating)
  2. Reads accessibility-report.txt
  3. Generates emails for each company
  4. Pushes 30 emails → SQS Queue acc1
  5. Pushes 30 emails → SQS Queue acc2
  6. Marks those rows as "queued" in CSV

Run:
  python prepare_queue.py              (full run)
  python prepare_queue.py --no-upload  (test locally, don't push to SQS)
"""

import os, sys, csv, json, random, argparse, boto3
from datetime import datetime, timedelta, date

# ── Add scripts dir to path (kept for compatibility) ──────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR   = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)
# from parse_report import parse_report   # disabled — observed_issues is now a fixed default list

# ══════════════════════════════════════════════════════════════════════════════
# CONFIG — update these when switching from dummy → real data
# ══════════════════════════════════════════════════════════════════════════════
CSV_PATH    = os.path.join(BASE_DIR, "data", "company_leads_details.csv")
# REPORT_PATH = os.path.join(BASE_DIR, "data", "accessibility-report.txt")   # disabled — no longer parsed
BATCH_SIZE  = 30   # 30 per account = 60 total

# AWS config
AWS_REGION      = "ap-south-1"
SQS_QUEUE_ACC1  = "automated_mail_sender_acc1"   # SQS queue name for account 1
SQS_QUEUE_ACC2  = "automated_mail_sender_acc2"   # SQS queue name for account 2
# ══════════════════════════════════════════════════════════════════════════════

SIGNATURE = """\
<br><br>
--<br>
Best Regards,<br>
<b>Pragati Chothe</b><br>
Freelancer | Full Stack Developer<br>
Specializing in Web Accessibility<br>
<b>Email:</b> <a href="mailto:pragatichothe@gmail.com">pragatichothe@gmail.com</a> | <b>Phone:</b> +91 9021927662<br>
<a href="https://pragatichothe.in/">Portfolio</a> | <a href="https://github.com/Pragati-C19">GitHub</a> | <a href="https://linkedin.com/in/pragati-c19">LinkedIn</a>"""

EMAIL_TEMPLATE = """\
<p>Hi {contact_name},</p>

<p>I came across <b>{firm_name}</b> while reviewing SEBI-registered <b>{category}</b> entities \
and noticed your digital platform here: <a href="{website_url}">{website_url}</a>.</p>

<p>As you may already be aware, SEBI's digital accessibility compliance workflow \
(Circular No. SEBI/HO/ITD-1/ITD_VIAP/P/CIR/2025/111) requires regulated \
entities to complete the accessibility audit process and remediate findings \
for final compliance submission.</p>

<p>We help SEBI-regulated IA / RA / PMS firms with the developer-side \
remediation work, including:</p>

<ul>
<li>Fixing WCAG 2.1 AA issues found in the initial accessibility audit</li>
<li>Resolving common issues such as missing alt text, low contrast, form label issues, keyboard-accessibility issues, and inaccessible links/buttons</li>
<li>Preparing before/after evidence for auditor re-validation</li>
<li>Creating a remediation summary that can support the final compliance submission</li>
</ul>

<p>While doing a quick preliminary check of <a href="{website_url}">{website_url}</a>, we noticed potential \
accessibility issues such as <b>low color contrast, missing image alternative text, links without \
discernible text, buttons without accessible names, and missing form labels</b>. This is not a formal audit, \
but it may be worth reviewing if your final accessibility compliance work is still in progress.</p>

<p>Have you already completed your initial IAAP accessibility audit / Table C3 \
report? If yes, we can help remediate the open findings and prepare the \
evidence pack for the final submission.</p>

<p>Would you be open to a short 15-minute call this week?</p>{signature}"""


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


# def format_issues(issues: list) -> str:
#     """Converts list of issue strings into a readable sentence. (disabled — replaced by DEFAULT_OBSERVED_ISSUES)"""
#     if not issues:
#         return "potential WCAG 2.1 AA accessibility issues"
#     main    = [i for i in issues if i != "among other issues"]
#     has_etc = "among other issues" in issues
#     if   len(main) == 1: text = main[0]
#     elif len(main) == 2: text = f"{main[0]} and {main[1]}"
#     else:                text = ", ".join(main[:-1]) + f", and {main[-1]}"
#     if has_etc: text += ", among other issues"
#     return text


def load_pending_companies(csv_path: str, batch_size: int) -> tuple:
    """
    Reads CSV and returns:
      acc1_companies → list of dicts (odd positions: row 1, 3, 5...)
      acc2_companies → list of dicts (even positions: row 2, 4, 6...)
      all_rows       → full CSV rows (for writing back status)
      fieldnames     → CSV column headers
    """
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader    = csv.DictReader(f)
        fieldnames = reader.fieldnames
        all_rows  = list(reader)

    # Pick next (batch_size * 2) pending rows
    pending = []
    for i, row in enumerate(all_rows):
        if len(pending) >= batch_size * 2:
            break
        if row.get("status", "").strip().lower() == "pending":
            pending.append((i, row))

    # Alternate: odd indexes → acc1, even indexes → acc2
    acc1 = [(i, r) for idx, (i, r) in enumerate(pending) if idx % 2 == 0]
    acc2 = [(i, r) for idx, (i, r) in enumerate(pending) if idx % 2 == 1]

    return acc1, acc2, all_rows, fieldnames


def build_email(row: dict, account_id: int) -> dict:
    """Fills the email template for one company."""
    website  = (row.get("website_url") or "").strip()
    contact  = row.get("recipient_name") or "Team"
    category = row.get("source_category") or "Portfolio Manager"

    return {
        "account_id": account_id,
        "to":         row.get("recipient_email", "").strip(),
        "subject":    f"Accessibility Remediation Support for {row['company_name']}",
        "body":       EMAIL_TEMPLATE.format(
                          contact_name=contact,
                          firm_name=row["company_name"],
                          category=category,
                          website_url=website,
                          signature=SIGNATURE,
                      ),
        "company":    row["company_name"],
        "website":    website,
    }


def push_to_sqs(emails: list, queue_name: str, account_id: int) -> bool:
    """Pushes a list of email dicts to an SQS queue."""
    try:
        sqs    = boto3.client("sqs", region_name=AWS_REGION)
        url    = sqs.get_queue_url(QueueName=queue_name)["QueueUrl"]
        failed = 0

        for email in emails:
            response = sqs.send_message(
                QueueUrl=url,
                MessageBody=json.dumps(email),
            )
            if "MessageId" not in response:
                failed += 1

        log(f"SQS acc{account_id}: pushed {len(emails) - failed}/{len(emails)} messages")
        return failed == 0

    except Exception as e:
        log(f"SQS ERROR for acc{account_id}: {e}")
        return False


def update_csv_status(csv_path: str, all_rows: list, fieldnames: list,
                      row_indexes: list, new_status: str):
    """Marks specific rows in CSV with new_status."""
    for i in row_indexes:
        all_rows[i]["status"] = new_status

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)


def preview_emails(acc1_emails: list, acc2_emails: list):
    """Prints a preview of generated emails."""
    print(f"\n{'─'*60}")
    print("PREVIEW — First email from each account:")
    print(f"{'─'*60}")
    for acc_id, emails in [(1, acc1_emails), (2, acc2_emails)]:
        if emails:
            e = emails[0]
            print(f"\n  Account {acc_id}")
            print(f"  TO      : {e['to']}")
            print(f"  SUBJECT : {e['subject']}")
            print(f"  COMPANY : {e['company']}")
            print(f"  WEBSITE : {e['website']}")
            body_preview = e['body'][:200].replace('\n', ' ')
            print(f"  BODY    : {body_preview}...")
    print(f"\n{'─'*60}\n")


def main():
    parser = argparse.ArgumentParser(description="Prepare email queue for SQS")
    parser.add_argument("--no-upload", action="store_true",
                        help="Generate emails locally but do NOT push to SQS")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  SEBI Mailer — Prepare Queue")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Mode: {'LOCAL PREVIEW (no SQS)' if args.no_upload else 'PUSH TO SQS'}")
    print(f"{'='*60}\n")

    # ── Step 1: Load pending companies from CSV ───────────────────────────────
    log(f"Reading CSV: {CSV_PATH}")
    if not os.path.exists(CSV_PATH):
        log(f"ERROR: CSV not found at {CSV_PATH}")
        sys.exit(1)

    acc1_rows, acc2_rows, all_rows, fieldnames = load_pending_companies(
        CSV_PATH, BATCH_SIZE
    )

    if not acc1_rows and not acc2_rows:
        log("No pending companies found in CSV. All done!")
        sys.exit(0)

    log(f"Account 1: {len(acc1_rows)} companies")
    log(f"Account 2: {len(acc2_rows)} companies")

    # ── Step 2: Parse accessibility report (disabled — using fixed issue list) ─
    # log(f"Parsing report: {REPORT_PATH}")
    # if not os.path.exists(REPORT_PATH):
    #     log(f"ERROR: Report not found at {REPORT_PATH}")
    #     log("Run scan.sh first to generate the accessibility report.")
    #     sys.exit(1)
    #
    # report = parse_report(REPORT_PATH)
    # log(f"Found accessibility data for {len(report)} websites")

    # ── Step 3: Generate emails ───────────────────────────────────────────────
    log("Generating emails...")

    acc1_emails = []
    for _, row in acc1_rows:
        acc1_emails.append(build_email(row, account_id=1))

    acc2_emails = []
    for _, row in acc2_rows:
        acc2_emails.append(build_email(row, account_id=2))

    log(f"Generated {len(acc1_emails) + len(acc2_emails)} emails total")

    # ── Step 4: Preview ───────────────────────────────────────────────────────
    preview_emails(acc1_emails, acc2_emails)

    # ── Step 5: Push to SQS (or skip if --no-upload) ─────────────────────────
    if args.no_upload:
        log("--no-upload flag set. Skipping SQS. Review preview above.")
        print("\n✓ Local test complete. Emails look correct? Then run without --no-upload.\n")
        return

    log("Pushing to SQS queues...")

    acc1_ok = push_to_sqs(acc1_emails, SQS_QUEUE_ACC1, account_id=1)
    acc2_ok = push_to_sqs(acc2_emails, SQS_QUEUE_ACC2, account_id=2)

    # ── Step 6: Mark rows as "queued" in CSV ─────────────────────────────────
    if acc1_ok or acc2_ok:
        queued_indexes = []
        if acc1_ok: queued_indexes += [i for i, _ in acc1_rows]
        if acc2_ok: queued_indexes += [i for i, _ in acc2_rows]

        update_csv_status(CSV_PATH, all_rows, fieldnames, queued_indexes, "queued")
        log(f"Marked {len(queued_indexes)} rows as 'queued' in CSV")

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    if acc1_ok and acc2_ok:
        print(f"✓ SUCCESS — {len(acc1_emails) + len(acc2_emails)} emails queued in SQS")
        print(f"  acc1 queue: {len(acc1_emails)} emails")
        print(f"  acc2 queue: {len(acc2_emails)} emails")
        print(f"  Lambda will send them next weekday from 8:00 AM IST")
    else:
        print("✗ Some uploads failed. Check errors above.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()