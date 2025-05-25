import streamlit as st
import matplotlib.pyplot as plt
import pandas as pd
import re
from financial_parser import extract_tables_from_pdf, find_financial_metric, read_data
from extract_yfinance_data import get_financials
from report_generator import generate_recommendation_report

st.set_page_config(page_title="Financial Analyzer", layout="wide")
st.title("📈 Multi-Company Financial Analyzer")

# Sidebar for ticker input
st.sidebar.header("📡 Ticker-Based Lookup")
tickers = st.sidebar.text_input("Enter stock tickers (comma-separated)", value="AAPL,MSFT")
yf_data = {}

if st.sidebar.button("Fetch Financials"):
    for ticker in tickers.split(","):
        ticker = ticker.strip().upper()
        result = get_financials(ticker)
        if "error" in result:
            st.error(f"{ticker}: {result['error']}")
        else:
            st.subheader(f"📊 {ticker} Financials")
            income_df = result["income"]
            balance_df = result["balance"]
            cashflow_df = result["cashflow"]
            yf_data[ticker] = result

            st.write("**Income Statement**")
            st.dataframe(income_df)
            st.write("**Balance Sheet**")
            st.dataframe(balance_df)
            st.write("**Cash Flow Statement**")
            st.dataframe(cashflow_df)

            # Extract latest values
            def safe_get(df, label):
                try:
                    return df[label].iloc[-1]
                except:
                    return None

            metrics = {
                "Revenue": safe_get(income_df, "Total Revenue"),
                "Net Income": safe_get(income_df, "Net Income"),
                "Total Assets": safe_get(balance_df, "Total Assets"),
                "Total Liabilities": safe_get(balance_df, "Total Liab"),
                "Shareholder Equity": safe_get(balance_df, "Total Stockholder Equity"),
                "Operating Cash Flow": safe_get(cashflow_df, "Total Cash From Operating Activities"),
                "Capital Expenditures": safe_get(cashflow_df, "Capital Expenditures"),
            }

            st.subheader("📊 Extracted Metrics")
            st.write(metrics)

            def get_investment_suggestion(metrics):
                suggestions = []
                invest = True

                if metrics['Net Income'] and metrics['Revenue']:
                    net_margin = metrics['Net Income'] / metrics['Revenue']
                    if net_margin > 0.10:
                        suggestions.append("✅ Healthy profit margin.")
                    else:
                        invest = False
                        suggestions.append("⚠️ Profit margin is low.")
                else:
                    suggestions.append("❓ Missing profit margin data.")

                if metrics['Total Liabilities'] and metrics['Shareholder Equity']:
                    d2e = metrics['Total Liabilities'] / metrics['Shareholder Equity']
                    if d2e < 1.5:
                        suggestions.append("✅ Debt-to-equity is manageable.")
                    else:
                        invest = False
                        suggestions.append("⚠️ High debt-to-equity ratio.")
                else:
                    suggestions.append("❓ Missing debt/equity data.")

                if metrics['Operating Cash Flow'] is not None and metrics['Capital Expenditures'] is not None:
                    fcf = metrics['Operating Cash Flow'] - metrics['Capital Expenditures']
                    if fcf > 0:
                        suggestions.append("✅ Positive free cash flow.")
                    else:
                        invest = False
                        suggestions.append("⚠️ Negative free cash flow.")
                else:
                    suggestions.append("❓ Free cash flow data missing.")

                verdict = "✅ This company appears investable." if invest else "❌ Financial indicators suggest caution."
                return suggestions, verdict

            # Get trends for PDF
            trends = {
                "Revenue": income_df["Total Revenue"] if "Total Revenue" in income_df.columns else pd.Series(),
                "Net Income": income_df["Net Income"] if "Net Income" in income_df.columns else pd.Series(),
                "Operating Cash Flow": cashflow_df["Total Cash From Operating Activities"] if "Total Cash From Operating Activities" in cashflow_df.columns else pd.Series(),
            }

            suggestions, verdict = get_investment_suggestion(metrics)

            st.subheader("🧠 Investment Summary")
            for s in suggestions:
                st.markdown(f"- {s}")
            st.markdown(f"### Final Verdict: {verdict}")

            report_path = generate_recommendation_report(
                company_name=ticker,
                metrics=metrics,
                trends=trends,
                suggestions=suggestions,
                verdict=verdict
            )

            with open(report_path, "rb") as f:
                st.download_button(f"📥 Download {ticker} Report", f, file_name=f"{ticker}_report.pdf")

            # Plot trend charts
            def plot_trend(series, title):
                if isinstance(series, pd.Series) and not series.empty:
                    fig, ax = plt.subplots()
                    series = pd.to_numeric(series, errors='coerce').dropna()
                    ax.plot(series.index.astype(str), series.values, marker='o')
                    ax.set_title(title)
                    ax.set_ylabel("Amount")
                    ax.set_xlabel("Year")
                    st.pyplot(fig)

            st.subheader("📉 Financial Trends")
            plot_trend(trends["Revenue"], f"{ticker} - Revenue Trend")
            plot_trend(trends["Net Income"], f"{ticker} - Net Income Trend")
            plot_trend(trends["Operating Cash Flow"], f"{ticker} - Operating Cash Flow Trend")