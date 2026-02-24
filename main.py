"""
CAMTEL Budget App v4
Multi-user · Direction-based access · Budget lines · Official Fiche DCF
Import/Export · Monthly reports · Document scanning
"""
import os, sqlite3, hashlib, json, io, csv
from datetime import datetime, date
from fastapi import FastAPI, Request, Response, Form, HTTPException, Depends, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from itsdangerous import URLSafeSerializer, BadSignature

APP_NAME = "CAMTEL Budget App"
SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-production")
DB_PATH    = os.environ.get("DB_PATH",    "camtel.db")
FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "*")

serializer = URLSafeSerializer(SECRET_KEY, salt="camtel-v4")
app = FastAPI(title=APP_NAME)
app.add_middleware(CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN] if FRONTEND_ORIGIN != "*" else ["*"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

ALL_DIRECTIONS = ['BUM', 'BUT', 'BUF', 'DG', 'DRH', 'DICOM', 'DIRCAB', 'DCRA', 'DAMR', 'DC', 'DNQ', 'DAS', 'DFA', 'DAJR', 'DAP', 'DR', 'DS', 'DSPI', 'DSIR', 'DOP', 'DT', 'DCF', 'DCRM', 'DRLM', 'RRSM', 'RREM', 'RROM', 'RRNOM', 'RRSOM', 'RRAM', 'RRNM', 'RRENM', 'DCRF', 'DRLF', 'RRSF', 'RREF', 'RROF', 'RRNOF', 'RRSOF', 'RRAF', 'RRNF', 'RRENF', 'DCRT', 'DRLT', 'RRNOT', 'RRENT']

# ═══════════════════════════════════════════════════════════
#  DATABASE
# ═══════════════════════════════════════════════════════════

def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:    yield conn
    finally: conn.close()

def _hash(pw): return hashlib.sha256(pw.encode()).hexdigest()

def init_db():
    with sqlite3.connect(DB_PATH) as c:
        c.execute("PRAGMA journal_mode=WAL")
        # Users — directions stored as JSON list
        c.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username  TEXT UNIQUE NOT NULL,
            password  TEXT NOT NULL,
            full_name TEXT DEFAULT \'\',
            role      TEXT DEFAULT \'agent\',
            directions TEXT DEFAULT \'[]\'  ,
            email     TEXT DEFAULT \'\',
            created_at TEXT DEFAULT (datetime(\'now\')))""")
        # Budget lines (one per direction/account/year)
        c.execute("""CREATE TABLE IF NOT EXISTS budget_lines (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            year          INTEGER NOT NULL,
            direction     TEXT NOT NULL,
            imputation    TEXT NOT NULL,
            libelle       TEXT NOT NULL DEFAULT \'\',
            nature        TEXT NOT NULL DEFAULT \'DEPENSE COURANTE\',
            budget_cp     REAL NOT NULL DEFAULT 0,
            cumul_engage  REAL NOT NULL DEFAULT 0,
            UNIQUE(year, direction, imputation))""")
        # Transactions
        c.execute("""CREATE TABLE IF NOT EXISTS transactions (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            code_ref     TEXT NOT NULL DEFAULT \'\',
            date_reception TEXT NOT NULL,
            direction    TEXT NOT NULL DEFAULT \'\',
            imputation   TEXT NOT NULL DEFAULT \'\',
            nature       TEXT NOT NULL DEFAULT \'DEPENSE COURANTE\',
            intitule     TEXT NOT NULL DEFAULT \'\',
            description  TEXT NOT NULL DEFAULT \'\',
            montant      REAL NOT NULL DEFAULT 0,
            year         INTEGER NOT NULL,
            status       TEXT NOT NULL DEFAULT \'validated\',
            statut_budget TEXT NOT NULL DEFAULT \'NORMAL\',
            created_by   TEXT NOT NULL DEFAULT \'\',
            created_by_name TEXT NOT NULL DEFAULT \'\',
            created_at   TEXT NOT NULL DEFAULT (datetime(\'now\')),
            doc_path     TEXT DEFAULT \'\')""")
        # Monthly reports log
        c.execute("""CREATE TABLE IF NOT EXISTS report_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            year INTEGER, month INTEGER,
            sent_at TEXT DEFAULT (datetime(\'now\')),
            recipients TEXT DEFAULT \'\')""")
        # Default admin
        dirs_json = json.dumps(ALL_DIRECTIONS)
        c.execute("INSERT OR IGNORE INTO users (username,password,full_name,role,directions) VALUES (?,?,\'Administrateur\',\'admin\',?)",
            (os.environ.get("ADMIN_USER","admin"), _hash(os.environ.get("ADMIN_PASS","admin123")), dirs_json))
        c.commit()

init_db()

# ═══════════════════════════════════════════════════════════
#  AUTH + HELPERS
# ═══════════════════════════════════════════════════════════

def _get_user(request):
    token = request.cookies.get("session")
    auth  = request.headers.get("Authorization","")
    if auth.startswith("Bearer "): token = auth[7:]
    if not token: return None
    try:    return serializer.loads(token)
    except BadSignature: return None

def require_login(request):
    u = _get_user(request)
    if not u: raise HTTPException(401,"Not logged in")
    return u

def require_admin(request):
    u = require_login(request)
    if u.get("role") not in ("admin","dcf_dir","dcf_sub"): raise HTTPException(403,"Access denied")
    return u

def user_directions(u):
    """Return list of directions this user can see."""
    if u.get("role") in ("admin","dcf_dir","dcf_sub"): return ALL_DIRECTIONS
    try:    return json.loads(u.get("directions","[]"))
    except: return []

def _fmt_fcfa(n):
    """Format number as FCFA with space thousands separator: 1 234 567"""
    try:
        n = int(round(float(n or 0)))
        s = f"{abs(n):,}".replace(",", "\u00a0")  # non-breaking space
        return f"-{s}" if n < 0 else s
    except: return "0"

def _line_balance(conn, bl_id, year):
    row = conn.execute("SELECT * FROM budget_lines WHERE id=?", (bl_id,)).fetchone()
    if not row: return None
    r = dict(row)
    eng = conn.execute("SELECT COALESCE(SUM(montant),0) FROM transactions WHERE imputation=? AND year=? AND status=\'validated\'",
        (r["imputation"], year)).fetchone()[0]
    dispo = r["budget_cp"] - eng
    return {**r, "cumul_engage": eng, "disponible": dispo, "dispo_ok": dispo >= 0}

# ═══════════════════════════════════════════════════════════
#  ROUTES — AUTH
# ═══════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    if not _get_user(request): return RedirectResponse("/login")
    return HTMLResponse(APP_HTML)

@app.get("/login", response_class=HTMLResponse)
def login_page(): return HTMLResponse(LOGIN_HTML.replace("__ERR__",""))

@app.post("/api/login")
def do_login(username: str = Form(...), password: str = Form(...)):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        u = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    if not u or u["password"] != _hash(password):
        return HTMLResponse(LOGIN_HTML.replace("__ERR__","<div class=\'err\'>Identifiants incorrects.</div>"), status_code=401)
    token = serializer.dumps({"u": username, "role": u["role"], "name": u["full_name"], "dirs": u["directions"]})
    resp  = RedirectResponse("/", status_code=302)
    resp.set_cookie("session", token, httponly=True, samesite="lax")
    return resp

@app.post("/api/login/token")
def api_login(payload: dict):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        u = conn.execute("SELECT * FROM users WHERE username=?", (payload.get("username",""),)).fetchone()
    if not u or u["password"] != _hash(payload.get("password","")):
        raise HTTPException(401,"Invalid credentials")
    token = serializer.dumps({"u": u["username"], "role": u["role"], "name": u["full_name"], "dirs": u["directions"]})
    return {"token": token, "user": u["username"], "role": u["role"]}

@app.post("/api/logout")
def logout():
    r = JSONResponse({"ok":True}); r.delete_cookie("session"); return r

@app.get("/api/me")
def me(request: Request):
    u = require_login(request)
    return {**u, "direction_list": user_directions(u)}

# ═══════════════════════════════════════════════════════════
#  ROUTES — USERS (admin)
# ═══════════════════════════════════════════════════════════

@app.get("/api/users")
def list_users(request: Request, db = Depends(get_db)):
    require_admin(request)
    rows = db.execute("SELECT id,username,full_name,role,directions,email,created_at FROM users ORDER BY id").fetchall()
    return [dict(r) for r in rows]

@app.post("/api/users")
def create_user(request: Request, payload: dict, db = Depends(get_db)):
    require_admin(request)
    dirs = json.dumps(payload.get("directions", []))
    try:
        db.execute("INSERT INTO users (username,password,full_name,role,directions,email) VALUES (?,?,?,?,?,?)",
            (payload["username"], _hash(payload["password"]),
             payload.get("full_name",""), payload.get("role","agent"),
             dirs, payload.get("email","")))
        db.commit()
    except sqlite3.IntegrityError: raise HTTPException(400,"Username already exists")
    return {"ok":True}

@app.put("/api/users/{uid}")
def update_user(request: Request, uid: int, payload: dict, db = Depends(get_db)):
    require_admin(request)
    fields, vals = [], []
    for k in ("full_name","role","email"):
        if k in payload: fields.append(f"{k}=?"); vals.append(payload[k])
    if "directions" in payload: fields.append("directions=?"); vals.append(json.dumps(payload["directions"]))
    if "password" in payload and payload["password"]: fields.append("password=?"); vals.append(_hash(payload["password"]))
    if not fields: raise HTTPException(400,"Nothing to update")
    vals.append(uid)
    db.execute("UPDATE users SET " + ",".join(fields) + " WHERE id=?", vals); db.commit()
    return {"ok":True}

@app.delete("/api/users/{uid}")
def del_user(request: Request, uid: int, db = Depends(get_db)):
    require_admin(request)
    db.execute("DELETE FROM users WHERE id=?", (uid,)); db.commit()
    return {"ok":True}

# ═══════════════════════════════════════════════════════════
#  ROUTES — BUDGET LINES
# ═══════════════════════════════════════════════════════════

@app.get("/api/budget-lines")
def list_bl(request: Request, year: int, direction: str = "", db = Depends(get_db)):
    u = require_login(request)
    dirs = user_directions(u)
    if direction and direction in dirs:
        rows = db.execute("SELECT * FROM budget_lines WHERE year=? AND direction=? ORDER BY imputation", (year,direction)).fetchall()
    else:
        placeholders = ",".join("?" for _ in dirs)
        rows = db.execute(f"SELECT * FROM budget_lines WHERE year=? AND direction IN ({placeholders}) ORDER BY direction,imputation",
            [year]+dirs).fetchall() if dirs else []
    result = []
    for r in rows:
        r = dict(r)
        eng = db.execute("SELECT COALESCE(SUM(montant),0) FROM transactions WHERE imputation=? AND year=? AND status=\'validated\'",
            (r["imputation"], year)).fetchone()[0]
        dispo = r["budget_cp"] - eng
        result.append({**r, "cumul_engage": eng, "disponible": dispo, "dispo_ok": dispo >= 0})
    return result

@app.post("/api/budget-lines")
def create_bl(request: Request, payload: dict, db = Depends(get_db)):
    require_admin(request)
    try:
        db.execute("INSERT INTO budget_lines (year,direction,imputation,libelle,nature,budget_cp) VALUES (?,?,?,?,?,?)",
            (payload["year"], payload["direction"].upper(), payload["imputation"],
             payload.get("libelle",""), payload.get("nature","DEPENSE COURANTE"),
             float(payload.get("budget_cp",0))))
        db.commit()
    except sqlite3.IntegrityError: raise HTTPException(400,"Budget line already exists")
    return {"ok":True}

@app.put("/api/budget-lines/{bl_id}")
def update_bl(request: Request, bl_id: int, payload: dict, db = Depends(get_db)):
    require_admin(request)
    db.execute("UPDATE budget_lines SET libelle=?,budget_cp=?,nature=? WHERE id=?",
        (payload.get("libelle",""), float(payload.get("budget_cp",0)),
         payload.get("nature","DEPENSE COURANTE"), bl_id))
    db.commit(); return {"ok":True}

@app.delete("/api/budget-lines/{bl_id}")
def del_bl(request: Request, bl_id: int, db = Depends(get_db)):
    require_admin(request)
    db.execute("DELETE FROM budget_lines WHERE id=?", (bl_id,)); db.commit()
    return {"ok":True}

# ═══════════════════════════════════════════════════════════
#  ROUTES — TRANSACTIONS
# ═══════════════════════════════════════════════════════════

@app.get("/api/transactions")
def list_tx(request: Request, year: int, direction: str = "", q: str = "",
            status: str = "", db = Depends(get_db)):
    u = require_login(request)
    dirs = user_directions(u)
    sql, params = "SELECT * FROM transactions WHERE year=?", [year]
    if direction and direction in dirs: sql += " AND direction=?"; params.append(direction)
    elif dirs:
        ph = ",".join("?" for _ in dirs)
        sql += f" AND direction IN ({ph})"; params += dirs
    if status: sql += " AND status=?"; params.append(status)
    rows = [dict(r) for r in db.execute(sql + " ORDER BY id DESC", params).fetchall()]
    if q:
        ql = q.lower()
        rows = [r for r in rows if ql in r.get("code_ref","").lower() or
                ql in r.get("intitule","").lower() or ql in r.get("imputation","").lower() or
                ql in r.get("direction","").lower()]
    return rows

@app.post("/api/transactions")
def create_tx(request: Request, payload: dict, db = Depends(get_db)):
    u = require_login(request)
    if u.get("role") == "viewer": raise HTTPException(403,"Read-only")
    dirs = user_directions(u)
    direction = payload.get("direction","").strip().upper()
    if direction not in dirs: raise HTTPException(403,"Direction not allowed")
    year  = int(payload.get("year", date.today().year))
    date_ = payload.get("date_reception", date.today().isoformat())

    # Auto-generate code ref
    n = db.execute("SELECT COUNT(*) FROM transactions WHERE direction=? AND year=?", (direction,year)).fetchone()[0] + 1
    code_ref = f"JD{direction}-{year}{str(date_)[5:7]}{str(date_)[8:10]}-{n:03d}"

    imputation = payload.get("imputation","")
    montant = float(payload.get("montant",0))
    # Check budget status
    bl = db.execute("SELECT * FROM budget_lines WHERE imputation=? AND year=?", (imputation,year)).fetchone()
    if bl:
        eng = db.execute("SELECT COALESCE(SUM(montant),0) FROM transactions WHERE imputation=? AND year=? AND status=\'validated\'",
            (imputation,year)).fetchone()[0]
        dispo = bl["budget_cp"] - eng - montant
        statut_budget = "NORMAL" if dispo >= 0 else "DEPASSEMENT"
    else: statut_budget = "NORMAL"

    cur = db.execute(
        "INSERT INTO transactions (code_ref,date_reception,direction,imputation,nature,intitule,description,montant,year,status,statut_budget,created_by,created_by_name) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (code_ref, date_, direction, imputation,
         payload.get("nature","DEPENSE COURANTE"),
         payload.get("intitule",""), payload.get("description",""),
         montant, year, payload.get("status","validated"), statut_budget,
         u.get("u",""), u.get("name","")))
    db.commit()
    return dict(db.execute("SELECT * FROM transactions WHERE id=?", (cur.lastrowid,)).fetchone())

@app.put("/api/transactions/{tx_id}")
def update_tx(request: Request, tx_id: int, payload: dict, db = Depends(get_db)):
    u = require_login(request)
    if u.get("role") == "viewer": raise HTTPException(403,"Read-only")
    db.execute("UPDATE transactions SET status=?,intitule=?,description=?,montant=? WHERE id=?",
        (payload.get("status","validated"), payload.get("intitule",""),
         payload.get("description",""), float(payload.get("montant",0)), tx_id))
    db.commit(); return {"ok":True}

@app.delete("/api/transactions/{tx_id}")
def del_tx(request: Request, tx_id: int, db = Depends(get_db)):
    u = require_login(request)
    if u.get("role") not in ("admin","dcf_dir","dcf_sub"): raise HTTPException(403,"Admin only")
    db.execute("DELETE FROM transactions WHERE id=?", (tx_id,)); db.commit()
    return {"ok":True}

# ═══════════════════════════════════════════════════════════
#  ROUTES — DASHBOARD
# ═══════════════════════════════════════════════════════════

@app.get("/api/dashboard")
def dashboard(request: Request, year: int, db = Depends(get_db)):
    u = require_login(request)
    dirs = user_directions(u)
    ph   = ",".join("?" for _ in dirs)

    txs  = [dict(r) for r in db.execute(
        f"SELECT * FROM transactions WHERE year=? AND direction IN ({ph})", [year]+dirs).fetchall()] if dirs else []
    bls  = [dict(r) for r in db.execute(
        f"SELECT * FROM budget_lines WHERE year=? AND direction IN ({ph})", [year]+dirs).fetchall()] if dirs else []

    total_budget  = sum(b["budget_cp"] for b in bls)
    total_engage  = sum(t["montant"] for t in txs if t["status"]=="validated")
    total_pending = sum(t["montant"] for t in txs if t["status"]=="pending")
    total_dispo   = total_budget - total_engage

    by_dir = {}
    for t in txs:
        if t["status"] == "validated":
            by_dir[t["direction"]] = by_dir.get(t["direction"],0) + t["montant"]

    by_month = [0]*12
    for t in txs:
        if t["status"] == "validated":
            try:
                m = int(t["date_reception"].split("-")[1])-1
                if 0 <= m < 12: by_month[m] += t["montant"]
            except: pass

    # Budget line summaries per direction
    bl_by_dir = {}
    for b in bls:
        d = b["direction"]
        if d not in bl_by_dir: bl_by_dir[d] = {"budget_cp":0,"engage":by_dir.get(d,0)}
        bl_by_dir[d]["budget_cp"] += b["budget_cp"]

    overdrawn = [{"direction":d,"montant":v["engage"]-v["budget_cp"]} for d,v in bl_by_dir.items() if v["engage"]>v["budget_cp"]]
    recent    = [dict(r) for r in db.execute(
        f"SELECT * FROM transactions WHERE year=? AND direction IN ({ph}) ORDER BY id DESC LIMIT 10",
        [year]+dirs).fetchall()] if dirs else []

    return {"total_budget": total_budget, "total_engage": total_engage,
            "total_pending": total_pending, "total_dispo": total_dispo,
            "tx_count": sum(1 for t in txs if t["status"]=="validated"),
            "pending_count": sum(1 for t in txs if t["status"]=="pending"),
            "by_dir": by_dir, "by_month": by_month,
            "bl_by_dir": bl_by_dir, "overdrawn": overdrawn, "recent": recent}

# ═══════════════════════════════════════════════════════════
#  ROUTES — IMPORT/EXPORT
# ═══════════════════════════════════════════════════════════

@app.get("/api/export/transactions")
def export_tx(request: Request, year: int, direction: str = "", db = Depends(get_db)):
    require_login(request)
    sql, params = "SELECT * FROM transactions WHERE year=?", [year]
    if direction: sql += " AND direction=?"; params.append(direction)
    rows = [dict(r) for r in db.execute(sql+" ORDER BY date_reception,direction", params).fetchall()]
    out  = io.StringIO()
    w    = csv.writer(out)
    w.writerow(["DATE DE RECEPTION","CODE/REF NUMBER","DIRECTION","IMPUTATION COMPTABLE",
                "NATURE","INTITULE DE LA COMMANDE","DESCRIPTION","MONTANT","STATUT","STATUT BUDGET","CREE PAR"])
    for r in rows:
        w.writerow([r["date_reception"],r["code_ref"],r["direction"],r["imputation"],
                    r["nature"],r["intitule"],r["description"],r["montant"],r["status"],r["statut_budget"],r["created_by_name"]])
    out.seek(0)
    return StreamingResponse(iter([out.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=transactions_{year}.csv"})

@app.get("/api/export/template-transactions")
def template_tx(request: Request):
    require_login(request)
    out = io.StringIO()
    w   = csv.writer(out)
    w.writerow(["DATE DE RECEPTION","DIRECTION","IMPUTATION COMPTABLE","NATURE",
                "INTITULE DE LA COMMANDE","DESCRIPTION","MONTANT","STATUT"])
    w.writerow(["2025-01-20","DG","SP4/DG/AD0025/VD0007/T00127/63840100","DEPENSE COURANTE",
                "FRAIS DE MISSION","Description détaillée",2800000,"validated"])
    out.seek(0)
    return StreamingResponse(iter([out.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=template_transactions.csv"})

@app.get("/api/export/template-budget-lines")
def template_bl(request: Request):
    require_login(request)
    out = io.StringIO()
    w   = csv.writer(out)
    w.writerow(["YEAR","DIRECTION","IMPUTATION COMPTABLE","LIBELLE","NATURE","BUDGET CP (FCFA)"])
    w.writerow([2026,"DG","SP4/DG/AD0025/VD0007/T00127/63840100","FRAIS DE MISSION A L\'EXTERIEUR","DEPENSE COURANTE",50000000])
    out.seek(0)
    return StreamingResponse(iter([out.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=template_budget_lines.csv"})

@app.post("/api/import/transactions")
async def import_tx(request: Request, file: UploadFile = File(...), year: int = Form(...), db = Depends(get_db)):
    u = require_login(request)
    if u.get("role") not in ("admin","dcf_dir","dcf_sub"): raise HTTPException(403,"Admin only")
    content = await file.read()
    reader  = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    created, errors = 0, []
    for i, row in enumerate(reader, 2):
        try:
            direction = (row.get("DIRECTION") or row.get("direction","")).strip().upper()
            imp = (row.get("IMPUTATION COMPTABLE") or row.get("imputation","")).strip()
            montant = float((row.get("MONTANT") or row.get("montant",0) or "0").replace(" ","").replace(",","."))
            date_r  = (row.get("DATE DE RECEPTION") or row.get("date_reception", date.today().isoformat())).strip()
            if not direction or not imp: continue
            n = db.execute("SELECT COUNT(*) FROM transactions WHERE direction=? AND year=?", (direction,year)).fetchone()[0] + 1
            code_ref = f"JD{direction}-{year}IMPORT-{n:03d}"
            db.execute("INSERT INTO transactions (code_ref,date_reception,direction,imputation,nature,intitule,description,montant,year,status,created_by,created_by_name) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (code_ref, date_r, direction, imp,
                 (row.get("NATURE") or "DEPENSE COURANTE").strip(),
                 (row.get("INTITULE DE LA COMMANDE") or "").strip(),
                 (row.get("DESCRIPTION") or "").strip(),
                 montant, year, (row.get("STATUT") or "validated").strip(),
                 u.get("u",""), u.get("name","IMPORT")))
            created += 1
        except Exception as e: errors.append(f"Ligne {i}: {e}")
    db.commit()
    return {"created": created, "errors": errors}

@app.post("/api/import/budget-lines")
async def import_bl(request: Request, file: UploadFile = File(...), db = Depends(get_db)):
    u = require_login(request)
    if u.get("role") not in ("admin","dcf_dir","dcf_sub"): raise HTTPException(403,"Admin only")
    content = await file.read()
    reader  = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    created, updated, errors = 0, 0, []
    for i, row in enumerate(reader, 2):
        try:
            yr   = int(row.get("YEAR") or row.get("year",0))
            dirn = (row.get("DIRECTION") or row.get("direction","")).strip().upper()
            imp  = (row.get("IMPUTATION COMPTABLE") or row.get("imputation","")).strip()
            lib  = (row.get("LIBELLE") or row.get("libelle","")).strip()
            nat  = (row.get("NATURE") or "DEPENSE COURANTE").strip()
            bcp  = float((str(row.get("BUDGET CP (FCFA)") or row.get("budget_cp",0) or "0")).replace(" ","").replace(",","."))
            if not yr or not dirn or not imp: continue
            existing = db.execute("SELECT id FROM budget_lines WHERE year=? AND direction=? AND imputation=?", (yr,dirn,imp)).fetchone()
            if existing:
                db.execute("UPDATE budget_lines SET libelle=?,nature=?,budget_cp=? WHERE id=?", (lib,nat,bcp,existing["id"])); updated+=1
            else:
                db.execute("INSERT INTO budget_lines (year,direction,imputation,libelle,nature,budget_cp) VALUES (?,?,?,?,?,?)", (yr,dirn,imp,lib,nat,bcp)); created+=1
        except Exception as e: errors.append(f"Ligne {i}: {e}")
    db.commit()
    return {"created": created, "updated": updated, "errors": errors}

# ═══════════════════════════════════════════════════════════
#  ROUTES — FICHE OFFICIELLE
# ═══════════════════════════════════════════════════════════

@app.get("/fiche", response_class=HTMLResponse)
def fiche_multi(request: Request, ids: str, db = Depends(get_db)):
    """Print 1 or 2 transactions per A4 page. ids = comma-separated tx ids"""
    user = require_login(request)
    tx_ids = [int(i.strip()) for i in ids.split(",") if i.strip().isdigit()]
    txs = []
    for tid in tx_ids[:20]:  # max 20
        t = db.execute("SELECT * FROM transactions WHERE id=?", (tid,)).fetchone()
        if t: txs.append(dict(t))

    # Build fiche HTML blocks (2 per page)
    pages_html = []
    for i in range(0, len(txs), 2):
        pair = txs[i:i+2]
        blocks = "".join(_fiche_block(t, db, user) for t in pair)
        # If only 1 on last page, add spacer
        if len(pair) == 1:
            blocks += "<div style=\'height:10mm\'></div>"
        pages_html.append(f"<div class=\'page\'>{blocks}</div>")

    body = "".join(pages_html)

    return HTMLResponse(f"""<!doctype html>
<html lang=\'fr\'><head><meta charset=\'utf-8\'/>
<title>Fiches d\'engagement</title>
<style>
*{{box-sizing:border-box;}}
body{{font-family:Arial,sans-serif;margin:0;padding:0;font-size:11pt;color:#000;}}
.noprint{{margin:12px;padding:8px;background:#f1f5f9;border-radius:6px;display:flex;gap:10px;}}
.noprint button{{padding:8px 16px;background:#1f4d8f;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:13px;font-weight:600;}}
.page{{width:210mm;min-height:297mm;padding:10mm 12mm;display:flex;flex-direction:column;gap:6mm;page-break-after:always;}}
.fiche{{border:1px solid #000;padding:4mm;flex:1;display:flex;flex-direction:column;}}
.fhdr{{display:flex;align-items:flex-start;gap:8px;border-bottom:2px solid #1f4d8f;padding-bottom:3mm;margin-bottom:3mm;}}
.flogo{{background:#1f4d8f;color:#fff;padding:5px 9px;font-weight:800;font-size:14pt;border-radius:4px;white-space:nowrap;}}
.ftitle h1{{font-size:10pt;font-weight:700;color:#1f4d8f;margin:0;}}
.ftitle p{{font-size:8pt;color:#64748b;margin:1px 0 0;}}
.sec{{background:#1f4d8f;color:#fff;padding:2px 6px;font-size:8pt;font-weight:700;text-transform:uppercase;letter-spacing:.04em;margin:3mm 0 2mm;}}
.box{{border:1px solid #334155;padding:2mm 3mm;margin-bottom:2mm;}}
.r{{display:flex;border-bottom:1px solid #e2e8f0;padding:1.5px 0;font-size:9pt;align-items:flex-start;}}
.r:last-child{{border-bottom:none;}}
.rl{{color:#475569;min-width:140px;font-weight:600;flex-shrink:0;}}
.rv{{flex:1;word-break:break-word;}}
.amt{{font-size:12pt;font-weight:800;color:#1f4d8f;margin:3mm 0 1mm;}}
.amtsub{{font-size:9pt;color:#334155;margin-bottom:2mm;}}
.dispo{{border:2px solid #000;padding:2mm 4mm;display:flex;justify-content:space-between;align-items:center;margin:3mm 0;}}
.dispo-lbl{{font-weight:800;font-size:11pt;letter-spacing:.1em;}}
.chks{{display:flex;gap:18px;font-size:10pt;font-weight:700;}}
.chk{{display:flex;align-items:center;gap:5px;}}
.chkb{{width:14px;height:14px;border:2px solid #000;display:inline-flex;align-items:center;justify-content:center;font-size:9pt;font-weight:800;}}
.signs{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-top:3mm;}}
.sign{{border:1px solid #334155;padding:2mm;min-height:16mm;}}
.sign label{{font-size:7pt;font-weight:700;text-transform:uppercase;color:#64748b;display:block;margin-bottom:2mm;}}
.initiator{{font-size:8pt;color:#64748b;text-align:right;margin-bottom:2mm;}}
@media print{{.noprint{{display:none!important;}} .page{{padding:8mm 10mm;}} @page{{size:A4;margin:0;}}}}
</style></head><body>
<div class=\'noprint\'>
  <button onclick=\'window.print()\'>🖨 Imprimer / Exporter PDF</button>
  <button onclick=\'window.close()\' style=\'background:#64748b\'>Fermer</button>
  <span style=\'font-size:12px;color:#64748b;align-self:center\'>{len(txs)} fiche(s) sur {len(pages_html)} page(s) A4</span>
</div>
{body}
</body></html>""")

def _fiche_block(t, db, user):
    bl = db.execute("SELECT * FROM budget_lines WHERE imputation=? AND year=?", (t["imputation"], t["year"])).fetchone()
    prevision   = bl["budget_cp"] if bl else 0
    libelle_bl  = bl["libelle"] if bl else t["imputation"]
    eng_before  = db.execute("SELECT COALESCE(SUM(montant),0) FROM transactions WHERE imputation=? AND year=? AND status=\'validated\' AND id<?",
        (t["imputation"], t["year"], t["id"])).fetchone()[0]
    solde_avant = prevision - eng_before
    solde_apres = solde_avant - t["montant"]
    dispo       = solde_apres >= 0
    gc          = "#16a34a" if dispo else "#dc2626"

    # DISPONIBLE display
    if dispo:
        oui_box = "<div class=\'chkb\'style=\'border-color:#16a34a;background:#dcfce7;color:#16a34a\'>✓</div> OUI"
        non_box = "<div class=\'chkb\'></div> NON"
    else:
        oui_box = "<div class=\'chkb\'></div> OUI"
        non_box = "<div class=\'chkb\'style=\'border-color:#dc2626;background:#fee2e2;color:#dc2626\'>✓</div> NON"

    return f"""
<div class=\'fiche\'>
  <div class=\'fhdr\'>
    <div class=\'flogo\'>CAMTEL</div>
    <div class=\'ftitle\'>
      <h1>REPRÉSENTATION RÉGIONALE {t.get("direction","—")} — BUSINESS UNIT FIXE</h1>
      <p>FICHE DE SUIVI BUDGÉTAIRE — SAAF / DCF / CONTRÔLE BUDGÉTAIRE</p>
    </div>
  </div>

  <div class=\'sec\'>Informations du compte budgétaire</div>
  <div class=\'box\'>
    <div class=\'r\'><span class=\'rl\'>Prévision sur le compte :</span><span class=\'rv\'><strong>{_fmt_fcfa(prevision)} FCFA</strong></span></div>
    <div class=\'r\'><span class=\'rl\'>NOTE COMPTABILITÉ — Solde initial :</span><span class=\'rv\'><strong>{_fmt_fcfa(prevision)} FCFA</strong></span></div>
  </div>

  <div class=\'sec\'>Référence(s) du compte / Libellé(s) / Montant de l\'engagement</div>
  <div class=\'box\'>
    <div class=\'r\'><span class=\'rl\'>Référence :</span><span class=\'rv\'style=\'font-family:monospace;font-size:8pt\'>{t["imputation"]}</span></div>
    <div class=\'r\'><span class=\'rl\'>Code/Réf. dossier :</span><span class=\'rv\'>{t["code_ref"]}</span></div>
    <div class=\'r\'><span class=\'rl\'>Direction :</span><span class=\'rv\'>{t["direction"]}</span></div>
    <div class=\'r\'><span class=\'rl\'>Date :</span><span class=\'rv\'>{t["date_reception"]}</span></div>
    <div class=\'r\'><span class=\'rl\'>Nature :</span><span class=\'rv\'>{t["nature"]}</span></div>
    <div style=\'margin-top:2mm\'><strong>{libelle_bl}</strong></div>
    <div style=\'margin-top:1mm;font-size:9pt;line-height:1.5\'><strong>OBJET / DESCRIPTION :</strong> {t["description"] or t["intitule"]}</div>
    <div class=\'amt\'>Montant de l\'engagement : {_fmt_fcfa(t["montant"])} FCFA</div>
    <div class=\'box\' style=\'padding:1.5mm 3mm;margin-top:1mm\'>
      <div class=\'r\'><span class=\'rl\'>Solde avant engagement :</span><span class=\'rv\'>{_fmt_fcfa(solde_avant)} FCFA</span></div>
      <div class=\'r\'><span class=\'rl\'><strong>Solde final du compte :</strong></span><span class=\'rv\'style=\'color:{gc};font-weight:800\'>{_fmt_fcfa(solde_apres)} FCFA</span></div>
    </div>
  </div>

  <div class=\'dispo\'>
    <div class=\'dispo-lbl\'>DISPONIBLE</div>
    <div class=\'chks\'>
      <div class=\'chk\'>{oui_box}</div>
      <div class=\'chk\'>{non_box}</div>
    </div>
  </div>

  <div class=\'initiator\'>Initié par : {t.get("created_by_name") or t.get("created_by","—")}</div>

  <div class=\'signs\'>
    <div class=\'sign\'><label>Avis de la DCF</label></div>
    <div class=\'sign\'><label>Visa du Contrôleur Budgétaire</label></div>
    <div class=\'sign\'><label>Approbation Direction</label></div>
  </div>
</div>"""

# ═══════════════════════════════════════════════════════════
#  ROUTES — MONTHLY REPORT
# ═══════════════════════════════════════════════════════════

@app.get("/api/report/monthly")
def monthly_report(request: Request, year: int, month: int, db = Depends(get_db)):
    u = require_login(request)
    dirs = user_directions(u)
    ph   = ",".join("?" for _ in dirs)
    txs  = [dict(r) for r in db.execute(
        f"SELECT * FROM transactions WHERE year=? AND strftime(\'%m\',date_reception)=? AND direction IN ({ph})",
        [year, f"{month:02d}"]+dirs).fetchall()] if dirs else []
    bls  = [dict(r) for r in db.execute(
        f"SELECT * FROM budget_lines WHERE year=? AND direction IN ({ph})", [year]+dirs).fetchall()] if dirs else []

    total_budget = sum(b["budget_cp"] for b in bls)
    total_engage = sum(t["montant"] for t in txs if t["status"]=="validated")

    out = io.StringIO()
    w   = csv.writer(out)
    mois = ["Janvier","Février","Mars","Avril","Mai","Juin","Juillet","Août","Septembre","Octobre","Novembre","Décembre"]
    w.writerow([f"RAPPORT MENSUEL CAMTEL — {mois[month-1].upper()} {year}"])
    w.writerow([]); w.writerow(["RÉSUMÉ EXÉCUTIF"])
    w.writerow(["Budget total CP", total_budget]); w.writerow(["Engagé ce mois", total_engage])
    w.writerow(["Taux d\'engagement", f"{round(total_engage/total_budget*100,1) if total_budget else 0}%"])
    w.writerow([])
    w.writerow(["DÉTAIL DES TRANSACTIONS"])
    w.writerow(["Date","Code/Réf","Direction","Imputation","Nature","Intitulé","Montant","Statut Budget"])
    for t in txs:
        w.writerow([t["date_reception"],t["code_ref"],t["direction"],t["imputation"],
                    t["nature"],t["intitule"],t["montant"],t["statut_budget"]])
    out.seek(0)
    return StreamingResponse(iter([out.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=rapport_{year}_{month:02d}.csv"})

# ═══════════════════════════════════════════════════════════
#  HTML FRONTEND — INJECTED BELOW
# ═══════════════════════════════════════════════════════════

LOGIN_HTML = "<!doctype html>\n<html lang='fr'><head><meta charset='utf-8'/>\n<meta name='viewport' content='width=device-width,initial-scale=1'/>\n<title>CAMTEL - Connexion</title>\n<style>\n*{box-sizing:border-box;margin:0;padding:0;}\nbody{font-family:'Segoe UI',system-ui,sans-serif;background:linear-gradient(135deg,#0f2a5e 0%,#1f4d8f 55%,#2563eb 100%);min-height:100vh;display:flex;align-items:center;justify-content:center;}\n.card{background:#fff;border-radius:16px;padding:36px 32px;width:420px;box-shadow:0 20px 60px rgba(0,0,0,.3);}\n.lrow{display:flex;align-items:center;gap:12px;margin-bottom:24px;}\n.logo{background:#1f4d8f;color:#fff;width:50px;height:50px;border-radius:12px;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:22px;flex-shrink:0;}\nh2{font-size:17px;font-weight:700;color:#0f2a5e;} p{font-size:12px;color:#64748b;margin-top:2px;}\nlabel{display:block;font-size:11px;font-weight:700;color:#475569;margin:14px 0 4px;text-transform:uppercase;letter-spacing:.04em;}\ninput{width:100%;padding:11px 12px;border-radius:8px;border:1.5px solid #e2e8f0;font-size:14px;font-family:inherit;}\ninput:focus{outline:none;border-color:#2563eb;}\nbutton{width:100%;padding:12px;border-radius:8px;background:#1f4d8f;color:#fff;border:none;cursor:pointer;font-size:14px;font-weight:600;margin-top:20px;}\nbutton:hover{background:#2563eb;}\n.hint{color:#94a3b8;font-size:12px;margin-top:14px;text-align:center;}\n.err{background:#fee2e2;color:#dc2626;padding:9px 12px;border-radius:6px;font-size:13px;margin-bottom:12px;border-left:3px solid #dc2626;}\n</style></head>\n<body><div class='card'>\n  <div class='lrow'>\n    <div class='logo'>C</div>\n    <div><h2>CAMTEL - Gestion Budgetaire</h2><p>SAAF / DCF / Controle Budgetaire</p></div>\n  </div>\n  __ERR__\n  <form method='post' action='/api/login'>\n    <label>Nom d utilisateur</label>\n    <input name='username' placeholder='admin' required autofocus autocomplete='username'/>\n    <label>Mot de passe</label>\n    <input name='password' type='password' placeholder='........' required autocomplete='current-password'/>\n    <button type='submit'>Se connecter</button>\n  </form>\n  <div class='hint'>Contactez l administrateur pour vos acces.</div>\n</div></body></html>"

APP_HTML = '<!doctype html>\n<html lang=\'fr\'>\n<head>\n<meta charset=\'utf-8\'/><meta name=\'viewport\' content=\'width=device-width,initial-scale=1\'/>\n<title>CAMTEL – Gestion Budgétaire 2025</title>\n<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>\n<style>\n:root{\n  --navy:#0f2a5e;--blue:#1f4d8f;--b2:#2563eb;--b3:#dbeafe;\n  --green:#16a34a;--g2:#dcfce7;--red:#dc2626;--r2:#fee2e2;\n  --yel:#d97706;--y2:#fef9c3;--bg:#f0f4f8;--card:#fff;\n  --bdr:#e2e8f0;--txt:#1e293b;--muted:#64748b;--lt:#f8fafc;\n}\n*{box-sizing:border-box;margin:0;padding:0;}\nbody{font-family:\'Segoe UI\',system-ui,sans-serif;background:var(--bg);color:var(--txt);font-size:14px;}\n/* ── HEADER ── */\nheader{background:var(--navy);color:#fff;padding:0 16px;height:54px;display:flex;align-items:center;gap:10px;position:sticky;top:0;z-index:200;box-shadow:0 2px 8px rgba(0,0,0,.25);}\n.hlogo{background:rgba(255,255,255,.18);padding:5px 10px;border-radius:7px;font-weight:800;font-size:15px;letter-spacing:.5px;}\n.htitle{flex:1;} .htitle h1{font-size:13px;font-weight:700;} .htitle p{font-size:10px;opacity:.65;}\nnav{display:flex;gap:2px;}\nnav button{background:transparent;color:rgba(255,255,255,.7);border:none;padding:7px 11px;border-radius:6px;cursor:pointer;font-size:12px;font-weight:500;white-space:nowrap;}\nnav button:hover,nav button.active{background:rgba(255,255,255,.2);color:#fff;}\n.upill{background:rgba(255,255,255,.12);padding:4px 10px;border-radius:20px;font-size:11px;display:flex;align-items:center;gap:6px;white-space:nowrap;}\n/* ── BUTTONS ── */\n.btn{padding:8px 14px;border-radius:7px;border:none;cursor:pointer;font-size:12px;font-weight:600;font-family:inherit;transition:all .15s;}\n.bp{background:var(--b2);color:#fff;} .bp:hover{background:#1d4ed8;}\n.bs{background:var(--bdr);color:var(--txt);} .bs:hover{background:#cbd5e1;}\n.bd{background:var(--red);color:#fff;} .bd:hover{background:#b91c1c;}\n.bg2{background:var(--g2);color:var(--green);border:1px solid var(--green);}\n.bsm{padding:5px 10px;font-size:11px;}\n.bxs{padding:3px 7px;font-size:11px;}\n/* ── LAYOUT ── */\n.wrap{max-width:1400px;margin:0 auto;padding:14px 14px;}\n.krow{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:14px;}\n@media(max-width:900px){.krow{grid-template-columns:repeat(2,1fr);}}\n.kpi{background:var(--card);border:1px solid var(--bdr);border-radius:11px;padding:13px 15px;}\n.kpi label{font-size:10px;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);font-weight:600;}\n.kpi .val{font-size:18px;font-weight:800;margin-top:4px;line-height:1.1;}\n.kpi .sub{font-size:11px;color:var(--muted);margin-top:3px;}\n.kpi.kb .val{color:var(--blue);} .kpi.kr .val{color:var(--red);} .kpi.ky .val{color:var(--yel);} .kpi.kg .val{color:var(--green);}\n/* ── CARDS ── */\n.card{background:var(--card);border:1px solid var(--bdr);border-radius:11px;overflow:hidden;margin-bottom:12px;}\n.ch{padding:10px 14px;border-bottom:1px solid var(--bdr);display:flex;align-items:center;justify-content:space-between;background:var(--lt);gap:8px;}\n.ch h2{font-size:13px;font-weight:700;flex:1;}\n.cb{padding:12px;}\n.g2{display:grid;grid-template-columns:1fr 1fr;gap:12px;}\n.g3{display:grid;grid-template-columns:2fr 1fr;gap:12px;}\n@media(max-width:900px){.g2,.g3{grid-template-columns:1fr;}}\n/* ── TOOLBAR ── */\n.tbar{display:flex;gap:7px;flex-wrap:wrap;padding:8px 12px;background:var(--lt);border-bottom:1px solid var(--bdr);align-items:center;}\n.tbar input,.tbar select{padding:6px 10px;border-radius:7px;border:1px solid var(--bdr);font-size:12px;background:#fff;font-family:inherit;}\n.tbar input{min-width:160px;}\n/* ── TABLES ── */\n.tbl-wrap{overflow-x:auto;}\ntable{width:100%;border-collapse:collapse;font-size:12px;}\nth{background:var(--lt);padding:8px 9px;text-align:left;font-weight:700;font-size:10px;color:var(--muted);border-bottom:2px solid var(--bdr);white-space:nowrap;text-transform:uppercase;letter-spacing:.04em;}\ntd{padding:7px 9px;border-bottom:1px solid #f1f5f9;vertical-align:middle;}\ntr:hover td{background:#f8fafc;}\n.tc{text-align:center;} .tr{text-align:right;}\n/* ── BADGES ── */\n.bdg{display:inline-flex;padding:2px 7px;border-radius:20px;font-size:10px;font-weight:700;white-space:nowrap;}\n.bg{background:var(--g2);color:var(--green);} .br{background:var(--r2);color:var(--red);}\n.by{background:var(--y2);color:var(--yel);} .bb{background:var(--b3);color:var(--blue);}\n.bdep{background:#fee2e2;color:#991b1b;border:1px solid #fca5a5;}\n/* ── PROGRESS ── */\n.prg{height:6px;background:var(--bdr);border-radius:3px;overflow:hidden;margin-top:4px;}\n.prf{height:100%;border-radius:3px;transition:width .5s;}\n/* ── MODALS ── */\n.mbg{display:none;position:fixed;inset:0;background:rgba(10,25,55,.5);z-index:300;align-items:flex-start;justify-content:center;padding-top:40px;overflow-y:auto;}\n.mbg.open{display:flex;}\n.modal{background:#fff;border-radius:13px;width:min(700px,95vw);max-height:86vh;overflow-y:auto;box-shadow:0 20px 60px rgba(0,0,0,.2);margin-bottom:20px;}\n.mh{padding:13px 17px;border-bottom:1px solid var(--bdr);display:flex;align-items:center;justify-content:space-between;background:var(--lt);position:sticky;top:0;z-index:1;}\n.mh h3{font-size:14px;font-weight:700;}\n.mb{padding:17px;}\n.mf{padding:11px 17px;border-top:1px solid var(--bdr);display:flex;gap:8px;justify-content:flex-end;background:var(--lt);}\n/* ── FORMS ── */\n.fr{display:grid;gap:8px;} .fc2{grid-template-columns:1fr 1fr;} .fc3{grid-template-columns:1fr 1fr 1fr;}\n@media(max-width:600px){.fc2,.fc3{grid-template-columns:1fr;}}\n.fld label{display:block;font-size:10px;font-weight:700;color:var(--muted);margin-bottom:3px;text-transform:uppercase;letter-spacing:.04em;}\n.fld input,.fld select,.fld textarea{width:100%;padding:8px 10px;border-radius:7px;border:1.5px solid var(--bdr);font-size:13px;font-family:inherit;background:#fff;}\n.fld input:focus,.fld select:focus,.fld textarea:focus{outline:none;border-color:var(--b2);box-shadow:0 0 0 3px rgba(37,99,235,.12);}\n.fld textarea{min-height:55px;resize:vertical;}\n.fld input[readonly]{background:var(--lt);cursor:default;}\n/* ── ALERTS ── */\n.alrt{padding:8px 12px;border-radius:7px;font-size:12px;margin-bottom:10px;display:flex;align-items:flex-start;gap:8px;}\n.alrt-r{background:var(--r2);color:var(--red);border-left:3px solid var(--red);}\n.alrt-y{background:var(--y2);color:var(--yel);border-left:3px solid var(--yel);}\n.alrt-g{background:var(--g2);color:var(--green);border-left:3px solid var(--green);}\n.alrt-b{background:var(--b3);color:var(--blue);border-left:3px solid var(--b2);}\n/* ── TABS ── */\n.tab-content{display:none;} .tab-content.active{display:block;}\n/* ── TOAST ── */\n.toast{position:fixed;right:14px;bottom:14px;padding:10px 16px;border-radius:9px;font-size:13px;font-weight:600;z-index:999;display:none;box-shadow:0 4px 14px rgba(0,0,0,.15);max-width:350px;}\n/* ── EMPTY ── */\n.empty{padding:36px 20px;text-align:center;color:var(--muted);}\n/* ── DIR LIST ── */\n.dir-chip{display:inline-flex;padding:3px 9px;border-radius:20px;font-size:11px;font-weight:600;background:var(--b3);color:var(--blue);margin:2px;cursor:pointer;}\n.dir-chip.selected{background:var(--blue);color:#fff;}\n/* ── Checkbox row ── */\n.cbox-row{display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--lt);}\n.cbox-row:last-child{border-bottom:none;}\n.cbox-row input[type=checkbox]{width:15px;height:15px;accent-color:var(--b2);}\n/* ── Scan preview ── */\n.scan-area{border:2px dashed var(--bdr);border-radius:9px;padding:18px;text-align:center;cursor:pointer;transition:border .2s;}\n.scan-area:hover{border-color:var(--b2);}\n</style>\n</head>\n<body>\n\n<!-- HEADER -->\n<header>\n  <div class=\'hlogo\'>C</div>\n  <div class=\'htitle\'>\n    <h1>CAMTEL – Gestion Budgétaire</h1>\n    <p>SAAF / DCF / Contrôle Budgétaire</p>\n  </div>\n  <nav>\n    <button class=\'active\' id=\'nav-dashboard\' onclick=\'showTab("dashboard")\'>📊 Dashboard</button>\n    <button id=\'nav-transactions\' onclick=\'showTab("transactions")\'>📋 Transactions</button>\n    <button id=\'nav-budgetlines\' onclick=\'showTab("budgetlines")\'>📂 Lignes Budget</button>\n    <button id=\'nav-reports\' onclick=\'showTab("reports")\'>📈 Rapports</button>\n    <button id=\'nav-import\' onclick=\'showTab("import")\'>⬆ Import/Export</button>\n    <button id=\'nav-users\' onclick=\'showTab("users")\' style=\'display:none\'>👥 Utilisateurs</button>\n    <button id=\'nav-settings\' onclick=\'showTab("settings")\' style=\'display:none\'>⚙ Paramètres</button>\n  </nav>\n  <div class=\'upill\'>\n    <span id=\'uname\'>—</span>\n    <span id=\'urole\' class=\'bdg bb\' style=\'font-size:9px\'>—</span>\n  </div>\n  <button class=\'btn bd bsm\' onclick=\'logout()\' style=\'margin-left:6px\'>Déconnexion</button>\n</header>\n\n<div class=\'wrap\'>\n  <!-- GLOBAL FILTERS -->\n  <div style=\'display:flex;align-items:center;gap:10px;margin-bottom:12px;flex-wrap:wrap;\'>\n    <label style=\'font-size:11px;font-weight:700;color:var(--muted)\'>ANNÉE :</label>\n    <select id=\'g-year\' style=\'padding:5px 10px;border-radius:7px;border:1px solid var(--bdr);font-weight:700;font-size:13px;\' onchange=\'onYearChange()\'></select>\n    <label style=\'font-size:11px;font-weight:700;color:var(--muted)\'>DIRECTION :</label>\n    <select id=\'g-dir\' style=\'padding:5px 10px;border-radius:7px;border:1px solid var(--bdr);font-size:13px;min-width:120px;\' onchange=\'onDirChange()\'></select>\n    <span id=\'last-upd\' style=\'font-size:10px;color:var(--muted);margin-left:auto\'></span>\n    <button class=\'btn bs bsm\' onclick=\'refreshAll()\'>↻ Actualiser</button>\n  </div>\n\n  <!-- KPIs -->\n  <div class=\'krow\'>\n    <div class=\'kpi kb\'><label>Budget CP Total</label><div class=\'val\' id=\'kpi-bud\'>—</div><div class=\'sub\' id=\'kpi-bud-s\'>0 ligne(s)</div></div>\n    <div class=\'kpi kr\'><label>Cumul Engagé</label><div class=\'val\' id=\'kpi-eng\'>—</div><div class=\'sub\' id=\'kpi-eng-s\'>0 transaction(s)</div></div>\n    <div class=\'kpi ky\'><label>En Attente</label><div class=\'val\' id=\'kpi-pend\'>—</div><div class=\'sub\' id=\'kpi-pend-s\'>—</div></div>\n    <div class=\'kpi kg\'><label>Disponible Après</label><div class=\'val\' id=\'kpi-dispo\'>—</div><div class=\'sub\' id=\'kpi-dispo-s\'>—</div></div>\n  </div>\n  <div id=\'alerts-row\'></div>\n\n  <!-- ─── DASHBOARD ─── -->\n  <div id=\'tab-dashboard\' class=\'tab-content active\'>\n    <div class=\'g3\' style=\'margin-bottom:12px\'>\n      <div class=\'card\'><div class=\'ch\'><h2>Engagements par direction</h2></div><div class=\'cb\'><canvas id=\'ch-dir\' height=\'185\'></canvas></div></div>\n      <div class=\'card\'><div class=\'ch\'><h2>Tendance mensuelle</h2></div><div class=\'cb\'><canvas id=\'ch-mo\' height=\'185\'></canvas></div></div>\n    </div>\n    <div class=\'card\'>\n      <div class=\'ch\'><h2>Taux d\'utilisation budgétaire</h2></div>\n      <div class=\'cb\' id=\'dir-prog\'><div class=\'empty\'>Chargement...</div></div>\n    </div>\n    <div class=\'card\'>\n      <div class=\'ch\'><h2>Dernières transactions</h2></div>\n      <div class=\'tbl-wrap\'><table>\n        <thead><tr><th>Date</th><th>Code/Réf</th><th>Direction</th><th>Imputation</th><th>Intitulé</th><th class=\'tr\'>Montant</th><th>Statut</th></tr></thead>\n        <tbody id=\'rec-rows\'></tbody>\n      </table></div>\n    </div>\n  </div>\n\n  <!-- ─── TRANSACTIONS ─── -->\n  <div id=\'tab-transactions\' class=\'tab-content\'>\n    <div class=\'card\'>\n      <div class=\'tbar\'>\n        <select id=\'tx-f-dir\'><option value=\'\'>Toutes directions</option></select>\n        <select id=\'tx-f-status\'><option value=\'\'>Tous statuts</option><option value=\'validated\'>Validé</option><option value=\'pending\'>Brouillon</option></select>\n        <input id=\'tx-q\' placeholder=\'🔍 Réf, intitulé, imputation...\'/>\n        <div style=\'margin-left:auto;display:flex;gap:6px;flex-wrap:wrap;\'>\n          <button class=\'btn bp bsm viewer-hide\' onclick=\'openTxModal()\'>+ Nouvelle transaction</button>\n          <button class=\'btn bg2 bsm\' id=\'print-selected-btn\' onclick=\'printSelected()\' style=\'display:none\'>🖨 Imprimer sélection</button>\n          <button class=\'btn bs bsm\' onclick=\'exportTx()\'>⬇ CSV</button>\n        </div>\n      </div>\n      <div id=\'tx-select-info\' style=\'padding:6px 12px;background:var(--b3);font-size:12px;color:var(--blue);display:none\'>\n        <strong id=\'tx-sel-count\'>0</strong> transaction(s) sélectionnée(s) — max 2 par fiche A4\n      </div>\n      <div class=\'tbl-wrap\'><table>\n        <thead><tr>\n          <th><input type=\'checkbox\' id=\'sel-all\' onchange=\'toggleSelAll(this)\'/></th>\n          <th>Date</th><th>Code/Réf</th><th>Direction</th><th>Imputation</th>\n          <th>Nature</th><th>Intitulé</th><th class=\'tr\'>Montant</th><th>Statut Budget</th><th>Statut</th><th>Initié par</th><th></th>\n        </tr></thead>\n        <tbody id=\'tx-rows\'></tbody>\n      </table></div>\n      <div id=\'tx-empty\' class=\'empty\' style=\'display:none\'>Aucune transaction trouvée.</div>\n    </div>\n  </div>\n\n  <!-- ─── BUDGET LINES ─── -->\n  <div id=\'tab-budgetlines\' class=\'tab-content\'>\n    <div class=\'card\'>\n      <div class=\'tbar\'>\n        <select id=\'bl-f-dir\'><option value=\'\'>Toutes directions</option></select>\n        <input id=\'bl-q\' placeholder=\'🔍 Imputation, libellé...\'/>\n        <div style=\'margin-left:auto;display:flex;gap:6px\'>\n          <button class=\'btn bp bsm admin-only\' onclick=\'openBLModal()\'>+ Nouvelle ligne</button>\n          <button class=\'btn bs bsm\' onclick=\'exportBL()\'>⬇ CSV</button>\n        </div>\n      </div>\n      <div class=\'tbl-wrap\'><table>\n        <thead><tr>\n          <th>Année</th><th>Direction</th><th>Imputation comptable</th><th>Libellé</th>\n          <th>Nature</th><th class=\'tr\'>Budget CP</th><th class=\'tr\'>Cumul Engagé</th>\n          <th class=\'tr\'>Disponible</th><th>Statut</th><th class=\'admin-only\'></th>\n        </tr></thead>\n        <tbody id=\'bl-rows\'></tbody>\n      </table></div>\n      <div id=\'bl-empty\' class=\'empty\' style=\'display:none\'>Aucune ligne budgétaire.</div>\n    </div>\n  </div>\n\n  <!-- ─── REPORTS ─── -->\n  <div id=\'tab-reports\' class=\'tab-content\'>\n    <div class=\'g2\'>\n      <div class=\'card\'>\n        <div class=\'ch\'><h2>Rapport mensuel</h2></div>\n        <div class=\'cb\'>\n          <div class=\'fr fc2\' style=\'margin-bottom:12px\'>\n            <div class=\'fld\'><label>Année</label><select id=\'rp-year\'></select></div>\n            <div class=\'fld\'><label>Mois</label>\n              <select id=\'rp-month\'>\n                <option value=\'1\'>Janvier</option><option value=\'2\'>Février</option><option value=\'3\'>Mars</option>\n                <option value=\'4\'>Avril</option><option value=\'5\'>Mai</option><option value=\'6\'>Juin</option>\n                <option value=\'7\'>Juillet</option><option value=\'8\'>Août</option><option value=\'9\'>Septembre</option>\n                <option value=\'10\'>Octobre</option><option value=\'11\'>Novembre</option><option value=\'12\'>Décembre</option>\n              </select>\n            </div>\n          </div>\n          <div style=\'display:flex;gap:8px;flex-wrap:wrap;\'>\n            <button class=\'btn bp\' onclick=\'downloadReport()\'>⬇ Télécharger rapport CSV</button>\n          </div>\n          <div style=\'margin-top:14px;padding:12px;background:var(--b3);border-radius:8px;font-size:12px;color:var(--blue)\'>\n            <strong>Note :</strong> Le rapport mensuel (format CSV/Excel) est généré automatiquement et peut être envoyé par email au Directeur DCF et au Sous-Directeur Budget.\n            Pour activer l\'envoi automatique, configurez les emails dans ⚙ Paramètres.\n          </div>\n        </div>\n      </div>\n      <div class=\'card\'>\n        <div class=\'ch\'><h2>Récapitulatif annuel</h2></div>\n        <div class=\'cb\' id=\'rp-summary\'><div class=\'empty\'>Sélectionnez une période.</div></div>\n      </div>\n    </div>\n    <div class=\'card\'>\n      <div class=\'ch\'><h2>Suivi par direction — Année <span id=\'rp-year-label\'>—</span></h2></div>\n      <div class=\'tbl-wrap\'><table>\n        <thead><tr><th>Direction</th><th class=\'tr\'>Budget CP</th><th class=\'tr\'>Engagé</th><th class=\'tr\'>Disponible</th><th>Taux</th><th>Statut</th></tr></thead>\n        <tbody id=\'rp-dir-rows\'></tbody>\n      </table></div>\n    </div>\n  </div>\n\n  <!-- ─── IMPORT/EXPORT ─── -->\n  <div id=\'tab-import\' class=\'tab-content\'>\n    <div class=\'g2\'>\n      <div class=\'card\'>\n        <div class=\'ch\'><h2>⬆ Importer des transactions</h2></div>\n        <div class=\'cb\'>\n          <div class=\'alrt alrt-b\' style=\'margin-bottom:12px\'>Utilisez le template CSV pour formater vos données correctement avant import.</div>\n          <div class=\'fld\' style=\'margin-bottom:10px\'><label>Année d\'import</label><input type=\'number\' id=\'imp-tx-year\' value=\'2025\'/></div>\n          <div class=\'scan-area\' onclick=\'document.getElementById("imp-tx-file").click()\' id=\'imp-tx-area\'>\n            <div style=\'font-size:28px;margin-bottom:6px\'>📂</div>\n            <div style=\'font-size:13px;font-weight:600\'>Glisser-déposer ou cliquer pour choisir le fichier CSV</div>\n            <div style=\'font-size:11px;color:var(--muted);margin-top:4px\'>Format: CSV UTF-8</div>\n            <div id=\'imp-tx-fname\' style=\'margin-top:8px;font-size:12px;color:var(--blue);font-weight:600\'></div>\n          </div>\n          <input type=\'file\' id=\'imp-tx-file\' accept=\'.csv\' style=\'display:none\' onchange=\'onFileSel(this,"imp-tx-fname","imp-tx-area")\'/>\n          <div style=\'margin-top:10px;display:flex;gap:8px;flex-wrap:wrap\'>\n            <button class=\'btn bp\' onclick=\'importTx()\'>⬆ Importer</button>\n            <button class=\'btn bs\' onclick=\'window.open("/api/export/template-transactions","_blank")\'>⬇ Télécharger le template</button>\n          </div>\n          <div id=\'imp-tx-result\' style=\'margin-top:10px\'></div>\n        </div>\n      </div>\n      <div class=\'card\'>\n        <div class=\'ch\'><h2>⬆ Importer des lignes budgétaires</h2></div>\n        <div class=\'cb\'>\n          <div class=\'alrt alrt-b\' style=\'margin-bottom:12px\'>Pour importer le budget 2026, 2027, etc. Téléchargez d\'abord le template.</div>\n          <div class=\'scan-area\' onclick=\'document.getElementById("imp-bl-file").click()\' id=\'imp-bl-area\'>\n            <div style=\'font-size:28px;margin-bottom:6px\'>📊</div>\n            <div style=\'font-size:13px;font-weight:600\'>Glisser-déposer ou cliquer pour le fichier CSV budget</div>\n            <div id=\'imp-bl-fname\' style=\'margin-top:8px;font-size:12px;color:var(--blue);font-weight:600\'></div>\n          </div>\n          <input type=\'file\' id=\'imp-bl-file\' accept=\'.csv\' style=\'display:none\' onchange=\'onFileSel(this,"imp-bl-fname","imp-bl-area")\'/>\n          <div style=\'margin-top:10px;display:flex;gap:8px;flex-wrap:wrap\'>\n            <button class=\'btn bp admin-only\' onclick=\'importBL()\'>⬆ Importer lignes budget</button>\n            <button class=\'btn bs\' onclick=\'window.open("/api/export/template-budget-lines","_blank")\'>⬇ Template budget</button>\n          </div>\n          <div id=\'imp-bl-result\' style=\'margin-top:10px\'></div>\n        </div>\n      </div>\n    </div>\n    <div class=\'card\'>\n      <div class=\'ch\'><h2>⬇ Exports</h2></div>\n      <div class=\'cb\' style=\'display:flex;gap:10px;flex-wrap:wrap\'>\n        <button class=\'btn bs\' onclick=\'window.open(`/api/export/transactions?year=${S.year}&direction=${S.dir}`,"_blank")\'>⬇ Transactions CSV</button>\n        <button class=\'btn bs\' onclick=\'window.open(`/api/report/monthly?year=${S.year}&month=${new Date().getMonth()+1}`,"_blank")\'>⬇ Rapport mensuel CSV</button>\n      </div>\n    </div>\n  </div>\n\n  <!-- ─── USERS ─── -->\n  <div id=\'tab-users\' class=\'tab-content\'>\n    <div class=\'card\'>\n      <div class=\'ch\'>\n        <h2>Gestion des utilisateurs</h2>\n        <button class=\'btn bp bsm\' onclick=\'openUserModal()\'>+ Ajouter utilisateur</button>\n      </div>\n      <div class=\'tbl-wrap\'><table>\n        <thead><tr><th>Nom complet</th><th>Identifiant</th><th>Email</th><th>Rôle</th><th>Directions autorisées</th><th>Créé le</th><th></th></tr></thead>\n        <tbody id=\'usr-rows\'></tbody>\n      </table></div>\n    </div>\n  </div>\n\n  <!-- ─── SETTINGS ─── -->\n  <div id=\'tab-settings\' class=\'tab-content\'>\n    <div class=\'g2\'>\n      <div class=\'card\'>\n        <div class=\'ch\'><h2>⚙ Configuration rapports automatiques</h2></div>\n        <div class=\'cb\'>\n          <div class=\'alrt alrt-y\' style=\'margin-bottom:12px\'>\n            Pour activer l\'envoi automatique de rapports, configurez un service d\'email (SMTP) dans les variables d\'environnement du serveur.\n          </div>\n          <div class=\'fld\' style=\'margin-bottom:8px\'><label>Email — Directeur DCF</label><input id=\'cfg-dcf-dir\' placeholder=\'directeur.dcf@camtel.cm\'/></div>\n          <div class=\'fld\' style=\'margin-bottom:8px\'><label>Email — Sous-Directeur Budget</label><input id=\'cfg-dcf-sub\' placeholder=\'sdb@camtel.cm\'/></div>\n          <div class=\'fld\' style=\'margin-bottom:12px\'><label>Envoi automatique</label>\n            <select id=\'cfg-auto\'>\n              <option value=\'manual\'>Manuel uniquement</option>\n              <option value=\'monthly\'>Mensuel (1er du mois)</option>\n            </select>\n          </div>\n          <button class=\'btn bp\' onclick=\'toast("Configuration sauvegardée (nécessite SMTP configuré sur le serveur)")\'>Enregistrer</button>\n        </div>\n      </div>\n      <div class=\'card\'>\n        <div class=\'ch\'><h2>ℹ À propos</h2></div>\n        <div class=\'cb\' style=\'font-size:13px;line-height:1.8\'>\n          <p><strong>CAMTEL Budget App v4</strong></p>\n          <p style=\'color:var(--muted);margin-top:6px\'>Application de gestion budgétaire multi-utilisateurs.</p>\n          <div style=\'margin-top:12px;padding:10px;background:var(--lt);border-radius:8px;font-size:12px\'>\n            <strong>Rôles :</strong><br>\n            🔴 <strong>admin</strong> — Accès total<br>\n            🔵 <strong>dcf_dir</strong> — Directeur DCF — Accès total + rapports<br>\n            🟡 <strong>dcf_sub</strong> — Sous-Dir. Budget — Accès total + rapports<br>\n            🟢 <strong>agent</strong> — Saisie sur directions assignées<br>\n            ⚪ <strong>viewer</strong> — Lecture seule\n          </div>\n        </div>\n      </div>\n    </div>\n  </div>\n\n</div><!-- /wrap -->\n\n<!-- ════ MODALS ════ -->\n\n<!-- TRANSACTION MODAL -->\n<div class=\'mbg\' id=\'tx-modal\'>\n  <div class=\'modal\'>\n    <div class=\'mh\'><h3 id=\'tx-modal-title\'>Nouvelle transaction</h3><button class=\'btn bs bxs\' onclick=\'closeModal("tx-modal")\'>✕</button></div>\n    <div class=\'mb\'>\n      <div id=\'tx-warn\' class=\'alrt alrt-y\' style=\'display:none\'>⚠️ Montant supérieur au solde disponible sur cette ligne.</div>\n      <div id=\'tx-dispo-info\' class=\'alrt alrt-b\' style=\'display:none\'></div>\n      <div class=\'fr fc3\' style=\'margin-bottom:10px\'>\n        <div class=\'fld\'><label>Direction *</label>\n          <select id=\'tx-dir\' onchange=\'onTxDirChange()\'>\n            <option value=\'\'>— Sélectionner —</option>\n          </select>\n        </div>\n        <div class=\'fld\'><label>Ligne budgétaire (Imputation) *</label>\n          <select id=\'tx-imp\' onchange=\'onImpChange()\'>\n            <option value=\'\'>— Choisir direction d\'abord —</option>\n          </select>\n        </div>\n        <div class=\'fld\'><label>Nature</label>\n          <select id=\'tx-nat\'>\n            <option>DEPENSE COURANTE</option><option>DEPENSE DE CAPITAL</option>\n            <option>PRESTATION DE SERVICES</option><option>SERVICES ET FRAIS DIVERS</option>\n            <option>TRAVAUX</option><option>FOURNITURES</option><option>IMMOBILISATION</option>\n          </select>\n        </div>\n      </div>\n      <div id=\'tx-bl-info\' style=\'display:none;padding:8px 10px;background:var(--lt);border-radius:7px;margin-bottom:8px;font-size:12px\'></div>\n      <div class=\'fr fc2\'>\n        <div class=\'fld\'><label>Date de réception *</label><input type=\'date\' id=\'tx-date\'/></div>\n        <div class=\'fld\'><label>Montant (FCFA) *</label><input type=\'number\' id=\'tx-amt\' placeholder=\'0\' oninput=\'chkSolde()\'/></div>\n      </div>\n      <div class=\'fld\' style=\'margin-top:8px\'><label>Intitulé de la commande *</label>\n        <input id=\'tx-intitule\' placeholder=\'ex: FRAIS DE MISSION A L\'EXTERIEUR\'/>\n      </div>\n      <div class=\'fld\' style=\'margin-top:8px\'><label>Objet / Description (détail)</label>\n        <textarea id=\'tx-desc\' placeholder=\'Description détaillée de l\'engagement, motif, bénéficiaire...\'></textarea>\n      </div>\n      <div class=\'fld\' style=\'margin-top:8px\'><label>Statut</label>\n        <select id=\'tx-stat\'>\n          <option value=\'validated\'>Validé (engage le budget)</option>\n          <option value=\'pending\'>Brouillon (n\'engage pas encore)</option>\n        </select>\n      </div>\n    </div>\n    <div class=\'mf\'>\n      <button class=\'btn bs\' onclick=\'closeModal("tx-modal")\'>Annuler</button>\n      <button class=\'btn bp\' onclick=\'saveTx()\'>💾 Enregistrer</button>\n    </div>\n  </div>\n</div>\n\n<!-- BUDGET LINE MODAL -->\n<div class=\'mbg\' id=\'bl-modal\'>\n  <div class=\'modal\' style=\'max-width:600px\'>\n    <div class=\'mh\'><h3>Nouvelle ligne budgétaire</h3><button class=\'btn bs bxs\' onclick=\'closeModal("bl-modal")\'>✕</button></div>\n    <div class=\'mb\'>\n      <div class=\'fr fc2\'>\n        <div class=\'fld\'><label>Année *</label><input type=\'number\' id=\'bl-yr\' value=\'2025\'/></div>\n        <div class=\'fld\'><label>Direction *</label>\n          <select id=\'bl-dir\'><option value=\'\'>— Sélectionner —</option></select>\n        </div>\n      </div>\n      <div class=\'fld\' style=\'margin-top:8px\'><label>Imputation comptable *</label>\n        <input id=\'bl-imp\' placeholder=\'ex: SP4/DG/AD0025/VD0007/T00127/63840100\'/>\n      </div>\n      <div class=\'fld\' style=\'margin-top:8px\'><label>Libellé</label>\n        <input id=\'bl-lib\' placeholder=\'ex: FRAIS DE MISSION A L\'EXTERIEUR\'/>\n      </div>\n      <div class=\'fr fc2\' style=\'margin-top:8px\'>\n        <div class=\'fld\'><label>Nature</label>\n          <select id=\'bl-nat\'><option>DEPENSE COURANTE</option><option>DEPENSE DE CAPITAL</option></select>\n        </div>\n        <div class=\'fld\'><label>Budget CP (FCFA) *</label>\n          <input type=\'number\' id=\'bl-bcp\' placeholder=\'0\'/>\n        </div>\n      </div>\n    </div>\n    <div class=\'mf\'>\n      <button class=\'btn bs\' onclick=\'closeModal("bl-modal")\'>Annuler</button>\n      <button class=\'btn bp\' onclick=\'saveBL()\'>💾 Enregistrer</button>\n    </div>\n  </div>\n</div>\n\n<!-- USER MODAL -->\n<div class=\'mbg\' id=\'usr-modal\'>\n  <div class=\'modal\' style=\'max-width:620px\'>\n    <div class=\'mh\'><h3 id=\'usr-modal-title\'>Ajouter un utilisateur</h3><button class=\'btn bs bxs\' onclick=\'closeModal("usr-modal")\'>✕</button></div>\n    <div class=\'mb\'>\n      <div class=\'fr fc2\'>\n        <div class=\'fld\'><label>Nom complet *</label><input id=\'u-nm\' placeholder=\'Jean Dupont\'/></div>\n        <div class=\'fld\'><label>Identifiant *</label><input id=\'u-usr\' placeholder=\'jdupont\'/></div>\n      </div>\n      <div class=\'fr fc2\' style=\'margin-top:8px\'>\n        <div class=\'fld\'><label>Mot de passe *</label><input type=\'password\' id=\'u-pw\' placeholder=\'Laisser vide pour ne pas changer\'/></div>\n        <div class=\'fld\'><label>Email</label><input id=\'u-em\' placeholder=\'jean.dupont@camtel.cm\'/></div>\n      </div>\n      <div class=\'fld\' style=\'margin-top:8px\'><label>Rôle *</label>\n        <select id=\'u-rl\' onchange=\'onRoleChange()\'>\n          <option value=\'agent\'>Agent (saisie sur directions assignées)</option>\n          <option value=\'viewer\'>Observateur (lecture seule)</option>\n          <option value=\'dcf_sub\'>Sous-Directeur Budget (accès total + rapports)</option>\n          <option value=\'dcf_dir\'>Directeur DCF (accès total + rapports)</option>\n          <option value=\'admin\'>Administrateur (accès complet)</option>\n        </select>\n      </div>\n      <div id=\'u-dirs-block\' style=\'margin-top:12px\'>\n        <div style=\'font-size:11px;font-weight:700;color:var(--muted);margin-bottom:6px;text-transform:uppercase\'>DIRECTIONS AUTORISÉES</div>\n        <div style=\'display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px\'>\n          <button class=\'btn bs bsm\' onclick=\'selAllDirs(true)\'>Tout sélectionner</button>\n          <button class=\'btn bs bsm\' onclick=\'selAllDirs(false)\'>Tout désélectionner</button>\n        </div>\n        <div id=\'u-dirs-list\' style=\'max-height:200px;overflow-y:auto;border:1px solid var(--bdr);border-radius:7px;padding:8px;\'></div>\n      </div>\n    </div>\n    <div class=\'mf\'>\n      <button class=\'btn bs\' onclick=\'closeModal("usr-modal")\'>Annuler</button>\n      <button class=\'btn bp\' onclick=\'saveUser()\'>💾 Enregistrer</button>\n    </div>\n  </div>\n</div>\n\n<div id=\'toast\' class=\'toast\'></div>\n\n<script>\n// ═══════════════════════════════════════════\n//  STATE & CONSTANTS\n// ═══════════════════════════════════════════\nconst ALL_DIRS = ["BUM","BUT","BUF","DG","DRH","DICOM","DIRCAB","DCRA","DAMR","DC","DNQ","DAS","DFA","DAJR","DAP","DR","DS","DSPI","DSIR","DOP","DT","DCF","DCRM","DRLM","RRSM","RREM","RROM","RRNOM","RRSOM","RRAM","RRNM","RRENM","DCRF","DRLF","RRSF","RREF","RROF","RRNOF","RRSOF","RRAF","RRNF","RRENF","DCRT","DRLT","RRNOT","RRENT"];\nlet S = {user:null, year:new Date().getFullYear(), dir:\'\', cDir:null, cMo:null, editUserId:null, selectedTxIds:new Set()};\n\n// ═══════════════════════════════════════════\n//  UTILS\n// ═══════════════════════════════════════════\nconst fmts = n => {\n  n = Number(n||0);\n  if(n>=1e9) return (n/1e9).toFixed(1)+\' Md\';\n  if(n>=1e6) return (n/1e6).toFixed(1)+\' M\';\n  if(n>=1e3) return Math.round(n/1e3).toLocaleString(\'fr-FR\')+\' K\';\n  return n.toLocaleString(\'fr-FR\');\n};\n// Format with space thousands separator (300 000 000)\nconst fmtFCFA = n => {\n  n = Math.round(Number(n||0));\n  return Math.abs(n).toLocaleString(\'fr-FR\').replace(/,/g,\' \') + (n<0?\' FCFA\':\' FCFA\');\n};\nfunction toast(msg, ok=true){\n  const t=document.getElementById(\'toast\');\n  t.textContent=msg; t.style.background=ok?\'#16a34a\':\'#dc2626\';\n  t.style.display=\'block\'; setTimeout(()=>t.style.display=\'none\',3500);\n}\nasync function api(path, opts){\n  const r = await fetch(path, {credentials:\'include\',...(opts||{})});\n  if(r.status===401){ window.location=\'/login\'; return null; }\n  return r;\n}\nfunction openModal(id){ document.getElementById(id).classList.add(\'open\'); }\nfunction closeModal(id){ document.getElementById(id).classList.remove(\'open\'); }\nfunction closeBtnEl(id){ return `<button class=\'btn bs bxs\' onclick=\'closeModal("${id}")\'>&times;</button>`; }\n\n// ═══════════════════════════════════════════\n//  YEAR / DIRECTION SELECTORS\n// ═══════════════════════════════════════════\nfunction initYears(){\n  const n = new Date().getFullYear();\n  [\'g-year\',\'rp-year\'].forEach(id => {\n    const s = document.getElementById(id); if(!s) return;\n    for(let y=n-3;y<=n+2;y++){ const o=document.createElement(\'option\');o.value=y;o.textContent=y;s.appendChild(o); }\n    s.value = n;\n  });\n  S.year = n;\n}\n\nfunction populateDirSelects(){\n  const dirs = S.user ? (isFullAccess() ? ALL_DIRS : JSON.parse(S.user.dirs||\'[]\')) : [];\n  [\'g-dir\',\'tx-f-dir\',\'bl-f-dir\'].forEach(id => {\n    const s = document.getElementById(id); if(!s) return;\n    const cur = s.value;\n    s.innerHTML = \'<option value="">Toutes directions</option>\';\n    dirs.forEach(d => { const o=document.createElement(\'option\');o.value=d;o.textContent=d;s.appendChild(o); });\n    if(cur) s.value = cur;\n  });\n  // tx-dir select in modal\n  const txDir = document.getElementById(\'tx-dir\');\n  if(txDir){ txDir.innerHTML=\'<option value="">— Sélectionner —</option>\'; dirs.forEach(d=>{const o=document.createElement(\'option\');o.value=d;o.textContent=d;txDir.appendChild(o);}); }\n  // bl-dir in modal\n  const blDir = document.getElementById(\'bl-dir\');\n  if(blDir){ blDir.innerHTML=\'<option value="">— Sélectionner —</option>\'; ALL_DIRS.forEach(d=>{const o=document.createElement(\'option\');o.value=d;o.textContent=d;blDir.appendChild(o);}); }\n}\n\nfunction isFullAccess(){ return S.user && [\'admin\',\'dcf_dir\',\'dcf_sub\'].includes(S.user.role); }\n\nfunction onYearChange(){ S.year=Number(document.getElementById(\'g-year\').value); refreshAll(); }\nfunction onDirChange(){ S.dir=document.getElementById(\'g-dir\').value; refreshAll(); }\n\nfunction showTab(n){\n  document.querySelectorAll(\'.tab-content\').forEach(e=>e.classList.remove(\'active\'));\n  document.querySelectorAll(\'nav button\').forEach(b=>b.classList.remove(\'active\'));\n  document.getElementById(\'tab-\'+n).classList.add(\'active\');\n  document.getElementById(\'nav-\'+n)?.classList.add(\'active\');\n  const map={dashboard:loadDash, transactions:loadTx, budgetlines:loadBL, reports:loadReports, users:loadUsers};\n  if(map[n]) map[n]();\n}\n\nfunction refreshAll(){\n  loadKPIs();\n  const active = document.querySelector(\'.tab-content.active\')?.id?.replace(\'tab-\',\'\');\n  if(active){ const map={dashboard:loadDash,transactions:loadTx,budgetlines:loadBL,reports:loadReports}; if(map[active])map[active](); }\n  document.getElementById(\'last-upd\').textContent = \'Actualisé: \'+new Date().toLocaleTimeString(\'fr-FR\');\n}\n\n// ═══════════════════════════════════════════\n//  KPIs\n// ═══════════════════════════════════════════\nasync function loadKPIs(){\n  const r = await api(`/api/dashboard?year=${S.year}`); if(!r) return;\n  const d = await r.json();\n  document.getElementById(\'kpi-bud\').textContent  = fmts(d.total_budget);\n  document.getElementById(\'kpi-bud-s\').textContent = \'— FCFA\';\n  document.getElementById(\'kpi-eng\').textContent  = fmts(d.total_engage);\n  document.getElementById(\'kpi-eng-s\').textContent = d.tx_count+\' transaction(s) validée(s)\';\n  document.getElementById(\'kpi-pend\').textContent = fmts(d.total_pending);\n  document.getElementById(\'kpi-pend-s\').textContent = d.pending_count+\' brouillon(s)\';\n  document.getElementById(\'kpi-dispo\').textContent= fmts(d.total_dispo);\n  const pct = d.total_budget ? Math.round(d.total_engage/d.total_budget*100) : 0;\n  document.getElementById(\'kpi-dispo-s\').textContent = pct+\'% du budget engagé\';\n\n  const ar = document.getElementById(\'alerts-row\'); ar.innerHTML=\'\';\n  (d.overdrawn||[]).forEach(a=>{ar.innerHTML+=`<div class=\'alrt alrt-r\'>🚨 Direction <strong>${a.direction}</strong> — dépassement budgétaire de <strong>${fmtFCFA(a.montant)}</strong></div>`;});\n}\n\n// ═══════════════════════════════════════════\n//  DASHBOARD CHARTS\n// ═══════════════════════════════════════════\nasync function loadDash(){\n  await loadKPIs();\n  const r = await api(`/api/dashboard?year=${S.year}`); if(!r) return;\n  const d = await r.json();\n\n  const dirs = Object.keys(d.by_dir).sort((a,b)=>d.by_dir[b]-d.by_dir[a]).slice(0,12);\n  const cols = [\'#2563eb\',\'#16a34a\',\'#d97706\',\'#dc2626\',\'#7c3aed\',\'#0891b2\',\'#db2777\',\'#65a30d\',\'#ea580c\',\'#0d9488\',\'#9333ea\',\'#0284c7\'];\n  if(S.cDir) S.cDir.destroy();\n  S.cDir = new Chart(document.getElementById(\'ch-dir\'),{\n    type:\'bar\', data:{labels:dirs, datasets:[{data:dirs.map(d2=>d.by_dir[d2]),backgroundColor:cols,borderRadius:5}]},\n    options:{responsive:true,plugins:{legend:{display:false}},scales:{y:{ticks:{callback:v=>fmts(v)}}}}\n  });\n  const months=[\'Jan\',\'Fév\',\'Mar\',\'Avr\',\'Mai\',\'Jun\',\'Jul\',\'Aoû\',\'Sep\',\'Oct\',\'Nov\',\'Déc\'];\n  if(S.cMo) S.cMo.destroy();\n  S.cMo = new Chart(document.getElementById(\'ch-mo\'),{\n    type:\'line\', data:{labels:months, datasets:[{data:d.by_month,borderColor:\'#2563eb\',backgroundColor:\'rgba(37,99,235,.1)\',fill:true,tension:.4,pointRadius:4}]},\n    options:{responsive:true,plugins:{legend:{display:false}},scales:{y:{ticks:{callback:v=>fmts(v)}}}}\n  });\n\n  // Progress bars\n  const dp = document.getElementById(\'dir-prog\');\n  const bld = d.bl_by_dir||{};\n  const dirKeys = Object.keys(bld).sort();\n  if(!dirKeys.length){ dp.innerHTML=\'<div class="empty">Aucune ligne budgétaire définie.</div>\'; }\n  else {\n    dp.innerHTML = `<div style=\'display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px;\'>` +\n    dirKeys.map(dir=>{\n      const bd=bld[dir];const pct=bd.budget_cp?Math.min(100,Math.round(bd.engage/bd.budget_cp*100)):0;\n      const col=pct>90?\'var(--red)\':pct>70?\'var(--yel)\':\'var(--green)\';\n      const av=bd.budget_cp-bd.engage;\n      return `<div style=\'padding:10px;border:1px solid var(--bdr);border-radius:8px;\'>\n        <div style=\'display:flex;justify-content:space-between;font-size:12px;font-weight:700;\'><span>${dir}</span><span style=\'color:${col}\'>${pct}%</span></div>\n        <div style=\'font-size:10px;color:var(--muted);margin:3px 0\'>CP: ${fmtFCFA(bd.budget_cp)} | Engagé: ${fmtFCFA(bd.engage)}</div>\n        <div style=\'font-size:11px;font-weight:700;color:${av>=0?"var(--green)":"var(--red)"}\'>${av>=0?\'Dispo:\':\'Dépassement:\'} ${fmtFCFA(Math.abs(av))}</div>\n        <div class=\'prg\'><div class=\'prf\' style=\'width:${pct}%;background:${col}\'></div></div>\n      </div>`;\n    }).join(\'\')+\'</div>\';\n  }\n\n  // Recent\n  const rr = document.getElementById(\'rec-rows\'); rr.innerHTML=\'\';\n  (d.recent||[]).forEach(t=>{\n    const sb=t.statut_budget===\'DEPASSEMENT\'?\'bdep\':\'bg\';\n    rr.innerHTML+=`<tr><td>${t.date_reception}</td><td style=\'font-family:monospace;font-size:10px\'>${t.code_ref}</td>\n      <td><span class=\'bdg bb\'>${t.direction}</span></td>\n      <td style=\'font-size:10px;max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap\'>${t.imputation}</td>\n      <td style=\'max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap\'>${t.intitule}</td>\n      <td class=\'tr\' style=\'font-weight:700;white-space:nowrap\'>${fmtFCFA(t.montant)}</td>\n      <td><span class=\'bdg ${sb}\'>${t.statut_budget}</span></td></tr>`;\n  });\n}\n\n// ═══════════════════════════════════════════\n//  TRANSACTIONS\n// ═══════════════════════════════════════════\nasync function loadTx(){\n  const dir = document.getElementById(\'tx-f-dir\').value;\n  const st  = document.getElementById(\'tx-f-status\').value;\n  const q   = document.getElementById(\'tx-q\').value;\n  const r = await api(`/api/transactions?year=${S.year}&direction=${encodeURIComponent(dir)}&status=${st}&q=${encodeURIComponent(q)}`);\n  if(!r) return;\n  const data = await r.json();\n  const tb = document.getElementById(\'tx-rows\'); tb.innerHTML=\'\';\n  document.getElementById(\'tx-empty\').style.display = data.length?\'none\':\'block\';\n  data.forEach(t=>{\n    const sb=t.statut_budget===\'DEPASSEMENT\'?\'bdep\':\'bg\';\n    const ss=t.status===\'validated\'?\'bg\':\'by\';\n    const sl=t.status===\'validated\'?\'Validé\':\'Brouillon\';\n    const canDel=isFullAccess();\n    const checked=S.selectedTxIds.has(t.id)?\'checked\':\'\';\n    tb.innerHTML+=`<tr id=\'tx-row-${t.id}\'>\n      <td><input type=\'checkbox\' class=\'tx-chk\' value=\'${t.id}\' ${checked} onchange=\'onTxSel(this)\'/></td>\n      <td style=\'white-space:nowrap\'>${t.date_reception}</td>\n      <td style=\'font-family:monospace;font-size:10px;white-space:nowrap\'>${t.code_ref}</td>\n      <td><span class=\'bdg bb\'>${t.direction}</span></td>\n      <td style=\'font-size:10px;max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap\' title=\'${t.imputation}\'>${t.imputation}</td>\n      <td style=\'font-size:10px\'>${t.nature}</td>\n      <td style=\'max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap\' title=\'${t.intitule}\'>${t.intitule}</td>\n      <td class=\'tr\' style=\'font-weight:700;white-space:nowrap\'>${fmtFCFA(t.montant)}</td>\n      <td><span class=\'bdg ${sb}\'>${t.statut_budget}</span></td>\n      <td><span class=\'bdg ${ss}\'>${sl}</span></td>\n      <td style=\'font-size:10px;color:var(--muted);white-space:nowrap\'>${t.created_by_name||t.created_by||\'—\'}</td>\n      <td style=\'white-space:nowrap\'>\n        <button class=\'btn bs bxs\' onclick=\'openFiche(${t.id})\' title=\'Fiche\'>🖨</button>\n        ${canDel?`<button class=\'btn bd bxs\' onclick=\'delTx(${t.id})\' title=\'Supprimer\' style=\'margin-left:3px\'>🗑</button>`:\'\'}\n      </td>\n    </tr>`;\n  });\n  updateSelUI();\n}\n\nfunction onTxSel(cb){\n  const id=Number(cb.value);\n  if(cb.checked) S.selectedTxIds.add(id); else S.selectedTxIds.delete(id);\n  updateSelUI();\n}\nfunction toggleSelAll(cb){\n  document.querySelectorAll(\'.tx-chk\').forEach(c=>{ c.checked=cb.checked; onTxSel(c); });\n}\nfunction updateSelUI(){\n  const n=S.selectedTxIds.size;\n  document.getElementById(\'print-selected-btn\').style.display=n>0?\'\':\'none\';\n  document.getElementById(\'tx-select-info\').style.display=n>0?\'block\':\'none\';\n  document.getElementById(\'tx-sel-count\').textContent=n;\n}\nfunction printSelected(){\n  if(!S.selectedTxIds.size){toast(\'Sélectionnez au moins une transaction\',false);return;}\n  window.open(\'/fiche?ids=\'+[...S.selectedTxIds].join(\',\'),\'_blank\');\n}\nfunction openFiche(id){ window.open(\'/fiche?ids=\'+id,\'_blank\'); }\nasync function delTx(id){\n  if(!confirm(\'Supprimer cette transaction?\')) return;\n  await api(\'/api/transactions/\'+id,{method:\'DELETE\'}); toast(\'Supprimé\'); loadTx(); loadKPIs();\n}\nfunction exportTx(){ window.open(`/api/export/transactions?year=${S.year}&direction=${S.dir}`,\'_blank\'); }\n\nasync function openTxModal(){\n  document.getElementById(\'tx-modal-title\').textContent=\'Nouvelle transaction\';\n  document.getElementById(\'tx-date\').value = new Date().toISOString().slice(0,10);\n  document.getElementById(\'tx-amt\').value=\'\'; document.getElementById(\'tx-intitule\').value=\'\';\n  document.getElementById(\'tx-desc\').value=\'\'; document.getElementById(\'tx-warn\').style.display=\'none\';\n  document.getElementById(\'tx-dispo-info\').style.display=\'none\';\n  document.getElementById(\'tx-bl-info\').style.display=\'none\';\n  document.getElementById(\'tx-imp\').innerHTML=\'<option value="">— Choisir direction d\\\'abord —</option>\';\n  // Set user\'s default direction\n  const dirs = S.user ? (isFullAccess() ? ALL_DIRS : JSON.parse(S.user.dirs||\'[]\')) : [];\n  if(S.dir && dirs.includes(S.dir)) document.getElementById(\'tx-dir\').value=S.dir;\n  if(document.getElementById(\'tx-dir\').value) await onTxDirChange();\n  openModal(\'tx-modal\');\n}\n\nasync function onTxDirChange(){\n  const dir = document.getElementById(\'tx-dir\').value;\n  if(!dir){ document.getElementById(\'tx-imp\').innerHTML=\'<option value="">— Choisir direction d\\\'abord —</option>\'; return; }\n  const r = await api(`/api/budget-lines?year=${S.year}&direction=${dir}`); if(!r) return;\n  const bls = await r.json();\n  const sel = document.getElementById(\'tx-imp\');\n  sel.innerHTML=\'<option value="">— Sélectionner ligne budgétaire —</option>\';\n  bls.forEach(b=>{\n    const o=document.createElement(\'option\');\n    o.value=b.imputation;\n    o.textContent=`${b.imputation} — ${b.libelle||\'\'}`;\n    o.dataset.lib=b.libelle; o.dataset.bcp=b.budget_cp; o.dataset.dispo=b.disponible;\n    sel.appendChild(o);\n  });\n  if(!bls.length) sel.innerHTML=\'<option value="">Aucune ligne pour cette direction</option>\';\n}\n\nfunction onImpChange(){\n  const sel = document.getElementById(\'tx-imp\');\n  const opt = sel.options[sel.selectedIndex];\n  if(!opt||!opt.value){ document.getElementById(\'tx-bl-info\').style.display=\'none\'; return; }\n  const dispo = Number(opt.dataset.dispo||0);\n  const bcp   = Number(opt.dataset.bcp||0);\n  document.getElementById(\'tx-bl-info\').style.display=\'block\';\n  document.getElementById(\'tx-bl-info\').innerHTML=\n    `<strong>${opt.dataset.lib||opt.value}</strong><br>\n     Budget CP: <strong>${fmtFCFA(bcp)}</strong> | Disponible: <strong style=\'color:${dispo>=0?"var(--green)":"var(--red)"}\'>${fmtFCFA(dispo)}</strong>`;\n  const info = document.getElementById(\'tx-dispo-info\');\n  info.style.display=\'block\';\n  info.innerHTML=`Solde disponible sur cette ligne : <strong style=\'color:${dispo>=0?"var(--green)":"var(--red)"}\'>${fmtFCFA(dispo)}</strong>`;\n  info.className=\'alrt \'+(dispo>=0?\'alrt-g\':\'alrt-r\');\n  chkSolde();\n}\n\nfunction chkSolde(){\n  const sel=document.getElementById(\'tx-imp\'); const opt=sel.options[sel.selectedIndex];\n  const dispo=opt?Number(opt.dataset.dispo||0):Infinity;\n  const amt=Number(document.getElementById(\'tx-amt\').value||0);\n  document.getElementById(\'tx-warn\').style.display=(dispo<Infinity&&amt>dispo)?\'flex\':\'none\';\n}\n\nasync function saveTx(){\n  const p={\n    direction: document.getElementById(\'tx-dir\').value,\n    imputation: document.getElementById(\'tx-imp\').value,\n    nature: document.getElementById(\'tx-nat\').value,\n    date_reception: document.getElementById(\'tx-date\').value,\n    montant: Number(document.getElementById(\'tx-amt\').value||0),\n    intitule: document.getElementById(\'tx-intitule\').value,\n    description: document.getElementById(\'tx-desc\').value,\n    status: document.getElementById(\'tx-stat\').value,\n    year: S.year,\n  };\n  if(!p.direction||!p.imputation||!p.date_reception||!p.montant){toast(\'Champs obligatoires manquants\',false);return;}\n  const r=await api(\'/api/transactions\',{method:\'POST\',headers:{\'Content-Type\':\'application/json\'},body:JSON.stringify(p)});\n  if(!r) return;\n  if(!r.ok){toast(\'Erreur: \'+(await r.text()),false);return;}\n  const tx=await r.json(); toast(\'Transaction enregistrée ✓\'); closeModal(\'tx-modal\'); loadTx(); loadKPIs();\n  if(confirm(\'Ouvrir la fiche d\\\'engagement?\')) openFiche(tx.id);\n}\n\n// ═══════════════════════════════════════════\n//  BUDGET LINES\n// ═══════════════════════════════════════════\nasync function loadBL(){\n  const dir=document.getElementById(\'bl-f-dir\').value;\n  const q=document.getElementById(\'bl-q\').value;\n  const r=await api(`/api/budget-lines?year=${S.year}&direction=${encodeURIComponent(dir)}`); if(!r) return;\n  let data=await r.json();\n  if(q){ const ql=q.toLowerCase(); data=data.filter(b=>ql in b.imputation.toLowerCase()||ql in (b.libelle||\'\').toLowerCase()); }\n  const tb=document.getElementById(\'bl-rows\'); tb.innerHTML=\'\';\n  document.getElementById(\'bl-empty\').style.display=data.length?\'none\':\'block\';\n  data.forEach(b=>{\n    const pct=b.budget_cp?Math.min(100,Math.round(b.cumul_engage/b.budget_cp*100)):0;\n    const col=pct>90?\'var(--red)\':pct>70?\'var(--yel)\':\'var(--green)\';\n    const ok=b.dispo_ok;\n    tb.innerHTML+=`<tr>\n      <td>${b.year}</td>\n      <td><span class=\'bdg bb\'>${b.direction}</span></td>\n      <td style=\'font-family:monospace;font-size:10px;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap\' title=\'${b.imputation}\'>${b.imputation}</td>\n      <td style=\'max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap\'>${b.libelle||\'—\'}</td>\n      <td><span class=\'bdg ${b.nature.includes("CAPITAL")?"by":"bb"}\'>${b.nature.split(" ")[1]||b.nature}</span></td>\n      <td class=\'tr\' style=\'font-weight:700\'>${fmtFCFA(b.budget_cp)}</td>\n      <td class=\'tr\' style=\'color:var(--red)\'>${fmtFCFA(b.cumul_engage)}</td>\n      <td class=\'tr\' style=\'color:${ok?"var(--green)":"var(--red)"};font-weight:700\'>${fmtFCFA(b.disponible)}</td>\n      <td><span class=\'bdg ${ok?"bg":"br"}\'>${ok?"DISPONIBLE":"ÉPUISÉ"}</span></td>\n      <td class=\'admin-only\'>\n        <button class=\'btn bd bxs\' onclick=\'delBL(${b.id})\'>🗑</button>\n      </td>\n    </tr>`;\n  });\n}\n\nfunction openBLModal(){\n  document.getElementById(\'bl-yr\').value=S.year;\n  if(S.dir) document.getElementById(\'bl-dir\').value=S.dir;\n  openModal(\'bl-modal\');\n}\n\nasync function saveBL(){\n  const p={year:Number(document.getElementById(\'bl-yr\').value),direction:document.getElementById(\'bl-dir\').value,\n    imputation:document.getElementById(\'bl-imp\').value.trim(),libelle:document.getElementById(\'bl-lib\').value.trim(),\n    nature:document.getElementById(\'bl-nat\').value,budget_cp:Number(document.getElementById(\'bl-bcp\').value||0)};\n  if(!p.year||!p.direction||!p.imputation||!p.budget_cp){toast(\'Champs obligatoires manquants\',false);return;}\n  const r=await api(\'/api/budget-lines\',{method:\'POST\',headers:{\'Content-Type\':\'application/json\'},body:JSON.stringify(p)});\n  if(!r) return;\n  if(!r.ok){toast(\'Erreur: \'+(await r.text()),false);return;}\n  toast(\'Ligne créée ✓\'); closeModal(\'bl-modal\'); loadBL(); loadKPIs();\n}\n\nasync function delBL(id){\n  if(!confirm(\'Supprimer cette ligne budgétaire?\')) return;\n  await api(\'/api/budget-lines/\'+id,{method:\'DELETE\'}); toast(\'Supprimé\'); loadBL();\n}\nfunction exportBL(){ window.open(`/api/export/transactions?year=${S.year}&direction=${S.dir}`,\'_blank\'); }\n\n// ═══════════════════════════════════════════\n//  REPORTS\n// ═══════════════════════════════════════════\nasync function loadReports(){\n  const yr=document.getElementById(\'rp-year\').value||S.year;\n  document.getElementById(\'rp-year-label\').textContent=yr;\n  const r=await api(`/api/dashboard?year=${yr}`); if(!r) return;\n  const d=await r.json();\n  // Summary\n  const pct=d.total_budget?Math.round(d.total_engage/d.total_budget*100):0;\n  document.getElementById(\'rp-summary\').innerHTML=`\n    <div style=\'font-size:13px\'>\n      <div style=\'display:flex;justify-content:space-between;padding:7px 0;border-bottom:1px solid var(--bdr)\'><span>Budget CP total</span><strong>${fmtFCFA(d.total_budget)}</strong></div>\n      <div style=\'display:flex;justify-content:space-between;padding:7px 0;border-bottom:1px solid var(--bdr);color:var(--red)\'><span>Cumul engagé</span><strong>${fmtFCFA(d.total_engage)}</strong></div>\n      <div style=\'display:flex;justify-content:space-between;padding:7px 0;border-bottom:1px solid var(--bdr);color:var(--yel)\'><span>En attente</span><strong>${fmtFCFA(d.total_pending)}</strong></div>\n      <div style=\'display:flex;justify-content:space-between;padding:10px 0;font-size:15px\'><strong>Disponible</strong><strong style=\'color:${d.total_dispo>=0?"var(--green)":"var(--red)"}\'>${fmtFCFA(d.total_dispo)}</strong></div>\n      <div style=\'font-size:11px;color:var(--muted)\'>${pct}% du budget engagé · ${d.tx_count} transaction(s)</div>\n    </div>`;\n  // Per direction table\n  const bld=d.bl_by_dir||{};\n  const tb=document.getElementById(\'rp-dir-rows\'); tb.innerHTML=\'\';\n  Object.keys(bld).sort().forEach(dir=>{\n    const bd=bld[dir];const av=bd.budget_cp-bd.engage;const pct2=bd.budget_cp?Math.min(100,Math.round(bd.engage/bd.budget_cp*100)):0;\n    const col=pct2>90?\'var(--red)\':pct2>70?\'var(--yel)\':\'var(--green)\';\n    tb.innerHTML+=`<tr>\n      <td><span class=\'bdg bb\'>${dir}</span></td>\n      <td class=\'tr\'>${fmtFCFA(bd.budget_cp)}</td>\n      <td class=\'tr\' style=\'color:var(--red)\'>${fmtFCFA(bd.engage)}</td>\n      <td class=\'tr\' style=\'color:${av>=0?"var(--green)":"var(--red)"};font-weight:700\'>${fmtFCFA(av)}</td>\n      <td><div style=\'display:flex;align-items:center;gap:6px;min-width:100px\'><div class=\'prg\' style=\'flex:1\'><div class=\'prf\' style=\'width:${pct2}%;background:${col}\'></div></div><span style=\'font-size:11px;color:${col};font-weight:700\'>${pct2}%</span></div></td>\n      <td><span class=\'bdg ${av>=0?"bg":"br"}\'>${av>=0?"OK":"DÉPASSEMENT"}</span></td>\n    </tr>`;\n  });\n}\nfunction downloadReport(){\n  const yr=document.getElementById(\'rp-year\').value||S.year;\n  const mo=document.getElementById(\'rp-month\').value;\n  window.open(`/api/report/monthly?year=${yr}&month=${mo}`,\'_blank\');\n}\n\n// ═══════════════════════════════════════════\n//  IMPORT\n// ═══════════════════════════════════════════\nfunction onFileSel(input, nameId, areaId){\n  const f=input.files[0]; if(!f) return;\n  document.getElementById(nameId).textContent=\'✓ \'+f.name;\n  document.getElementById(areaId).style.borderColor=\'var(--green)\';\n}\nasync function importTx(){\n  const f=document.getElementById(\'imp-tx-file\').files[0];\n  const yr=document.getElementById(\'imp-tx-year\').value;\n  if(!f){toast(\'Sélectionnez un fichier\',false);return;}\n  const fd=new FormData(); fd.append(\'file\',f); fd.append(\'year\',yr);\n  const r=await api(\'/api/import/transactions\',{method:\'POST\',body:fd}); if(!r) return;\n  const d=await r.json();\n  document.getElementById(\'imp-tx-result\').innerHTML=`<div class=\'alrt ${d.errors.length?"alrt-y":"alrt-g"}\'>${d.created} transaction(s) importée(s). ${d.errors.length?" Erreurs: "+d.errors.slice(0,3).join(\'; \'):\'\'}</div>`;\n  if(d.created) { toast(d.created+\' transactions importées ✓\'); loadTx(); loadKPIs(); }\n}\nasync function importBL(){\n  const f=document.getElementById(\'imp-bl-file\').files[0];\n  if(!f){toast(\'Sélectionnez un fichier\',false);return;}\n  const fd=new FormData(); fd.append(\'file\',f);\n  const r=await api(\'/api/import/budget-lines\',{method:\'POST\',body:fd}); if(!r) return;\n  const d=await r.json();\n  document.getElementById(\'imp-bl-result\').innerHTML=`<div class=\'alrt ${d.errors.length?"alrt-y":"alrt-g"}\'>${d.created} créée(s), ${d.updated} mise(s) à jour. ${d.errors.length?" Erreurs: "+d.errors.slice(0,3).join(\'; \'):\'\'}</div>`;\n  if(d.created||d.updated) { toast(\'Lignes budgétaires importées ✓\'); loadBL(); loadKPIs(); }\n}\n\n// ═══════════════════════════════════════════\n//  USERS\n// ═══════════════════════════════════════════\nasync function loadUsers(){\n  const r=await api(\'/api/users\'); if(!r) return;\n  const data=await r.json();\n  const rl={admin:\'Administrateur\',dcf_dir:\'Dir. DCF\',dcf_sub:\'S-Dir. Budget\',agent:\'Agent\',viewer:\'Observateur\'};\n  const rb={admin:\'br\',dcf_dir:\'br\',dcf_sub:\'by\',agent:\'bb\',viewer:\'bg\'};\n  document.getElementById(\'usr-rows\').innerHTML=data.map(u=>{\n    let dirs=\'—\';\n    try{ const d=JSON.parse(u.directions||\'[]\'); dirs=d.length===ALL_DIRS.length?\'Toutes directions\':d.slice(0,4).join(\', \')+(d.length>4?\'…\':\'\'); }catch(e){}\n    return `<tr>\n      <td><strong>${u.full_name||u.username}</strong></td>\n      <td style=\'font-family:monospace;font-size:11px\'>${u.username}</td>\n      <td style=\'font-size:11px\'>${u.email||\'—\'}</td>\n      <td><span class=\'bdg ${rb[u.role]||"bb"}\'>${rl[u.role]||u.role}</span></td>\n      <td style=\'font-size:11px;max-width:200px;overflow:hidden;text-overflow:ellipsis\'>${dirs}</td>\n      <td style=\'font-size:11px;color:var(--muted)\'>${(u.created_at||\'\').slice(0,10)}</td>\n      <td style=\'white-space:nowrap\'>\n        <button class=\'btn bs bxs\' onclick=\'editUser(${u.id})\'>✏</button>\n        ${u.username!==S.user?.u?`<button class=\'btn bd bxs\' onclick=\'delUser(${u.id})\' style=\'margin-left:3px\'>🗑</button>`:\'<span style="font-size:10px;color:var(--muted);padding:0 4px">Vous</span>\'}\n      </td>\n    </tr>`;\n  }).join(\'\');\n}\n\nfunction openUserModal(){\n  S.editUserId=null;\n  document.getElementById(\'usr-modal-title\').textContent=\'Ajouter un utilisateur\';\n  document.getElementById(\'u-nm\').value=\'\'; document.getElementById(\'u-usr\').value=\'\';\n  document.getElementById(\'u-pw\').value=\'\'; document.getElementById(\'u-em\').value=\'\';\n  document.getElementById(\'u-rl\').value=\'agent\';\n  buildDirCheckboxes([]);\n  onRoleChange();\n  openModal(\'usr-modal\');\n}\nasync function editUser(id){\n  S.editUserId=id;\n  const r=await api(\'/api/users\'); if(!r) return;\n  const users=await r.json(); const u=users.find(x=>x.id===id); if(!u) return;\n  document.getElementById(\'usr-modal-title\').textContent=\'Modifier utilisateur: \'+u.username;\n  document.getElementById(\'u-nm\').value=u.full_name||\'\';\n  document.getElementById(\'u-usr\').value=u.username;\n  document.getElementById(\'u-pw\').value=\'\';\n  document.getElementById(\'u-em\').value=u.email||\'\';\n  document.getElementById(\'u-rl\').value=u.role;\n  let dirs=[];try{dirs=JSON.parse(u.directions||\'[]\');}catch(e){}\n  buildDirCheckboxes(dirs);\n  onRoleChange();\n  openModal(\'usr-modal\');\n}\nfunction buildDirCheckboxes(selected){\n  const c=document.getElementById(\'u-dirs-list\'); c.innerHTML=\'\';\n  ALL_DIRS.forEach(d=>{\n    c.innerHTML+=`<div class=\'cbox-row\'>\n      <input type=\'checkbox\' id=\'dir-${d}\' value=\'${d}\' ${selected.includes(d)?\'checked\':\'\'}>\n      <label for=\'dir-${d}\' style=\'font-size:12px;cursor:pointer\'>${d}</label>\n    </div>`;\n  });\n}\nfunction selAllDirs(sel){ document.querySelectorAll(\'#u-dirs-list input[type=checkbox]\').forEach(c=>c.checked=sel); }\nfunction onRoleChange(){\n  const role=document.getElementById(\'u-rl\').value;\n  const fullAccess=[\'admin\',\'dcf_dir\',\'dcf_sub\'].includes(role);\n  document.getElementById(\'u-dirs-block\').style.opacity=fullAccess?\'.5\':\'1\';\n  if(fullAccess) selAllDirs(true);\n}\nasync function saveUser(){\n  const role=document.getElementById(\'u-rl\').value;\n  const dirs=[\'admin\',\'dcf_dir\',\'dcf_sub\'].includes(role)?ALL_DIRS:\n    [...document.querySelectorAll(\'#u-dirs-list input:checked\')].map(c=>c.value);\n  const p={\n    username:document.getElementById(\'u-usr\').value.trim(),\n    password:document.getElementById(\'u-pw\').value,\n    full_name:document.getElementById(\'u-nm\').value.trim(),\n    role:role, email:document.getElementById(\'u-em\').value.trim(), directions:dirs\n  };\n  if(!p.username){toast(\'Identifiant requis\',false);return;}\n  if(!S.editUserId&&!p.password){toast(\'Mot de passe requis pour un nouvel utilisateur\',false);return;}\n  const url=S.editUserId?\'/api/users/\'+S.editUserId:\'/api/users\';\n  const method=S.editUserId?\'PUT\':\'POST\';\n  if(S.editUserId&&!p.password) delete p.password;\n  const r=await api(url,{method,headers:{\'Content-Type\':\'application/json\'},body:JSON.stringify(p)});\n  if(!r) return;\n  if(!r.ok){toast(\'Erreur: \'+(await r.text()),false);return;}\n  toast(S.editUserId?\'Modifié ✓\':\'Utilisateur créé ✓\'); closeModal(\'usr-modal\'); loadUsers();\n}\nasync function delUser(id){\n  if(!confirm(\'Supprimer cet utilisateur?\')) return;\n  await api(\'/api/users/\'+id,{method:\'DELETE\'}); toast(\'Supprimé\'); loadUsers();\n}\n\n// ═══════════════════════════════════════════\n//  ROLE-BASED UI\n// ═══════════════════════════════════════════\nfunction applyRole(){\n  const fa=isFullAccess();\n  const isViewer=S.user?.role===\'viewer\';\n  document.querySelectorAll(\'.admin-only\').forEach(e=>e.style.display=fa?\'\':\'none\');\n  document.querySelectorAll(\'.viewer-hide\').forEach(e=>e.style.display=isViewer?\'none\':\'\');\n  if(fa){ document.getElementById(\'nav-users\').style.display=\'\'; document.getElementById(\'nav-settings\').style.display=\'\'; }\n}\n\n// ═══════════════════════════════════════════\n//  AUTH\n// ═══════════════════════════════════════════\nasync function logout(){ await fetch(\'/api/logout\',{method:\'POST\',credentials:\'include\'}); window.location=\'/login\'; }\n\n// ═══════════════════════════════════════════\n//  INIT\n// ═══════════════════════════════════════════\nasync function init(){\n  initYears();\n  const r=await api(\'/api/me\'); if(!r) return;\n  S.user=await r.json();\n  document.getElementById(\'uname\').textContent=S.user.name||S.user.u;\n  const roleLabel={admin:\'Admin\',dcf_dir:\'Dir.DCF\',dcf_sub:\'S-Dir.Budget\',agent:\'Agent\',viewer:\'Lecteur\'};\n  document.getElementById(\'urole\').textContent=roleLabel[S.user.role]||S.user.role;\n  populateDirSelects();\n  applyRole();\n  await loadDash();\n  setInterval(loadKPIs, 30000);\n}\n\n// Event listeners\n[\'tx-q\'].forEach(id=>{ document.getElementById(id)?.addEventListener(\'input\',()=>{clearTimeout(window.__t);window.__t=setTimeout(loadTx,350);}); });\n[\'bl-q\'].forEach(id=>{ document.getElementById(id)?.addEventListener(\'input\',()=>{clearTimeout(window.__t2);window.__t2=setTimeout(loadBL,350);}); });\n[\'tx-f-dir\',\'tx-f-status\'].forEach(id=>document.getElementById(id)?.addEventListener(\'change\',loadTx));\n[\'bl-f-dir\'].forEach(id=>document.getElementById(id)?.addEventListener(\'change\',loadBL));\ndocument.querySelectorAll(\'.mbg\').forEach(bg=>bg.addEventListener(\'click\',e=>{ if(e.target===bg) bg.classList.remove(\'open\'); }));\n\ninit();\n</script>\n</body>\n</html>\n'
