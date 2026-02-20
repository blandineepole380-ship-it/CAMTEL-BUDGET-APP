# CAMTEL Budget App (Render-ready)

This is a **simple, stable** web app that matches your requested features:

- ✅ Login system (Admin + User roles)
- ✅ Multi-PC shared database (Render Postgres)
- ✅ Department filter (BUM/DIG/DRH)
- ✅ OM auto calculation (dates, days, amount/day, total)
- ✅ BC Cameroon tax system (HT, TVA 19.25%, IR dropdown 2.2% / 5.5%, totals)
- ✅ Fiche PDF (2 transactions per A4, signature blocks, exact selection order)

## Deploy on Render (Docker)
1. Upload this folder to GitHub (root must contain `Dockerfile`).
2. On Render: **New Web Service** → connect GitHub repo → choose **Docker**.
3. Set Environment Variables:
   - `DATABASE_URL` = your Render Postgres connection string
   - `SECRET_KEY` = random long string
   - `ADMIN_USERNAME` / `ADMIN_PASSWORD` = first admin login
4. Deploy.

## Local run
```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export SECRET_KEY=dev
uvicorn main:app --reload
```

Open http://127.0.0.1:8000

## Notes
- If you don’t create budget lines, the “New Transaction” budget line dropdown will be empty.
- Admin can add budget lines in **Admin → Manage Budget Lines**.
- Replace the logo at `static/img/logo.png` if you want a different one.
