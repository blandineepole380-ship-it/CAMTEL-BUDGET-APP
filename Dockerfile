# ============================================================
# Dockerfile — Deploy Kolo-Ride to any cloud in minutes
# ============================================================

FROM python:3.12-slim

WORKDIR /app

# Install system deps for psycopg2
RUN apt-get update && apt-get install -y \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

# Production WSGI server (not Flask dev server)
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "api.server:app"]
