# CAMTEL Budget App v2 — Render-ready

Full-featured budget tracking app for CAMTEL with:
- ✅ **SQLite persistent database** (survives restarts)
- ✅ **Dashboard with charts** (by direction, by month)
- ✅ **Budget limits per direction** with progress bars & available balance
- ✅ **CORS support** for Lovable frontend integration
- ✅ **Bearer token auth** for API clients

---

## Deploy on Render (Docker)

1. Push these files to your GitHub repo root.
2. In Render: **New Web Service** → connect repo → Environment: **Docker**
3. Add Environment Variables:

| Variable | Description | Default |
|---|---|---|
| `SECRET_KEY` | Long random string for sessions | `change-me` |
| `ADMIN_USER` | Login username | `admin` |
| `ADMIN_PASS` | Login password | `admin123` |
| `DB_PATH` | SQLite file path | `camtel.db` |
| `FRONTEND_ORIGIN` | Your Lovable app URL (for CORS) | `*` |

4. Deploy → Default login: `admin / admin123`

---

## Connecting your Lovable Frontend

The backend exposes a full REST API:

### Auth
```
POST /api/login/token
Body: { "username": "admin", "password": "admin123" }
Returns: { "token": "...", "user": "admin" }
```
Use the token as: `Authorization: Bearer <token>`

### Transactions
```
GET  /api/tx?year=2025&q=search&direction=DRH
POST /api/tx         { code, direction, doc, budget_line, title, nature, date, amount, year, status }
GET  /api/tx/:id
DELETE /api/tx/:id
```

### Budget Limits
```
GET    /api/budget-limits?year=2025
POST   /api/budget-limits   { direction, year, limit_amount }
DELETE /api/budget-limits/:id
```

### Dashboard Summary
```
GET /api/dashboard?year=2025
Returns: { total_limit, total_engaged, total_pending, available, by_direction, by_month, limits }
```

### Fiche (printable)
```
GET /fiche/:id   → HTML printable page
```

---

## Persistent Storage on Render

By default, Render's disk resets on redeploy. To keep data:
1. In Render: go to your service → **Disks** → Add a disk
2. Mount path: `/data`
3. Set env var: `DB_PATH=/data/camtel.db`

This ensures your SQLite database survives all redeployments.
