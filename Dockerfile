FROM python:3.9-slim

# Create a folder for the app
WORKDIR /app

# Install dependencies first for speed
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy your code into the /app folder
COPY . .

# Match the port Render expects
EXPOSE 8000

# Start the server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]