# SEBI Accessibility Email Pipeline — Setup Guide

## What this system does
One command → scans websites → generates personalized emails → sends via Gmail → marks Excel as done.

---

## STEP 1 — Install Python (if not already installed)
1. Go to https://www.python.org/downloads/
2. Download Python 3.11 or newer
3. During install, **tick "Add Python to PATH"** (important!)
4. Open Command Prompt and run: `python --version`
   - You should see something like `Python 3.11.x`

---

## STEP 2 — Copy this project folder to your Windows PC
Copy the entire `sebi_mailer` folder to somewhere easy, like:
```
C:\Users\pragati_c19\sebi_mailer\
```

---

## STEP 3 — Install required Python libraries
Open Command Prompt, paste this and press Enter:
```
pip install openpyxl pandas google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client
```
Wait for it to finish (may take 1-2 minutes).

---

## STEP 4 — Gmail API Setup (do this ONCE, takes ~15 minutes)

### 4a. Create a Google Cloud Project
1. Go to: https://console.cloud.google.com/
2. Sign in with **any** Google account (doesn't have to be pragatichothe001)
3. Click the project dropdown at the top → **New Project**
4. Name it: `sebi-mailer` → click **Create**

### 4b. Enable Gmail API
1. In the search bar, type `Gmail API` → click on it
2. Click **Enable**

### 4c. Create OAuth Credentials
1. Go to: **APIs & Services → Credentials**
2. Click **+ Create Credentials → OAuth client ID**
3. If asked for consent screen first:
   - User Type: **External** → Create
   - App name: `SEBI Mailer`
   - Support email: your email
   - Click **Save and Continue** through all steps
   - On Scopes page → click **Save and Continue** (skip scopes here)
   - On Test Users page → Add both your Gmail addresses:
     - pragatichothe001@gmail.com
     - pragatichothe002@gmail.com
   - Click **Save and Continue → Back to Dashboard**
4. Now go back to **Credentials → + Create Credentials → OAuth client ID**
5. Application type: **Desktop app**
6. Name: `SEBI Mailer Desktop`
7. Click **Create**
8. Click **Download JSON**
9. Rename the downloaded file to: `client_secret.json`
10. Place it in: `C:\Users\pragati_c19\sebi_mailer\credentials\client_secret.json`

### 4d. Authenticate both Gmail accounts
Open Command Prompt, navigate to the scripts folder:
```
cd C:\Users\pragati_c19\sebi_mailer\scripts
```

Authenticate Account 1:
```
python gmail_sender.py setup --account 1
```
→ Browser opens → Log in with **pragatichothe001@gmail.com** → Allow access

Authenticate Account 2:
```
python gmail_sender.py setup --account 2
```
→ Browser opens → Log in with **pragatichothe002@gmail.com** → Allow access

You should see: `Token saved in: .../credentials/token_acc1.json` (and acc2)

---

## STEP 5 — Prepare your Excel file

### Add the `website_url` column
1. Open `purged_sebi_accessibility_leads.xlsx`
2. Add a new column called `website_url`
3. For each company, paste their actual website URL (e.g., `https://www.unificap.com`)
   - Tip: Start with `=CONCAT("https://www.",[@[email_domain]])` as a first guess, then fix wrong ones
4. Add a new column called `status`
5. For all rows, set the value to `pending`
6. Save the file as `leads.xlsx` in `C:\Users\pragati_c19\sebi_mailer\data\`

---

## STEP 6 — Test with dummy data first

```
cd C:\Users\pragati_c19\sebi_mailer\scripts

python run_pipeline.py --account 1 --no-scan --dry-run
```

This will print 3 sample emails without sending anything. Verify they look correct.

---

## STEP 7 — Run for real

### Every day workflow:

**Morning (Account 1 — pragatichothe001):**
```
cd C:\Users\pragati_c19\sebi_mailer\scripts
python run_pipeline.py --account 1
```

**Then for Account 2 — pragatichothe002:**
```
python run_pipeline.py --account 2
```

The script will:
1. Pick the next 30 pending companies
2. Update scan.sh and run accessibility scans
3. Generate personalized emails
4. Send them from 8:00 AM with random 1-5 min gaps
5. Mark each company as `sent` in your Excel

---

## STEP 8 — Switch from dummy data to real data

In `run_pipeline.py`, find these two lines near the top and update them:
```python
EXCEL_PATH  = os.path.join(BASE_DIR, "data", "dummy_leads.xlsx")
REPORT_PATH = os.path.join(BASE_DIR, "data", "dummy_accessibility_report.txt")
```
Change to:
```python
EXCEL_PATH  = os.path.join(BASE_DIR, "data", "leads.xlsx")
REPORT_PATH = os.path.join(BASE_DIR, "data", "accessibility-report.txt")
```

Also change:
```python
BATCH_SIZE = 3    →    BATCH_SIZE = 30
DRY_RUN    = True →    DRY_RUN    = False
```

---

## Folder Structure
```
sebi_mailer/
├── credentials/
│   ├── client_secret.json     ← you download this from Google Cloud
│   ├── token_acc1.json        ← auto-created after setup
│   └── token_acc2.json        ← auto-created after setup
├── data/
│   ├── dummy_leads.xlsx       ← test data
│   ├── dummy_accessibility_report.txt ← test report
│   └── leads.xlsx             ← your real data (you add this)
├── scripts/
│   ├── run_pipeline.py        ← THE MAIN SCRIPT (run this daily)
│   ├── parse_report.py        ← reads accessibility report
│   ├── generate_emails.py     ← fills email template
│   └── gmail_sender.py        ← handles Gmail OAuth + sending
├── scan.sh                    ← auto-updated by pipeline
└── SETUP_GUIDE.md             ← this file
```

---

## Troubleshooting

**"bash not found" on Windows:**
Install Git for Windows: https://git-scm.com/download/win
It includes Git Bash which runs .sh files.

**"client_secret.json not found":**
Make sure you placed it in `sebi_mailer/credentials/` (not the scripts folder).

**Browser doesn't open for OAuth:**
Run the setup command again. If it still fails, copy the URL it prints and paste it manually in your browser.

**Email not sending:**
First run with `--dry-run` to check emails look right.
Then check Gmail API is enabled in Google Cloud Console.
