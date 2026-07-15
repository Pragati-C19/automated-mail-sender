"""
gmail_sender.py
Handles Gmail OAuth authentication and email scheduling.
Uses Gmail API to create scheduled drafts/sends.

FIRST TIME SETUP:
- Run: python gmail_sender.py setup --account 1
- A browser window will open, log in with pragatichothe001@gmail.com
- Run: python gmail_sender.py setup --account 2
- A browser window will open, log in with pragatichothe002@gmail.com

After setup, tokens are saved in ../credentials/token_acc1.json and token_acc2.json
"""

import os
import sys
import json
import base64
import argparse
from email.mime.text import MIMEText
from datetime import datetime

# Gmail API imports
try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError:
    print("ERROR: Google API libraries not installed.")
    print("Run this command first:")
    print("  pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client")
    sys.exit(1)

# Scopes needed: send email + manage drafts
SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.settings.basic",
]

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CREDS_DIR = os.path.join(BASE_DIR, "credentials")


def get_credentials(account_id: int) -> Credentials:
    """
    Loads or refreshes OAuth credentials for the given account.
    On first run: opens browser for login.
    """
    token_path   = os.path.join(CREDS_DIR, f"token_acc{account_id}.json")
    secrets_path = os.path.join(CREDS_DIR, "client_secret.json")

    if not os.path.exists(secrets_path):
        print(f"\nERROR: client_secret.json not found at:\n  {secrets_path}")
        print("\nPlease follow the Gmail API setup steps in SETUP_GUIDE.md")
        sys.exit(1)

    creds = None

    # Load existing token if present
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    # If no valid token, do OAuth flow (opens browser)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(secrets_path, SCOPES)
            creds = flow.run_local_server(port=0)

        # Save token for future runs
        with open(token_path, "w") as f:
            f.write(creds.to_json())
        print(f"Token saved: {token_path}")

    return creds


def build_message(to: str, subject: str, body: str) -> dict:
    """Creates a base64-encoded email message."""
    message = MIMEText(body, "plain")
    message["to"] = to
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return {"raw": raw}


def send_email(service, to: str, subject: str, body: str) -> str:
    """Sends an email immediately. Returns message ID."""
    message = build_message(to, subject, body)
    sent = service.users().messages().send(
        userId="me", body=message
    ).execute()
    return sent["id"]


def schedule_email(service, to: str, subject: str, body: str, send_time: str) -> str:
    """
    Creates a Gmail draft then schedules it.
    send_time format: "2026-07-14 08:03"

    NOTE: Gmail API does not natively support scheduled sending.
    We create the draft + return its ID. The master script
    will handle actual timing using Python's sleep/scheduler.
    """
    message = build_message(to, subject, body)
    draft = service.users().drafts().create(
        userId="me", body={"message": message}
    ).execute()
    return draft["id"]


def setup_account(account_id: int):
    """Interactive first-time OAuth setup for an account."""
    print(f"\n{'='*50}")
    print(f"Setting up Gmail Account {account_id}")
    print(f"{'='*50}")
    account_email = f"pragatichothe00{account_id}@gmail.com"
    print(f"Account email: {account_email}")
    print("\nA browser window will open. Please log in with this account.")
    print("If wrong account opens, log out of Gmail in browser first.\n")
    input("Press Enter to open browser...")

    creds = get_credentials(account_id)
    service = build("gmail", "v1", credentials=creds)
    profile = service.users().getProfile(userId="me").execute()
    print(f"\nSuccess! Authenticated as: {profile['emailAddress']}")
    print(f"Token saved in: {CREDS_DIR}/token_acc{account_id}.json")


def test_connection(account_id: int):
    """Tests that credentials work by fetching account profile."""
    creds = get_credentials(account_id)
    service = build("gmail", "v1", credentials=creds)
    profile = service.users().getProfile(userId="me").execute()
    print(f"Account {account_id} connected: {profile['emailAddress']}")
    return service


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gmail OAuth Setup & Test")
    parser.add_argument("action", choices=["setup", "test"], help="Action to perform")
    parser.add_argument("--account", type=int, choices=[1, 2], required=True)
    args = parser.parse_args()

    os.makedirs(CREDS_DIR, exist_ok=True)

    if args.action == "setup":
        setup_account(args.account)
    elif args.action == "test":
        test_connection(args.account)
