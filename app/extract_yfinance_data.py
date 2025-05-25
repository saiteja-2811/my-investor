import yfinance as yf

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