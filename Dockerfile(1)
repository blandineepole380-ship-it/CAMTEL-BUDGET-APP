FROM python:3.11-slim

# Create app directory
WORKDIR /app

# Install system dependencies for psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (cache layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose Render's expected port
EXPOSE 8000

# Start the server — single-file deployment
CMD ["uvicorn", "main_fixed:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
