import streamlit as st
import matplotlib.pyplot as plt
import pandas as pd
from extract_yfinance_data import get_financials, get_ticker_from_company_name, get_company_overview
from io import BytesIO
import base64

st.set_page_config(page_title="Financial Analyzer", layout="wide")
st.title("📈 Multi-Company Financial Analyzer")

# Sidebar input
st.sidebar.header("📡 Company-Based Lookup")
company_names = st.sidebar.text_input("Enter company names (comma-separated)", value="Apple,Meta Platforms")

if st.sidebar.button("Fetch Financials"):
    for name in company_names.split(","):
        name = name.strip()
        ticker, resolved_name = get_ticker_from_company_name(name)
        if not ticker:
            st.error(f"❌ Could not find ticker for '{name}'")
            continue

        st.success(f"🔎 Found ticker `{ticker}` for **{resolved_name}**")
        overview = get_company_overview(ticker)
        if "error" in overview:
            st.warning(f"⚠️ Failed to load company overview: {overview['error']}")
        else:
            st.markdown(f"## 🏢 {overview['name']} ({overview['symbol']})")
            st.markdown(f"**Sector:** {overview['sector']}  |  **Industry:** {overview['industry']}")
            if overview.get("marketCap"):
                st.markdown(f"**Market Cap:** ${overview['marketCap']:,}")
            st.markdown(f"**Website:** [{overview['website']}]({overview['website']})")
            st.markdown(f"**About:** {overview['summary']}")

        result = get_financials(ticker)
        if "error" in result:
            st.error(f"❌ Failed to load financials for {ticker}: {result['error']}")
            continue

        income_df = result["income"]
        balance_df = result["balance"]
        cashflow_df = result["cashflow"]

        st.write("### Income Statement")
        st.dataframe(income_df)
        st.write("### Balance Sheet")
        st.dataframe(balance_df)
        st.write("### Cash Flow Statement")
        st.dataframe(cashflow_df)

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

        def get_investment_suggestion(metrics):
            suggestions = []
            invest = True

            if metrics['Net Income'] and metrics['Revenue']:
                net_margin = metrics['Net Income'] / metrics['Revenue']
                suggestions.append("✅ Healthy profit margin." if net_margin > 0.10 else "⚠️ Profit margin is low.")
                if net_margin <= 0.10:
                    invest = False
            else:
                suggestions.append("❓ Missing profit margin data.")

            if metrics['Total Liabilities'] and metrics['Shareholder Equity']:
                d2e = metrics['Total Liabilities'] / metrics['Shareholder Equity']
                suggestions.append("✅ Debt-to-equity is manageable." if d2e < 1.5 else "⚠️ High debt-to-equity ratio.")
                if d2e >= 1.5:
                    invest = False
            else:
                suggestions.append("❓ Missing debt/equity data.")

            if metrics['Operating Cash Flow'] is not None and metrics['Capital Expenditures'] is not None:
                fcf = metrics['Operating Cash Flow'] - metrics['Capital Expenditures']
                suggestions.append("✅ Positive free cash flow." if fcf > 0 else "⚠️ Negative free cash flow.")
                if fcf <= 0:
                    invest = False
            else:
                suggestions.append("❓ Free cash flow data missing.")

            verdict = "✅ This company appears investable." if invest else "❌ Financial indicators suggest caution."
            return suggestions, verdict

        trends = {
            "Revenue": income_df["Total Revenue"] if "Total Revenue" in income_df.columns else pd.Series(),
            "Net Income": income_df["Net Income"] if "Net Income" in income_df.columns else pd.Series(),
            "Operating Cash Flow": cashflow_df["Total Cash From Operating Activities"] if "Total Cash From Operating Activities" in cashflow_df.columns else pd.Series(),
        }

        suggestions, verdict = get_investment_suggestion(metrics)

        st.markdown("### 🧠 Investment Summary")
        summary_line_1 = next((s for s in suggestions if "⚠" in s or "❌" in s), suggestions[0])
        summary_line_2 = verdict
        st.success(summary_line_1)
        st.info(summary_line_2)

        def plot_trends_side_by_side(trends_dict, ticker):
            metrics = {
                "Revenue": trends_dict.get("Revenue", pd.Series()),
                "Net Income": trends_dict.get("Net Income", pd.Series()),
                "Operating Cash Flow": trends_dict.get("Operating Cash Flow", pd.Series())
            }

            fig, axes = plt.subplots(1, 3, figsize=(15, 4), constrained_layout=True)
            fig.suptitle(f"{ticker} – Financial Trends", fontsize=14)

            for ax, (label, series) in zip(axes, metrics.items()):
                if isinstance(series, pd.Series) and not series.empty:
                    series = pd.to_numeric(series, errors='coerce').dropna().sort_index()
                    color = 'green' if series.iloc[-1] >= 0 else 'red'
                    ax.plot(series.index.astype(str), series.values, marker='o', color=color, linewidth=2)
                    ax.set_title(label)
                    ax.set_xlabel("Year")
                    ax.set_ylabel("USD")
                    ax.grid(True, linestyle='--', alpha=0.5)
                else:
                    ax.set_visible(False)

            st.pyplot(fig)

            # Save to PNG in memory and offer download
            buf = BytesIO()
            fig.savefig(buf, format="png")
            buf.seek(0)
            b64 = base64.b64encode(buf.read()).decode()

            st.download_button(
                label="📥 Download Trends as PNG",
                data=buf,
                file_name=f"{ticker}_trends.png",
                mime="image/png"
            )

        st.subheader("📉 Financial Trends")
        plot_trends_side_by_side(trends, ticker)