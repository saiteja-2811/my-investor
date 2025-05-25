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