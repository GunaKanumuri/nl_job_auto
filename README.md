# 🇳🇱 NL Job Hunter

Autonomous Netherlands job search agent. Runs daily on GitHub Actions for free. Scrapes 120+ companies, scores with Gemini AI, emails you the results.

## Setup (30 minutes)

### 1. Create GitHub repo

```bash
git init nl-job-hunter
cd nl-job-hunter
# Copy all files here
git add .
git commit -m "initial"
git remote add origin git@github.com:GunaKanumuri/nl-job-hunter.git
git push -u origin main
```

### 2. Gmail App Password

You need an App Password (not your regular Gmail password):

1. Go to https://myaccount.google.com/apppasswords
2. Generate a new app password for "Mail"
3. Copy the 16-character password

### 3. Google Sheet setup

1. Create a new Google Sheet
2. Name the first tab `Jobs`
3. Add headers in Row 1:
   ```
   Company | Title | Location | URL | Source | Fit Score | Stack Match | Seniority Fit | Visa Friendly | Match Reasons | Cold Email Hook | Subject Line | Hiring Manager | Dedup Hash | Date | Status
   ```
4. Create a Google Cloud service account:
   - Go to https://console.cloud.google.com
   - Create project → Enable Google Sheets API
   - Create Service Account → Download JSON key
   - Share your Google Sheet with the service account email (Editor access)
5. Copy the Sheet ID from the URL: `docs.google.com/spreadsheets/d/THIS_IS_THE_ID/edit`

### 4. Add GitHub Secrets

Go to your repo → Settings → Secrets and variables → Actions → New repository secret:

| Secret Name | Value |
|---|---|
| `GEMINI_API_KEY` | Your Gemini API key from https://aistudio.google.com/apikey |
| `GMAIL_ADDRESS` | `gunakanumuri5@gmail.com` |
| `GMAIL_APP_PASSWORD` | The 16-char app password from step 2 |
| `GOOGLE_SHEET_ID` | The sheet ID from step 3 |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | The entire JSON content of the service account key file |

### 5. Activate

Push to GitHub. The workflow runs automatically every day at 8am CET.

To test immediately: Go to Actions tab → "NL Job Hunter — Daily" → Run workflow.

## What you get every morning

An email with:
- Top 10 high-fit jobs (score ≥ 7/10) with apply links
- For each job: a personalized cold email opener, subject line, and the exact hiring manager title to search on LinkedIn (with a direct LinkedIn search link)
- Visa friendliness indicator
- All jobs also saved to your Google Sheet

## Files

```
nl-job-hunter/
├── job_hunter.py              # Main script (one file, ~400 lines)
├── requirements.txt           # Python deps
├── README.md                  # This file
└── .github/
    └── workflows/
        └── daily-hunt.yml     # GitHub Actions cron
```

## Cost

$0. Forever.
- GitHub Actions: ~4 min/day × 30 days = 120 min/month (free tier: 2,000 min)
- Gemini API: ~25 calls/day × 30 = 750 calls/month (free tier: 1,500 RPD)
- Gmail SMTP: free
- Google Sheets API: free

## Adding more companies

Edit `GREENHOUSE_COMPANIES` or `LEVER_COMPANIES` in `job_hunter.py`. Format:
```python
("company-slug", "Company Name"),
```

To find a company's slug:
- Greenhouse: check `boards.greenhouse.io/SLUG` or `boards-api.greenhouse.io/v1/boards/SLUG/jobs`
- Lever: check `jobs.lever.co/SLUG` or `api.lever.co/v0/postings/SLUG`
