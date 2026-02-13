import os, secrets, datetime as dt, json
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get("DATABASE_URL","")
DEFAULT_ADMIN_USER = os.environ.get("DEFAULT_ADMIN_USER","admin")
DEFAULT_ADMIN_PASS = os.environ.get("DEFAULT_ADMIN_PASS","admin")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is required.")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
BASE = os.path.dirname(__file__)

app = FastAPI()
app.mount("/static", StaticFiles(directory=os.path.join(BASE,"static")), name="static")

def init_db():
    with engine.begin() as con:
        con.execute(text("""
        CREATE TABLE IF NOT EXISTS users(
          id SERIAL PRIMARY KEY,
          username TEXT UNIQUE NOT NULL,
          password TEXT NOT NULL,
          role TEXT NOT NULL DEFAULT 'USER',
          direction TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS sessions(
          token TEXT PRIMARY KEY,
          username TEXT NOT NULL,
          expires_at TIMESTAMP NOT NULL
        );
        CREATE TABLE IF NOT EXISTS budgets(
          id SERIAL PRIMARY KEY,
          year INT NOT NULL,
          sheet TEXT NOT NULL,
          direction TEXT NOT NULL,
          linekey TEXT NOT NULL,
          label TEXT NOT NULL,
          account TEXT NOT NULL,
          cp BIGINT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_budgets_year_dir ON budgets(year, direction);
        CREATE TABLE IF NOT EXISTS transactions(
          id SERIAL PRIMARY KEY,
          date DATE NOT NULL,
          year INT NOT NULL,
          direction TEXT NOT NULL,
          doctype TEXT NOT NULL,
          budgetline TEXT NOT NULL,
          account TEXT NOT NULL,
          amount BIGINT NOT NULL,
          details JSONB NOT NULL DEFAULT '{}'::jsonb,
          created_by TEXT NOT NULL,
          created_at TIMESTAMP NOT NULL,
          locked BOOLEAN NOT NULL DEFAULT FALSE
        );
        CREATE INDEX IF NOT EXISTS idx_tx_year_dir ON transactions(year, direction);
        """))
        # seed admin
        r = con.execute(text("SELECT 1 FROM users WHERE username=:u"), {"u": DEFAULT_ADMIN_USER}).fetchone()
        if not r:
            con.execute(text("INSERT INTO users(username,password,role) VALUES(:u,:p,'ADMIN')"),
                        {"u": DEFAULT_ADMIN_USER, "p": DEFAULT_ADMIN_PASS})

def ensure_budgets_loaded():
    budgets_path = os.path.join(BASE, "static", "budgets_2025.json")
    if not os.path.exists(budgets_path):
        return
    with engine.begin() as con:
        any_budget = con.execute(text("SELECT 1 FROM budgets LIMIT 1")).fetchone()
        if any_budget:
            return
        rows = json.loads(open(budgets_path, encoding="utf-8").read())
        if rows:
            con.execute(text("""INSERT INTO budgets(year,sheet,direction,linekey,label,account,cp)
                            VALUES(:year,:sheet,:direction,:linekey,:label,:account,:cp)"""), rows)

def create_session(username:str)->str:
    token = secrets.token_urlsafe(24)
    exp = dt.datetime.utcnow() + dt.timedelta(days=7)
    with engine.begin() as con:
        con.execute(text("INSERT INTO sessions(token,username,expires_at) VALUES(:t,:u,:e)"),
                    {"t": token, "u": username, "e": exp})
    return token

def get_user(token:str):
    if not token: return None
    with engine.begin() as con:
        s = con.execute(text("SELECT username, expires_at FROM sessions WHERE token=:t"), {"t": token}).fetchone()
        if not s: return None
        if s.expires_at < dt.datetime.utcnow(): return None
        u = con.execute(text("SELECT username, role, direction FROM users WHERE username=:u"), {"u": s.username}).fetchone()
        return dict(u._mapping) if u else None

def require_auth(req:Request):
    user = get_user(req.cookies.get("camtel_session",""))
    if not user: raise HTTPException(401,"Unauthorized")
    return user

@app.on_event("startup")
def _startup():
    init_db()
    ensure_budgets_loaded()

@app.get("/login", response_class=HTMLResponse)
def login_page(req: Request):
    e = req.query_params.get("e","")
    err = "Wrong credentials" if e=="1" else ""
    return HTMLResponse(f"""<!doctype html><html><head><meta charset='utf-8'>
    <meta name='viewport' content='width=device-width,initial-scale=1'><title>Login</title>
    <style>body{{font-family:Arial;background:#f4f6f8;margin:0}}
    .card{{max-width:420px;margin:10vh auto;background:#fff;padding:22px;border-radius:10px;border:1px solid #e5e7eb}}
    label{{display:block;margin:12px 0 6px;font-size:13px;color:#374151}}
    input{{width:100%;padding:10px;border:1px solid #d1d5db;border-radius:8px;font-size:14px}}
    button{{margin-top:14px;width:100%;padding:10px;border:0;border-radius:8px;background:#0b5fff;color:#fff;font-weight:700;cursor:pointer}}
    .err{{color:#b91c1c;font-size:12px;margin-top:8px}}</style></head><body>
    <div class='card'><h2>CAMTEL Budget — Login</h2>
      <form method='post' action='/login'>
        <label>Username</label><input name='username' required value='{DEFAULT_ADMIN_USER}'/>
        <label>Password</label><input name='password' type='password' required value='{DEFAULT_ADMIN_PASS}'/>
        <button type='submit'>Login</button>
      </form><div class='err'>{err}</div></div></body></html>""")

@app.post("/login")
def login(username: str = Form(...), password: str = Form(...)):
    with engine.begin() as con:
        row = con.execute(text("SELECT username,password FROM users WHERE username=:u"), {"u": username}).fetchone()
    if not row or row.password != password:
        return RedirectResponse("/login?e=1", status_code=302)
    token = create_session(username)
    resp = RedirectResponse("/", status_code=302)
    resp.set_cookie("camtel_session", token, httponly=True, samesite="lax", secure=True)
    return resp

@app.get("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=302)
    resp.delete_cookie("camtel_session")
    return resp

@app.get("/", response_class=HTMLResponse)
def home(req: Request):
    if not get_user(req.cookies.get("camtel_session","")):
        return RedirectResponse("/login", status_code=302)
    return HTMLResponse(open(os.path.join(BASE,"static","index.html"), encoding="utf-8").read())

@app.get("/api/directions")
def directions(req: Request, year: int = 2025):
    require_auth(req)
    with engine.begin() as con:
        rows = con.execute(text("SELECT DISTINCT direction FROM budgets WHERE year=:y ORDER BY direction"), {"y": year}).fetchall()
    return [r.direction for r in rows]

@app.get("/api/budgets")
def budgets(req: Request, year: int = 2025, direction: str = ""):
    user = require_auth(req)
    if user["role"] != "ADMIN" and user.get("direction"):
        direction = user["direction"]
    q="SELECT year,sheet,direction,linekey,label,account,cp FROM budgets WHERE year=:y"
    params={"y": year}
    if direction:
        q += " AND direction=:d"; params["d"]=direction.upper()
    q += " ORDER BY direction,linekey"
    with engine.begin() as con:
        rows = con.execute(text(q), params).fetchall()
    return [dict(r._mapping) for r in rows]

@app.get("/api/transactions")
def list_tx(req: Request, year: int = 0, direction: str = ""):
    user = require_auth(req)
    q="SELECT * FROM transactions WHERE 1=1"
    params={}
    if year:
        q += " AND year=:y"; params["y"]=year
    if user["role"]!="ADMIN" and user.get("direction"):
        q += " AND direction=:d"; params["d"]=user["direction"]
    elif direction:
        q += " AND direction=:d"; params["d"]=direction.upper()
    q += " ORDER BY id DESC"
    with engine.begin() as con:
        rows = con.execute(text(q), params).fetchall()
    return [dict(r._mapping) for r in rows]

@app.post("/api/transactions")
async def create_tx(req: Request):
    user = require_auth(req)
    body = await req.json()
    date = body.get("date")
    if not date: raise HTTPException(400,"date required")
    year = int(str(date)[:4])
    direction = (body.get("direction") or "").upper()
    if user["role"]!="ADMIN" and user.get("direction"):
        direction = user["direction"]
    with engine.begin() as con:
        con.execute(text("""INSERT INTO transactions(date,year,direction,doctype,budgetline,account,amount,details,created_by,created_at,locked)
                           VALUES(:date,:year,:direction,:doctype,:budgetline,:account,:amount,:details::jsonb,:created_by,:created_at,false)"""),
                    {"date":date,"year":year,"direction":direction,
                     "doctype":(body.get("doctype") or "").upper(),
                     "budgetline":body.get("budgetline") or "",
                     "account":body.get("account") or "",
                     "amount":int(body.get("amount") or 0),
                     "details":json.dumps(body.get("details") or {}),
                     "created_by":user["username"],
                     "created_at":dt.datetime.utcnow()})
    return {"ok": True}
