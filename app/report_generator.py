import os
import re
from fpdf import FPDF
import pandas as pd

# A subclass of FPDF with Unicode font support
class UnicodePDF(FPDF):
    def __init__(self):
        super().__init__()
        font_path = "app/fonts/DejaVuSans.ttf"
        if not os.path.exists(font_path):
            raise FileNotFoundError(f"Missing font: {font_path}")
        self.add_font('DejaVu', '', font_path, uni=True)
        self.set_font('DejaVu', '', 10)

# Truncate long text and insert soft breaks for unbreakable strings
def safe_text(text, max_len=80):
    text = str(text)
    if len(text) > max_len:
        text = text[:max_len - 3] + "..."
    # Insert soft break after long blocks of non-spaced characters
    return re.sub(r'([^\s]{25,})', r'\1 ', text)

# Main function to generate PDF report
def generate_recommendation_report(company_name, metrics, trends, suggestions, verdict, save_dir="reports"):
    os.makedirs(save_dir, exist_ok=True)
    file_path = os.path.join(save_dir, f"{company_name}_report.pdf")

    pdf = UnicodePDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Title
    pdf.set_font("DejaVu", '', 14)
    pdf.cell(200, 10, f"Investment Report: {company_name}", ln=True, align='C')
    pdf.ln(5)

    # Section: Key Financial Metrics
    pdf.set_font("DejaVu", '', 11)
    pdf.cell(200, 10, "Key Financial Metrics", ln=True)
    for key, value in metrics.items():
        if value is not None:
            formatted = f"${value:,.2f}" if isinstance(value, float) else str(value)
            line = safe_text(f"{key}: {formatted}")
            try:
                pdf.multi_cell(0, 8, line)
            except:
                pdf.set_font("DejaVu", '', 9)
                pdf.multi_cell(0, 6, safe_text(line))
                pdf.set_font("DejaVu", '', 10)

    pdf.ln(5)

    # Section: Growth Metrics
    pdf.cell(200, 10, "Year-over-Year Growth", ln=True)
    for label, series in trends.items():
        if isinstance(series, pd.Series) and len(series.dropna()) >= 2:
            try:
                recent = series.dropna().iloc[-1]
                previous = series.dropna().iloc[-2]
                growth = (recent - previous) / abs(previous)
                growth_text = safe_text(f"{label} Growth (Last Year): {growth:.2%}")
                pdf.multi_cell(0, 8, growth_text)
            except:
                continue

    pdf.ln(5)

    # Section: Investment Suggestions
    pdf.cell(200, 10, "Decision Engine Insights", ln=True)
    for s in suggestions:
        try:
            pdf.multi_cell(0, 8, safe_text(f"- {s}"))
        except:
            pdf.set_font("DejaVu", '', 9)
            pdf.multi_cell(0, 6, safe_text(f"- {s}"))
            pdf.set_font("DejaVu", '', 10)

    pdf.ln(5)

    # Final Verdict
    pdf.set_font("DejaVu", '', 11)
    pdf.multi_cell(0, 10, safe_text(f"Final Verdict: {verdict}"))

    pdf.output(file_path)
    return file_path