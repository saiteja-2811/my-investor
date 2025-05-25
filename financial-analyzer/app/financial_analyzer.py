import streamlit as st
import matplotlib.pyplot as plt
import pandas as pd
import re
from financial_parser import extract_tables_from_pdf, find_financial_metric, read_data
from extract_yfinance_data import get_financials

st.set_page_config(page_title="Financial Analyzer", layout="wide")
st.title("📈 Multi-Company Financial Analyzer")

# Ticker-based analysis
st.sidebar.header("📡 Ticker-Based Lookup")
tickers = st.sidebar.text_input("Enter stock tickers (comma-separated)", value="AAPL,MSFT")
yf_data = {}

if st.sidebar.button("Fetch Financials"):
    for t in tickers.split(","):
        t = t.strip().upper()
        data = get_financials(t)
        if "error" in data:
            st.error(f"{t}: {data['error']}")
        else:
            st.subheader(f"{t} Financials")
            st.write("Income Statement")
            st.dataframe(data['income'])
            st.write("Balance Sheet")
            st.dataframe(data['balance'])
            st.write("Cash Flow")
            st.dataframe(data['cashflow'])
            yf_data[t] = data

    def plot_metric(metric, section, title):
        fig, ax = plt.subplots()
        for t, data in yf_data.items():
            df = data[section]
            if metric in df.columns:
                ax.plot(df.index, df[metric], label=t, marker='o')
        ax.set_title(title)
        ax.set_xlabel("Year")
        ax.set_ylabel(metric)
        ax.legend()
        st.pyplot(fig)

    plot_metric("Net Income", "income", "Net Income Trend")
    plot_metric("Total Revenue", "income", "Revenue Trend")
    plot_metric("Total Cash From Operating Activities", "cashflow", "Operating CF Trend")