FROM python:3.11-slim

WORKDIR /app

# Install Node.js for pptxgenjs PowerPoint generator
RUN apt-get update && apt-get install -y \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create package.json inline and install pptxgenjs (no file needed in repo)
RUN echo '{"name":"kpi-pptx","version":"1.0.0","dependencies":{"pptxgenjs":"^3.12.0"}}' > package.json \
    && npm install

# Copy application code
COPY . .

# Create required directories
RUN mkdir -p uploads outputs

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
