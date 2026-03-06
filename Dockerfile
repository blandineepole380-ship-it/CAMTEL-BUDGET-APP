FROM python:3.11-slim

WORKDIR /app

# Install Node.js + npm
RUN apt-get update && apt-get install -y \
    nodejs \
    npm \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies inline (no requirements.txt needed in repo)
RUN pip install --no-cache-dir \
    fastapi==0.115.0 \
    "uvicorn[standard]==0.30.6" \
    sqlalchemy==2.0.36 \
    pydantic==2.9.2 \
    python-multipart==0.0.12 \
    aiofiles==24.1.0

# Install Node pptxgenjs inline (no package.json needed in repo)
RUN echo '{"name":"kpi-pptx","version":"1.0.0","dependencies":{"pptxgenjs":"^3.12.0"}}' > package.json \
    && npm install

# Copy application code
COPY . .

# Create required runtime directories
RUN mkdir -p uploads outputs

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
