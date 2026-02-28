# CAMTEL Budget Management System — v10

Professional government budget tracking system built with FastAPI + SQLAlchemy.

## Project Structure

```
camtel-budget-app/
├── app/
│   ├── main.py          — FastAPI app, all routes, auth
│   ├── database.py      — SQLAlchemy engine (PostgreSQL + SQLite)
│   ├── models.py        — All DB tables with FK relationships
│   ├── schemas.py       — Pydantic validation schemas
│   ├── crud.py          — All database operations
│   ├── routers/
│   │   └── import_data.py  — Excel/CSV import engine
│   └── utils/
│       └── calculations.py — Auto analytics (balance, KPIs)
├── requirements.txt
├── Dockerfile
├── render.yaml          — Render deployment with PostgreSQL
└── README.md
```

## Local Development

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Visit: http://localhost:8000  
Login: `admin` / `admin123`

## Deploy to Render (with PostgreSQL)

### Option A — render.yaml (recommended)
1. Push this repo to GitHub
2. Go to [render.com](https://render.com) → New → Blueprint
3. Connect your GitHub repo
4. Render automatically creates the web service + PostgreSQL database

### Option B — Manual
1. Create a **PostgreSQL** database on Render → copy `DATABASE_URL`
2. Create a **Web Service** → Docker → connect your repo
3. Add environment variables:
   ```
   DATABASE_URL=postgresql://...
   SECRET_KEY=your-random-secret
   ADMIN_USER=admin
   ADMIN_PASS=your-secure-password
   ```
4. Deploy

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | SQLite (local) |
| `SECRET_KEY` | JWT signing key | `camtel-secret-v10` |
| `ADMIN_USER` | Admin username | `admin` |
| `ADMIN_PASS` | Admin password | `admin123` |

## Import Formats

### Transactions CSV
```
DATE ENGAGEMENT,DIRECTION,IMPUTATION COMPTABLE,NATURE DE LA DEPENSE,INTITULE DE LA COMMANDE,MONTANT,CODE /REF NUMBER
15/03/2025,DCF,604100,DEPENSE COURANTE,ACHAT FOURNITURES,250000,DCF-001
```

### Transactions Excel (.xlsx)
Same columns — title rows like "SITUATION DES ENGAGEMENTS..." are skipped automatically.  
Amounts like `291,959,762` are parsed correctly.

### Budget Lines CSV
```
YEAR,DIRECTION,IMPUTATION COMPTABLE,LIBELLE,NATURE,BUDGET CP (FCFA)
2025,DCF,604100,FOURNITURES DE BUREAU,DEPENSE COURANTE,5000000
```

## Roles

| Role | Access |
|---|---|
| `admin` | Full access — all directions, users, import |
| `dcf_dir` | All directions, import, reports |
| `dcf_sub` | All directions, import, budget lines |
| `agent_plus` | Own directions, import transactions |
| `agent` | Own directions, create transactions |
| `viewer` | Read only |

## API Endpoints

### Auth
- `POST /api/login/token` — get bearer token
- `POST /api/logout`

### Dashboard
- `GET /api/dashboard?year=2025` — KPIs, charts, progress

### Transactions
- `GET /api/transactions?year=2025&direction=DCF&status=validated&q=search`
- `POST /api/transactions`
- `PUT /api/transactions/{id}`
- `DELETE /api/transactions/{id}`
- `POST /api/transactions/validate-batch`

### Budget Lines
- `GET /api/budget-lines?year=2025&direction=DCF`
- `POST /api/budget-lines`

### Import
- `POST /api/import/transactions` — CSV or Excel
- `POST /api/import/budget-lines` — CSV or Excel

### Export
- `GET /api/export/transactions?year=2025`
- `GET /api/export/template-transactions`
- `GET /api/export/template-budget-lines`

### Reports
- `GET /api/report/monthly?year=2025&month=0` — month=0 for full year

### Health
- `GET /version` — DB stats and version
