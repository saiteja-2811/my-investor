import streamlit as st
import matplotlib.pyplot as plt
import pandas as pd
import re
from app.financial_parser import extract_tables_from_pdf, find_financial_metric, read_data

st.set_page_config(page_title="Multi-Company Financial Analyzer", layout="wide")
st.title("📊 Multi-Company Financial Analyzer")

st.markdown("Upload PDF, Excel, or CSV files for **Income Statement** and **Cash Flow Statement** of multiple companies.")

income_files = st.file_uploader("Upload Income Statements", type=["pdf", "csv", "xlsx"], accept_multiple_files=True)
cashflow_files = st.file_uploader("Upload Cash Flow Statements", type=["pdf", "csv", "xlsx"], accept_multiple_files=True)

company_names = []
for i in range(len(income_files)):
    name = st.text_input(f"Company #{i+1} Name", value=f"Company_{i+1}")
    company_names.append(name)

def get_tables(file):
    if file.name.endswith('.pdf'):
        return extract_tables_from_pdf(file)
    else:
        return read_data(file)

def plot_multi_company_trend(data_dict, metric, title):
    fig, ax = plt.subplots()
    for company, df in data_dict.items():
        if metric in df.columns:
            df[metric] = pd.to_numeric(df[metric], errors='coerce')
            ax.plot(df.index, df[metric], label=company, marker='o')
    ax.set_title(title)
    ax.set_ylabel(metric)
    ax.set_xlabel("Year")
    ax.legend()
    st.pyplot(fig)

if income_files and cashflow_files:
    income_data = {}
    cashflow_data = {}

    for f, name in zip(income_files, company_names):
        tables = get_tables(f)
        if tables:
            income_data[name] = tables[0]

    for f, name in zip(cashflow_files, company_names):
        tables = get_tables(f)
        if tables:
            cashflow_data[name] = tables[0]

    st.subheader("📈 Revenue Comparison")
    plot_multi_company_trend(income_data, 'Revenue', 'Revenue Trend')

    st.subheader("📈 Net Income Comparison")
    plot_multi_company_trend(income_data, 'Net Income', 'Net Income Trend')

    st.subheader("📈 Operating Cash Flow Comparison")
    plot_multi_company_trend(cashflow_data, 'Operating Cash Flow', 'Operating CF Trend')

    for name in company_names:
        with st.expander(f"📄 Detailed View: {name}"):
            st.write("Income Statement")
            st.dataframe(income_data.get(name))
            st.write("Cash Flow Statement")
            st.dataframe(cashflow_data.get(name))