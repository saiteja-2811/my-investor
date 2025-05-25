import pdfplumber
import pandas as pd
import re

def extract_tables_from_pdf(file):
    """
    Extract all tables from a PDF file using pdfplumber.
    Returns a list of cleaned DataFrames.
    """
    tables = []
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            page_tables = page.extract_tables()
            for table in page_tables:
                df = pd.DataFrame(table)
                df.columns = df.iloc[0]
                df = df.drop(index=0).reset_index(drop=True)
                tables.append(df)
    return tables

def read_data(file):
    """
    Read and process a CSV or Excel file.
    If the file contains year-like columns (e.g., 2019, 2020), the data will be transposed to time-series format.
    Returns a list with one or more DataFrames.
    """
    if file.name.endswith('.csv'):
        df = pd.read_csv(file)
    elif file.name.endswith('.xlsx'):
        df = pd.read_excel(file)
    else:
        return []

    # Clean column names
    df.columns = [str(c).strip() for c in df.columns]

    # Check for year-based columns
    year_cols = [col for col in df.columns if re.match(r'20\d{2}', str(col))]

    if year_cols and df.shape[1] > 1:
        df = df.set_index(df.columns[0])
        df.index.name = "Metric"
        df = df.loc[:, year_cols]
        return [df.T]  # Return transposed for trend plotting
    return [df]

def find_financial_metric(tables, keywords):
    """
    Searches through a list of DataFrames to find the first match for any keyword.
    Extracts the last column value of the matched row and returns it as a float.
    """
    for df in tables:
        for keyword in keywords:
            try:
                matches = df[df.iloc[:, 0].str.contains(keyword, case=False, na=False)]
                if not matches.empty:
                    raw_value = matches.iloc[0, -1]
                    cleaned = str(raw_value).replace(',', '').replace('$', '').replace('(', '-').replace(')', '')
                    return float(cleaned)
            except Exception:
                continue
    return None