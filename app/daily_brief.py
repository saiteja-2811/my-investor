"""Daily portfolio brief: news + SEC filings + upcoming earnings for the holdings in portfolio.json."""
from __future__ import annotations

import argparse
import json
import os
import smtplib
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parsedate_to_datetime
from html import escape
from pathlib import Path

import yfinance as yf

PORTFOLIO_PATH = Path(__file__).parent / "portfolio.json"

# SEC CIKs (verified against https://www.sec.gov/files/company_tickers.json).
# SKHYY is an unsponsored ADR with no SEC filings — intentionally omitted.
CIK_MAP = {
    "AVGO": "0001730168",
    "GOOGL": "0001652044",
    "MU": "0000723125",
    "INTC": "0000050863",
    "NVDA": "0001045810",
    "DELL": "0001571996",
    "TXN": "0000097476",
    "TSM": "0001046179",
}

INTERESTING_FORMS = {"8-K", "10-Q", "10-K", "6-K", "20-F", "SC 13D", "SC 13G", "SC 13D/A", "SC 13G/A"}

# SEC requires a descriptive User-Agent identifying the requester.
SEC_USER_AGENT = os.environ.get("SEC_USER_AGENT", "my-investor-brief contact@example.com")

# Human-readable names used in the news query (Google News is keyword-based).
NEWS_QUERY = {
    "AVGO": "Broadcom AVGO",
    "000660.KS": "SK Hynix",
    "TSM": "TSMC",
    "GOOGL": "Alphabet Google GOOGL",
    "MU": "Micron MU",
    "INTC": "Intel INTC",
    "NVDA": "Nvidia NVDA",
    "DELL": "Dell Technologies DELL",
    "TXN": "Texas Instruments TXN",
}

NEWS_LOOKBACK_HOURS = 24
FILING_LOOKBACK_DAYS = 2
EARNINGS_LOOKAHEAD_DAYS = 7


def load_tickers() -> list[str]:
    with PORTFOLIO_PATH.open() as f:
        return json.load(f)["tickers"]


def fetch_news(ticker: str) -> list[dict]:
    """Query Google News RSS for the ticker and return items from the last NEWS_LOOKBACK_HOURS.
    Yahoo's news endpoint (used by yfinance) was returning empty / broken at build time."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=NEWS_LOOKBACK_HOURS)
    query = NEWS_QUERY.get(ticker, ticker)
    url = (
        "https://news.google.com/rss/search?"
        + urllib.parse.urlencode({"q": f"{query} stock", "hl": "en-US", "gl": "US", "ceid": "US:en"})
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15, context=_ssl_context()) as resp:
        body = resp.read()
    root = ET.fromstring(body)
    out = []
    for item in root.findall(".//item"):
        title = item.findtext("title") or ""
        link = item.findtext("link") or ""
        pub_date_str = item.findtext("pubDate")
        publisher = item.findtext("source") or "Google News"
        if not (title and link and pub_date_str):
            continue
        try:
            pub_time = parsedate_to_datetime(pub_date_str)
        except (TypeError, ValueError):
            continue
        if pub_time.tzinfo is None:
            pub_time = pub_time.replace(tzinfo=timezone.utc)
        if pub_time < cutoff:
            continue
        out.append({"title": title, "link": link, "publisher": publisher, "time": pub_time})
    return sorted(out, key=lambda x: x["time"], reverse=True)[:10]


def _ssl_context() -> ssl.SSLContext:
    """SSL context that prefers certifi's CA bundle when available (fixes some
    pyenv/Python-3.13 installs that lack system certs)."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def fetch_filings(ticker: str) -> list[dict]:
    """Return recent filings from SEC EDGAR submissions API."""
    cik = CIK_MAP.get(ticker)
    if not cik:
        return []
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    req = urllib.request.Request(url, headers={"User-Agent": SEC_USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15, context=_ssl_context()) as resp:
        data = json.load(resp)
    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])

    cutoff = (datetime.now(timezone.utc) - timedelta(days=FILING_LOOKBACK_DAYS)).date()
    out = []
    for form, date_str, accession, _doc in zip(forms, dates, accessions, primary_docs):
        try:
            filed = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            continue
        if filed < cutoff:
            continue
        acc_no_dashes = accession.replace("-", "")
        filing_index = (
            f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
            f"&CIK={cik}&type={form}&dateb=&owner=include&count=10"
        )
        filing_doc = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_no_dashes}/"
        out.append({
            "form": form,
            "date": filed,
            "url": filing_doc,
            "index_url": filing_index,
            "interesting": form in INTERESTING_FORMS,
        })
    return out


def fetch_upcoming_earnings(ticker: str) -> datetime | None:
    """Return next earnings date if within EARNINGS_LOOKAHEAD_DAYS, else None."""
    try:
        cal = yf.Ticker(ticker).calendar
    except Exception:
        return None
    if cal is None:
        return None
    # yfinance returns dict in newer versions, DataFrame in older ones.
    dates = None
    if isinstance(cal, dict):
        dates = cal.get("Earnings Date")
    else:
        try:
            dates = cal.loc["Earnings Date"].tolist() if "Earnings Date" in cal.index else None
        except Exception:
            dates = None
    if not dates:
        return None
    if not isinstance(dates, list):
        dates = [dates]
    today = datetime.now(timezone.utc).date()
    horizon = today + timedelta(days=EARNINGS_LOOKAHEAD_DAYS)
    for d in dates:
        try:
            dt = d if hasattr(d, "year") else datetime.fromisoformat(str(d)).date()
        except (ValueError, TypeError):
            continue
        if today <= dt <= horizon:
            return dt
    return None


def collect(ticker: str) -> dict:
    """Pull everything for one ticker. Isolate errors so one bad ticker doesn't kill the brief."""
    result: dict = {"ticker": ticker, "errors": []}
    try:
        result["news"] = fetch_news(ticker)
    except Exception as e:
        result["news"] = []
        result["errors"].append(f"news: {e}")
    try:
        result["filings"] = fetch_filings(ticker)
    except Exception as e:
        result["filings"] = []
        result["errors"].append(f"filings: {e}")
    try:
        result["earnings"] = fetch_upcoming_earnings(ticker)
    except Exception as e:
        result["earnings"] = None
        result["errors"].append(f"earnings: {e}")
    return result


def render_html(sections: list[dict]) -> str:
    today = datetime.now(timezone.utc).strftime("%A, %B %d, %Y")
    parts = [f"""<!DOCTYPE html>
<html><body style="font-family: -apple-system, Segoe UI, sans-serif; max-width: 720px; margin: auto; color: #222;">
<h1 style="border-bottom: 2px solid #0a66c2; padding-bottom: 8px;">Portfolio Brief — {today}</h1>
<p style="color: #555; font-size: 13px;">News from the last {NEWS_LOOKBACK_HOURS}h · SEC filings from the last {FILING_LOOKBACK_DAYS}d · Earnings within {EARNINGS_LOOKAHEAD_DAYS}d</p>
"""]
    error_blobs = []
    for sec in sections:
        t = sec["ticker"]
        parts.append(f'<h2 style="margin-top: 28px; color: #0a66c2;">{t}</h2>')

        if sec["earnings"]:
            parts.append(
                f'<p style="background: #fff8e1; padding: 8px 12px; border-left: 4px solid #f5a623; margin: 8px 0;">'
                f'⏰ <strong>Earnings on {sec["earnings"].strftime("%a %b %d")}</strong></p>'
            )

        if sec["filings"]:
            parts.append('<p style="margin: 10px 0 4px; font-weight: 600;">SEC filings</p><ul style="margin: 0 0 8px; padding-left: 20px;">')
            for f in sec["filings"]:
                marker = "📄 " if f["interesting"] else ""
                parts.append(
                    f'<li>{marker}<strong>{escape(f["form"])}</strong> · {f["date"]} · '
                    f'<a href="{escape(f["url"])}">filing</a></li>'
                )
            parts.append("</ul>")

        if sec["news"]:
            parts.append('<p style="margin: 10px 0 4px; font-weight: 600;">News</p><ul style="margin: 0 0 8px; padding-left: 20px;">')
            for n in sec["news"]:
                when = n["time"].strftime("%H:%M UTC")
                parts.append(
                    f'<li><a href="{escape(n["link"])}">{escape(n["title"])}</a> '
                    f'<span style="color: #777; font-size: 12px;">— {escape(n["publisher"])} · {when}</span></li>'
                )
            parts.append("</ul>")

        if not sec["earnings"] and not sec["filings"] and not sec["news"]:
            parts.append('<p style="color: #999; font-style: italic;">No updates.</p>')

        if sec["errors"]:
            error_blobs.append(f"{t}: {'; '.join(sec['errors'])}")

    if error_blobs:
        parts.append('<hr><p style="color: #a94442; font-size: 12px;"><strong>⚠️ Fetch errors:</strong></p><ul style="color: #a94442; font-size: 12px;">')
        for e in error_blobs:
            parts.append(f"<li>{escape(e)}</li>")
        parts.append("</ul>")

    parts.append("</body></html>")
    return "\n".join(parts)


def send_email(html: str) -> None:
    user = os.environ["GMAIL_USER"]
    password = os.environ["GMAIL_APP_PASSWORD"]
    recipient = os.environ["RECIPIENT_EMAIL"]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Portfolio Brief — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
    msg["From"] = user
    msg["To"] = recipient
    msg.attach(MIMEText(html, "html"))

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(user, password)
        server.sendmail(user, [recipient], msg.as_string())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print HTML to stdout instead of emailing.")
    args = parser.parse_args()

    tickers = load_tickers()
    sections = [collect(t) for t in tickers]
    html = render_html(sections)

    if args.dry_run:
        sys.stdout.write(html)
        return 0

    send_email(html)
    print(f"Sent brief for {len(tickers)} tickers.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
