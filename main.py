"""
CAMTEL Budget App v5 — Excel-like UI, CAMTEL logo, colorful columns, fixed budget upload
"""
import os, sqlite3, hashlib, json, io, csv
from datetime import datetime, date
from fastapi import FastAPI, Request, Response, Form, HTTPException, Depends, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from itsdangerous import URLSafeSerializer, BadSignature

SECRET_KEY = os.environ.get("SECRET_KEY","camtel-secret-v5")
DB_PATH    = os.environ.get("DB_PATH","camtel.db")
FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN","*")
ADMIN_USER = os.environ.get("ADMIN_USER","admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS","admin123")

serializer = URLSafeSerializer(SECRET_KEY, salt="camtel-v5")
app = FastAPI(title="CAMTEL Budget")
app.add_middleware(CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN] if FRONTEND_ORIGIN!="*" else ["*"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

ALL_DIRECTIONS = [
    "BUM","BUT","BUF","DG","DRH","DICOM","DIRCAB","DCRA","DAMR","DC","DNQ","DAS","DFA",
    "DAJR","DAP","DR","DS","DSPI","DSIR","DOP","DT","DCF","DCRM","DRLM","RRSM","RREM",
    "RROM","RRNOM","RRSOM","RRAM","RRNM","RRENM","DCRF","DRLF","RRSF","RREF","RROF",
    "RRNOF","RRSOF","RRAF","RRNF","RRENF","DCRT","DRLT","RRNOT","RRENT"
]

NATURES = [
    "DEPENSE COURANTE","DEPENSE DE CAPITAL","PRESTATION DE SERVICES",
    "SERVICES ET FRAIS DIVERS","FRAIS DE MISSION","TRAVAUX","FOURNITURES",
    "IMMOBILISATION","CARBURANT ET LUBRIFIANT","FRAIS HOTEL ET RESTAURATION",
    "BILLET D'AVION","PENSION ET RETRAITE","COTISATION","TAXES ET IMPOTS"
]

def get_db():
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    try:    yield c
    finally: c.close()

def _hash(pw): return hashlib.sha256(pw.encode()).hexdigest()

def init_db():
    with sqlite3.connect(DB_PATH) as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username  TEXT UNIQUE NOT NULL,
    password  TEXT NOT NULL,
    full_name TEXT DEFAULT '',
    role      TEXT DEFAULT 'agent',
    directions TEXT DEFAULT '[]',
    email     TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS budget_lines (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    year       INTEGER NOT NULL,
    direction  TEXT NOT NULL,
    imputation TEXT NOT NULL,
    libelle    TEXT DEFAULT '',
    nature     TEXT DEFAULT 'DEPENSE COURANTE',
    budget_cp  REAL DEFAULT 0,
    UNIQUE(year, direction, imputation)
);
CREATE TABLE IF NOT EXISTS transactions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    code_ref     TEXT DEFAULT '',
    date_reception TEXT NOT NULL,
    direction    TEXT DEFAULT '',
    imputation   TEXT DEFAULT '',
    nature       TEXT DEFAULT 'DEPENSE COURANTE',
    intitule     TEXT DEFAULT '',
    description  TEXT DEFAULT '',
    montant      REAL DEFAULT 0,
    year         INTEGER NOT NULL,
    status       TEXT DEFAULT 'validated',
    statut_budget TEXT DEFAULT 'OK',
    created_by   TEXT DEFAULT '',
    created_by_name TEXT DEFAULT '',
    created_at   TEXT DEFAULT (datetime('now'))
);
""")
        dirs_json = json.dumps(ALL_DIRECTIONS)
        c.execute("INSERT OR IGNORE INTO users (username,password,full_name,role,directions) VALUES (?,?,'Administrateur','admin',?)",
            (ADMIN_USER, _hash(ADMIN_PASS), dirs_json))
        c.commit()

init_db()

# ── AUTH ──────────────────────────────────────────────────

def _get_user(request):
    token = request.cookies.get("session") or ""
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
    if u.get("role") not in ("admin","dcf_dir","dcf_sub"): raise HTTPException(403,"Forbidden")
    return u

def user_dirs(u):
    if u.get("role") in ("admin","dcf_dir","dcf_sub"): return ALL_DIRECTIONS
    try:    return json.loads(u.get("dirs") or u.get("directions","[]"))
    except: return []

def fmt_fcfa(n):
    n = int(round(float(n or 0)))
    s = f"{abs(n):,}".replace(","," ")
    return (f"-{s}" if n < 0 else s)

# ── PAGES ─────────────────────────────────────────────────

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
        return HTMLResponse(LOGIN_HTML.replace("__ERR__","<div class='err'>❌ Identifiants incorrects.</div>"), status_code=401)
    token = serializer.dumps({"u": username,"role":u["role"],"name":u["full_name"],"dirs":u["directions"]})
    r = RedirectResponse("/",status_code=302)
    r.set_cookie("session",token,httponly=True,samesite="lax")
    return r

@app.post("/api/login/token")
def api_login(payload: dict):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        u = conn.execute("SELECT * FROM users WHERE username=?",(payload.get("username",""),)).fetchone()
    if not u or u["password"] != _hash(payload.get("password","")):
        raise HTTPException(401,"Invalid credentials")
    token = serializer.dumps({"u":u["username"],"role":u["role"],"name":u["full_name"],"dirs":u["directions"]})
    return {"token":token,"role":u["role"]}

@app.post("/api/logout")
def api_logout():
    r = JSONResponse({"ok":True}); r.delete_cookie("session"); return r

@app.get("/api/me")
def api_me(request: Request):
    u = require_login(request)
    return {**u, "direction_list": user_dirs(u)}

# ── USERS ─────────────────────────────────────────────────

@app.get("/api/users")
def api_list_users(request: Request, db=Depends(get_db)):
    require_admin(request)
    return [dict(r) for r in db.execute("SELECT id,username,full_name,role,directions,email,created_at FROM users ORDER BY id").fetchall()]

@app.post("/api/users")
def api_create_user(request: Request, payload: dict, db=Depends(get_db)):
    require_admin(request)
    dirs = json.dumps(payload.get("directions",[]))
    try:
        db.execute("INSERT INTO users (username,password,full_name,role,directions,email) VALUES (?,?,?,?,?,?)",
            (payload["username"],_hash(payload["password"]),payload.get("full_name",""),
             payload.get("role","agent"),dirs,payload.get("email","")))
        db.commit()
    except sqlite3.IntegrityError: raise HTTPException(400,"Identifiant déjà utilisé")
    return {"ok":True}

@app.put("/api/users/{uid}")
def api_update_user(request: Request, uid: int, payload: dict, db=Depends(get_db)):
    require_admin(request)
    fields,vals=[],[]
    for k in ("full_name","role","email"):
        if k in payload: fields.append(k+"=?"); vals.append(payload[k])
    if "directions" in payload: fields.append("directions=?"); vals.append(json.dumps(payload["directions"]))
    if payload.get("password"): fields.append("password=?"); vals.append(_hash(payload["password"]))
    if not fields: raise HTTPException(400,"Nothing to update")
    vals.append(uid)
    db.execute("UPDATE users SET "+",".join(fields)+" WHERE id=?",vals); db.commit()
    return {"ok":True}

@app.delete("/api/users/{uid}")
def api_del_user(request: Request, uid: int, db=Depends(get_db)):
    require_admin(request)
    db.execute("DELETE FROM users WHERE id=?",(uid,)); db.commit()
    return {"ok":True}

# ── BUDGET LINES ──────────────────────────────────────────

@app.get("/api/budget-lines")
def api_list_bl(request: Request, year: int, direction: str="", db=Depends(get_db)):
    u = require_login(request)
    dirs = user_dirs(u)
    if direction and direction in dirs:
        rows = db.execute("SELECT * FROM budget_lines WHERE year=? AND direction=? ORDER BY imputation",(year,direction)).fetchall()
    elif dirs:
        ph = ",".join("?"*len(dirs))
        rows = db.execute(f"SELECT * FROM budget_lines WHERE year=? AND direction IN ({ph}) ORDER BY direction,imputation",[year]+dirs).fetchall()
    else:
        rows = []
    result = []
    for r in rows:
        r = dict(r)
        eng = db.execute("SELECT COALESCE(SUM(montant),0) FROM transactions WHERE imputation=? AND year=? AND status='validated'",(r["imputation"],year)).fetchone()[0]
        dispo = r["budget_cp"] - eng
        result.append({**r,"cumul_engage":eng,"disponible":dispo,"dispo_ok":dispo>=0})
    return result

@app.post("/api/budget-lines")
def api_create_bl(request: Request, payload: dict, db=Depends(get_db)):
    require_admin(request)
    try:
        db.execute("INSERT INTO budget_lines (year,direction,imputation,libelle,nature,budget_cp) VALUES (?,?,?,?,?,?)",
            (int(payload["year"]),payload["direction"].strip().upper(),payload["imputation"].strip(),
             payload.get("libelle","").strip(),payload.get("nature","DEPENSE COURANTE"),float(payload.get("budget_cp",0))))
        db.commit()
    except sqlite3.IntegrityError: raise HTTPException(400,"Ligne déjà existante")
    return {"ok":True}

@app.put("/api/budget-lines/{bid}")
def api_update_bl(request: Request, bid: int, payload: dict, db=Depends(get_db)):
    require_admin(request)
    db.execute("UPDATE budget_lines SET libelle=?,budget_cp=?,nature=? WHERE id=?",
        (payload.get("libelle",""),float(payload.get("budget_cp",0)),payload.get("nature","DEPENSE COURANTE"),bid))
    db.commit(); return {"ok":True}

@app.delete("/api/budget-lines/{bid}")
def api_del_bl(request: Request, bid: int, db=Depends(get_db)):
    require_admin(request)
    db.execute("DELETE FROM budget_lines WHERE id=?",(bid,)); db.commit()
    return {"ok":True}

# ── TRANSACTIONS ──────────────────────────────────────────

@app.get("/api/transactions")
def api_list_tx(request: Request, year: int, direction: str="", q: str="", status: str="", db=Depends(get_db)):
    u = require_login(request)
    dirs = user_dirs(u)
    sql,params = "SELECT * FROM transactions WHERE year=?",[year]
    if direction and direction in dirs: sql+=" AND direction=?"; params.append(direction)
    elif dirs:
        ph=",".join("?"*len(dirs)); sql+=f" AND direction IN ({ph})"; params+=dirs
    if status: sql+=" AND status=?"; params.append(status)
    rows = [dict(r) for r in db.execute(sql+" ORDER BY date_reception DESC,id DESC",params).fetchall()]
    if q:
        ql=q.lower()
        rows=[r for r in rows if any(ql in str(r.get(k,"")).lower() for k in ("code_ref","intitule","imputation","direction","description"))]
    return rows

@app.post("/api/transactions")
def api_create_tx(request: Request, payload: dict, db=Depends(get_db)):
    u = require_login(request)
    if u.get("role")=="viewer": raise HTTPException(403,"Lecture seule")
    dirs = user_dirs(u)
    direction = payload.get("direction","").strip().upper()
    if direction not in dirs: raise HTTPException(403,"Direction non autorisée")
    year = int(payload.get("year",date.today().year))
    date_ = payload.get("date_reception",date.today().isoformat())
    n = db.execute("SELECT COUNT(*) FROM transactions WHERE direction=? AND year=?",(direction,year)).fetchone()[0]+1
    code_ref = f"JD{direction}-{str(year)}{str(date_)[5:7]}{str(date_)[8:10]}-{n:03d}"
    imp = payload.get("imputation","").strip()
    montant = float(payload.get("montant",0))
    bl = db.execute("SELECT * FROM budget_lines WHERE imputation=? AND year=?",(imp,year)).fetchone()
    if bl:
        eng = db.execute("SELECT COALESCE(SUM(montant),0) FROM transactions WHERE imputation=? AND year=? AND status='validated'",(imp,year)).fetchone()[0]
        statut_budget = "OK" if bl["budget_cp"]-eng-montant>=0 else "DEPASSEMENT"
    else: statut_budget="OK"
    cur = db.execute(
        "INSERT INTO transactions (code_ref,date_reception,direction,imputation,nature,intitule,description,montant,year,status,statut_budget,created_by,created_by_name) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (code_ref,date_,direction,imp,payload.get("nature","DEPENSE COURANTE"),
         payload.get("intitule",""),payload.get("description",""),
         montant,year,payload.get("status","validated"),statut_budget,
         u.get("u",""),u.get("name","")))
    db.commit()
    return dict(db.execute("SELECT * FROM transactions WHERE id=?",(cur.lastrowid,)).fetchone())

@app.put("/api/transactions/{tid}")
def api_update_tx(request: Request, tid: int, payload: dict, db=Depends(get_db)):
    u = require_login(request)
    if u.get("role")=="viewer": raise HTTPException(403,"Lecture seule")
    imp = payload.get("imputation","")
    montant = float(payload.get("montant",0))
    year = payload.get("year",date.today().year)
    bl = db.execute("SELECT * FROM budget_lines WHERE imputation=? AND year=?",(imp,year)).fetchone()
    if bl:
        eng = db.execute("SELECT COALESCE(SUM(montant),0) FROM transactions WHERE imputation=? AND year=? AND status='validated' AND id!=?",(imp,year,tid)).fetchone()[0]
        statut_budget = "OK" if bl["budget_cp"]-eng-montant>=0 else "DEPASSEMENT"
    else: statut_budget="OK"
    db.execute("UPDATE transactions SET date_reception=?,direction=?,imputation=?,nature=?,intitule=?,description=?,montant=?,status=?,statut_budget=? WHERE id=?",
        (payload.get("date_reception",date.today().isoformat()),payload.get("direction",""),imp,
         payload.get("nature","DEPENSE COURANTE"),payload.get("intitule",""),payload.get("description",""),
         montant,payload.get("status","validated"),statut_budget,tid))
    db.commit(); return {"ok":True}

@app.delete("/api/transactions/{tid}")
def api_del_tx(request: Request, tid: int, db=Depends(get_db)):
    u = require_login(request)
    if u.get("role") not in ("admin","dcf_dir","dcf_sub"): raise HTTPException(403,"Admin seulement")
    db.execute("DELETE FROM transactions WHERE id=?",(tid,)); db.commit()
    return {"ok":True}

# ── DASHBOARD ─────────────────────────────────────────────

@app.get("/api/dashboard")
def api_dashboard(request: Request, year: int, db=Depends(get_db)):
    u = require_login(request)
    dirs = user_dirs(u)
    ph = ",".join("?"*len(dirs)) if dirs else "NULL"
    txs  = [dict(r) for r in db.execute(f"SELECT * FROM transactions WHERE year=? AND direction IN ({ph})",[year]+dirs).fetchall()] if dirs else []
    bls  = [dict(r) for r in db.execute(f"SELECT * FROM budget_lines WHERE year=? AND direction IN ({ph})",[year]+dirs).fetchall()] if dirs else []
    total_budget  = sum(b["budget_cp"] for b in bls)
    total_engage  = sum(t["montant"] for t in txs if t["status"]=="validated")
    total_pending = sum(t["montant"] for t in txs if t["status"]=="pending")
    total_dispo   = total_budget - total_engage
    by_dir={}
    for t in txs:
        if t["status"]=="validated": by_dir[t["direction"]]=by_dir.get(t["direction"],0)+t["montant"]
    by_month=[0]*12
    for t in txs:
        if t["status"]=="validated":
            try: m=int(t["date_reception"].split("-")[1])-1; by_month[m]+=t["montant"]
            except: pass
    bl_by_dir={}
    for b in bls:
        d=b["direction"]
        if d not in bl_by_dir: bl_by_dir[d]={"budget_cp":0,"engage":by_dir.get(d,0)}
        bl_by_dir[d]["budget_cp"]+=b["budget_cp"]
    overdrawn=[{"direction":d,"montant":v["engage"]-v["budget_cp"]} for d,v in bl_by_dir.items() if v["engage"]>v["budget_cp"]]
    recent=[dict(r) for r in db.execute(f"SELECT * FROM transactions WHERE year=? AND direction IN ({ph}) ORDER BY id DESC LIMIT 15",[year]+dirs).fetchall()] if dirs else []
    return {"total_budget":total_budget,"total_engage":total_engage,"total_pending":total_pending,
            "total_dispo":total_dispo,"tx_count":sum(1 for t in txs if t["status"]=="validated"),
            "pending_count":sum(1 for t in txs if t["status"]=="pending"),
            "by_dir":by_dir,"by_month":by_month,"bl_by_dir":bl_by_dir,"overdrawn":overdrawn,"recent":recent}

# ── IMPORT ────────────────────────────────────────────────

@app.post("/api/import/budget-lines")
async def api_import_bl(request: Request, file: UploadFile=File(...), db=Depends(get_db)):
    require_admin(request)
    raw = await file.read()
    # Try multiple encodings
    content = None
    for enc in ("utf-8-sig","utf-8","latin-1","cp1252"):
        try: content = raw.decode(enc); break
        except: pass
    if content is None: raise HTTPException(400,"Cannot decode file")
    reader = csv.DictReader(io.StringIO(content))
    created=updated=skipped=0; errors=[]
    for i,row in enumerate(reader,2):
        try:
            yr_raw = (row.get("YEAR") or row.get("ANNEE") or row.get("year") or row.get("Annee") or "").strip()
            dirn   = (row.get("DIRECTION") or row.get("direction") or row.get("Direction") or "").strip().upper()
            imp    = (row.get("IMPUTATION COMPTABLE") or row.get("IMPUTATION") or row.get("imputation")
                      or row.get("Imputation comptable") or row.get("ACCOUNTING ENTRY") or "").strip()
            lib    = (row.get("LIBELLE") or row.get("libelle") or row.get("DESCRIPTION")
                      or row.get("Libelle") or "").strip()
            nat    = (row.get("NATURE") or row.get("nature") or "DEPENSE COURANTE").strip()
            raw_bcp= str(row.get("BUDGET CP (FCFA)") or row.get("BUDGET CP") or row.get("budget_cp")
                         or row.get("Budget CP") or row.get("Budget CP (FCFA)") or "0").strip()
            # Skip completely blank or subtotal rows silently
            if not yr_raw and not dirn and not imp: skipped+=1; continue
            if not yr_raw: skipped+=1; continue
            try: yr = int(float(yr_raw))
            except (ValueError, TypeError): skipped+=1; continue
            if not dirn or not imp: skipped+=1; continue
            # Clean numeric value
            for ch in [" "," "," ","	"]: raw_bcp=raw_bcp.replace(ch,"")
            raw_bcp = raw_bcp.replace(",",".")
            try: bcp = float(raw_bcp) if raw_bcp and raw_bcp not in ("-","") else 0.0
            except: bcp = 0.0
            ex = db.execute("SELECT id,libelle FROM budget_lines WHERE year=? AND direction=? AND imputation=?",(yr,dirn,imp)).fetchone()
            if ex:
                db.execute("UPDATE budget_lines SET libelle=?,nature=?,budget_cp=? WHERE id=?",(lib or ex["libelle"],nat,bcp,ex["id"])); updated+=1
            else:
                db.execute("INSERT INTO budget_lines (year,direction,imputation,libelle,nature,budget_cp) VALUES (?,?,?,?,?,?)",(yr,dirn,imp,lib,nat,bcp)); created+=1
        except Exception as e:
            errors.append(f"Ligne {i}: {e}")
    db.commit()
    return {"created":created,"updated":updated,"skipped":skipped,"errors":errors[:10]}

@app.post("/api/import/transactions")
async def api_import_tx(request: Request, file: UploadFile=File(...), year: int=Form(...), db=Depends(get_db)):
    u = require_login(request)
    if u.get("role") not in ("admin","dcf_dir","dcf_sub"): raise HTTPException(403,"Admin seulement")
    raw = await file.read()
    content=None
    for enc in ("utf-8-sig","utf-8","latin-1","cp1252"):
        try: content=raw.decode(enc); break
        except: pass
    if content is None: raise HTTPException(400,"Cannot decode")
    reader = csv.DictReader(io.StringIO(content))
    created=0; errors=[]
    for i,row in enumerate(reader,2):
        try:
            direction=(row.get("DIRECTION") or row.get("direction","")).strip().upper()
            imp=(row.get("IMPUTATION COMPTABLE") or row.get("IMPUTATION") or row.get("imputation","")).strip()
            raw_m=str(row.get("MONTANT") or row.get("montant",0) or "0")
            montant=float(raw_m.replace(" ","").replace(" ","").replace(" ","").replace(",","."))
            date_r=(row.get("DATE DE RECEPTION") or row.get("DATE") or row.get("date_reception",date.today().isoformat())).strip()
            intitule=(row.get("INTITULE DE LA COMMANDE") or row.get("INTITULE") or row.get("intitule","")).strip()
            desc=(row.get("DESCRIPTION") or row.get("description","")).strip()
            nature=(row.get("NATURE") or "DEPENSE COURANTE").strip()
            status=(row.get("STATUT") or row.get("status","validated")).strip()
            code_ref=(row.get("CODE/REF NUMBER") or row.get("code_ref","")).strip()
            if not direction or not date_r: errors.append(f"Ligne {i}: direction/date manquante"); continue
            n=db.execute("SELECT COUNT(*) FROM transactions WHERE direction=? AND year=?",(direction,year)).fetchone()[0]+1
            if not code_ref: code_ref=f"JD{direction}-{year}IMP-{n:03d}"
            bl=db.execute("SELECT * FROM budget_lines WHERE imputation=? AND year=?",(imp,year)).fetchone()
            if bl:
                eng=db.execute("SELECT COALESCE(SUM(montant),0) FROM transactions WHERE imputation=? AND year=? AND status='validated'",(imp,year)).fetchone()[0]
                sb="OK" if bl["budget_cp"]-eng-montant>=0 else "DEPASSEMENT"
            else: sb="OK"
            db.execute("INSERT INTO transactions (code_ref,date_reception,direction,imputation,nature,intitule,description,montant,year,status,statut_budget,created_by,created_by_name) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (code_ref,date_r,direction,imp,nature,intitule,desc,montant,year,status,sb,u.get("u",""),u.get("name","IMPORT")))
            created+=1
        except Exception as e: errors.append(f"Ligne {i}: {e}")
    db.commit()
    return {"created":created,"errors":errors[:10]}

# ── EXPORT ────────────────────────────────────────────────

@app.get("/api/export/transactions")
def api_export_tx(request: Request, year: int, direction: str="", db=Depends(get_db)):
    u = require_login(request)
    dirs=user_dirs(u); sql,params="SELECT * FROM transactions WHERE year=?",[year]
    if direction and direction in dirs: sql+=" AND direction=?"; params.append(direction)
    elif dirs: ph=",".join("?"*len(dirs)); sql+=f" AND direction IN ({ph})"; params+=dirs
    rows=[dict(r) for r in db.execute(sql+" ORDER BY date_reception,direction",params).fetchall()]
    out=io.StringIO(); w=csv.writer(out)
    w.writerow(["DATE DE RECEPTION","CODE/REF NUMBER","DIRECTION","IMPUTATION COMPTABLE","NATURE","INTITULE DE LA COMMANDE","DESCRIPTION","MONTANT","STATUT","STATUT BUDGET","INITIE PAR"])
    for r in rows:
        w.writerow([r["date_reception"],r["code_ref"],r["direction"],r["imputation"],r["nature"],r["intitule"],r["description"],r["montant"],r["status"],r["statut_budget"],r.get("created_by_name","")])
    out.seek(0)
    return StreamingResponse(iter([out.getvalue()]),media_type="text/csv",headers={"Content-Disposition":f"attachment; filename=transactions_{year}.csv"})

@app.get("/api/export/template-transactions")
def tpl_tx(request: Request):
    require_login(request)
    out=io.StringIO(); w=csv.writer(out)
    w.writerow(["DATE DE RECEPTION","DIRECTION","IMPUTATION COMPTABLE","NATURE","INTITULE DE LA COMMANDE","DESCRIPTION","MONTANT","STATUT"])
    w.writerow(["2025-01-20","DG","SP4/DG/AD0025/VD0007/T00127/63840100","DEPENSE COURANTE","FRAIS DE MISSION A L'EXTERIEUR","Description détaillée",2800000,"validated"])
    w.writerow(["2025-01-06","DRH","SP4/DRH/AD0002/VD0029/T00362/66410200","PENSION VIEILLESSE","COTISATION DE CNPS DE MOIS DE DECEMBER 2024","",291959762,"validated"])
    out.seek(0)
    return StreamingResponse(iter([out.getvalue()]),media_type="text/csv",headers={"Content-Disposition":"attachment; filename=template_transactions.csv"})

@app.get("/api/export/template-budget-lines")
def tpl_bl(request: Request):
    require_login(request)
    out=io.StringIO(); w=csv.writer(out)
    w.writerow(["YEAR","DIRECTION","IMPUTATION COMPTABLE","LIBELLE","NATURE","BUDGET CP (FCFA)"])
    examples=[
        (2025,"DG","SP4/DG/AD0025/VD0007/T00127/63840100","FRAIS DE MISSION A L'EXTERIEUR","DEPENSE COURANTE",50000000),
        (2025,"DG","SP4/DG/AD0025/VD0075/T00430/60570000","FRAIS HOTEL ET RESTAURATION","DEPENSE COURANTE",12000000),
        (2025,"DRH","SP4/DRH/AD0002/VD0029/T00362/66410200","PENSION VIEILLESSE NATIONAUX","DEPENSE COURANTE",500000000),
        (2025,"DCF","SP4/AD0025/VD0060/PD0006/DCF/90530000","FOURNISSEURS","DEPENSE COURANTE",27500000000),
        (2025,"DICOM","SP4/DICOM/AD0033/VD0014/T00127/60570000","FRAIS HOTEL ET RESTAURATION","DEPENSE COURANTE",5000000),
        (2025,"DAP","SP4/DAP/AD0019/VD0065/T00187/63280000","SERVICES ET FRAIS DIVERS","DEPENSE COURANTE",3000000),
        (2026,"DG","SP4/DG/AD0025/VD0007/T00127/63840100","FRAIS DE MISSION A L'EXTERIEUR","DEPENSE COURANTE",55000000),
    ]
    for ex in examples: w.writerow(ex)
    out.seek(0)
    return StreamingResponse(iter([out.getvalue()]),media_type="text/csv",headers={"Content-Disposition":"attachment; filename=template_budget_lines.csv"})

@app.get("/api/report/monthly")
def api_report(request: Request, year: int, month: int, db=Depends(get_db)):
    u=require_login(request); dirs=user_dirs(u)
    ph=",".join("?"*len(dirs)) if dirs else "NULL"
    txs=[dict(r) for r in db.execute(f"SELECT * FROM transactions WHERE year=? AND strftime('%m',date_reception)=? AND direction IN ({ph})",[year,f"{month:02d}"]+dirs).fetchall()] if dirs else []
    bls=[dict(r) for r in db.execute(f"SELECT * FROM budget_lines WHERE year=? AND direction IN ({ph})",[year]+dirs).fetchall()] if dirs else []
    out=io.StringIO(); w=csv.writer(out)
    MOIS=["Janvier","Février","Mars","Avril","Mai","Juin","Juillet","Août","Septembre","Octobre","Novembre","Décembre"]
    w.writerow([f"RAPPORT MENSUEL CAMTEL — {MOIS[month-1].upper()} {year}"])
    w.writerow([]); w.writerow(["RÉSUMÉ"])
    total_budget=sum(b["budget_cp"] for b in bls)
    total_engage=sum(t["montant"] for t in txs if t["status"]=="validated")
    w.writerow(["Budget total CP",total_budget])
    w.writerow(["Engagé ce mois",total_engage])
    w.writerow(["Taux",f"{round(total_engage/total_budget*100,1) if total_budget else 0}%"])
    w.writerow([]); w.writerow(["DATE","CODE/REF","DIRECTION","IMPUTATION","NATURE","INTITULE","MONTANT","STATUT BUDGET"])
    for t in txs:
        w.writerow([t["date_reception"],t["code_ref"],t["direction"],t["imputation"],t["nature"],t["intitule"],t["montant"],t["statut_budget"]])
    out.seek(0)
    return StreamingResponse(iter([out.getvalue()]),media_type="text/csv",headers={"Content-Disposition":f"attachment; filename=rapport_{year}_{month:02d}.csv"})

# ── FICHE DCF ─────────────────────────────────────────────

@app.get("/fiche", response_class=HTMLResponse)
def fiche(request: Request, ids: str, db=Depends(get_db)):
    u = require_login(request)
    tx_ids=[int(i.strip()) for i in ids.split(",") if i.strip().isdigit()]
    txs=[]
    for tid in tx_ids[:20]:
        t=db.execute("SELECT * FROM transactions WHERE id=?",(tid,)).fetchone()
        if t: txs.append(dict(t))
    pages=[]
    for i in range(0,len(txs),2):
        pair=txs[i:i+2]
        blocks="".join(_fiche_block(t,db) for t in pair)
        if len(pair)==1: blocks+="<div style='height:5mm'></div>"
        pages.append(f"<div class='page'>{blocks}</div>")
    FICHE_CSS="""
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:Arial,sans-serif;font-size:10pt;color:#000;}
.noprint{padding:10px 14px;background:#f1f5f9;display:flex;gap:10px;align-items:center;}
.noprint button{padding:8px 16px;background:#003e7e;color:#fff;border:none;border-radius:6px;cursor:pointer;font-weight:700;font-size:13px;}
.page{width:210mm;min-height:297mm;padding:8mm 10mm;display:flex;flex-direction:column;gap:5mm;page-break-after:always;}
.fiche{border:2px solid #003e7e;padding:4mm;flex:1;display:flex;flex-direction:column;font-size:9.5pt;}
.fhdr{display:flex;align-items:center;gap:8px;padding-bottom:3mm;border-bottom:2px solid #003e7e;margin-bottom:3mm;}
.flogo{background:#00adef;color:#fff;font-weight:900;font-size:16pt;padding:4px 10px;border-radius:6px;letter-spacing:1px;}
.ftitle h1{font-size:10pt;font-weight:800;color:#003e7e;} .ftitle p{font-size:8pt;color:#64748b;}
.sec{background:#003e7e;color:#fff;padding:2px 6px;font-size:8pt;font-weight:800;text-transform:uppercase;margin:2mm 0 1.5mm;}
.box{border:1px solid #334155;padding:2mm 3mm;margin-bottom:1.5mm;}
.r{display:flex;border-bottom:1px solid #e2e8f0;padding:1.5px 0;align-items:flex-start;}
.r:last-child{border-bottom:none;}
.rl{color:#475569;min-width:150px;font-weight:700;font-size:8.5pt;flex-shrink:0;}
.rv{flex:1;font-size:8.5pt;word-break:break-word;}
.amt-box{background:#f0f7ff;border:2px solid #003e7e;padding:3mm;margin:2mm 0;text-align:center;}
.amt-val{font-size:16pt;font-weight:900;color:#003e7e;letter-spacing:1px;}
.amt-sub{font-size:9pt;color:#334155;margin-top:1mm;}
.dispo{border:2px solid #000;padding:2mm 4mm;display:flex;justify-content:space-between;align-items:center;margin:2.5mm 0;}
.dispo-lbl{font-weight:900;font-size:11pt;letter-spacing:.15em;}
.chks{display:flex;gap:20px;font-size:10.5pt;font-weight:800;}
.chk{display:flex;align-items:center;gap:6px;}
.chkb{width:15px;height:15px;border:2.5px solid #000;display:inline-flex;align-items:center;justify-content:center;font-size:10pt;font-weight:900;}
.solde-box{border:1px solid #334155;padding:2mm 3mm;margin:2mm 0;}
.solde-r{display:flex;justify-content:space-between;padding:1.5px 0;font-size:9pt;border-bottom:1px solid #f1f5f9;}
.solde-r:last-child{border-bottom:none;font-weight:800;font-size:10pt;}
.signs{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin-top:auto;}
.sign{border:1px solid #334155;padding:2mm;min-height:18mm;}
.sign label{font-size:7.5pt;font-weight:800;text-transform:uppercase;color:#475569;display:block;margin-bottom:1.5mm;}
.initby{font-size:8pt;color:#64748b;text-align:right;margin:1.5mm 0;}
@media print{.noprint{display:none!important;}.page{padding:6mm 8mm;}@page{size:A4;margin:0;}}
"""
    return HTMLResponse(f"""<!doctype html><html lang='fr'><head><meta charset='utf-8'/>
<title>Fiches DCF</title><style>{FICHE_CSS}</style></head><body>
<div class='noprint'>
  <button onclick='window.print()'>🖨 Imprimer / PDF</button>
  <button onclick='window.close()' style='background:#64748b'>Fermer</button>
  <span style='font-size:12px;color:#64748b'>{len(txs)} fiche(s) — {len(pages)} page(s) A4</span>
</div>
{"".join(pages)}
</body></html>""")

def _fiche_block(t, db):
    bl=db.execute("SELECT * FROM budget_lines WHERE imputation=? AND year=?",(t["imputation"],t["year"])).fetchone()
    prevision=bl["budget_cp"] if bl else 0
    libelle_bl=bl["libelle"] if bl else (t["imputation"] or "—")
    eng_before=db.execute("SELECT COALESCE(SUM(montant),0) FROM transactions WHERE imputation=? AND year=? AND status='validated' AND id<?",(t["imputation"],t["year"],t["id"])).fetchone()[0]
    solde_avant=prevision-eng_before; solde_apres=solde_avant-t["montant"]; dispo=solde_apres>=0
    gc="#16a34a" if dispo else "#dc2626"
    oui_chk=f"<div class='chkb' style='border-color:#16a34a;background:#dcfce7;color:#16a34a'>✓</div>" if dispo else "<div class='chkb'></div>"
    non_chk=f"<div class='chkb' style='border-color:#dc2626;background:#fee2e2;color:#dc2626'>✓</div>" if not dispo else "<div class='chkb'></div>"
    return f"""
<div class='fiche'>
  <div class='fhdr'>
    <div class='flogo'>C</div>
    <div class='ftitle'><h1>CAMTEL — REPRÉSENTATION {t.get("direction","—")} — BUSINESS UNIT FIXE</h1>
    <p>FICHE DE SUIVI BUDGÉTAIRE — SAAF / DCF / CONTRÔLE BUDGÉTAIRE</p></div>
  </div>
  <div class='sec'>Compte budgétaire</div>
  <div class='box'>
    <div class='r'><span class='rl'>Prévision sur le compte :</span><span class='rv'><strong>{fmt_fcfa(prevision)} FCFA</strong></span></div>
    <div class='r'><span class='rl'>NOTE COMPTABILITÉ – Solde initial :</span><span class='rv'><strong>{fmt_fcfa(prevision)} FCFA</strong></span></div>
  </div>
  <div class='sec'>Référence / Libellé / Engagement</div>
  <div class='box'>
    <div class='r'><span class='rl'>Référence du compte :</span><span class='rv' style='font-family:monospace;font-size:8pt'>{t["imputation"]}</span></div>
    <div class='r'><span class='rl'>Code / Réf. dossier :</span><span class='rv'>{t["code_ref"]}</span></div>
    <div class='r'><span class='rl'>Direction :</span><span class='rv'><strong>{t["direction"]}</strong></span></div>
    <div class='r'><span class='rl'>Date :</span><span class='rv'>{t["date_reception"]}</span></div>
    <div class='r'><span class='rl'>Nature :</span><span class='rv'>{t["nature"]}</span></div>
    <div class='r'><span class='rl'>LIBELLÉ(S) :</span><span class='rv'><strong>{libelle_bl}</strong></span></div>
    <div class='r'><span class='rl'>OBJET / DESCRIPTION :</span><span class='rv'>{t["description"] or t["intitule"] or "—"}</span></div>
  </div>
  <div class='amt-box'>
    <div style='font-size:9pt;font-weight:700;color:#475569;letter-spacing:.1em'>MONTANT DE L'ENGAGEMENT</div>
    <div class='amt-val'>{fmt_fcfa(t["montant"])} FCFA</div>
  </div>
  <div class='solde-box'>
    <div class='solde-r'><span>Solde avant engagement :</span><span>{fmt_fcfa(solde_avant)} FCFA</span></div>
    <div class='solde-r'><span>Engagement :</span><span>- {fmt_fcfa(t["montant"])} FCFA</span></div>
    <div class='solde-r'><span>SOLDE FINAL DU COMPTE :</span><span style='color:{gc}'>{fmt_fcfa(solde_apres)} FCFA</span></div>
  </div>
  <div class='dispo'>
    <div class='dispo-lbl'>DISPONIBLE</div>
    <div class='chks'>
      <div class='chk'>{oui_chk} OUI</div>
      <div class='chk'>{non_chk} NON</div>
    </div>
  </div>
  <div class='initby'>Initié par : {t.get("created_by_name") or t.get("created_by","—")}</div>
  <div class='signs'>
    <div class='sign'><label>Avis de la DCF</label></div>
    <div class='sign'><label>Visa Contrôleur Budgétaire</label></div>
    <div class='sign'><label>Approbation Direction</label></div>
  </div>
</div>"""

LOGIN_HTML = "<!doctype html>\n<html lang='fr'><head><meta charset='utf-8'/>\n<meta name='viewport' content='width=device-width,initial-scale=1'/>\n<title>CAMTEL - Connexion</title>\n<style>\n*{box-sizing:border-box;margin:0;padding:0;}\nbody{font-family:'Segoe UI',system-ui,sans-serif;background:linear-gradient(135deg,#0a1f4e 0%,#1f4d8f 55%,#00b0e8 100%);min-height:100vh;display:flex;align-items:center;justify-content:center;}\n.card{background:#fff;border-radius:16px;padding:36px 32px;width:440px;box-shadow:0 20px 60px rgba(0,0,0,.3);}\n.lrow{display:flex;align-items:center;gap:14px;margin-bottom:24px;}\n.lsvg{width:56px;height:56px;flex-shrink:0;}\nh2{font-size:18px;font-weight:800;color:#0f2a5e;} p{font-size:11px;color:#64748b;margin-top:2px;}\nlabel{display:block;font-size:11px;font-weight:700;color:#475569;margin:14px 0 4px;text-transform:uppercase;letter-spacing:.04em;}\ninput{width:100%;padding:11px 12px;border-radius:8px;border:1.5px solid #e2e8f0;font-size:14px;font-family:inherit;}\ninput:focus{outline:none;border-color:#00b0e8;}\nbutton{width:100%;padding:12px;border-radius:8px;background:linear-gradient(135deg,#1f4d8f,#00b0e8);color:#fff;border:none;cursor:pointer;font-size:14px;font-weight:700;margin-top:20px;}\n.hint{color:#94a3b8;font-size:11px;margin-top:14px;text-align:center;}\n.err{background:#fee2e2;color:#dc2626;padding:9px 12px;border-radius:6px;font-size:12px;margin-bottom:12px;border-left:3px solid #dc2626;}\n</style></head>\n<body><div class='card'>\n  <div class='lrow'>\n    <svg class='lsvg' viewBox='0 0 100 100' fill='none'>\n      <circle cx='50' cy='50' r='48' fill='#e0f6fd'/>\n      <path d='M72 28 L54 28 C34 28 20 37 20 50 C20 63 34 72 54 72 L72 72 L72 59 L56 59 C45 59 37 55 37 50 C37 45 45 41 56 41 L72 41 Z' fill='#00b0e8'/>\n      <path d='M72 28 L91 50 L72 72 Z' fill='#00b0e8' opacity='0.8'/>\n    </svg>\n    <div>\n      <h2>CAMTEL</h2>\n      <p>Gestion Budgetaire - SAAF/DCF/Controle Budgetaire</p>\n    </div>\n  </div>\n  __ERR__\n  <form method='post' action='/api/login'>\n    <label>Identifiant</label>\n    <input name='username' placeholder='admin' required autofocus autocomplete='username'/>\n    <label>Mot de passe</label>\n    <input name='password' type='password' placeholder='........' required/>\n    <button type='submit'>Se connecter</button>\n  </form>\n  <div class='hint'>Contactez l administrateur pour vos acces.</div>\n</div></body></html>"

APP_HTML = '<!doctype html>\n<html lang="fr">\n<head>\n<meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>\n<title>CAMTEL – Gestion Budgétaire 2025</title>\n<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>\n<style>\n:root{\n  --navy:#0f2a5e;--blue:#1f4d8f;--camtel:#00b0e8;--b3:#e0f6fd;\n  --green:#16a34a;--g2:#dcfce7;--red:#dc2626;--r2:#fee2e2;\n  --yel:#d97706;--y2:#fef9c3;\n  --bg:#f0f4f8;--card:#fff;--bdr:#e2e8f0;--txt:#1e293b;--muted:#64748b;--lt:#f8fafc;\n}\n*{box-sizing:border-box;margin:0;padding:0;}\nbody{font-family:"Segoe UI",system-ui,sans-serif;background:var(--bg);color:var(--txt);font-size:13px;}\nheader{background:linear-gradient(135deg,#0a1f4e 0%,#1f4d8f 60%,#007fb5 100%);color:#fff;padding:0 14px;height:56px;display:flex;align-items:center;gap:10px;position:sticky;top:0;z-index:200;box-shadow:0 3px 12px rgba(0,0,0,.3);}\n.hlogo-svg{width:42px;height:42px;flex-shrink:0;}\n.hbrand h1{font-size:13px;font-weight:800;letter-spacing:.2px;}\n.hbrand p{font-size:9px;opacity:.65;margin-top:1px;}\nnav{display:flex;gap:2px;margin:0 6px;}\nnav button{background:transparent;color:rgba(255,255,255,.7);border:none;padding:6px 9px;border-radius:5px;cursor:pointer;font-size:11px;font-weight:600;white-space:nowrap;}\nnav button:hover,nav button.active{background:rgba(255,255,255,.18);color:#fff;}\n.upill{background:rgba(255,255,255,.1);padding:3px 9px;border-radius:20px;font-size:11px;display:flex;align-items:center;gap:5px;white-space:nowrap;}\n.btn{padding:6px 12px;border-radius:7px;border:none;cursor:pointer;font-size:11px;font-weight:700;font-family:inherit;transition:all .15s;display:inline-flex;align-items:center;gap:4px;}\n.bp{background:#1f4d8f;color:#fff;}.bp:hover{background:#00b0e8;}\n.bs{background:#e5e7eb;color:#374151;}.bs:hover{background:#d1d5db;}\n.bd{background:#dc2626;color:#fff;}.bd:hover{background:#b91c1c;}\n.bg2{background:#d1fae5;color:#065f46;border:1px solid #6ee7b7;}\n.bsm{padding:4px 8px;font-size:11px;}\n.bxs{padding:2px 6px;font-size:11px;border-radius:4px;}\n.btn-logout{background:#dc2626;color:#fff;border:none;padding:5px 11px;border-radius:6px;cursor:pointer;font-size:11px;font-weight:700;margin-left:5px;}\n.wrap{max-width:100%;padding:10px 12px;}\n.krow{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:10px;}\n.kpi{background:#fff;border:1px solid var(--bdr);border-radius:10px;padding:11px 13px;}\n.kpi label{font-size:9px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);font-weight:700;}\n.kpi .val{font-size:18px;font-weight:800;margin-top:3px;}\n.kpi .sub{font-size:10px;color:var(--muted);margin-top:2px;}\n.kpi.kb .val{color:#1f4d8f;}.kpi.kr .val{color:#dc2626;}.kpi.ky .val{color:#d97706;}.kpi.kg .val{color:#16a34a;}\n.gbar{display:flex;align-items:center;gap:8px;margin-bottom:10px;background:#fff;border:1px solid var(--bdr);border-radius:10px;padding:8px 12px;flex-wrap:wrap;}\n.gbar label{font-size:10px;font-weight:700;color:var(--muted);text-transform:uppercase;}\n.gbar select,.gbar input{padding:5px 8px;border-radius:6px;border:1px solid var(--bdr);font-size:12px;font-family:inherit;}\n.tab-content{display:none;}.tab-content.active{display:block;}\n.card{background:#fff;border:1px solid var(--bdr);border-radius:10px;overflow:hidden;margin-bottom:10px;}\n.ch{padding:9px 13px;border-bottom:1px solid var(--bdr);display:flex;align-items:center;justify-content:space-between;background:var(--lt);}\n.ch h2{font-size:12px;font-weight:700;flex:1;}\n.cb{padding:11px;}\n.g2{display:grid;grid-template-columns:1fr 1fr;gap:10px;}\n.g3{display:grid;grid-template-columns:2fr 1fr;gap:10px;}\n.alrt{padding:7px 10px;border-radius:6px;font-size:11px;margin-bottom:7px;border-left:3px solid;}\n.alrt-r{background:#fee2e2;color:#dc2626;border-color:#dc2626;}\n.alrt-y{background:#fef9c3;color:#d97706;border-color:#d97706;}\n.alrt-g{background:#dcfce7;color:#16a34a;border-color:#16a34a;}\n.alrt-b{background:#dbeafe;color:#1e40af;border-color:#3b82f6;}\n.prg{height:5px;background:#e5e7eb;border-radius:3px;overflow:hidden;margin-top:3px;}\n.prf{height:100%;border-radius:3px;}\n.mbg{display:none;position:fixed;inset:0;background:rgba(10,25,55,.5);z-index:300;align-items:flex-start;justify-content:center;padding-top:30px;overflow-y:auto;}\n.mbg.open{display:flex;}\n.modal{background:#fff;border-radius:13px;width:min(660px,96vw);max-height:88vh;overflow-y:auto;box-shadow:0 20px 60px rgba(0,0,0,.25);margin-bottom:20px;}\n.mh{padding:11px 15px;border-bottom:1px solid var(--bdr);display:flex;align-items:center;justify-content:space-between;background:var(--lt);position:sticky;top:0;}\n.mh h3{font-size:13px;font-weight:700;}\n.mb{padding:15px;}.mf{padding:10px 15px;border-top:1px solid var(--bdr);display:flex;gap:7px;justify-content:flex-end;background:var(--lt);}\n.fr{display:grid;gap:7px;}.fc2{grid-template-columns:1fr 1fr;}.fc3{grid-template-columns:1fr 1fr 1fr;}\n.fld label{display:block;font-size:10px;font-weight:700;color:var(--muted);margin-bottom:3px;text-transform:uppercase;letter-spacing:.04em;}\n.fld input,.fld select,.fld textarea{width:100%;padding:7px 9px;border-radius:6px;border:1.5px solid var(--bdr);font-size:12px;font-family:inherit;}\n.fld input:focus,.fld select:focus,.fld textarea:focus{outline:none;border-color:#1f4d8f;}\n.fld textarea{min-height:50px;resize:vertical;}\n.scan-area{border:2px dashed var(--bdr);border-radius:8px;padding:15px;text-align:center;cursor:pointer;}\n.scan-area:hover{border-color:#1f4d8f;background:#eff6ff;}\n.cbox-row{display:flex;align-items:center;gap:6px;padding:4px 0;border-bottom:1px solid #f1f5f9;}\n.cbox-row input[type=checkbox]{width:13px;height:13px;accent-color:#1f4d8f;}\n.toast{position:fixed;right:14px;bottom:14px;padding:8px 14px;border-radius:8px;font-size:12px;font-weight:700;z-index:999;display:none;box-shadow:0 4px 14px rgba(0,0,0,.15);}\n\n/* === EXCEL-STYLE TABLE === */\n.tbar{display:flex;align-items:center;gap:6px;flex-wrap:wrap;padding:8px 10px;background:linear-gradient(90deg,#f8fafc,#eff6ff);border:1px solid var(--bdr);border-bottom:none;border-radius:10px 10px 0 0;}\n.tbar input,.tbar select{padding:5px 8px;border-radius:6px;border:1px solid var(--bdr);font-size:11px;font-family:inherit;}\n.excel-wrap{overflow-x:auto;border:2px solid #1e3a8a;border-radius:0 0 8px 8px;}\n.xtbl{width:100%;border-collapse:collapse;font-size:12px;min-width:1350px;}\n\n/* Header colors matching Excel screenshot */\n.xtbl thead tr th{padding:8px 7px;font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:.05em;color:#fff;text-align:left;white-space:nowrap;border:1px solid rgba(255,255,255,.2);position:sticky;top:0;z-index:5;}\n.xtbl thead th.th-chk{background:#374151;width:32px;}\n.xtbl thead th.th-date{background:#5b21b6;}\n.xtbl thead th.th-code{background:#3730a3;}\n.xtbl thead th.th-dir{background:#0e7490;}\n.xtbl thead th.th-imp{background:#1e3a8a;min-width:200px;}\n.xtbl thead th.th-nat{background:#166534;}\n.xtbl thead th.th-int{background:#7c2d12;min-width:160px;}\n.xtbl thead th.th-amt{background:#991b1b;text-align:right;}\n.xtbl thead th.th-bcp{background:#065f46;text-align:right;}\n.xtbl thead th.th-cum{background:#4c1d95;text-align:right;}\n.xtbl thead th.th-dis{background:#14532d;text-align:right;}\n.xtbl thead th.th-sta{background:#1e40af;text-align:center;}\n.xtbl thead th.th-act{background:#374151;width:70px;}\n\n/* Row coloring */\n.xtbl tbody tr.row-dep td{background:#fee2e2;}\n.xtbl tbody tr.row-ok td{background:#f0fdf4;}\n.xtbl tbody tr.row-pend td{background:#fffbeb;}\n.xtbl tbody tr:hover td{background:#dbeafe !important;transition:background .08s;}\n.xtbl tbody tr.row-sel td{background:#bfdbfe !important;}\n\n/* Cell styles */\n.xtbl tbody td{padding:6px 7px;border:1px solid #e5e7eb;vertical-align:middle;}\n.xtbl tbody td.tc{text-align:center;}\n.xtbl tbody td.tr{text-align:right;font-family:"Courier New",monospace;font-weight:700;white-space:nowrap;}\n.xtbl tbody td.td-date{color:#5b21b6;font-weight:600;white-space:nowrap;}\n.xtbl tbody td.td-code{font-family:monospace;font-size:10px;color:#3730a3;white-space:nowrap;}\n.xtbl tbody td.td-imp{font-family:monospace;font-size:9px;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}\n.xtbl tbody td.td-int{max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}\n.xtbl tbody td.td-amt{text-align:right;font-family:"Courier New",monospace;font-weight:800;color:#991b1b;white-space:nowrap;}\n.xtbl tbody td.td-bcp{text-align:right;font-family:"Courier New",monospace;font-weight:700;color:#065f46;white-space:nowrap;}\n.xtbl tbody td.td-cum{text-align:right;font-family:"Courier New",monospace;font-weight:700;color:#7c3aed;white-space:nowrap;}\n.xtbl tbody td.td-dis{text-align:right;font-family:"Courier New",monospace;font-weight:800;white-space:nowrap;}\n\n/* Badges */\n.dir-b{display:inline-block;padding:2px 7px;border-radius:4px;font-size:10px;font-weight:800;background:#0e7490;color:#fff;}\n.nat-c{background:#d1fae5;color:#065f46;padding:2px 5px;border-radius:3px;font-size:9px;font-weight:700;}\n.nat-k{background:#fef9c3;color:#92400e;padding:2px 5px;border-radius:3px;font-size:9px;font-weight:700;}\n.nat-s{background:#e0e7ff;color:#3730a3;padding:2px 5px;border-radius:3px;font-size:9px;font-weight:700;}\n.sb-ok{background:#d1fae5;color:#065f46;padding:2px 8px;border-radius:4px;font-size:10px;font-weight:700;border:1px solid #6ee7b7;}\n.sb-dep{background:#fee2e2;color:#991b1b;padding:2px 8px;border-radius:4px;font-size:10px;font-weight:700;border:1px solid #fca5a5;}\n.sb-pen{background:#fef9c3;color:#92400e;padding:2px 8px;border-radius:4px;font-size:9px;font-weight:700;}\n\n/* Inline new row */\n.new-row td{background:#fffbeb !important;border:2px solid #f59e0b !important;}\n.new-row td input,.new-row td select{width:100%;padding:3px 5px;border:1px solid #d1d5db;border-radius:4px;font-size:11px;font-family:inherit;}\n.new-row td input:focus,.new-row td select:focus{outline:none;border-color:#1f4d8f;}\n.new-row td.td-amt input{text-align:right;}\n\n/* Table footer */\n.tfoot{display:flex;justify-content:space-between;align-items:center;padding:6px 10px;background:linear-gradient(90deg,#1e3a8a,#1f4d8f);color:#fff;font-size:11px;font-weight:700;border-radius:0 0 8px 8px;}\n\n/* Budget lines table */\n.bl-tbl{width:100%;border-collapse:collapse;font-size:12px;}\n.bl-tbl thead th{background:linear-gradient(180deg,#1e3a8a,#1f4d8f);color:#fff;padding:8px 8px;font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:.04em;white-space:nowrap;border:1px solid rgba(255,255,255,.15);}\n.bl-tbl thead th.tr{text-align:right;}\n.bl-tbl tbody td{padding:7px 8px;border:1px solid #e5e7eb;}\n.bl-tbl tbody tr.bl-ok td{background:#f0fdf4;}\n.bl-tbl tbody tr.bl-dep td{background:#fee2e2;}\n.bl-tbl tbody tr:hover td{background:#eff6ff;}\n.bl-tbl td.num{text-align:right;font-family:"Courier New",monospace;font-weight:700;}\n\n/* Users table */\n.u-tbl{width:100%;border-collapse:collapse;font-size:12px;}\n.u-tbl thead th{background:#1f4d8f;color:#fff;padding:8px 8px;font-size:10px;font-weight:700;text-transform:uppercase;white-space:nowrap;}\n.u-tbl tbody td{padding:7px 8px;border-bottom:1px solid #f1f5f9;}\n.u-tbl tbody tr:hover td{background:#f8fafc;}\n\n/* Reports table */\n.r-tbl{width:100%;border-collapse:collapse;font-size:12px;}\n.r-tbl thead th{background:linear-gradient(135deg,#065f46,#16a34a);color:#fff;padding:8px 8px;font-size:9px;font-weight:800;text-transform:uppercase;white-space:nowrap;}\n.r-tbl thead th.tr{text-align:right;}\n.r-tbl tbody td{padding:7px 8px;border-bottom:1px solid #f1f5f9;}\n.r-tbl tbody tr:hover td{background:#f0fdf4;}\n.r-tbl td.num{text-align:right;font-family:"Courier New",monospace;font-weight:700;}\n</style>\n</head>\n<body>\n\n<header>\n  <!-- CAMTEL Logo SVG -->\n  <svg class="hlogo-svg" viewBox="0 0 100 100" fill="none">\n    <circle cx="50" cy="50" r="48" fill="rgba(255,255,255,0.12)"/>\n    <path d="M72 28 L54 28 C34 28 20 37 20 50 C20 63 34 72 54 72 L72 72 L72 59 L56 59 C45 59 37 55 37 50 C37 45 45 41 56 41 L72 41 Z" fill="#00b0e8"/>\n    <path d="M72 28 L91 50 L72 72 Z" fill="#00b0e8" opacity="0.75"/>\n    <text x="50" y="92" text-anchor="middle" fill="white" font-size="10" font-family="Arial" font-weight="bold" opacity="0.8">camtel</text>\n  </svg>\n  <div class="hbrand">\n    <h1>CAMTEL – Gestion Budgétaire</h1>\n    <p>SAAF / DCF / Contrôle Budgétaire</p>\n  </div>\n  <nav>\n    <button class="active" id="nav-dashboard" onclick="showTab(\'dashboard\')">📊 Dashboard</button>\n    <button id="nav-transactions" onclick="showTab(\'transactions\')">📋 Transactions</button>\n    <button id="nav-budgetlines" onclick="showTab(\'budgetlines\')">📂 Lignes Budget</button>\n    <button id="nav-reports" onclick="showTab(\'reports\')">📈 Rapports</button>\n    <button id="nav-import" onclick="showTab(\'import\')">⬆ Import/Export</button>\n    <button id="nav-users" onclick="showTab(\'users\')" style="display:none">👥 Utilisateurs</button>\n  </nav>\n  <div class="upill">\n    <span id="uname">—</span>\n    <span id="urole" style="background:rgba(0,176,232,.35);padding:2px 7px;border-radius:10px;font-size:9px;font-weight:800;">—</span>\n  </div>\n  <button class="btn-logout" onclick="logout()">Déconnexion</button>\n</header>\n\n<div class="wrap">\n  <div class="gbar">\n    <label>ANNÉE :</label>\n    <select id="g-year" style="font-weight:800;" onchange="onYearChange()"></select>\n    <label>DIRECTION :</label>\n    <select id="g-dir" style="min-width:110px;" onchange="onDirChange()"></select>\n    <span id="last-upd" style="font-size:10px;color:var(--muted);margin-left:auto"></span>\n    <button class="btn bs bsm" onclick="refreshAll()">↻ Actualiser</button>\n  </div>\n\n  <div class="krow">\n    <div class="kpi kb"><label>Budget CP Total</label><div class="val" id="kpi-bud">—</div><div class="sub" id="kpi-bud-s"></div></div>\n    <div class="kpi kr"><label>Cumul Engagé</label><div class="val" id="kpi-eng">—</div><div class="sub" id="kpi-eng-s"></div></div>\n    <div class="kpi ky"><label>En Attente</label><div class="val" id="kpi-pend">—</div><div class="sub" id="kpi-pend-s"></div></div>\n    <div class="kpi kg"><label>Disponible Après</label><div class="val" id="kpi-dispo">—</div><div class="sub" id="kpi-dispo-s"></div></div>\n  </div>\n  <div id="alerts-row"></div>\n\n  <!-- DASHBOARD -->\n  <div id="tab-dashboard" class="tab-content active">\n    <div class="g3" style="margin-bottom:10px">\n      <div class="card"><div class="ch"><h2>Engagements par direction</h2></div><div class="cb"><canvas id="ch-dir" height="190"></canvas></div></div>\n      <div class="card"><div class="ch"><h2>Tendance mensuelle</h2></div><div class="cb"><canvas id="ch-mo" height="190"></canvas></div></div>\n    </div>\n    <div class="card"><div class="ch"><h2>Taux d\'utilisation — toutes directions</h2></div><div class="cb" id="dir-prog"></div></div>\n    <div class="card" style="margin-top:10px">\n      <div class="ch"><h2>Dernières transactions</h2></div>\n      <div style="overflow-x:auto">\n        <table class="xtbl" style="min-width:900px">\n          <thead><tr>\n            <th class="th-chk"></th><th class="th-date">Date</th><th class="th-code">Code/Réf</th>\n            <th class="th-dir">Direction</th><th class="th-imp">Imputation</th><th class="th-nat">Nature</th>\n            <th class="th-int">Intitulé</th><th class="th-amt">Montant</th>\n            <th class="th-bcp">Budget CP</th><th class="th-cum">Cumul Engagé</th>\n            <th class="th-dis">Disponible Après</th><th class="th-sta">Statut Budget</th><th class="th-act"></th>\n          </tr></thead>\n          <tbody id="rec-rows"></tbody>\n        </table>\n      </div>\n    </div>\n  </div>\n\n  <!-- TRANSACTIONS -->\n  <div id="tab-transactions" class="tab-content">\n    <div class="tbar">\n      <select id="tx-f-dir" onchange="loadTx()" style="min-width:100px"><option value="">Toutes directions</option></select>\n      <select id="tx-f-status" onchange="loadTx()">\n        <option value="">Tous statuts</option><option value="validated">Validé</option><option value="pending">Brouillon</option>\n      </select>\n      <select id="tx-f-statbud" onchange="loadTx()">\n        <option value="">Tous statuts budget</option><option value="NORMAL">Normal (OK)</option><option value="DEPASSEMENT">Dépassement</option>\n      </select>\n      <input id="tx-q" placeholder="🔍 Réf, intitulé, imputation..."/>\n      <div style="margin-left:auto;display:flex;gap:5px;flex-wrap:wrap;">\n        <button class="btn bp bsm viewer-hide" onclick="addNewRow()">➕ Nouvelle ligne</button>\n        <button class="btn bg2 bsm" id="print-sel-btn" onclick="printSelected()" style="display:none">🖨 Imprimer sélection</button>\n        <button class="btn bs bsm" onclick="exportTx()">⬇ CSV</button>\n      </div>\n    </div>\n    <div id="tx-sel-info" style="padding:5px 10px;background:#dbeafe;font-size:11px;color:#1e40af;border:1px solid #93c5fd;border-top:none;display:none">\n      <strong id="tx-sel-count">0</strong> sélectionnée(s) — 🖨 pour imprimer (2 max par page A4)\n    </div>\n    <div class="excel-wrap">\n      <table class="xtbl" id="tx-table">\n        <thead><tr>\n          <th class="th-chk"><input type="checkbox" id="sel-all" onchange="toggleSelAll(this)" style="accent-color:#fff"/></th>\n          <th class="th-date">DATE DE RÉCEPTION</th>\n          <th class="th-code">CODE / RÉF</th>\n          <th class="th-dir">DIRECTION</th>\n          <th class="th-imp">IMPUTATION COMPTABLE</th>\n          <th class="th-nat">NATURE</th>\n          <th class="th-int">INTITULÉ DE LA COMMANDE</th>\n          <th class="th-amt">MONTANT</th>\n          <th class="th-bcp">BUDGET CP</th>\n          <th class="th-cum">CUMUL ENGAGÉ</th>\n          <th class="th-dis">DISPONIBLE APRÈS</th>\n          <th class="th-sta">STATUT BUDGET</th>\n          <th class="th-act">ACTIONS</th>\n        </tr></thead>\n        <tbody id="tx-rows"></tbody>\n      </table>\n    </div>\n    <div id="tx-empty" style="padding:28px;text-align:center;color:var(--muted);display:none">Aucune transaction. Cliquez <strong>➕ Nouvelle ligne</strong> pour ajouter.</div>\n    <div class="tfoot" id="tx-foot" style="display:none">\n      <span id="tx-foot-count">0 transaction(s)</span>\n      <span id="tx-foot-total" style="font-family:\'Courier New\',monospace;font-size:13px"></span>\n    </div>\n  </div>\n\n  <!-- BUDGET LINES -->\n  <div id="tab-budgetlines" class="tab-content">\n    <div class="tbar">\n      <select id="bl-f-dir" onchange="loadBL()" style="min-width:100px"><option value="">Toutes directions</option></select>\n      <input id="bl-q" placeholder="🔍 Imputation, libellé..."/>\n      <div style="margin-left:auto;display:flex;gap:5px">\n        <button class="btn bp bsm admin-only" onclick="openBLModal()">+ Nouvelle ligne</button>\n        <button class="btn bs bsm" onclick="window.open(\'/api/export/template-budget-lines\',\'_blank\')">⬇ Template</button>\n      </div>\n    </div>\n    <div style="overflow-x:auto;border:2px solid #1e3a8a;border-top:none;border-radius:0 0 8px 8px">\n      <table class="bl-tbl">\n        <thead><tr>\n          <th>Direction</th><th>Imputation comptable</th><th>Libellé</th><th>Nature</th>\n          <th class="tr">Budget CP</th><th class="tr">Cumul Engagé</th><th class="tr">Disponible Après</th>\n          <th>Taux</th><th>Statut</th><th class="admin-only"></th>\n        </tr></thead>\n        <tbody id="bl-rows"></tbody>\n      </table>\n    </div>\n    <div id="bl-empty" style="padding:28px;text-align:center;color:var(--muted);display:none">Aucune ligne budgétaire. Importez via ⬆ Import/Export.</div>\n  </div>\n\n  <!-- REPORTS -->\n  <div id="tab-reports" class="tab-content">\n    <div class="g2" style="margin-bottom:10px">\n      <div class="card">\n        <div class="ch"><h2>Rapport mensuel</h2></div>\n        <div class="cb">\n          <div class="fr fc2" style="margin-bottom:10px">\n            <div class="fld"><label>Année</label><select id="rp-year"></select></div>\n            <div class="fld"><label>Mois</label><select id="rp-month">\n              <option value="1">Janvier</option><option value="2">Février</option><option value="3">Mars</option>\n              <option value="4">Avril</option><option value="5">Mai</option><option value="6">Juin</option>\n              <option value="7">Juillet</option><option value="8">Août</option><option value="9">Septembre</option>\n              <option value="10">Octobre</option><option value="11">Novembre</option><option value="12">Décembre</option>\n            </select></div>\n          </div>\n          <div style="display:flex;gap:7px"><button class="btn bp" onclick="downloadReport()">⬇ CSV</button><button class="btn bs" onclick="loadReports()">📊 Afficher</button></div>\n          <div class="alrt alrt-b" style="margin-top:10px">Rapport mensuel pour Directeur DCF et Sous-Directeur Budget.</div>\n        </div>\n      </div>\n      <div class="card"><div class="ch"><h2>Résumé annuel</h2></div><div class="cb" id="rp-summary"><div style="padding:16px;text-align:center;color:var(--muted)">Cliquez Afficher →</div></div></div>\n    </div>\n    <div class="card">\n      <div class="ch"><h2>Suivi par direction — <span id="rp-year-label">—</span></h2></div>\n      <div style="overflow-x:auto"><table class="r-tbl">\n        <thead><tr><th>Direction</th><th class="tr">Budget CP</th><th class="tr">Cumul Engagé</th><th class="tr">Disponible</th><th>Taux %</th><th>Statut</th></tr></thead>\n        <tbody id="rp-dir-rows"></tbody>\n      </table></div>\n    </div>\n  </div>\n\n  <!-- IMPORT/EXPORT -->\n  <div id="tab-import" class="tab-content">\n    <div class="g2" style="margin-bottom:10px">\n      <div class="card">\n        <div class="ch" style="background:linear-gradient(90deg,#fffbeb,#fef9c3)"><h2>⬆ Importer transactions (CSV)</h2></div>\n        <div class="cb">\n          <div class="alrt alrt-b" style="margin-bottom:9px">Colonnes: DATE DE RECEPTION · CODE /REF NUMBER · DIRECTION · IMPUTATION COMPTABLE · NATURE · INTITULE DE LA COMMANDE · MONTANT</div>\n          <div class="fld" style="margin-bottom:8px"><label>Année *</label><input type="number" id="imp-tx-year" value="2025"/></div>\n          <div class="scan-area" onclick="document.getElementById(\'imp-tx-file\').click()" id="imp-tx-area">\n            <div style="font-size:24px;margin-bottom:5px">📂</div>\n            <div style="font-size:12px;font-weight:700">Cliquer pour choisir fichier CSV</div>\n            <div id="imp-tx-fname" style="margin-top:5px;font-size:11px;color:#1f4d8f;font-weight:700"></div>\n          </div>\n          <input type="file" id="imp-tx-file" accept=".csv,.txt" style="display:none" onchange="onFileSel(this,\'imp-tx-fname\',\'imp-tx-area\')"/>\n          <div style="margin-top:8px;display:flex;gap:6px;flex-wrap:wrap">\n            <button class="btn bp" onclick="importTx()">⬆ Importer</button>\n            <button class="btn bs" onclick="window.open(\'/api/export/template-transactions\',\'_blank\')">⬇ Template</button>\n          </div>\n          <div id="imp-tx-result" style="margin-top:7px"></div>\n        </div>\n      </div>\n      <div class="card">\n        <div class="ch" style="background:linear-gradient(90deg,#f0fdf4,#dcfce7)"><h2>⬆ Importer lignes budgétaires (CSV)</h2></div>\n        <div class="cb">\n          <div class="alrt alrt-b" style="margin-bottom:9px">Colonnes: YEAR · DIRECTION · IMPUTATION COMPTABLE · LIBELLE · NATURE · BUDGET CP (FCFA)<br>Pour budget 2026, 2027...</div>\n          <div class="scan-area" onclick="document.getElementById(\'imp-bl-file\').click()" id="imp-bl-area">\n            <div style="font-size:24px;margin-bottom:5px">📊</div>\n            <div style="font-size:12px;font-weight:700">Cliquer pour choisir fichier CSV budget</div>\n            <div id="imp-bl-fname" style="margin-top:5px;font-size:11px;color:#1f4d8f;font-weight:700"></div>\n          </div>\n          <input type="file" id="imp-bl-file" accept=".csv,.txt" style="display:none" onchange="onFileSel(this,\'imp-bl-fname\',\'imp-bl-area\')"/>\n          <div style="margin-top:8px;display:flex;gap:6px;flex-wrap:wrap">\n            <button class="btn bp admin-only" onclick="importBL()">⬆ Importer lignes budget</button>\n            <button class="btn bs" onclick="window.open(\'/api/export/template-budget-lines\',\'_blank\')">⬇ Template</button>\n          </div>\n          <div id="imp-bl-result" style="margin-top:7px"></div>\n        </div>\n      </div>\n    </div>\n    <div class="card">\n      <div class="ch"><h2>⬇ Exports</h2></div>\n      <div class="cb" style="display:flex;gap:8px;flex-wrap:wrap">\n        <button class="btn bs" onclick="window.open(`/api/export/transactions?year=${S.year}&direction=${S.dir}`,\'_blank\')">⬇ Transactions CSV</button>\n        <button class="btn bs" onclick="window.open(`/api/report/monthly?year=${S.year}&month=${new Date().getMonth()+1}`,\'_blank\')">⬇ Rapport mensuel</button>\n        <button class="btn bs" onclick="window.open(\'/api/export/template-transactions\',\'_blank\')">⬇ Template transactions</button>\n        <button class="btn bs" onclick="window.open(\'/api/export/template-budget-lines\',\'_blank\')">⬇ Template budget</button>\n      </div>\n    </div>\n  </div>\n\n  <!-- USERS -->\n  <div id="tab-users" class="tab-content">\n    <div class="card">\n      <div class="ch"><h2>👥 Gestion des utilisateurs</h2><button class="btn bp bsm" onclick="openUserModal()">+ Ajouter</button></div>\n      <div style="overflow-x:auto"><table class="u-tbl">\n        <thead><tr><th>Nom complet</th><th>Identifiant</th><th>Email</th><th>Rôle</th><th>Directions autorisées</th><th>Créé le</th><th></th></tr></thead>\n        <tbody id="usr-rows"></tbody>\n      </table></div>\n    </div>\n  </div>\n</div>\n\n<!-- BUDGET LINE MODAL -->\n<div class="mbg" id="bl-modal">\n  <div class="modal" style="max-width:580px">\n    <div class="mh"><h3>Nouvelle ligne budgétaire</h3><button class="btn bs bxs" onclick="closeModal(\'bl-modal\')">✕</button></div>\n    <div class="mb">\n      <div class="fr fc2">\n        <div class="fld"><label>Année *</label><input type="number" id="bl-yr" value="2025"/></div>\n        <div class="fld"><label>Direction *</label><select id="bl-dir"><option value="">—</option></select></div>\n      </div>\n      <div class="fld" style="margin-top:7px"><label>Imputation comptable *</label><input id="bl-imp" placeholder="SP4/DG/AD0025/VD0007/T00127/63840100"/></div>\n      <div class="fld" style="margin-top:7px"><label>Libellé</label><input id="bl-lib" placeholder="FRAIS DE MISSION A L\'EXTERIEUR"/></div>\n      <div class="fr fc2" style="margin-top:7px">\n        <div class="fld"><label>Nature</label><select id="bl-nat"><option>DEPENSE COURANTE</option><option>DEPENSE DE CAPITAL</option></select></div>\n        <div class="fld"><label>Budget CP (FCFA) *</label><input type="number" id="bl-bcp" placeholder="0"/></div>\n      </div>\n    </div>\n    <div class="mf"><button class="btn bs" onclick="closeModal(\'bl-modal\')">Annuler</button><button class="btn bp" onclick="saveBL()">💾 Enregistrer</button></div>\n  </div>\n</div>\n\n<!-- USER MODAL -->\n<div class="mbg" id="usr-modal">\n  <div class="modal" style="max-width:620px">\n    <div class="mh"><h3 id="usr-modal-title">Ajouter un utilisateur</h3><button class="btn bs bxs" onclick="closeModal(\'usr-modal\')">✕</button></div>\n    <div class="mb">\n      <div class="fr fc2">\n        <div class="fld"><label>Nom complet *</label><input id="u-nm" placeholder="Jean Dupont"/></div>\n        <div class="fld"><label>Identifiant *</label><input id="u-usr" placeholder="jdupont"/></div>\n      </div>\n      <div class="fr fc2" style="margin-top:7px">\n        <div class="fld"><label>Mot de passe</label><input type="password" id="u-pw" placeholder="Vide = ne pas changer"/></div>\n        <div class="fld"><label>Email</label><input id="u-em" placeholder="jean@camtel.cm"/></div>\n      </div>\n      <div class="fld" style="margin-top:7px"><label>Rôle *</label>\n        <select id="u-rl" onchange="onRoleChange()">\n          <option value="agent">Agent — saisie sur directions assignées</option>\n          <option value="viewer">Observateur — lecture seule</option>\n          <option value="dcf_sub">Sous-Directeur Budget — accès total</option>\n          <option value="dcf_dir">Directeur DCF — accès total</option>\n          <option value="admin">Administrateur — accès complet</option>\n        </select>\n      </div>\n      <div id="u-dirs-block" style="margin-top:11px">\n        <div style="font-size:10px;font-weight:700;color:var(--muted);margin-bottom:5px;text-transform:uppercase">DIRECTIONS AUTORISÉES</div>\n        <div style="display:flex;gap:5px;flex-wrap:wrap;margin-bottom:6px">\n          <button class="btn bs bsm" onclick="selAllDirs(true)">Tout sél.</button>\n          <button class="btn bs bsm" onclick="selAllDirs(false)">Tout désél.</button>\n        </div>\n        <div id="u-dirs-list" style="max-height:180px;overflow-y:auto;border:1px solid var(--bdr);border-radius:6px;padding:7px;display:grid;grid-template-columns:repeat(5,1fr);gap:2px"></div>\n      </div>\n    </div>\n    <div class="mf"><button class="btn bs" onclick="closeModal(\'usr-modal\')">Annuler</button><button class="btn bp" onclick="saveUser()">💾 Enregistrer</button></div>\n  </div>\n</div>\n\n<div id="toast" class="toast"></div>\n\n<script>\nconst ALL_DIRS=["BUM","BUT","BUF","DG","DRH","DICOM","DIRCAB","DCRA","DAMR","DC","DNQ","DAS","DFA","DAJR","DAP","DR","DS","DSPI","DSIR","DOP","DT","DCF","DCRM","DRLM","RRSM","RREM","RROM","RRNOM","RRSOM","RRAM","RRNM","RRENM","DCRF","DRLF","RRSF","RREF","RROF","RRNOF","RRSOF","RRAF","RRNF","RRENF","DCRT","DRLT","RRNOT","RRENT"];\nconst NATURES=["DEPENSE COURANTE","DEPENSE DE CAPITAL","PRESTATION DE SERVICES","SERVICES ET FRAIS DIVERS","TRAVAUX","FOURNITURES","IMMOBILISATION"];\n\nlet S={user:null,year:new Date().getFullYear(),dir:"",cDir:null,cMo:null,editUserId:null,selectedTxIds:new Set()};\nlet BL_CACHE={};\n\n// Format with space thousands: 27 311 774 252 FCFA\nconst fmtFCFA=n=>{\n  n=Math.round(Number(n||0));\n  if(isNaN(n))return "0 FCFA";\n  const s=Math.abs(n).toString().replace(/\\B(?=(\\d{3})+(?!\\d))/g,"\\u00a0");\n  return (n<0?"-":"")+s+"\\u00a0FCFA";\n};\nconst fmts=n=>{n=Number(n||0);if(n>=1e9)return (n/1e9).toFixed(1)+" Md";if(n>=1e6)return (n/1e6).toFixed(1)+" M";if(n>=1e3)return Math.round(n/1e3)+" K";return Math.round(n).toLocaleString("fr-FR");};\nconst fmtDisp=n=>`<span style="color:${n>=0?"#16a34a":"#dc2626"};font-weight:800">${fmtFCFA(n)}</span>`;\n\nlet _dt={};\nconst debounce=(f,ms)=>{clearTimeout(_dt[f]);_dt[f]=setTimeout(f,ms);};\nconst toast=(msg,ok=true)=>{const t=document.getElementById("toast");t.textContent=msg;t.style.background=ok?"#16a34a":"#dc2626";t.style.display="block";setTimeout(()=>t.style.display="none",3500);};\nconst api=async(path,opts)=>{const r=await fetch(path,{credentials:"include",...(opts||{})});if(r.status===401){window.location="/login";return null;}return r;};\nconst openModal=id=>document.getElementById(id).classList.add("open");\nconst closeModal=id=>document.getElementById(id).classList.remove("open");\nconst isFullAccess=()=>S.user&&["admin","dcf_dir","dcf_sub"].includes(S.user.role);\nconst myDirs=()=>isFullAccess()?ALL_DIRS:(()=>{try{return JSON.parse(S.user.dirs||"[]")}catch{return []}})();\n\nfunction initYears(){\n  const n=new Date().getFullYear();\n  ["g-year","rp-year"].forEach(id=>{\n    const s=document.getElementById(id);if(!s)return;\n    for(let y=n-3;y<=n+2;y++){const o=document.createElement("option");o.value=y;o.textContent=y;s.appendChild(o);}\n    s.value=n;\n  });\n  S.year=n;\n}\nfunction populateDirSelects(dirs){\n  ["g-dir","tx-f-dir","bl-f-dir"].forEach(id=>{\n    const s=document.getElementById(id);if(!s)return;\n    const cur=s.value;\n    s.innerHTML="<option value=\\"\\">Toutes directions</option>";\n    dirs.forEach(d=>{const o=document.createElement("option");o.value=d;o.textContent=d;s.appendChild(o);});\n    if(cur&&dirs.includes(cur))s.value=cur;\n  });\n  const blDir=document.getElementById("bl-dir");\n  if(blDir){blDir.innerHTML="<option value=\\"\\">—</option>";ALL_DIRS.forEach(d=>{const o=document.createElement("option");o.value=d;o.textContent=d;blDir.appendChild(o);});}\n}\nfunction onYearChange(){S.year=Number(document.getElementById("g-year").value);BL_CACHE={};refreshAll();}\nfunction onDirChange(){S.dir=document.getElementById("g-dir").value;refreshAll();}\nfunction showTab(n){\n  document.querySelectorAll(".tab-content").forEach(e=>e.classList.remove("active"));\n  document.querySelectorAll("nav button").forEach(b=>b.classList.remove("active"));\n  document.getElementById("tab-"+n).classList.add("active");\n  document.getElementById("nav-"+n)?.classList.add("active");\n  ({dashboard:loadDash,transactions:loadTx,budgetlines:loadBL,reports:loadReports,users:loadUsers})[n]?.();\n}\nfunction refreshAll(){\n  loadKPIs();\n  const a=document.querySelector(".tab-content.active")?.id?.replace("tab-","");\n  ({dashboard:loadDash,transactions:loadTx,budgetlines:loadBL,reports:loadReports})[a]?.();\n  document.getElementById("last-upd").textContent="Actualisé: "+new Date().toLocaleTimeString("fr-FR");\n}\n\nasync function loadKPIs(){\n  const r=await api(`/api/dashboard?year=${S.year}`);if(!r)return;\n  const d=await r.json();\n  document.getElementById("kpi-bud").textContent=fmts(d.total_budget);\n  document.getElementById("kpi-eng").textContent=fmts(d.total_engage);\n  document.getElementById("kpi-eng-s").textContent=d.tx_count+" transaction(s) validée(s)";\n  document.getElementById("kpi-pend").textContent=fmts(d.total_pending);\n  document.getElementById("kpi-pend-s").textContent=d.pending_count+" brouillon(s)";\n  document.getElementById("kpi-dispo").textContent=fmts(d.total_dispo);\n  const pct=d.total_budget?Math.round(d.total_engage/d.total_budget*100):0;\n  document.getElementById("kpi-dispo-s").textContent=pct+"% du budget engagé";\n  const ar=document.getElementById("alerts-row");ar.innerHTML="";\n  (d.overdrawn||[]).forEach(a=>{ar.innerHTML+=`<div class="alrt alrt-r">🚨 <strong>${a.direction}</strong> — dépassement de <strong>${fmtFCFA(a.montant)}</strong></div>`;});\n}\n\nasync function loadDash(){\n  await loadKPIs();\n  const r=await api(`/api/dashboard?year=${S.year}`);if(!r)return;\n  const d=await r.json();\n  const dirs=Object.keys(d.by_dir).sort((a,b)=>d.by_dir[b]-d.by_dir[a]).slice(0,12);\n  const cols=["#00b0e8","#16a34a","#d97706","#dc2626","#7c3aed","#0891b2","#db2777","#65a30d","#ea580c","#0d9488","#9333ea","#0284c7"];\n  if(S.cDir)S.cDir.destroy();\n  S.cDir=new Chart(document.getElementById("ch-dir"),{type:"bar",data:{labels:dirs,datasets:[{data:dirs.map(x=>d.by_dir[x]),backgroundColor:cols,borderRadius:5}]},options:{responsive:true,plugins:{legend:{display:false}},scales:{y:{ticks:{callback:v=>fmts(v)}}}}});\n  const months=["Jan","Fév","Mar","Avr","Mai","Jun","Jul","Aoû","Sep","Oct","Nov","Déc"];\n  if(S.cMo)S.cMo.destroy();\n  S.cMo=new Chart(document.getElementById("ch-mo"),{type:"line",data:{labels:months,datasets:[{data:d.by_month,borderColor:"#00b0e8",backgroundColor:"rgba(0,176,232,.12)",fill:true,tension:.4,pointRadius:4}]},options:{responsive:true,plugins:{legend:{display:false}},scales:{y:{ticks:{callback:v=>fmts(v)}}}}});\n  const dp=document.getElementById("dir-prog");const bld=d.bl_by_dir||{};const dk=Object.keys(bld).sort();\n  dp.innerHTML=dk.length?`<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:9px">${dk.map(dir=>{const bd=bld[dir];const pct=bd.budget_cp?Math.min(100,Math.round(bd.engage/bd.budget_cp*100)):0;const col=pct>90?"#dc2626":pct>70?"#d97706":"#16a34a";const av=bd.budget_cp-bd.engage;return `<div style="padding:9px;border:1px solid #e5e7eb;border-radius:8px;border-left:4px solid ${col}"><div style="display:flex;justify-content:space-between;font-size:12px;font-weight:800"><span>${dir}</span><span style="color:${col}">${pct}%</span></div><div style="font-size:10px;color:var(--muted);margin:2px 0">CP: ${fmtFCFA(bd.budget_cp)}</div><div style="font-size:11px;font-weight:700;color:${av>=0?"#16a34a":"#dc2626"}">${av>=0?"Dispo":"⚠ Dépass"}: ${fmtFCFA(Math.abs(av))}</div><div class="prg"><div class="prf" style="width:${pct}%;background:${col}"></div></div></div>`;}).join("")}</div>`:"<div style=\\"padding:16px;text-align:center;color:var(--muted)\\">Aucune ligne budgétaire. Importez d\\\'abord via ⬆ Import/Export.</div>";\n  const rr=document.getElementById("rec-rows");rr.innerHTML="";\n  (d.recent||[]).forEach(t=>rr.innerHTML+=buildRow(t));\n}\n\nfunction natBadge(n){n=n||"";if(n.includes("CAPITAL"))return`<span class="nat-k">CAPITAL</span>`;if(n.includes("SERVICES"))return`<span class="nat-s">SERVICES</span>`;return`<span class="nat-c">COURANTE</span>`;}\n\nfunction buildRow(t){\n  const dep=t.statut_budget==="DEPASSEMENT";\n  const pend=t.status==="pending";\n  const rc=dep?"row-dep":pend?"row-pend":"row-ok";\n  const sel=S.selectedTxIds.has(t.id)?"checked":"";\n  const sb=dep?`<span class="sb-dep">⚠ DÉPASSEMENT</span>`:`<span class="sb-ok">✓ OK</span>`;\n  const stlbl=t.status==="validated"?`<span style="font-size:10px;color:#16a34a;font-weight:700">✓</span>`:`<span style="font-size:10px;color:#d97706;font-weight:700">◷</span>`;\n  return `<tr class="${rc}" id="tx-tr-${t.id}">\n    <td class="tc"><input type="checkbox" class="tx-chk" value="${t.id}" ${sel} onchange="onTxSel(this)"/></td>\n    <td class="td-date">${t.date_reception||"—"}</td>\n    <td class="td-code" title="${t.code_ref}">${t.code_ref||"—"}</td>\n    <td class="tc"><span class="dir-b">${t.direction}</span></td>\n    <td class="td-imp" title="${t.imputation}">${t.imputation||"—"}</td>\n    <td>${natBadge(t.nature)}</td>\n    <td class="td-int" title="${t.intitule}">${t.intitule||"—"}</td>\n    <td class="td-amt">${fmtFCFA(t.montant)}</td>\n    <td class="td-bcp">${t.budget_cp_val?fmtFCFA(t.budget_cp_val):"—"}</td>\n    <td class="td-cum">${t.cumul_engage?fmtFCFA(t.cumul_engage):"—"}</td>\n    <td class="td-dis">${fmtDisp(t.disponible_val!==undefined?t.disponible_val:(t.budget_cp_val?t.budget_cp_val-t.cumul_engage:0))}</td>\n    <td class="tc">${sb}</td>\n    <td style="white-space:nowrap">${stlbl} <button class="btn bs bxs" onclick="openFiche(${t.id})">🖨</button>${isFullAccess()?` <button class="btn bd bxs" onclick="delTx(${t.id})">🗑</button>`:""}</td>\n  </tr>`;\n}\n\nasync function loadTx(){\n  const dir=document.getElementById("tx-f-dir").value;\n  const st=document.getElementById("tx-f-status").value;\n  const sb=document.getElementById("tx-f-statbud").value;\n  const q=document.getElementById("tx-q").value;\n  const r=await api(`/api/transactions?year=${S.year}&direction=${encodeURIComponent(dir)}&status=${st}&q=${encodeURIComponent(q)}`);if(!r)return;\n  let data=await r.json();\n  if(sb)data=data.filter(t=>t.statut_budget===sb);\n  const tb=document.getElementById("tx-rows");tb.innerHTML="";\n  document.getElementById("tx-empty").style.display=data.length?"none":"block";\n  document.getElementById("tx-foot").style.display=data.length?"flex":"none";\n  let tot=0;data.forEach(t=>{tot+=t.montant;tb.innerHTML+=buildRow(t);});\n  document.getElementById("tx-foot-count").textContent=data.length+" transaction(s)";\n  document.getElementById("tx-foot-total").textContent="Total: "+fmtFCFA(tot);\n  updateSelUI();\n}\n\nasync function addNewRow(){\n  document.getElementById("new-tx-row")?.remove();\n  document.getElementById("tx-empty").style.display="none";\n  const dirs=myDirs();\n  const dirOpts=dirs.map(d=>`<option value="${d}">${d}</option>`).join("");\n  const natOpts=NATURES.map(n=>`<option>${n}</option>`).join("");\n  const today=new Date().toISOString().slice(0,10);\n  const row=document.createElement("tr");\n  row.id="new-tx-row";row.className="new-row";\n  row.innerHTML=`\n    <td><button class="btn bd bxs" onclick="cancelNewRow()">✕</button></td>\n    <td><input type="date" id="nr-date" value="${today}" style="min-width:130px"/></td>\n    <td style="font-size:9px;color:#666">Auto</td>\n    <td><select id="nr-dir" onchange="onNrDirChange(this)" style="min-width:85px"><option value="">—</option>${dirOpts}</select></td>\n    <td><select id="nr-imp" onchange="onNrImpChange(this)" style="min-width:220px"><option value="">— Choisir direction —</option></select></td>\n    <td><select id="nr-nat" style="min-width:110px">${natOpts}</select></td>\n    <td><input id="nr-int" placeholder="Intitulé de la commande..." style="min-width:160px"/></td>\n    <td class="td-amt"><input type="number" id="nr-amt" placeholder="0" style="min-width:100px;text-align:right" oninput="onNrAmtChange()"/></td>\n    <td id="nr-bcp" class="td-bcp">—</td>\n    <td id="nr-cum" class="td-cum">—</td>\n    <td id="nr-dis">—</td>\n    <td><select id="nr-stat"><option value="validated">✓ Validé</option><option value="pending">◷ Brouillon</option></select></td>\n    <td><button class="btn bp bxs" onclick="saveNewRow()" style="white-space:nowrap">💾 Enregistrer</button></td>`;\n  const tb=document.getElementById("tx-rows");tb.insertBefore(row,tb.firstChild);\n  if(S.dir&&dirs.includes(S.dir)){document.getElementById("nr-dir").value=S.dir;await onNrDirChange(document.getElementById("nr-dir"));}\n  document.getElementById("nr-date").focus();\n}\n\nasync function onNrDirChange(sel){\n  const dir=sel.value;const imp=document.getElementById("nr-imp");\n  imp.innerHTML="<option value=\\"\\">— Chargement... —</option>";\n  if(!dir){imp.innerHTML="<option value=\\"\\">— Choisir direction —</option>";return;}\n  const r=await api(`/api/budget-lines?year=${S.year}&direction=${dir}`);if(!r)return;\n  const bls=await r.json();\n  bls.forEach(b=>{BL_CACHE[`${b.direction}|${b.imputation}|${b.year}`]=b;});\n  imp.innerHTML="<option value=\\"\\">— Sélectionner ligne budgétaire —</option>";\n  if(!bls.length){imp.innerHTML="<option value=\\"\\">Aucune ligne pour cette direction</option>";return;}\n  bls.forEach(b=>{\n    const o=document.createElement("option");o.value=b.imputation;\n    const ok=b.disponible>=0;\n    o.textContent=`${b.imputation.split("/").slice(-1)[0]} | ${b.libelle||""} | ${ok?"✅":"⚠"} ${fmtFCFA(b.disponible)}`;\n    o.dataset.bcp=b.budget_cp;o.dataset.cum=b.cumul_engage;o.dataset.dis=b.disponible;\n    imp.appendChild(o);\n  });\n  if(bls.length===1){imp.value=bls[0].imputation;onNrImpChange(imp);}\n}\n\nfunction onNrImpChange(sel){\n  const opt=sel.options[sel.selectedIndex];\n  if(!opt||!opt.value){document.getElementById("nr-bcp").textContent="—";document.getElementById("nr-dis").innerHTML="—";return;}\n  document.getElementById("nr-bcp").textContent=fmtFCFA(Number(opt.dataset.bcp||0));\n  document.getElementById("nr-cum").textContent=fmtFCFA(Number(opt.dataset.cum||0));\n  onNrAmtChange();\n}\nfunction onNrAmtChange(){\n  const imp=document.getElementById("nr-imp");const opt=imp.options[imp.selectedIndex];\n  if(!opt||!opt.value){return;}\n  const d=Number(opt.dataset.dis||0)-Number(document.getElementById("nr-amt").value||0);\n  document.getElementById("nr-dis").innerHTML=fmtDisp(d+(Number(opt.dataset.dis||0)-(Number(opt.dataset.dis||0)-Number(opt.dataset.cum||0)+Number(opt.dataset.cum||0))));\n  // Simpler: new disponible = original_dispo - new_amount_entered\n  const origDis=Number(opt.dataset.dis||0);\n  const amt=Number(document.getElementById("nr-amt").value||0);\n  document.getElementById("nr-dis").innerHTML=fmtDisp(origDis-amt);\n}\n\nasync function saveNewRow(){\n  const dir=document.getElementById("nr-dir").value;\n  const imp=document.getElementById("nr-imp").value;\n  const date_=document.getElementById("nr-date").value;\n  const amt=Number(document.getElementById("nr-amt").value||0);\n  const intitule=document.getElementById("nr-int").value.trim();\n  const nat=document.getElementById("nr-nat").value;\n  const stat=document.getElementById("nr-stat").value;\n  if(!dir||!imp||!date_||!amt||!intitule){toast("Champs obligatoires: direction, imputation, date, montant, intitulé",false);return;}\n  const p={direction:dir,imputation:imp,date_reception:date_,montant:amt,intitule:intitule,nature:nat,status:stat,year:S.year};\n  const r=await api("/api/transactions",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(p)});\n  if(!r)return;\n  if(!r.ok){toast("Erreur: "+(await r.text()),false);return;}\n  BL_CACHE={};const tx=await r.json();toast("Transaction enregistrée ✓");\n  document.getElementById("new-tx-row").remove();\n  await loadTx();loadKPIs();\n  if(confirm("Ouvrir la fiche d\'engagement?"))openFiche(tx.id);\n}\nfunction cancelNewRow(){document.getElementById("new-tx-row")?.remove();}\n\nfunction onTxSel(cb){\n  const id=Number(cb.value);\n  if(cb.checked)S.selectedTxIds.add(id);else S.selectedTxIds.delete(id);\n  document.getElementById("tx-tr-"+id)?.classList.toggle("row-sel",cb.checked);\n  updateSelUI();\n}\nfunction toggleSelAll(cb){document.querySelectorAll(".tx-chk").forEach(c=>{c.checked=cb.checked;onTxSel(c);});}\nfunction updateSelUI(){\n  const n=S.selectedTxIds.size;\n  document.getElementById("print-sel-btn").style.display=n>0?"":"none";\n  document.getElementById("tx-sel-info").style.display=n>0?"flex":"none";\n  document.getElementById("tx-sel-count").textContent=n;\n}\nfunction printSelected(){if(!S.selectedTxIds.size){toast("Sélectionnez au moins une transaction",false);return;}window.open("/fiche?ids="+[...S.selectedTxIds].join(","),"_blank");}\nfunction openFiche(id){window.open("/fiche?ids="+id,"_blank");}\nasync function delTx(id){if(!confirm("Supprimer?"))return;await api("/api/transactions/"+id,{method:"DELETE"});BL_CACHE={};toast("Supprimé");loadTx();loadKPIs();}\nfunction exportTx(){window.open(`/api/export/transactions?year=${S.year}&direction=${S.dir}`,"_blank");}\n\nasync function loadBL(){\n  const dir=document.getElementById("bl-f-dir").value;\n  const q=(document.getElementById("bl-q").value||"").toLowerCase();\n  const r=await api(`/api/budget-lines?year=${S.year}&direction=${encodeURIComponent(dir)}`);if(!r)return;\n  let data=await r.json();\n  if(q)data=data.filter(b=>b.imputation.toLowerCase().includes(q)||(b.libelle||"").toLowerCase().includes(q));\n  const tb=document.getElementById("bl-rows");tb.innerHTML="";\n  document.getElementById("bl-empty").style.display=data.length?"none":"block";\n  data.forEach(b=>{\n    const pct=b.budget_cp?Math.min(100,Math.round(b.cumul_engage/b.budget_cp*100)):0;\n    const col=pct>90?"#dc2626":pct>70?"#d97706":"#16a34a";\n    const rc=pct>=100?"bl-dep":b.dispo_ok?"bl-ok":"";\n    const sl=pct>=100?`<span class="sb-dep">⚠ DÉPASSEMENT</span>`:b.dispo_ok?`<span class="sb-ok">✓ DISPONIBLE</span>`:`<span class="sb-pen">⚡ PARTIEL</span>`;\n    tb.innerHTML+=`<tr class="${rc}">\n      <td><span class="dir-b">${b.direction}</span></td>\n      <td style="font-family:monospace;font-size:10px;max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${b.imputation}">${b.imputation}</td>\n      <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${b.libelle||"—"}</td>\n      <td>${natBadge(b.nature)}</td>\n      <td class="num" style="color:#065f46">${fmtFCFA(b.budget_cp)}</td>\n      <td class="num" style="color:#7c3aed">${fmtFCFA(b.cumul_engage)}</td>\n      <td class="num">${fmtDisp(b.disponible)}</td>\n      <td style="min-width:90px"><div style="display:flex;align-items:center;gap:4px"><div class="prg" style="flex:1"><div class="prf" style="width:${pct}%;background:${col}"></div></div><span style="font-size:10px;color:${col};font-weight:800">${pct}%</span></div></td>\n      <td>${sl}</td>\n      <td class="admin-only"><button class="btn bd bxs" onclick="delBL(${b.id})">🗑</button></td>\n    </tr>`;\n  });\n}\nfunction openBLModal(){document.getElementById("bl-yr").value=S.year;if(S.dir)document.getElementById("bl-dir").value=S.dir;openModal("bl-modal");}\nasync function saveBL(){\n  const p={year:Number(document.getElementById("bl-yr").value),direction:document.getElementById("bl-dir").value,imputation:document.getElementById("bl-imp").value.trim(),libelle:document.getElementById("bl-lib").value.trim(),nature:document.getElementById("bl-nat").value,budget_cp:Number(document.getElementById("bl-bcp").value||0)};\n  if(!p.year||!p.direction||!p.imputation||!p.budget_cp){toast("Champs obligatoires manquants",false);return;}\n  const r=await api("/api/budget-lines",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(p)});\n  if(!r)return;if(!r.ok){toast("Erreur: "+(await r.text()),false);return;}\n  BL_CACHE={};toast("Ligne créée ✓");closeModal("bl-modal");loadBL();loadKPIs();\n}\nasync function delBL(id){if(!confirm("Supprimer?"))return;await api("/api/budget-lines/"+id,{method:"DELETE"});BL_CACHE={};toast("Supprimé");loadBL();}\n\nasync function loadReports(){\n  const yr=document.getElementById("rp-year").value||S.year;\n  document.getElementById("rp-year-label").textContent=yr;\n  const r=await api(`/api/dashboard?year=${yr}`);if(!r)return;\n  const d=await r.json();const pct=d.total_budget?Math.round(d.total_engage/d.total_budget*100):0;\n  document.getElementById("rp-summary").innerHTML=`<div style="font-size:12px">\n    <div style="display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid #f1f5f9"><span>Budget CP total</span><strong>${fmtFCFA(d.total_budget)}</strong></div>\n    <div style="display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid #f1f5f9;color:#dc2626"><span>Cumul engagé</span><strong>${fmtFCFA(d.total_engage)}</strong></div>\n    <div style="display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid #f1f5f9;color:#d97706"><span>En attente</span><strong>${fmtFCFA(d.total_pending)}</strong></div>\n    <div style="display:flex;justify-content:space-between;padding:8px 0;font-size:14px"><strong>Disponible</strong><strong style="color:${d.total_dispo>=0?"#16a34a":"#dc2626"}">${fmtFCFA(d.total_dispo)}</strong></div>\n    <div style="font-size:10px;color:var(--muted)">${pct}% engagé · ${d.tx_count} transaction(s)</div>\n  </div>`;\n  const bld=d.bl_by_dir||{};const tb=document.getElementById("rp-dir-rows");tb.innerHTML="";\n  Object.keys(bld).sort().forEach(dir=>{\n    const bd=bld[dir];const av=bd.budget_cp-bd.engage;const p2=bd.budget_cp?Math.min(100,Math.round(bd.engage/bd.budget_cp*100)):0;const col=p2>90?"#dc2626":p2>70?"#d97706":"#16a34a";\n    tb.innerHTML+=`<tr><td><span class="dir-b">${dir}</span></td><td class="num">${fmtFCFA(bd.budget_cp)}</td><td class="num" style="color:#dc2626">${fmtFCFA(bd.engage)}</td><td class="num" style="color:${av>=0?"#16a34a":"#dc2626"}">${fmtFCFA(av)}</td><td><div style="display:flex;align-items:center;gap:5px;min-width:80px"><div class="prg" style="flex:1"><div class="prf" style="width:${p2}%;background:${col}"></div></div><span style="font-size:10px;color:${col};font-weight:800">${p2}%</span></div></td><td>${av>=0?"<span class=\\"sb-ok\\">OK</span>":"<span class=\\"sb-dep\\">⚠ DÉPASSEMENT</span>"}</td></tr>`;\n  });\n}\nfunction downloadReport(){window.open(`/api/report/monthly?year=${document.getElementById("rp-year").value||S.year}&month=${document.getElementById("rp-month").value}`,"_blank");}\n\nfunction onFileSel(inp,nId,aId){const f=inp.files[0];if(!f)return;document.getElementById(nId).textContent="✓ "+f.name;document.getElementById(aId).style.borderColor="#16a34a";document.getElementById(aId).style.background="#f0fdf4";}\nasync function importTx(){\n  const f=document.getElementById("imp-tx-file").files[0];const yr=Number(document.getElementById("imp-tx-year").value);\n  if(!f){toast("Sélectionnez un fichier CSV",false);return;}\n  if(!yr){toast("Saisissez une année",false);return;}\n  const fd=new FormData();fd.append("file",f);fd.append("year",yr);\n  const r=await api("/api/import/transactions",{method:"POST",body:fd});if(!r)return;\n  const d=await r.json();\n  const errH=d.errors.length?`<details style="margin-top:4px"><summary style="cursor:pointer;font-size:10px">Voir ${d.errors.length} erreur(s)</summary><div style="font-size:10px;max-height:80px;overflow-y:auto">${d.errors.slice(0,10).join("<br>")}</div></details>`:"";\n  document.getElementById("imp-tx-result").innerHTML=`<div class="alrt ${d.errors.length?"alrt-y":"alrt-g"}">${d.created} transaction(s) importée(s).${errH}</div>`;\n  if(d.created){BL_CACHE={};toast(d.created+" transactions importées ✓");loadTx();loadKPIs();}\n}\nasync function importBL(){\n  const f=document.getElementById("imp-bl-file").files[0];\n  if(!f){toast("Sélectionnez un fichier CSV",false);return;}\n  const fd=new FormData();fd.append("file",f);\n  const r=await api("/api/import/budget-lines",{method:"POST",body:fd});if(!r)return;\n  const d=await r.json();\n  const errH=d.errors.length?`<details style="margin-top:4px"><summary style="cursor:pointer;font-size:10px">Voir ${d.errors.length} erreur(s)</summary><div style="font-size:10px;max-height:80px;overflow-y:auto">${d.errors.slice(0,10).join("<br>")}</div></details>`:"";\n  document.getElementById("imp-bl-result").innerHTML=`<div class="alrt ${d.errors.length?"alrt-y":"alrt-g"}"><strong>${d.created} créée(s)</strong>, <strong>${d.updated} mise(s) à jour</strong>${d.skipped?" ("+d.skipped+" lignes vides ignorées)":""}. ${d.errors.length?"⚠ "+d.errors.length+" erreur(s)":"✓ Import réussi!"}${errH}</div>`;\n  if(d.created||d.updated){BL_CACHE={};toast("Lignes budgétaires importées ✓");loadBL();loadKPIs();}\n}\n\nasync function loadUsers(){\n  const r=await api("/api/users");if(!r)return;const data=await r.json();\n  const rl={admin:"Administrateur",dcf_dir:"Dir. DCF",dcf_sub:"S-Dir. Budget",agent:"Agent",viewer:"Observateur"};\n  const rb={admin:"#991b1b",dcf_dir:"#991b1b",dcf_sub:"#d97706",agent:"#1f4d8f",viewer:"#374151"};\n  document.getElementById("usr-rows").innerHTML=data.map(u=>{\n    let dirs="—";try{const d=JSON.parse(u.directions||"[]");dirs=d.length===ALL_DIRS.length?"Toutes ("+ALL_DIRS.length+")":d.length?d.slice(0,5).join(", ")+(d.length>5?"…":""):"Aucune";}catch{}\n    return `<tr><td><strong>${u.full_name||u.username}</strong></td><td style="font-family:monospace;font-size:11px">${u.username}</td><td style="font-size:11px">${u.email||"—"}</td><td><span style="display:inline-block;padding:2px 7px;border-radius:4px;font-size:10px;font-weight:800;background:${rb[u.role]||"#1f4d8f"};color:#fff">${rl[u.role]||u.role}</span></td><td style="font-size:10px;max-width:200px;overflow:hidden;text-overflow:ellipsis">${dirs}</td><td style="font-size:10px;color:var(--muted)">${(u.created_at||"").slice(0,10)}</td><td style="white-space:nowrap"><button class="btn bs bxs" onclick="editUser(${u.id})">✏</button>${u.username!==S.user?.u?` <button class="btn bd bxs" onclick="delUser(${u.id})">🗑</button>`:"<span style=\\"font-size:9px;color:var(--muted)\\">Vous</span>"}</td></tr>`;\n  }).join("");\n}\nfunction openUserModal(){S.editUserId=null;document.getElementById("usr-modal-title").textContent="Ajouter un utilisateur";["u-nm","u-usr","u-em"].forEach(id=>document.getElementById(id).value="");document.getElementById("u-pw").value="";document.getElementById("u-rl").value="agent";buildDirCheckboxes([]);onRoleChange();openModal("usr-modal");}\nasync function editUser(id){\n  S.editUserId=id;const r=await api("/api/users");if(!r)return;\n  const u=(await r.json()).find(x=>x.id===id);if(!u)return;\n  document.getElementById("usr-modal-title").textContent="Modifier: "+u.username;\n  ["u-nm","u-usr","u-em"].forEach(id2=>document.getElementById(id2).value=u[id2.replace("u-","").replace("nm","full_name").replace("usr","username").replace("em","email")]||"");\n  document.getElementById("u-pw").value="";document.getElementById("u-rl").value=u.role;\n  let dirs=[];try{dirs=JSON.parse(u.directions||"[]");}catch{}\n  buildDirCheckboxes(dirs);onRoleChange();openModal("usr-modal");\n}\nfunction buildDirCheckboxes(sel){document.getElementById("u-dirs-list").innerHTML=ALL_DIRS.map(d=>`<div class="cbox-row"><input type="checkbox" id="dir-${d}" value="${d}" ${sel.includes(d)?"checked":""}><label for="dir-${d}" style="font-size:11px;cursor:pointer;font-weight:600">${d}</label></div>`).join("");}\nfunction selAllDirs(v){document.querySelectorAll("#u-dirs-list input").forEach(c=>c.checked=v);}\nfunction onRoleChange(){const fa=["admin","dcf_dir","dcf_sub"].includes(document.getElementById("u-rl").value);document.getElementById("u-dirs-block").style.opacity=fa?.5:1;if(fa)selAllDirs(true);}\nasync function saveUser(){\n  const role=document.getElementById("u-rl").value;\n  const dirs=["admin","dcf_dir","dcf_sub"].includes(role)?ALL_DIRS:[...document.querySelectorAll("#u-dirs-list input:checked")].map(c=>c.value);\n  const nm=document.getElementById("u-nm").value;const usr=document.getElementById("u-usr").value;const pw=document.getElementById("u-pw").value;\n  if(!usr.trim()){toast("Identifiant requis",false);return;}\n  if(!S.editUserId&&!pw){toast("Mot de passe requis pour un nouvel utilisateur",false);return;}\n  const p={username:usr.trim(),full_name:nm.trim(),role,email:document.getElementById("u-em").value.trim(),directions:dirs};\n  if(pw)p.password=pw;\n  const r=await api(S.editUserId?"/api/users/"+S.editUserId:"/api/users",{method:S.editUserId?"PUT":"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(p)});\n  if(!r)return;if(!r.ok){toast("Erreur: "+(await r.text()),false);return;}\n  toast(S.editUserId?"Modifié ✓":"Créé ✓");closeModal("usr-modal");loadUsers();\n}\nasync function delUser(id){if(!confirm("Supprimer?"))return;await api("/api/users/"+id,{method:"DELETE"});toast("Supprimé");loadUsers();}\n\nfunction applyRole(){\n  const fa=isFullAccess();const isViewer=S.user?.role==="viewer";\n  document.querySelectorAll(".admin-only").forEach(e=>e.style.display=fa?"":"none");\n  document.querySelectorAll(".viewer-hide").forEach(e=>e.style.display=isViewer?"none":"");\n  if(fa)document.getElementById("nav-users").style.display="";\n}\nasync function logout(){await fetch("/api/logout",{method:"POST",credentials:"include"});window.location="/login";}\n\nasync function init(){\n  initYears();\n  const r=await api("/api/me");if(!r)return;\n  S.user=await r.json();\n  document.getElementById("uname").textContent=S.user.name||S.user.u;\n  const rl={admin:"Admin",dcf_dir:"Dir.DCF",dcf_sub:"S-Dir.Budget",agent:"Agent",viewer:"Lecteur"};\n  document.getElementById("urole").textContent=rl[S.user.role]||S.user.role;\n  const dirs=myDirs();populateDirSelects(dirs);applyRole();\n  await loadDash();\n  document.getElementById("tx-q").addEventListener("input",()=>debounce(loadTx,350));\n  document.getElementById("bl-q").addEventListener("input",()=>debounce(loadBL,350));\n  document.querySelectorAll(".mbg").forEach(bg=>bg.addEventListener("click",e=>{if(e.target===bg)bg.classList.remove("open");}));\n  setInterval(loadKPIs,30000);\n}\ninit();\n</script>\n</body>\n</html>'
