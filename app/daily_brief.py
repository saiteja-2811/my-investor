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

try:
    from google import genai  # optional — summaries are skipped if the SDK or key is missing
except ImportError:
    genai = None

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
DEALS_LOOKBACK_HOURS = 72  # wider window — deal announcements are rarer

# Keyword clusters used to detect AI-related deal/partnership news.
# A story counts as an "AI deal" if its title matches at least one DEAL_KEYWORD
# AND at least one AI_KEYWORD. (We also keep stories that explicitly name a
# major AI company via AI_COMPANY_KEYWORDS even without an AI_KEYWORD hit.)
DEAL_KEYWORDS = (
    "deal", "partnership", "partners with", "collaborat", "agreement",
    "contract", "acquisition", "acquires", "to acquire", "merger",
    "investment", "invests", "stake", "joint venture", "jv",
    "supply agreement", "licensing", "strategic alliance",
)
AI_KEYWORDS = (
    "ai ", " ai", "artificial intelligence", "generative ai", "genai",
    "llm", "foundation model", "machine learning", "gpu", "accelerator",
    "data center", "datacenter", "inference", "training cluster",
)
AI_COMPANY_KEYWORDS = (
    "openai", "anthropic", "microsoft", "google", "alphabet", "meta",
    "amazon", "aws", "oracle", "xai", "mistral", "cohere", "perplexity",
    "databricks", "scale ai", "huggingface", "hugging face", "stability ai",
    "coreweave", "lambda labs", "together ai", "cerebras", "groq",
    "tesla", "apple", "nvidia", "amd", "arm",
)


def load_tickers() -> list[str]:
    with PORTFOLIO_PATH.open() as f:
        return json.load(f)["tickers"]


def _google_news(query: str, cutoff: datetime) -> list[dict]:
    """Hit Google News RSS for a query, return items newer than cutoff."""
    url = (
        "https://news.google.com/rss/search?"
        + urllib.parse.urlencode({"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"})
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
    return out


def fetch_news(ticker: str) -> list[dict]:
    """General news for the ticker from the last NEWS_LOOKBACK_HOURS."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=NEWS_LOOKBACK_HOURS)
    query = NEWS_QUERY.get(ticker, ticker)
    items = _google_news(f"{query} stock", cutoff)
    return sorted(items, key=lambda x: x["time"], reverse=True)[:10]


def fetch_ai_deals(ticker: str) -> list[dict]:
    """Find deal/partnership stories involving AI companies for this ticker.
    Casts a wider net (72h) and uses a targeted query, then filters by keyword
    presence so we don't surface generic 'AI stock' noise."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=DEALS_LOOKBACK_HOURS)
    base = NEWS_QUERY.get(ticker, ticker)
    # Query asks for the company name together with any one of several deal
    # or AI-partner keywords. Google News honors OR with "|".
    deal_query = (
        f'{base} (deal OR partnership OR acquisition OR invest OR collaboration '
        f'OR agreement OR OpenAI OR Anthropic OR Microsoft OR Google OR Meta '
        f'OR Oracle OR xAI OR CoreWeave)'
    )
    items = _google_news(deal_query, cutoff)
    scored = []
    for n in items:
        title_lower = n["title"].lower()
        has_deal = any(k in title_lower for k in DEAL_KEYWORDS)
        has_ai = any(k in title_lower for k in AI_KEYWORDS)
        has_ai_co = any(k in title_lower for k in AI_COMPANY_KEYWORDS)
        # Keep if: it's a deal-shaped headline that mentions AI or an AI company,
        # OR it names an AI company AND some deal-shaped language.
        if (has_deal and (has_ai or has_ai_co)) or (has_ai_co and has_deal):
            scored.append(n)
    return sorted(scored, key=lambda x: x["time"], reverse=True)[:5]


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
    try:
        result["ai_deals"] = fetch_ai_deals(ticker)
    except Exception as e:
        result["ai_deals"] = []
        result["errors"].append(f"ai_deals: {e}")
    return result


SUMMARY_SYSTEM = (
    "You are a terse equity analyst writing a pre-market brief. "
    "Given a stock ticker and today's headlines, filings, and any AI-partnership "
    "deals for it, write 2-3 sentences a long-term holder actually cares about: "
    "material events only (deals, M&A, earnings beats/misses, guidance changes, "
    "regulatory, management changes). Skip generic market commentary and price "
    "movement. If nothing material happened, say exactly: \"No material updates.\" "
    "No bullet points, no preamble, no sign-off."
)


def _summary_input(sec: dict) -> str:
    """Compact text payload sent to the LLM for one ticker."""
    lines = [f"Ticker: {sec['ticker']}"]
    if sec.get("earnings"):
        lines.append(f"Earnings scheduled: {sec['earnings'].strftime('%Y-%m-%d')}")
    if sec.get("ai_deals"):
        lines.append("AI deal/partnership headlines (last 72h):")
        for n in sec["ai_deals"]:
            lines.append(f"  - [{n['publisher']}] {n['title']}")
    if sec.get("filings"):
        lines.append("Recent SEC filings:")
        for f in sec["filings"]:
            lines.append(f"  - {f['form']} on {f['date']}")
    if sec.get("news"):
        lines.append("General news headlines (last 24h):")
        for n in sec["news"][:8]:
            lines.append(f"  - [{n['publisher']}] {n['title']}")
    return "\n".join(lines)


def generate_summaries(sections: list[dict]) -> None:
    """Add a `summary` string to each section in place using Gemini.
    No-op if the google-genai SDK isn't installed or GEMINI_API_KEY isn't set.
    Honors SUMMARY_MODEL (defaults to gemini-3.8-flash)."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not genai or not api_key:
        return
    client = genai.Client(api_key=api_key)
    model = (os.environ.get("SUMMARY_MODEL") or "gemini-3.8-flash").strip() or "gemini-3.8-flash"
    print(f"[diag] gemini model resolved to {model!r}")
    for sec in sections:
        has_signal = sec.get("news") or sec.get("ai_deals") or sec.get("filings") or sec.get("earnings")
        if not has_signal:
            sec["summary"] = "No material updates."
            continue
        try:
            resp = client.models.generate_content(
                model=model,
                contents=[SUMMARY_SYSTEM, _summary_input(sec)],
            )
            sec["summary"] = (resp.text or "").strip()
        except Exception as e:
            sec["errors"].append(f"summary: {type(e).__name__}: {str(e)[:200]}")


def render_html(sections: list[dict]) -> str:
    today = datetime.now(timezone.utc).strftime("%A, %B %d, %Y")
    parts = [f"""<!DOCTYPE html>
<html><body style="font-family: -apple-system, Segoe UI, sans-serif; max-width: 720px; margin: auto; color: #222;">
<h1 style="border-bottom: 2px solid #0a66c2; padding-bottom: 8px;">Portfolio Brief — {today}</h1>
<p style="color: #555; font-size: 13px;">News from the last {NEWS_LOOKBACK_HOURS}h · AI deals from the last {DEALS_LOOKBACK_HOURS}h · SEC filings from the last {FILING_LOOKBACK_DAYS}d · Earnings within {EARNINGS_LOOKAHEAD_DAYS}d</p>
"""]
    error_blobs = []
    for sec in sections:
        t = sec["ticker"]
        parts.append(f'<h2 style="margin-top: 28px; color: #0a66c2;">{t}</h2>')

        if sec.get("summary"):
            parts.append(
                '<p style="background: #f6f8fa; padding: 10px 14px; border-left: 4px solid #0a66c2; '
                'margin: 8px 0; font-size: 14px; line-height: 1.5;">'
                f'<strong>Today:</strong> {escape(sec["summary"])}</p>'
            )

        if sec["earnings"]:
            parts.append(
                f'<p style="background: #fff8e1; padding: 8px 12px; border-left: 4px solid #f5a623; margin: 8px 0;">'
                f'⏰ <strong>Earnings on {sec["earnings"].strftime("%a %b %d")}</strong></p>'
            )

        if sec.get("ai_deals"):
            parts.append(
                '<p style="margin: 10px 0 4px; font-weight: 600;">🤝 Deals & AI partnerships</p>'
                '<ul style="margin: 0 0 8px; padding-left: 20px; background: #f0f7ff; border-left: 3px solid #0a66c2; padding: 8px 8px 8px 28px;">'
            )
            for n in sec["ai_deals"]:
                when = n["time"].strftime("%b %d %H:%M UTC")
                parts.append(
                    f'<li><a href="{escape(n["link"])}">{escape(n["title"])}</a> '
                    f'<span style="color: #777; font-size: 12px;">— {escape(n["publisher"])} · {when}</span></li>'
                )
            parts.append("</ul>")

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

        if not sec["earnings"] and not sec["filings"] and not sec["news"] and not sec.get("ai_deals"):
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
    generate_summaries(sections)
    html = render_html(sections)

    if args.dry_run:
        sys.stdout.write(html)
        return 0

    send_email(html)
    print(f"Sent brief for {len(tickers)} tickers.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
