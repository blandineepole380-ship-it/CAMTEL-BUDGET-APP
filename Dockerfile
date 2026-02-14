FROM python:3.11-slim

WORKDIR /code

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy everything (main.py, index.html, budgets_2025.json, assets/)
COPY . ./

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
