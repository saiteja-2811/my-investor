import pdfplumber
import pandas as pd
import re

def extract_tables_from_pdf(file):
    tables = []
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                df = pd.DataFrame(table)
                df.columns = df.iloc[0]
                df = df.drop(index=0).reset_index(drop=True)
                tables.append(df)
    return tables

def read_data(file):
    if file.name.endswith('.csv'):
        df = pd.read_csv(file)
    elif file.name.endswith('.xlsx'):
        df = pd.read_excel(file)
    else:
        return []

    df.columns = [str(c).strip() for c in df.columns]
    year_cols = [col for col in df.columns if re.match(r'20\d{2}', str(col))]
    if year_cols and df.shape[1] > 1:
        df = df.set_index(df.columns[0])
        df.index.name = "Metric"
        df = df.loc[:, year_cols]
        return [df.T]
    return [df]

def find_financial_metric(tables, keywords):
    for df in tables:
        for keyword in keywords:
            matches = df[df.iloc[:, 0].str.contains(keyword, case=False, na=False)]
            if not matches.empty:
                try:
                    return float(matches.iloc[0, -1].replace(',', '').replace('$', ''))
                except:
                    continue
    return None