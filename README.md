# 🧾 Financial Analyzer

A Streamlit app for analyzing multi-company financial statements from PDF, CSV, or Excel.

## Features

- Supports Income, Cash Flow Statements
- PDF + Excel/CSV upload
- Multi-year trend charts
- Multi-company comparison

## Run Locally

```bash
docker build -t financial-analyzer .
docker run -p 8501:8501 financial-analyzer
```

## Daily Portfolio Brief

A scheduled email digest of news (last 24h), SEC filings (last 2d), and upcoming earnings (within 7d) for the tickers in [app/portfolio.json](app/portfolio.json).

### One-time setup

1. **Gmail app password**: Google Account → Security → 2-Step Verification → App passwords → create one.
2. **GitHub repo secrets** (Settings → Secrets and variables → Actions):
   - `GMAIL_USER` — your gmail address (also used as the SEC `User-Agent`)
   - `GMAIL_APP_PASSWORD` — the 16-char app password from step 1
   - `RECIPIENT_EMAIL` — where to send the brief
3. **Trigger a test run**: Actions tab → "Daily Brief" → "Run workflow".

The scheduled run fires at 11:30 UTC Mon–Fri (~6:30–7:30 AM ET).

### Local test

```bash
# Preview the HTML without sending
python app/daily_brief.py --dry-run > /tmp/brief.html && open /tmp/brief.html

# Send to yourself
export GMAIL_USER=you@gmail.com GMAIL_APP_PASSWORD=xxxx RECIPIENT_EMAIL=you@gmail.com
python app/daily_brief.py
```