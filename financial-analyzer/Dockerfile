FROM python:3.9-slim

RUN apt-get update && apt-get install -y libglib2.0-0 libsm6 libxrender1 libxext6

WORKDIR /app
COPY . .
COPY app/fonts/DejaVuSans.ttf app/fonts/DejaVuSans.ttf

# Set PYTHONPATH to include current directory (so "app" is importable)
ENV PYTHONPATH="${PYTHONPATH}:/app"

RUN pip install --no-cache-dir -r requirements.txt

CMD ["streamlit", "run", "app/financial_analyzer.py", "--server.port=8501", "--server.enableCORS=false"]