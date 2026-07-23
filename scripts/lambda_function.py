"""
lambda_function.py
=================
AWS Lambda function — triggered by EventBridge every 3 minutes (8–11 AM IST).

What it does each trigger:
  1. Reads 1 message from SQS queue acc1 → sends via Gmail acc1
  2. Reads 1 message from SQS queue acc2 → sends via Gmail acc2
  3. Deletes from SQS only after confirmed send

Deployment:
  - Runtime : Python 3.12
  - Handler : lambda_function.lambda_handler
  - Timeout : 60 seconds
  - Memory  : 128 MB
  - Layer   : google-auth, google-auth-httplib2, google-api-python-client

Environment variables (set in Lambda console):
  SQS_QUEUE_ACC1      = https://sqs.ap-south-1.amazonaws.com/<id>/sebi-mailer-acc1
  SQS_QUEUE_ACC2      = https://sqs.ap-south-1.amazonaws.com/<id>/sebi-mailer-acc2
  AWS_REGION_NAME     = ap-south-1
  ACC1_REFRESH_TOKEN  = (from token_acc1.json → refresh_token field)
  ACC1_CLIENT_ID      = (from token_acc1.json → client_id field)
  ACC1_CLIENT_SECRET  = (from token_acc1.json → client_secret field)
  ACC2_REFRESH_TOKEN  = (from token_acc2.json → refresh_token field)
  ACC2_CLIENT_ID      = (from token_acc2.json → client_id field)
  ACC2_CLIENT_SECRET  = (from token_acc2.json → client_secret field)
"""

import os
import json
import base64
import logging
from email.mime.text import MIMEText

import boto3
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ── Config ────────────────────────────────────────────────────────────────────
REGION        = os.environ.get("AWS_REGION_NAME", "ap-south-1")
SQS_URL_ACC1  = os.environ["SQS_QUEUE_ACC1"]
SQS_URL_ACC2  = os.environ["SQS_QUEUE_ACC2"]

TOKEN_URI = "https://oauth2.googleapis.com/token"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.settings.basic",
]

# Gmail credentials from environment variables (no Secrets Manager needed)
GMAIL_CREDS = {
    1: {
        "refresh_token": os.environ["ACC1_REFRESH_TOKEN"],
        "client_id":     os.environ["ACC1_CLIENT_ID"],
        "client_secret": os.environ["ACC1_CLIENT_SECRET"],
    },
    2: {
        "refresh_token": os.environ["ACC2_REFRESH_TOKEN"],
        "client_id":     os.environ["ACC2_CLIENT_ID"],
        "client_secret": os.environ["ACC2_CLIENT_SECRET"],
    },
}

# ── AWS client ────────────────────────────────────────────────────────────────
sqs_client = boto3.client("sqs", region_name=REGION)


# ══════════════════════════════════════════════════════════════════════════════
# GMAIL AUTH
# ══════════════════════════════════════════════════════════════════════════════

def get_gmail_service(account_id: int):
    """
    Builds authenticated Gmail service using refresh token from env vars.
    No Secrets Manager, no browser — just the stored refresh token.
    """
    creds_data = GMAIL_CREDS[account_id]

    creds = Credentials(
        token         = None,   # no cached access token — will fetch fresh one
        refresh_token = creds_data["refresh_token"],
        token_uri     = TOKEN_URI,
        client_id     = creds_data["client_id"],
        client_secret = creds_data["client_secret"],
        scopes        = SCOPES,
    )

    # Always refresh to get a valid access token
    creds.refresh(Request())
    logger.info(f"acc{account_id}: access token refreshed OK")

    return build("gmail", "v1", credentials=creds)


# ══════════════════════════════════════════════════════════════════════════════
# EMAIL SENDING
# ══════════════════════════════════════════════════════════════════════════════

def build_raw_message(to: str, subject: str, body: str) -> dict:
    message            = MIMEText(body, "html")
    message["to"]      = to
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return {"raw": raw}


def send_one_email(service, email_data: dict) -> str:
    """Sends email via Gmail API. Returns Gmail message ID."""
    msg  = build_raw_message(email_data["to"], email_data["subject"], email_data["body"])
    sent = service.users().messages().send(userId="me", body=msg).execute()
    return sent["id"]


# ══════════════════════════════════════════════════════════════════════════════
# SQS
# ══════════════════════════════════════════════════════════════════════════════

def poll_sqs(queue_url: str) -> tuple:
    """Returns (email_dict, receipt_handle) or (None, None) if queue is empty."""
    response = sqs_client.receive_message(
        QueueUrl            = queue_url,
        MaxNumberOfMessages = 1,
        WaitTimeSeconds     = 2,
    )
    messages = response.get("Messages", [])
    if not messages:
        return None, None

    msg = messages[0]
    return json.loads(msg["Body"]), msg["ReceiptHandle"]


def delete_sqs_message(queue_url: str, receipt_handle: str):
    sqs_client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def process_account(queue_url: str, account_id: int, label: str) -> dict:
    """
    One full cycle for one Gmail account:
      SQS poll → build Gmail service → send → delete from SQS
    """
    result = {"account": label, "status": "no_messages"}

    # Step 1: Get next email from SQS
    email_data, receipt_handle = poll_sqs(queue_url)
    if email_data is None:
        logger.info(f"{label}: queue empty — nothing to send")
        return result

    logger.info(f"{label}: dequeued → {email_data.get('company')} ({email_data.get('to')})")

    # Step 2: Build Gmail service from env var credentials
    try:
        service = get_gmail_service(account_id)
    except Exception as e:
        logger.error(f"{label}: auth error — {e}")
        result.update({"status": "auth_error", "error": str(e)})
        return result   # leave in SQS for retry next trigger

    # Step 3: Send email
    try:
        gmail_msg_id = send_one_email(service, email_data)
        logger.info(f"{label}: sent ✓  Gmail ID: {gmail_msg_id}")
    except HttpError as e:
        logger.error(f"{label}: Gmail send failed — {e}")
        result.update({"status": "send_error", "error": str(e)})
        return result   # leave in SQS for retry next trigger

    # Step 4: Delete from SQS only after confirmed send
    delete_sqs_message(queue_url, receipt_handle)
    logger.info(f"{label}: deleted from SQS ✓")

    result.update({
        "status":     "sent",
        "to":         email_data.get("to"),
        "company":    email_data.get("company"),
        "message_id": gmail_msg_id,
    })
    return result


def lambda_handler(event, context):
    """Entry point. Triggered by EventBridge every 3 minutes, 8–11 AM IST."""
    logger.info("Lambda triggered — processing one email per account")

    result_acc1 = process_account(SQS_URL_ACC1, account_id=1, label="acc1")
    result_acc2 = process_account(SQS_URL_ACC2, account_id=2, label="acc2")

    summary = {"acc1": result_acc1, "acc2": result_acc2}
    logger.info(f"Summary: {json.dumps(summary)}")
    return summary