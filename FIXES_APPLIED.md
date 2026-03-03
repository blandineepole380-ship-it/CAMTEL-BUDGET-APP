# Bug Fixes Applied — CAMTEL Budget App v10.1

## Critical Bugs Fixed (12 total)

### 1. `requirements.txt` — INCOMPLETE (app would not start)
**Before:** Only `fastapi` and `uvicorn`  
**Fixed:** Added `sqlalchemy`, `itsdangerous`, `python-multipart`, `pydantic`, `openpyxl`, `psycopg2-binary`

### 2. `Dockerfile` — WRONG ENTRY POINT (app would not start)
**Before:** `CMD ["uvicorn", "main:app", ...]` — wrong filename  
**Fixed:** `CMD ["uvicorn", "main_fixed:app", ...]`  
Also: Updated to Python 3.11, added `libpq-dev` for PostgreSQL support

### 3. `delete_bl` — MISPLACED `except` BLOCK (route always errored)
**Cause:** A section comment `# ── IMPORT ENDPOINTS ──` was placed between  
the `return` statement and the `except` clause, breaking the try/except.  
**Fixed:** Moved the comment after the except block.

### 4. `api_report` — MISPLACED `except` BLOCK (reports always errored)
Same pattern as above — `# ── Users ──` comment broke the try/except.

### 5. `delete_user_route` — MISPLACED `except` BLOCK (user delete errored)
Same pattern — `# ── Plan Comptable ──` comment broke the try/except.

### 6. `dashboard_data` — INVALID SQLALCHEMY FILTER (`recent` always crashed)
**Before:** `.filter(Transaction.year==year if year else True)` — Python `True` is  
not a valid SQLAlchemy filter expression, causing a runtime error.  
**Fixed:** Rebuilt the query with a proper conditional `.filter()` call.

### 7. `planning_master_data` — WRONG FUNCTION SIGNATURE
**Before:** `return api_planning_ref(request, db)` — but `api_planning_ref` doesn't accept `db`  
**Fixed:** `return api_planning_ref(request)`

### 8–12. PTA Planning Routes — RAW SQL WITH SQLite `?` PLACEHOLDERS
All planning API routes used `db.execute("... WHERE x=?", params)` which  
**fails silently on PostgreSQL** (production uses `%s`, not `?`).  
Fixed routes: `api_pta_list`, `api_pta_update`, `api_pta_delete`,  
`api_pta_export`, `api_pta_summary`, `api_pta_import`  
**Fixed:** Replaced all raw SQL with proper SQLAlchemy ORM queries.

### Bonus: `fiche` / `fiche_imputation` routes — `dict(t)` on ORM objects
**Before:** `txs.append(dict(t))` — SQLAlchemy ORM objects are not directly  
iterable as dicts; this would raise a `TypeError` at runtime.  
**Fixed:** `txs.append(_tx_dict(t))` — uses the existing helper function.

---

## Deployment Instructions (Render)

1. Push this folder to a GitHub repo
2. Go to render.com → New → Blueprint → connect repo
3. Render auto-creates web service + PostgreSQL from `render.yaml`

### Environment Variables (auto-set by render.yaml, but confirm):
| Variable | Value |
|---|---|
| `DATABASE_URL` | Set automatically from PostgreSQL add-on |
| `SECRET_KEY` | Auto-generated |
| `ADMIN_USER` | `admin` |
| `ADMIN_PASS` | `admin123` ← **Change in production!** |

### Default Login:
- URL: https://your-app.onrender.com
- Username: `admin`
- Password: `admin123`
