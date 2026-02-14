# CAMTEL Budget App (Web)

## Quick start (local)
1. Install Python 3.11
2. `pip install -r requirements.txt`
3. `uvicorn main:app --reload`
4. Open http://127.0.0.1:8000
Default login: admin / admin123

## Deploy on Render (Docker)
- Push this folder to GitHub
- Render -> New Web Service -> connect repo
- Environment variables:
  - APP_SECRET: a random string
  - DATABASE_URL: your Render Postgres URL (optional; app falls back to sqlite locally)
