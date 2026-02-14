
import os
import json
from datetime import datetime, date

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, Response
from starlette.middleware.sessions import SessionMiddleware
import psycopg2
from psycopg2.extras import RealDictCursor
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm

APP_NAME = "CAMTEL Budget App"
DEFAULT_USER = os.getenv("APP_USER", "admin")
DEFAULT_PASS = os.getenv("APP_PASS", "admin")
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-please")

DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or os.getenv("RENDER_POSTGRES_URL")

app = FastAPI(title=APP_NAME)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, same_site="lax")

def _require_login(request: Request):
    if not request.session.get("user"):
        raise HTTPException(status_code=401, detail="Not authenticated")

def _db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set. Add it in Render Environment Variables.")
    return psycopg2.connect(DATABASE_URL, sslmode="require")

def init_db():
    conn = _db()
    try:
        with conn.cursor() as cur:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS budgets (
                year INT NOT NULL,
                direction TEXT NOT NULL,
                code TEXT NOT NULL,
                title TEXT NOT NULL,
                cp BIGINT NOT NULL DEFAULT 0,
                engaged BIGINT NOT NULL DEFAULT 0,
                PRIMARY KEY (year, direction, code)
            );
            """)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id BIGSERIAL PRIMARY KEY,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                year INT NOT NULL,
                direction TEXT NOT NULL,
                doc TEXT NOT NULL,
                budget_code TEXT NOT NULL,
                budget_title TEXT NOT NULL,
                code_ref TEXT NOT NULL,
                tdate DATE NOT NULL,
                title TEXT NOT NULL,
                amount BIGINT NOT NULL DEFAULT 0
            );
            """)
        conn.commit()
    finally:
        conn.close()

def seed_budgets_from_json():
    path = os.path.join(os.path.dirname(__file__), "budgets_2025.json")
    if not os.path.exists(path):
        return
    data = json.load(open(path, "r", encoding="utf-8"))
    conn = _db()
    try:
        with conn.cursor() as cur:
            for row in data:
                year = int(row.get("year", 2025))
                direction = row.get("direction") or "DRH"
                code = str(row.get("code") or "").strip()
                title = str(row.get("title") or "").strip()
                cp = int(row.get("cp") or 0)
                engaged = int(row.get("engaged") or 0)
                if not code or not title:
                    continue
                cur.execute(
                    """
                    INSERT INTO budgets(year, direction, code, title, cp, engaged)
                    VALUES (%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (year, direction, code)
                    DO UPDATE SET title=EXCLUDED.title, cp=EXCLUDED.cp, engaged=EXCLUDED.engaged;
                    """,
                    (year, direction, code, title, cp, engaged),
                )
        conn.commit()
    finally:
        conn.close()

@app.on_event("startup")
def _startup():
    init_db()
    seed_budgets_from_json()

HTML = r"""<!doctype html>
<html><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>CAMTEL Budget App</title>
<style>
body{font-family:system-ui,Segoe UI,Arial;margin:0;background:#f5f6f8}
header{background:#1f5fbf;color:#fff;padding:12px 16px;display:flex;justify-content:space-between;align-items:center}
.wrap{max-width:1100px;margin:18px auto;padding:0 12px}
.card{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:12px}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
input,select,button{padding:9px 10px;border:1px solid #d1d5db;border-radius:8px;font-size:14px}
button{background:#2563eb;color:white;border:none;cursor:pointer}
button.secondary{background:#6b7280}
button.danger{background:#dc2626}
table{width:100%;border-collapse:collapse;margin-top:10px}
th,td{border-bottom:1px solid #eef2f7;padding:8px;text-align:left;font-size:14px}
tr:hover{background:#f9fafb}
.muted{color:#6b7280;font-size:13px}
.right{margin-left:auto}
.hidden{display:none}
.modal{position:fixed;inset:0;background:rgba(0,0,0,.4);display:none;align-items:center;justify-content:center;padding:14px}
.modal .box{width:min(920px,100%);background:#fff;border-radius:12px;padding:14px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:10px}
@media (max-width:800px){.grid2{grid-template-columns:1fr}}
</style></head>
<body>
<header><div><b>CAMTEL</b> Budget App</div><div id="userbar" class="muted"></div></header>

<div class="wrap">
  <div class="card" id="loginCard">
    <h3>Login</h3>
    <div class="row">
      <input id="u" placeholder="Username" value="admin"/>
      <input id="p" placeholder="Password" type="password" value="admin"/>
      <button onclick="login()">Login</button>
      <span id="loginMsg" class="muted"></span>
    </div>
    <p class="muted">Default is admin/admin (change on Render with APP_USER + APP_PASS).</p>
  </div>

  <div class="card hidden" id="appCard">
    <div class="row">
      <select id="yearSel"></select>
      <select id="docSel"><option value="NC">NC</option><option value="OM">OM</option><option value="BC">BC</option></select>
      <input id="search" placeholder="Search code/title..." style="min-width:240px"/>
      <button class="secondary" onclick="refresh()">Refresh</button>
      <button onclick="openNew()">+ New</button>
      <button onclick="printA4()" class="secondary" id="printBtn">Print A4 (0)</button>
      <button onclick="delSelected()" class="danger">Delete</button>
      <div class="right"><button class="secondary" onclick="logout()">Logout</button></div>
    </div>
    <p class="muted">Tip: select up to 2 transactions, then click Print A4 (2).</p>

    <table id="tbl">
      <thead><tr><th></th><th>Code/Ref</th><th>Direction</th><th>Doc</th><th>Budget line</th><th>Amount (FCFA)</th><th>Date</th></tr></thead>
      <tbody></tbody>
    </table>
  </div>
</div>

<div class="modal" id="modal">
  <div class="box">
    <div class="row">
      <h3 style="margin:0">New transaction</h3>
      <div class="right"></div>
      <button class="secondary" onclick="closeModal()">Close</button>
      <button onclick="saveTx()">Save</button>
    </div>
    <div class="grid2">
      <div><label class="muted">Year</label><br/><select id="mYear"></select></div>
      <div><label class="muted">Direction</label><br/>
        <select id="mDir"><option value="DRH">DRH</option><option value="DCF">DCF</option><option value="DG">DG</option><option value="DOP">DOP</option><option value="DCP">DCP</option></select></div>
      <div><label class="muted">Doc</label><br/><select id="mDoc"><option value="NC">NC</option><option value="OM">OM</option><option value="BC">BC</option></select></div>
      <div><label class="muted">Code/Ref</label><br/><input id="mCode" placeholder="Auto"/></div>
      <div style="grid-column:1/-1">
        <label class="muted">Budget line</label><br/>
        <input id="budgetSearch" placeholder="Type to search budget lines..." oninput="budgetSuggest()"/>
        <select id="budgetPick" style="width:100%;margin-top:6px"></select>
      </div>
      <div><label class="muted">Date</label><br/><input id="mDate" type="date"/></div>
      <div><label class="muted">Amount (FCFA)</label><br/><input id="mAmount" type="number" min="0" step="1"/></div>
      <div style="grid-column:1/-1"><label class="muted">Title / Description</label><br/><input id="mTitle" placeholder="Description"/></div>
    </div>
    <div id="saveMsg" class="muted" style="margin-top:8px"></div>
  </div>
</div>

<script>
let budgetsCache=[], txs=[], selectedIds=[], selectedOrder=[];
function fmt(n){ try{return new Intl.NumberFormat().format(n||0);}catch(e){return n||0;} }
async function api(path, opts={}){
  const res = await fetch(path, {credentials:'include', ...opts});
  if(!res.ok){ const t=await res.text(); throw new Error(t||res.statusText); }
  const ct=res.headers.get('content-type')||'';
  if(ct.includes('application/json')) return res.json();
  return res.text();
}
async function login(){
  const u=document.getElementById('u').value.trim();
  const p=document.getElementById('p').value;
  document.getElementById('loginMsg').textContent='Logging in...';
  try{
    await api('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:u,password:p})});
    await boot();
  }catch(e){ document.getElementById('loginMsg').textContent='Login failed.'; }
}
async function logout(){ await api('/api/logout',{method:'POST'}); location.reload(); }
async function boot(){
  try{
    const me=await api('/api/me');
    document.getElementById('loginCard').classList.add('hidden');
    document.getElementById('appCard').classList.remove('hidden');
    document.getElementById('userbar').textContent='User: '+me.username;
    const years=[2025,2026,2027], ys=document.getElementById('yearSel'); ys.innerHTML='';
    years.forEach(y=>{const o=document.createElement('option');o.value=y;o.textContent=y;ys.appendChild(o);});
    ys.value=new Date().getFullYear(); ys.onchange=refresh;
    document.getElementById('search').oninput=render;
    await refresh();
    document.getElementById('loginMsg').textContent='';
  }catch(e){}
}
async function loadBudgets(){
  const y=document.getElementById('yearSel').value;
  budgetsCache=await api('/api/budgets?year='+encodeURIComponent(y));
}
function budgetSuggest(){
  const q=document.getElementById('budgetSearch').value.toLowerCase().trim();
  const pick=document.getElementById('budgetPick'); pick.innerHTML='';
  const items=budgetsCache.filter(b=>(b.code+' '+b.title+' '+b.direction).toLowerCase().includes(q)).slice(0,50);
  items.forEach(b=>{const o=document.createElement('option');o.value=b.code;o.textContent=`${b.direction} — ${b.code} — ${b.title}`;o.dataset.dir=b.direction;o.dataset.title=b.title;pick.appendChild(o);});
  if(items.length===0){const o=document.createElement('option');o.value='';o.textContent='No match';pick.appendChild(o);}
}
async function refresh(){
  await loadBudgets();
  selectedIds=[]; selectedOrder=[];
  const y=document.getElementById('yearSel').value;
  txs=await api('/api/transactions?year='+encodeURIComponent(y));
  render();
}
function toggleSelect(id, checked){
  if(checked){
    if(selectedIds.length>=2){document.getElementById('cb_'+id).checked=false; return;}
    selectedIds.push(id); selectedOrder.push(id);
  }else{
    selectedIds=selectedIds.filter(x=>x!==id);
    selectedOrder=selectedOrder.filter(x=>x!==id);
  }
  document.getElementById('printBtn').textContent=`Print A4 (${selectedIds.length})`;
}
function render(){
  const q=document.getElementById('search').value.toLowerCase().trim();
  const tbody=document.querySelector('#tbl tbody'); tbody.innerHTML='';
  txs.filter(t=> (t.code_ref+' '+t.direction+' '+t.doc+' '+t.budget_code+' '+t.budget_title+' '+t.title).toLowerCase().includes(q))
    .forEach(t=>{
      const tr=document.createElement('tr');
      tr.innerHTML=`<td><input type="checkbox" id="cb_${t.id}"></td><td>${t.code_ref}</td><td>${t.direction}</td><td>${t.doc}</td><td>${t.budget_code} — ${t.budget_title}</td><td>${fmt(t.amount)}</td><td>${t.tdate}</td>`;
      tr.querySelector('input').addEventListener('change',(e)=>toggleSelect(t.id,e.target.checked));
      tbody.appendChild(tr);
    });
  document.getElementById('printBtn').textContent=`Print A4 (${selectedIds.length})`;
}
function openNew(){
  document.getElementById('modal').style.display='flex';
  const y=document.getElementById('yearSel').value;
  const my=document.getElementById('mYear'); my.innerHTML='';
  [2025,2026,2027].forEach(v=>{const o=document.createElement('option');o.value=v;o.textContent=v;my.appendChild(o);});
  my.value=y;
  document.getElementById('mDoc').value=document.getElementById('docSel').value;
  document.getElementById('mDate').value=new Date().toISOString().slice(0,10);
  document.getElementById('mAmount').value='';
  document.getElementById('mTitle').value='';
  document.getElementById('mCode').value='';
  document.getElementById('budgetSearch').value='';
  budgetSuggest();
  document.getElementById('saveMsg').textContent='';
}
function closeModal(){ document.getElementById('modal').style.display='none'; }
async function saveTx(){
  const pick=document.getElementById('budgetPick');
  const opt=pick.options[pick.selectedIndex];
  if(!opt || !opt.value){document.getElementById('saveMsg').textContent='Choose a budget line.'; return;}
  const payload={
    year:Number(document.getElementById('mYear').value),
    direction:opt.dataset.dir || document.getElementById('mDir').value,
    doc:document.getElementById('mDoc').value,
    budget_code:opt.value,
    budget_title:opt.dataset.title,
    code_ref:document.getElementById('mCode').value.trim(),
    tdate:document.getElementById('mDate').value,
    title:document.getElementById('mTitle').value.trim(),
    amount:Number(document.getElementById('mAmount').value||0)
  };
  document.getElementById('saveMsg').textContent='Saving...';
  try{
    await api('/api/transactions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    closeModal(); await refresh();
  }catch(e){ document.getElementById('saveMsg').textContent='Save failed: '+e.message; }
}
async function delSelected(){
  if(selectedIds.length===0) return;
  if(!confirm('Delete selected?')) return;
  await api('/api/transactions',{method:'DELETE',headers:{'Content-Type':'application/json'},body:JSON.stringify({ids:selectedIds})});
  selectedIds=[]; selectedOrder=[]; await refresh();
}
function printA4(){
  if(selectedIds.length===0) return;
  const ids=selectedOrder.filter(id=>selectedIds.includes(id));
  window.open('/api/fiche.pdf?ids='+encodeURIComponent(ids.join(',')),'_blank');
}
boot();
</script></body></html>
"""

@app.get("/", response_class=HTMLResponse)
def index(_: Request):
    return HTMLResponse(HTML)

@app.post("/api/login")
async def api_login(request: Request):
    data = await request.json()
    u = (data.get("username") or "").strip()
    p = data.get("password") or ""
    if u == DEFAULT_USER and p == DEFAULT_PASS:
        request.session["user"] = {"username": u}
        return {"ok": True}
    raise HTTPException(status_code=401, detail="Bad credentials")

@app.post("/api/logout")
def api_logout(request: Request):
    request.session.clear()
    return {"ok": True}

@app.get("/api/me")
def api_me(request: Request):
    _require_login(request)
    return request.session["user"]

@app.get("/api/budgets")
def api_budgets(request: Request, year: int):
    _require_login(request)
    conn = _db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT year,direction,code,title,cp,engaged FROM budgets WHERE year=%s ORDER BY direction, code",
                (year,),
            )
            return cur.fetchall()
    finally:
        conn.close()

def _auto_code(direction: str, tdate: date):
    conn = _db()
    try:
        with conn.cursor() as cur:
            prefix = f"JD{direction}"
            cur.execute("SELECT COUNT(*) FROM transactions WHERE direction=%s AND tdate=%s", (direction, tdate))
            n = cur.fetchone()[0] + 1
        return f"{prefix}-{tdate.strftime('%Y%m%d')}-{n:03d}"
    finally:
        conn.close()

@app.get("/api/transactions")
def api_transactions(request: Request, year: int):
    _require_login(request)
    conn = _db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, year, direction, doc, budget_code, budget_title, code_ref,
                       to_char(tdate,'YYYY-MM-DD') as tdate, title, amount
                FROM transactions WHERE year=%s ORDER BY id DESC
                """,
                (year,),
            )
            return cur.fetchall()
    finally:
        conn.close()

@app.post("/api/transactions")
async def api_create_tx(request: Request):
    _require_login(request)
    data = await request.json()
    year = int(data["year"])
    direction = data["direction"]
    doc = data["doc"]
    budget_code = data["budget_code"]
    budget_title = data["budget_title"]
    tdate = datetime.strptime(data["tdate"], "%Y-%m-%d").date()
    title = (data.get("title") or "").strip() or budget_title
    amount = int(data.get("amount") or 0)
    code_ref = (data.get("code_ref") or "").strip() or _auto_code(direction, tdate)

    conn = _db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO transactions(year,direction,doc,budget_code,budget_title,code_ref,tdate,title,amount)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id
                """,
                (year, direction, doc, budget_code, budget_title, code_ref, tdate, title, amount),
            )
            tid = cur.fetchone()[0]
        conn.commit()
        return {"id": tid}
    finally:
        conn.close()

@app.delete("/api/transactions")
async def api_delete_tx(request: Request):
    _require_login(request)
    data = await request.json()
    ids = data.get("ids") or []
    if not ids:
        return {"ok": True}
    conn = _db()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM transactions WHERE id = ANY(%s)", (ids,))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()

def draw_fiche(c: canvas.Canvas, x0, y0, w, h, tx: dict):
    pad = 8 * mm
    c.rect(x0, y0, w, h)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(x0 + pad, y0 + h - pad - 4, "FICHE DE TRANSACTION")
    c.setFont("Helvetica", 10)
    lines = [
        ("Code/Ref:", tx["code_ref"]),
        ("Direction:", tx["direction"]),
        ("Doc:", tx["doc"]),
        ("Budget line:", f'{tx["budget_code"]} — {tx["budget_title"]}'),
        ("Date:", tx["tdate"]),
        ("Title:", tx["title"]),
        ("Amount (FCFA):", f'{tx["amount"]:,}'.replace(",", " ")),
    ]
    yy = y0 + h - pad - 22
    for k, v in lines:
        c.drawString(x0 + pad, yy, k)
        c.drawString(x0 + pad + 35 * mm, yy, str(v))
        yy -= 10 * mm

    c.setFont("Helvetica-Bold", 10)
    c.drawString(x0 + pad, y0 + 28 * mm, "Signatures")
    c.setFont("Helvetica", 9)
    c.drawString(x0 + pad, y0 + 22 * mm, "Initiated by:")
    c.line(x0 + pad + 25 * mm, y0 + 22 * mm, x0 + w / 2 - 10 * mm, y0 + 22 * mm)
    c.drawString(x0 + w / 2 + 5 * mm, y0 + 22 * mm, "Checked/Approved:")
    c.line(x0 + w / 2 + 40 * mm, y0 + 22 * mm, x0 + w - pad, y0 + 22 * mm)
    c.drawString(x0 + pad, y0 + 12 * mm, "Finance:")
    c.line(x0 + pad + 18 * mm, y0 + 12 * mm, x0 + w / 2 - 10 * mm, y0 + 12 * mm)
    c.drawString(x0 + w / 2 + 5 * mm, y0 + 12 * mm, "Receiver:")
    c.line(x0 + w / 2 + 25 * mm, y0 + 12 * mm, x0 + w - pad, y0 + 12 * mm)

@app.get("/api/fiche.pdf")
def api_fiche_pdf(request: Request, ids: str):
    _require_login(request)
    id_list = [int(x) for x in ids.split(",") if x.strip().isdigit()]
    if not id_list:
        raise HTTPException(status_code=400, detail="No ids")

    conn = _db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, direction, doc, budget_code, budget_title, code_ref,
                       to_char(tdate,'YYYY-MM-DD') as tdate, title, amount
                FROM transactions WHERE id = ANY(%s)
                """,
                (id_list,),
            )
            rows = {int(r["id"]): r for r in cur.fetchall()}
    finally:
        conn.close()

    ordered = [rows[i] for i in id_list if i in rows]
    if not ordered:
        raise HTTPException(status_code=404, detail="Not found")

    from io import BytesIO
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4
    half = H / 2
    fiche_h = half - 10 * mm
    fiche_w = W - 20 * mm
    x0 = 10 * mm

    i = 0
    while i < len(ordered):
        draw_fiche(c, x0, half + 5 * mm, fiche_w, fiche_h, ordered[i]); i += 1
        if i < len(ordered):
            draw_fiche(c, x0, 5 * mm, fiche_w, fiche_h, ordered[i]); i += 1
        c.showPage()
    c.save()
    pdf = buf.getvalue()
    return Response(content=pdf, media_type="application/pdf")
