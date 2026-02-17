import os
from fastapi import FastAPI, Request, Response, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from itsdangerous import URLSafeSerializer, BadSignature

APP_NAME = "CAMTEL Budget App"
SECRET_KEY = os.environ.get("SECRET_KEY", "change-me")
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "admin123")

serializer = URLSafeSerializer(SECRET_KEY, salt="camtel-budget")

app = FastAPI(title=APP_NAME)


def _get_user(request: Request):
    token = request.cookies.get("session")
    if not token:
        return None
    try:
        data = serializer.loads(token)
        return data.get("u")
    except BadSignature:
        return None


def require_login(request: Request):
    user = _get_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")
    return user


INDEX_HTML = """<!doctype html>
<html lang='en'>
<head>
  <meta charset='utf-8'/>
  <meta name='viewport' content='width=device-width,initial-scale=1'/>
  <title>CAMTEL Budget App</title>
  <style>
    body{font-family:system-ui,Segoe UI,Roboto,Arial,sans-serif;margin:0;background:#f6f7fb;}
    header{background:#1f4d8f;color:#fff;padding:14px 18px;font-weight:700;}
    .wrap{max-width:1100px;margin:18px auto;padding:0 14px;}
    .card{background:#fff;border:1px solid #e6e8f0;border-radius:10px;box-shadow:0 1px 2px rgba(0,0,0,.04);}
    .row{display:flex;gap:12px;flex-wrap:wrap;align-items:center;padding:12px;}
    input,select,button{padding:10px;border-radius:8px;border:1px solid #d7dbe7;}
    button{background:#2563eb;color:#fff;border:none;cursor:pointer;}
    button.secondary{background:#64748b;}
    table{width:100%;border-collapse:collapse;}
    th,td{padding:10px;border-top:1px solid #eef0f6;font-size:14px;text-align:left;}
    .right{text-align:right;}
    .muted{color:#6b7280;font-size:13px;}
    .grid{display:grid;grid-template-columns:1fr 320px;gap:12px;}
    @media(max-width:900px){.grid{grid-template-columns:1fr;}}
    .toast{position:fixed;right:16px;bottom:16px;background:#111827;color:#fff;padding:10px 12px;border-radius:10px;display:none;}
  </style>
</head>
<body>
<header>CAMTEL Budget App</header>
<div class='wrap'>
  <div class='grid'>
    <div class='card'>
      <div class='row'>
        <select id='year'></select>
        <input id='search' placeholder='Search code/title' style='flex:1;min-width:220px'/>
        <button onclick='openNew()'>+ New</button>
        <button class='secondary' onclick='loadTx()'>Refresh</button>
      </div>
      <div style='overflow:auto'>
        <table>
          <thead>
            <tr><th>Code/Ref</th><th>Direction</th><th>Doc</th><th>Budget line</th><th class='right'>Amount</th><th>Date</th></tr>
          </thead>
          <tbody id='rows'></tbody>
        </table>
      </div>
      <div class='row muted'>Tip: create a transaction, then print the fiche from Details.</div>
    </div>

    <div class='card' style='padding:12px'>
      <div style='display:flex;justify-content:space-between;align-items:center'>
        <strong>Details</strong>
        <button class='secondary' onclick='logout()'>Logout</button>
      </div>
      <div id='detail' class='muted' style='margin-top:10px'>Select a transaction, or click + New.</div>
    </div>
  </div>
</div>

<div id='toast' class='toast'></div>

<script>
const toast=(m)=>{const t=document.getElementById('toast');t.textContent=m;t.style.display='block';setTimeout(()=>t.style.display='none',2500)};

function initYears(){
  const y=document.getElementById('year');
  const now=new Date().getFullYear();
  for(let i=now-1;i<=now+2;i++){const o=document.createElement('option');o.value=i;o.textContent=i;y.appendChild(o)}
  y.value=now;
}

async function api(path, opts){
  const r=await fetch(path, {credentials:'include', ...(opts||{})});
  if(r.status===401){ window.location='/login'; return null; }
  return r;
}

async function loadTx(){
  const year=document.getElementById('year').value;
  const q=document.getElementById('search').value.trim();
  const r=await api(`/api/tx?year=${encodeURIComponent(year)}&q=${encodeURIComponent(q)}`);
  if(!r) return;
  const data=await r.json();
  const body=document.getElementById('rows');
  body.innerHTML='';
  for(const t of data){
    const tr=document.createElement('tr');
    tr.innerHTML=`<td><a href='#' onclick='showDetail(${t.id});return false;'>${t.code}</a></td><td>${t.direction}</td><td>${t.doc}</td><td>${t.budget_line}</td><td class='right'>${t.amount.toLocaleString()}</td><td>${t.date}</td>`;
    body.appendChild(tr);
  }
}

function openNew(){
  const html=`
    <div>
      <h3 style='margin:8px 0 10px'>New transaction</h3>
      <div class='muted'>Minimal working online version (save + fiche). We can add full budget lines next.</div>
      <div style='display:grid;gap:8px;margin-top:10px'>
        <input id='f_code' placeholder='Code/Ref (auto if empty)'/>
        <input id='f_direction' placeholder='Direction (e.g., DRH)' value='DRH'/>
        <input id='f_doc' placeholder='Doc (e.g., NC)' value='NC'/>
        <input id='f_budget' placeholder='Budget line' value='DRH - 60530000 - CARBURANT ET LUBRIFIANT'/>
        <input id='f_title' placeholder='Title/Description' value='CARBURANT ET LUBRIFIANT'/>
        <input id='f_date' type='date'/>
        <input id='f_amount' type='number' placeholder='Amount (FCFA)' value='70000'/>
        <div style='display:flex;gap:8px'>
          <button onclick='saveNew()'>Save</button>
          <button class='secondary' onclick='clearDetail()'>Close</button>
        </div>
      </div>
    </div>
  `;
  document.getElementById('detail').innerHTML=html;
  const d=new Date();
  document.getElementById('f_date').value = d.toISOString().slice(0,10);
}

function clearDetail(){
  document.getElementById('detail').innerHTML="Select a transaction, or click + New.";
}

async function saveNew(){
  const payload={
    code: document.getElementById('f_code').value,
    direction: document.getElementById('f_direction').value,
    doc: document.getElementById('f_doc').value,
    budget_line: document.getElementById('f_budget').value,
    title: document.getElementById('f_title').value,
    date: document.getElementById('f_date').value,
    amount: Number(document.getElementById('f_amount').value||0),
    year: Number(document.getElementById('year').value)
  };
  const r=await api('/api/tx', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
  if(!r) return;
  const data=await r.json();
  toast('Saved');
  await loadTx();
  await showDetail(data.id);
}

async function showDetail(id){
  const r=await api('/api/tx/'+id);
  if(!r) return;
  const t=await r.json();
  const html=`
    <div>
      <div style='display:flex;justify-content:space-between;align-items:center'>
        <strong>Transaction</strong>
        <button onclick='openFiche(${t.id})'>Print fiche</button>
      </div>
      <div class='muted' style='margin-top:8px'>${t.title}</div>
      <div style='margin-top:10px'>
        <div><b>Code:</b> ${t.code}</div>
        <div><b>Direction:</b> ${t.direction}</div>
        <div><b>Doc:</b> ${t.doc}</div>
        <div><b>Budget line:</b> ${t.budget_line}</div>
        <div><b>Amount:</b> ${t.amount.toLocaleString()} FCFA</div>
        <div><b>Date:</b> ${t.date}</div>
      </div>
    </div>
  `;
  document.getElementById('detail').innerHTML=html;
}

function openFiche(id){
  window.open('/fiche/'+id, '_blank');
}

async function logout(){
  await fetch('/api/logout', {method:'POST', credentials:'include'});
  window.location='/login';
}

initYears();
loadTx();
document.getElementById('year').addEventListener('change', loadTx);
document.getElementById('search').addEventListener('input', ()=>{clearTimeout(window.__t);window.__t=setTimeout(loadTx,250)});
</script>
</body>
</html>"""


LOGIN_HTML = """<!doctype html>
<html lang='en'><head><meta charset='utf-8'/><meta name='viewport' content='width=device-width,initial-scale=1'/>
<title>Login - CAMTEL Budget App</title>
<style>
body{font-family:system-ui,Segoe UI,Roboto,Arial,sans-serif;background:#f6f7fb;margin:0;display:flex;min-height:100vh;align-items:center;justify-content:center;}
.card{width:360px;background:#fff;border:1px solid #e6e8f0;border-radius:12px;padding:16px;box-shadow:0 1px 2px rgba(0,0,0,.04)}
input,button{width:100%;padding:10px;border-radius:8px;border:1px solid #d7dbe7;margin-top:10px;}
button{background:#2563eb;color:#fff;border:none;cursor:pointer;}
.small{color:#6b7280;font-size:13px;margin-top:10px;}
</style></head>
<body>
<div class='card'>
  <h2 style='margin:0 0 6px'>CAMTEL Budget App</h2>
  <div class='small'>Login to start working.</div>
  <form method='post' action='/api/login'>
    <input name='username' placeholder='Username' required />
    <input name='password' placeholder='Password' type='password' required />
    <button type='submit'>Login</button>
  </form>
  <div class='small'>Default: admin / admin123 (change with env vars ADMIN_USER / ADMIN_PASS)</div>
</div>
</body></html>"""


# in-memory storage (simple + reliable on free tier; can switch to Postgres later)
TX = []
NEXT_ID = 1


def _make_code(direction: str, year: int, n: int):
    return f"JD{direction}-{year}{n:04d}"


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    user = _get_user(request)
    if not user:
        return RedirectResponse("/login")
    return HTMLResponse(INDEX_HTML)


@app.get("/login", response_class=HTMLResponse)
def login_page():
    return HTMLResponse(LOGIN_HTML)


@app.post("/api/login")
def login(username: str = Form(...), password: str = Form(...)):
    if username != ADMIN_USER or password != ADMIN_PASS:
        return HTMLResponse(LOGIN_HTML.replace("Login to start working.", "Invalid credentials."), status_code=401)
    token = serializer.dumps({"u": username})
    resp = RedirectResponse("/", status_code=302)
    resp.set_cookie("session", token, httponly=True, samesite="lax")
    return resp


@app.post("/api/logout")
def logout(response: Response):
    resp = JSONResponse({"ok": True})
    resp.delete_cookie("session")
    return resp


@app.get("/api/tx")
def list_tx(request: Request, year: int, q: str = ""):
    require_login(request)
    ql = q.lower().strip()
    items = [t for t in TX if t["year"] == year]
    if ql:
        items = [t for t in items if ql in t["code"].lower() or ql in t["title"].lower()]
    return items[::-1]


@app.post("/api/tx")
def create_tx(request: Request, payload: dict):
    require_login(request)
    global NEXT_ID
    direction = (payload.get("direction") or "").strip() or "DRH"
    doc = (payload.get("doc") or "").strip() or "NC"
    budget_line = (payload.get("budget_line") or "").strip() or ""
    title = (payload.get("title") or "").strip() or ""
    date = (payload.get("date") or "").strip() or ""
    amount = int(payload.get("amount") or 0)
    year = int(payload.get("year") or 0)

    if not year:
        raise HTTPException(status_code=400, detail="Year required")
    if not date:
        raise HTTPException(status_code=400, detail="Date required")

    code = (payload.get("code") or "").strip()
    if not code:
        code = _make_code(direction, year, NEXT_ID)

    tx = {
        "id": NEXT_ID,
        "code": code,
        "direction": direction,
        "doc": doc,
        "budget_line": budget_line,
        "title": title,
        "date": date,
        "amount": amount,
        "year": year,
    }
    TX.append(tx)
    NEXT_ID += 1
    return tx


@app.get("/api/tx/{tx_id}")
def get_tx(request: Request, tx_id: int):
    require_login(request)
    for t in TX:
        if t["id"] == tx_id:
            return t
    raise HTTPException(status_code=404, detail="Not found")


@app.get("/fiche/{tx_id}", response_class=HTMLResponse)
def fiche(request: Request, tx_id: int):
    user = require_login(request)
    t = None
    for x in TX:
        if x["id"] == tx_id:
            t = x
            break
    if not t:
        raise HTTPException(status_code=404, detail="Not found")

    html = f"""<!doctype html>
<html><head><meta charset='utf-8'/><title>Fiche {t['code']}</title>
<style>
body{{font-family:Arial,sans-serif;margin:18px;}}
.box{{border:1px solid #333;padding:14px;}}
.row{{display:flex;justify-content:space-between;}}
small{{color:#555;}}
@media print{{button{{display:none;}}}}
</style></head>
<body>
<button onclick='window.print()'>Print</button>
<h2>Fiche d'engagement</h2>
<div class='box'>
  <div class='row'><div><b>Code/Ref:</b> {t['code']}</div><div><b>Date:</b> {t['date']}</div></div>
  <p><b>Direction:</b> {t['direction']} &nbsp; | &nbsp; <b>Doc:</b> {t['doc']}</p>
  <p><b>Budget line:</b> {t['budget_line']}</p>
  <p><b>Title/Description:</b> {t['title']}</p>
  <p><b>Amount:</b> {t['amount']:,} FCFA</p>
  <hr/>
  <small>Generated by {APP_NAME} (user: {user})</small>
</div>
</body></html>"""
    return HTMLResponse(html)
