import yfinance as yf
from yahooquery import Ticker, search

def get_financials(ticker):
    try:
        stock = yf.Ticker(ticker)
        return {
            "income": stock.financials.T,
            "balance": stock.balance_sheet.T,
            "cashflow": stock.cashflow.T
        }
    except Exception as e:
        return {"error": str(e)}

def get_company_overview(ticker):
    try:
        yq = Ticker(ticker)
        profile = yq.summary_profile.get(ticker, {})
        info = yq.quote_type.get(ticker, {})
        return {
            "name": info.get("longName", ticker),
            "symbol": ticker,
            "industry": profile.get("industry", "N/A"),
            "sector": profile.get("sector", "N/A"),
            "summary": profile.get("longBusinessSummary", "No description available."),
            "website": profile.get("website", ""),
            "marketCap": yq.price[ticker].get("marketCap", None)
        }
    except Exception as e:
        return {"error": str(e)}

def get_ticker_from_company_name(company_name):
    try:
        results = search(company_name)
        for result in results['quotes']:
            if result.get("quoteType") == "EQUITY":
                return result.get("symbol"), result.get("shortname", company_name)
    except Exception as e:
        return None, None
    return None, None