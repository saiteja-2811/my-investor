import os
from fpdf import FPDF
import pandas as pd

class UnicodePDF(FPDF):
    def __init__(self):
        super().__init__()
        font_path = "app/fonts/DejaVuSans.ttf"
        if not os.path.exists(font_path):
            raise FileNotFoundError(f"Font not found at {font_path}. Please make sure DejaVuSans.ttf is present.")
        self.add_font('DejaVu', '', font_path, uni=True)
        self.set_font('DejaVu', '', 11)

def generate_recommendation_report(company_name, metrics, trends, suggestions, verdict, save_dir="reports"):
    """
    Generate a PDF investment report for a company.

    Parameters:
    - company_name: str
    - metrics: dict of key financial metrics
    - trends: dict of pandas Series (e.g., revenue trend)
    - suggestions: list of decision engine notes
    - verdict: final investment recommendation
    - save_dir: directory to save the PDF

    Returns:
    - file_path: path to the saved PDF
    """
    os.makedirs(save_dir, exist_ok=True)
    file_path = os.path.join(save_dir, f"{company_name}_report.pdf")

    pdf = UnicodePDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Title
    pdf.set_font("DejaVu", '', 16)
    pdf.cell(200, 10, f"Investment Report: {company_name}", ln=True, align='C')
    pdf.ln(5)

    # Key Financial Metrics
    pdf.set_font("DejaVu", '', 13)
    pdf.cell(200, 10, "Key Financial Metrics", ln=True)
    pdf.set_font("DejaVu", '', 11)
    for key, value in metrics.items():
        if value is not None:
            if isinstance(value, float):
                formatted = f"${value:,.2f}"
            else:
                formatted = str(value)
            pdf.cell(200, 8, f"{key}: {formatted}", ln=True)
    pdf.ln(5)

    # Growth Metrics
    pdf.set_font("DejaVu", '', 13)
    pdf.cell(200, 10, "Year-over-Year Growth", ln=True)
    pdf.set_font("DejaVu", '', 11)
    for label, series in trends.items():
        if isinstance(series, pd.Series) and len(series.dropna()) >= 2:
            try:
                recent = series.dropna().iloc[-1]
                previous = series.dropna().iloc[-2]
                growth = (recent - previous) / abs(previous)
                pdf.cell(200, 8, f"{label} Growth (Last Year): {growth:.2%}", ln=True)
            except:
                continue
    pdf.ln(5)

    # Decision Engine Output
    pdf.set_font("DejaVu", '', 13)
    pdf.cell(200, 10, "Decision Engine Insights", ln=True)
    pdf.set_font("DejaVu", '', 11)
    for s in suggestions:
        pdf.multi_cell(0, 8, f"- {s}")
    pdf.ln(5)

    # Final Verdict
    pdf.set_font("DejaVu", '', 13)
    pdf.multi_cell(0, 10, f"Final Verdict: {verdict}")

    # Save PDF
    pdf.output(file_path)
    return file_path