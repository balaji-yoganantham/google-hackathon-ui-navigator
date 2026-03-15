FROM mcr.microsoft.com/playwright/python:v1.41.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install only Chromium (avoids downloading Firefox + WebKit)
RUN playwright install chromium

COPY . .

ENV PYTHONUNBUFFERED=1

# Cloud Run injects PORT; fall back to 8000 locally
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
