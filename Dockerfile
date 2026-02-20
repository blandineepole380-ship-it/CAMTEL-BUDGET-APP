FROM python:3.11-slim
WORKDIR /code

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Ensure the repo root is always on the import path (fixes `ModuleNotFoundError: app`)
ENV PYTHONPATH=/code

COPY requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir -r /code/requirements.txt

# Copy everything (this ensures /code/app, /code/static and /code/templates exist)
COPY . /code

EXPOSE 8000
CMD ["uvicorn", "main:app", "--app-dir", "/code", "--host", "0.0.0.0", "--port", "8000"]
