import os
import sqlite3
import contextlib
from fastapi import FastAPI, Request, Response, Form, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from itsdangerous import URLSafeSerializer, BadSignature
from typing import Optional
import json

APP_NAME = "CAMTEL Budget App"
SECRET_KEY = os.environ.get("SECRET_KEY", "change-me")
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "admin123")
DB_PATH = os.environ.get("DB_PATH", "camtel.db")

# Allow Lovable frontend origin (set FRONTEND_ORIGIN env var to your Lovable URL)
FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "*")

serializer = URLSafeSerializer(SECRET_KEY, salt="camtel-budget")

app = FastAPI(title=APP_NAME)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN] if FRONTEND_ORIGIN != "*" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Database setup ────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                code       TEXT NOT NULL,
                direction  TEXT NOT NULL,
                doc        TEXT NOT NULL DEFAULT 'NC',
                budget_line TEXT NOT NULL DEFAULT '',
                title      TEXT NOT NULL DEFAULT '',
                nature     TEXT NOT NULL DEFAULT 'DEPENSE COURANTE',
                description TEXT NOT NULL DEFAULT '',
                date       TEXT NOT NULL,
                amount     INTEGER NOT NULL DEFAULT 0,
                year       INTEGER NOT NULL,
                status     TEXT NOT NULL DEFAULT 'validated'
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS budget_limits (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                direction TEXT NOT NULL,
                year      INTEGER NOT NULL,
                limit_amount INTEGER NOT NULL DEFAULT 0,
                UNIQUE(direction, year)
            )
        """)
        conn.commit()


init_db()

# ── Auth helpers ──────────────────────────────────────────────────────────────

def _get_user(request: Request):
    token = request.cookies.get("session")
    # Also support Bearer token for API clients (Lovable frontend)
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
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

# ── HTML pages ────────────────────────────────────────────────────────────────

INDEX_HTML = """<!doctype html>
<html lang='fr'>
<head>
  <meta charset='utf-8'/>
  <meta name='viewport' content='width=device-width,initial-scale=1'/>
  <title>CAMTEL Budget App</title>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
  <style>
    :root {
      --blue: #1f4d8f; --blue2: #2563eb; --green: #16a34a; --red: #dc2626;
      --yellow: #d97706; --bg: #f1f5f9; --card: #fff;
      --border: #e2e8f0; --text: #1e293b; --muted: #64748b;
    }
    *{box-sizing:border-box;margin:0;padding:0;}
    body{font-family:'Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--text);}
    header{background:var(--blue);color:#fff;padding:14px 20px;display:flex;align-items:center;gap:12px;}
    header h1{font-size:16px;font-weight:700;}
    header small{opacity:.75;font-size:12px;}
    nav{display:flex;gap:4px;margin-left:auto;}
    nav button{background:rgba(255,255,255,.15);color:#fff;border:none;padding:7px 14px;border-radius:6px;cursor:pointer;font-size:13px;}
    nav button.active,nav button:hover{background:rgba(255,255,255,.3);}
    .wrap{max-width:1200px;margin:0 auto;padding:18px 14px;}
    .kpi-row{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:16px;}
    @media(max-width:800px){.kpi-row{grid-template-columns:repeat(2,1fr);}}
    .kpi{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:14px 16px;}
    .kpi label{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);}
    .kpi .val{font-size:22px;font-weight:700;margin-top:4px;}
    .kpi .sub{font-size:12px;color:var(--muted);margin-top:2px;}
    .kpi.green .val{color:var(--green);}
    .kpi.red .val{color:var(--red);}
    .kpi.yellow .val{color:var(--yellow);}
    .grid2{display:grid;grid-template-columns:1fr 340px;gap:12px;}
    @media(max-width:900px){.grid2{grid-template-columns:1fr;}}
    .card{background:var(--card);border:1px solid var(--border);border-radius:10px;overflow:hidden;}
    .card-head{padding:12px 16px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;}
    .card-head h2{font-size:14px;font-weight:600;}
    .toolbar{display:flex;gap:8px;flex-wrap:wrap;padding:10px 12px;background:#f8fafc;border-bottom:1px solid var(--border);}
    select,input{padding:8px 10px;border-radius:7px;border:1px solid var(--border);font-size:13px;background:#fff;}
    button{padding:8px 14px;border-radius:7px;border:none;cursor:pointer;font-size:13px;font-weight:500;}
    .btn-primary{background:var(--blue2);color:#fff;}
    .btn-secondary{background:#e2e8f0;color:var(--text);}
    .btn-danger{background:var(--red);color:#fff;}
    .btn-success{background:var(--green);color:#fff;}
    table{width:100%;border-collapse:collapse;font-size:13px;}
    th{background:#f8fafc;padding:9px 10px;text-align:left;font-weight:600;font-size:12px;color:var(--muted);border-bottom:1px solid var(--border);}
    td{padding:9px 10px;border-bottom:1px solid #f1f5f9;}
    tr:hover td{background:#f8fafc;}
    .badge{display:inline-block;padding:2px 8px;border-radius:20px;font-size:11px;font-weight:600;}
    .badge-green{background:#dcfce7;color:var(--green);}
    .badge-yellow{background:#fef9c3;color:var(--yellow);}
    .badge-red{background:#fee2e2;color:var(--red);}
    .right{text-align:right;}
    .detail-body{padding:14px;}
    .detail-row{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #f1f5f9;font-size:13px;}
    .detail-row label{color:var(--muted);}
    .form-grid{display:grid;gap:8px;padding:12px;}
    .form-grid input,.form-grid select{width:100%;}
    .form-grid label{font-size:12px;color:var(--muted);display:block;margin-bottom:3px;}
    .progress-bar{height:6px;background:#e2e8f0;border-radius:3px;overflow:hidden;margin-top:6px;}
    .progress-fill{height:100%;border-radius:3px;transition:width .4s;}
    .tab-content{display:none;}
    .tab-content.active{display:block;}
    .chart-wrap{padding:14px;}
    .toast{position:fixed;right:16px;bottom:16px;background:#111827;color:#fff;padding:10px 16px;border-radius:10px;display:none;z-index:999;font-size:13px;}
    .empty{padding:40px;text-align:center;color:var(--muted);font-size:13px;}
    a{color:var(--blue2);text-decoration:none;}
    .section-title{font-size:13px;font-weight:600;margin:16px 0 8px;}
    .budget-item{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:12px;margin-bottom:8px;}
    .budget-item .brow{display:flex;justify-content:space-between;font-size:13px;font-weight:600;}
    .budget-item .bsub{font-size:12px;color:var(--muted);margin-top:3px;}
  </style>
</head>
<body>
<header>
  <div>
    <h1>CAMTEL – Gestion Budgétaire 2025</h1>
    <small>SAAF / Contrôle Budgétaire</small>
  </div>
  <nav>
    <button class='active' onclick='showTab("dashboard")'>Dashboard</button>
    <button onclick='showTab("transactions")'>Transactions</button>
    <button onclick='showTab("budget")'>Budgets</button>
    <button class='btn-danger' style='margin-left:8px' onclick='logout()'>Déconnexion</button>
  </nav>
</header>

<div class='wrap'>

  <!-- KPI row -->
  <div class='kpi-row' id='kpis'>
    <div class='kpi'><label>Budget CP</label><div class='val' id='kpi-total'>—</div><div class='sub' id='kpi-total-sub'></div></div>
    <div class='kpi red'><label>Engagé</label><div class='val' id='kpi-engaged'>—</div><div class='sub' id='kpi-engaged-sub'></div></div>
    <div class='kpi yellow'><label>En attente</label><div class='val' id='kpi-pending'>—</div><div class='sub' id='kpi-pending-sub'></div></div>
    <div class='kpi green'><label>Disponible</label><div class='val' id='kpi-available'>—</div><div class='sub' id='kpi-available-sub'></div></div>
  </div>

  <!-- DASHBOARD TAB -->
  <div id='tab-dashboard' class='tab-content active'>
    <div class='grid2'>
      <div class='card'>
        <div class='card-head'><h2>Dépenses par direction</h2></div>
        <div class='chart-wrap'><canvas id='chartDir' height='220'></canvas></div>
      </div>
      <div class='card'>
        <div class='card-head'><h2>Dépenses par mois</h2></div>
        <div class='chart-wrap'><canvas id='chartMonth' height='220'></canvas></div>
      </div>
    </div>
    <div style='margin-top:12px' class='card'>
      <div class='card-head'><h2>Taux d'utilisation par direction</h2></div>
      <div style='padding:14px' id='budget-progress'></div>
    </div>
  </div>

  <!-- TRANSACTIONS TAB -->
  <div id='tab-transactions' class='tab-content'>
    <div class='card'>
      <div class='toolbar'>
        <select id='year'></select>
        <select id='filter-dir'><option value=''>Toutes directions</option></select>
        <input id='search' placeholder='Rechercher...' style='flex:1;min-width:180px'/>
        <button class='btn-primary' onclick='openNew()'>+ Nouvelle ligne</button>
        <button class='btn-secondary' onclick='loadAll()'>↻</button>
      </div>
      <div style='overflow:auto'>
        <table>
          <thead><tr>
            <th>N°</th><th>Date</th><th>Engagement</th><th>DIR</th>
            <th>Budget Line</th><th>Nature</th><th>Libellé</th>
            <th class='right'>Montant</th><th>Statut</th>
          </tr></thead>
          <tbody id='rows'></tbody>
        </table>
      </div>
      <div id='empty-tx' class='empty' style='display:none'>Aucune transaction trouvée.</div>
    </div>
  </div>

  <!-- BUDGET TAB -->
  <div id='tab-budget' class='tab-content'>
    <div class='grid2'>
      <div class='card'>
        <div class='card-head'>
          <h2>Limites budgétaires</h2>
          <button class='btn-primary' onclick='openBudgetForm()'>+ Définir limite</button>
        </div>
        <div style='padding:14px' id='budget-list'></div>
      </div>
      <div class='card' id='budget-form-card' style='display:none'>
        <div class='card-head'><h2>Définir une limite</h2></div>
        <div class='form-grid'>
          <div><label>Direction</label><input id='bl-dir' placeholder='ex: DRH'/></div>
          <div><label>Année</label><input id='bl-year' type='number' placeholder='2025'/></div>
          <div><label>Montant limite (FCFA)</label><input id='bl-amount' type='number' placeholder='10000000'/></div>
          <div style='display:flex;gap:8px;margin-top:4px'>
            <button class='btn-success' onclick='saveBudgetLimit()'>Enregistrer</button>
            <button class='btn-secondary' onclick='document.getElementById("budget-form-card").style.display="none"'>Annuler</button>
          </div>
        </div>
      </div>
    </div>
  </div>

</div>

<!-- Detail side panel (in transactions tab) -->

<div id='toast' class='toast'></div>

<script>
// ── State ──────────────────────────────────────────────────────────────────
let chartDir=null, chartMonth=null;
let currentTab='dashboard';

// ── Toast ──────────────────────────────────────────────────────────────────
function toast(m,ok=true){
  const t=document.getElementById('toast');
  t.textContent=m;t.style.background=ok?'#111827':'#dc2626';
  t.style.display='block';setTimeout(()=>t.style.display='none',2500);
}

// ── Tabs ───────────────────────────────────────────────────────────────────
function showTab(name){
  document.querySelectorAll('.tab-content').forEach(el=>el.classList.remove('active'));
  document.querySelectorAll('nav button').forEach((b,i)=>{
    const tabs=['dashboard','transactions','budget'];
    b.classList.toggle('active', tabs[i]===name);
  });
  document.getElementById('tab-'+name).classList.add('active');
  currentTab=name;
  if(name==='dashboard') loadDashboard();
  if(name==='transactions') loadTx();
  if(name==='budget') loadBudgets();
}

// ── Year select ────────────────────────────────────────────────────────────
function initYears(){
  const y=document.getElementById('year');
  const now=new Date().getFullYear();
  for(let i=now-1;i<=now+2;i++){
    const o=document.createElement('option');o.value=i;o.textContent=i;y.appendChild(o);
  }
  y.value=now;
  document.getElementById('bl-year').value=now;
}

// ── API helper ─────────────────────────────────────────────────────────────
async function api(path,opts){
  const r=await fetch(path,{credentials:'include',...(opts||{})});
  if(r.status===401){window.location='/login';return null;}
  return r;
}

// ── Load transactions ──────────────────────────────────────────────────────
async function loadTx(){
  const year=document.getElementById('year').value;
  const q=document.getElementById('search').value.trim();
  const dir=document.getElementById('filter-dir').value;
  const r=await api(`/api/tx?year=${year}&q=${encodeURIComponent(q)}&direction=${encodeURIComponent(dir)}`);
  if(!r) return;
  const data=await r.json();
  const body=document.getElementById('rows');
  body.innerHTML='';
  document.getElementById('empty-tx').style.display=data.length?'none':'block';
  data.forEach((t,i)=>{
    const statusClass=t.status==='validated'?'badge-green':t.status==='pending'?'badge-yellow':'badge-red';
    const statusLabel=t.status==='validated'?'Validée':t.status==='pending'?'Brouillon':'Rejeté';
    const tr=document.createElement('tr');
    tr.innerHTML=`
      <td>${i+1}</td>
      <td>${t.date}</td>
      <td><a href='#' onclick='openFiche(${t.id});return false;' style='font-family:monospace;font-size:12px'>${t.code}</a></td>
      <td><strong>${t.direction}</strong></td>
      <td style='max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap' title='${t.budget_line}'>${t.budget_line||'—'}</td>
      <td style='font-size:12px'>${t.nature}</td>
      <td>${t.title}</td>
      <td class='right'><strong>${t.amount.toLocaleString('fr-FR')}</strong></td>
      <td><span class='badge ${statusClass}'>${statusLabel}</span></td>
    `;
    body.appendChild(tr);
  });
}

// ── Load dashboard ─────────────────────────────────────────────────────────
async function loadDashboard(){
  const year=document.getElementById('year')?document.getElementById('year').value:new Date().getFullYear();
  const [txRes, budRes] = await Promise.all([
    api(`/api/tx?year=${year}&q=&direction=`),
    api(`/api/budget-limits?year=${year}`)
  ]);
  if(!txRes||!budRes) return;
  const txs=await txRes.json();
  const limits=await budRes.json();

  // KPIs
  const totalLimit=limits.reduce((s,b)=>s+b.limit_amount,0);
  const totalEngaged=txs.filter(t=>t.status==='validated').reduce((s,t)=>s+t.amount,0);
  const totalPending=txs.filter(t=>t.status==='pending').reduce((s,t)=>s+t.amount,0);
  const available=totalLimit-totalEngaged-totalPending;

  document.getElementById('kpi-total').textContent=totalLimit?totalLimit.toLocaleString('fr-FR')+' FCFA':'N/A';
  document.getElementById('kpi-total-sub').textContent=limits.length+' direction(s)';
  document.getElementById('kpi-engaged').textContent=totalEngaged.toLocaleString('fr-FR')+' FCFA';
  document.getElementById('kpi-engaged-sub').textContent=txs.filter(t=>t.status==='validated').length+' transaction(s)';
  document.getElementById('kpi-pending').textContent=totalPending.toLocaleString('fr-FR')+' FCFA';
  document.getElementById('kpi-pending-sub').textContent=txs.filter(t=>t.status==='pending').length+' brouillon(s)';
  document.getElementById('kpi-available').textContent=(totalLimit?available:0).toLocaleString('fr-FR')+' FCFA';
  document.getElementById('kpi-available-sub').textContent=totalLimit?Math.round(available/totalLimit*100)+'% restant':'Aucune limite définie';

  // Chart by direction
  const byDir={};
  txs.forEach(t=>{byDir[t.direction]=(byDir[t.direction]||0)+t.amount;});
  const dirs=Object.keys(byDir).sort((a,b)=>byDir[b]-byDir[a]).slice(0,8);
  const colors=['#2563eb','#16a34a','#d97706','#dc2626','#7c3aed','#0891b2','#db2777','#65a30d'];

  if(chartDir) chartDir.destroy();
  chartDir=new Chart(document.getElementById('chartDir'),{
    type:'bar',
    data:{labels:dirs,datasets:[{label:'Montant (FCFA)',data:dirs.map(d=>byDir[d]),backgroundColor:colors}]},
    options:{responsive:true,plugins:{legend:{display:false}},scales:{y:{ticks:{callback:v=>v.toLocaleString('fr-FR')}}}}
  });

  // Chart by month
  const byMonth=Array(12).fill(0);
  txs.forEach(t=>{const m=parseInt((t.date||'').split('-')[1]||1)-1;if(m>=0&&m<12)byMonth[m]+=t.amount;});
  const months=['Jan','Fév','Mar','Avr','Mai','Jui','Jul','Aoû','Sep','Oct','Nov','Déc'];
  if(chartMonth) chartMonth.destroy();
  chartMonth=new Chart(document.getElementById('chartMonth'),{
    type:'line',
    data:{labels:months,datasets:[{label:'Dépenses',data:byMonth,borderColor:'#2563eb',backgroundColor:'rgba(37,99,235,.1)',fill:true,tension:.4}]},
    options:{responsive:true,plugins:{legend:{display:false}},scales:{y:{ticks:{callback:v=>v.toLocaleString('fr-FR')}}}}
  });

  // Budget progress bars
  const prog=document.getElementById('budget-progress');
  prog.innerHTML='';
  if(!limits.length){prog.innerHTML='<div class="empty">Aucune limite budgétaire définie. <a href="#" onclick=\'showTab("budget");return false\'>Définir maintenant →</a></div>';return;}
  limits.forEach(b=>{
    const spent=(byDir[b.direction]||0);
    const pct=b.limit_amount?Math.min(100,Math.round(spent/b.limit_amount*100)):0;
    const col=pct>90?'#dc2626':pct>70?'#d97706':'#16a34a';
    prog.innerHTML+=`
      <div class='budget-item'>
        <div class='brow'><span>${b.direction}</span><span>${spent.toLocaleString('fr-FR')} / ${b.limit_amount.toLocaleString('fr-FR')} FCFA</span></div>
        <div class='bsub'>${pct}% utilisé</div>
        <div class='progress-bar'><div class='progress-fill' style='width:${pct}%;background:${col}'></div></div>
      </div>`;
  });
}

// ── New transaction form ───────────────────────────────────────────────────
function openNew(){
  showTab('transactions');
  // inject inline form above table
  const existing=document.getElementById('inline-form');
  if(existing){existing.remove();return;}
  const form=document.createElement('div');
  form.id='inline-form';
  form.style.cssText='padding:14px;border-bottom:1px solid #e2e8f0;background:#f8fafc;';
  form.innerHTML=`
    <h3 style='font-size:13px;font-weight:600;margin-bottom:10px'>Nouvelle transaction</h3>
    <div style='display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:8px'>
      <div><label style='font-size:11px;color:#64748b'>Code (auto si vide)</label><input id='f_code' placeholder='Code/Ref' style='width:100%'/></div>
      <div><label style='font-size:11px;color:#64748b'>Direction</label><input id='f_dir' value='DRH' style='width:100%'/></div>
      <div><label style='font-size:11px;color:#64748b'>Doc</label><input id='f_doc' value='NC' style='width:100%'/></div>
      <div><label style='font-size:11px;color:#64748b'>Budget line</label><input id='f_budget' value='DRH - 60530000 - CARBURANT' style='width:100%'/></div>
      <div><label style='font-size:11px;color:#64748b'>Libellé</label><input id='f_title' value='CARBURANT ET LUBRIFIANT' style='width:100%'/></div>
      <div><label style='font-size:11px;color:#64748b'>Date</label><input id='f_date' type='date' style='width:100%'/></div>
      <div><label style='font-size:11px;color:#64748b'>Montant (FCFA)</label><input id='f_amount' type='number' value='70000' style='width:100%'/></div>
      <div><label style='font-size:11px;color:#64748b'>Statut</label>
        <select id='f_status' style='width:100%'>
          <option value='validated'>Validée</option>
          <option value='pending'>Brouillon</option>
        </select>
      </div>
    </div>
    <div style='display:flex;gap:8px;margin-top:10px'>
      <button class='btn-primary' onclick='saveNew()'>Enregistrer</button>
      <button class='btn-secondary' onclick='document.getElementById("inline-form").remove()'>Annuler</button>
    </div>
  `;
  const card=document.querySelector('#tab-transactions .card');
  card.insertBefore(form, card.querySelector('div[style*="overflow"]'));
  document.getElementById('f_date').value=new Date().toISOString().slice(0,10);
}

async function saveNew(){
  const payload={
    code: document.getElementById('f_code').value,
    direction: document.getElementById('f_dir').value,
    doc: document.getElementById('f_doc').value,
    budget_line: document.getElementById('f_budget').value,
    title: document.getElementById('f_title').value,
    date: document.getElementById('f_date').value,
    amount: Number(document.getElementById('f_amount').value||0),
    year: Number(document.getElementById('year').value),
    status: document.getElementById('f_status').value,
  };
  const r=await api('/api/tx',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  if(!r) return;
  if(!r.ok){toast('Erreur: '+await r.text(),false);return;}
  toast('Transaction enregistrée ✓');
  document.getElementById('inline-form')?.remove();
  loadTx();
}

// ── Budget limits ──────────────────────────────────────────────────────────
function openBudgetForm(){
  document.getElementById('budget-form-card').style.display='block';
}

async function saveBudgetLimit(){
  const payload={
    direction: document.getElementById('bl-dir').value.trim().toUpperCase(),
    year: Number(document.getElementById('bl-year').value),
    limit_amount: Number(document.getElementById('bl-amount').value||0),
  };
  if(!payload.direction||!payload.year||!payload.limit_amount){toast('Remplissez tous les champs',false);return;}
  const r=await api('/api/budget-limits',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  if(!r) return;
  if(!r.ok){toast('Erreur',false);return;}
  toast('Limite enregistrée ✓');
  document.getElementById('budget-form-card').style.display='none';
  loadBudgets();
}

async function loadBudgets(){
  const year=document.getElementById('year')?document.getElementById('year').value:new Date().getFullYear();
  const [limRes, txRes]=await Promise.all([
    api(`/api/budget-limits?year=${year}`),
    api(`/api/tx?year=${year}&q=&direction=`)
  ]);
  if(!limRes||!txRes) return;
  const limits=await limRes.json();
  const txs=await txRes.json();
  const byDir={};
  txs.forEach(t=>{byDir[t.direction]=(byDir[t.direction]||0)+t.amount;});
  const list=document.getElementById('budget-list');
  if(!limits.length){list.innerHTML='<div class="empty">Aucune limite définie.</div>';return;}
  list.innerHTML=limits.map(b=>{
    const spent=byDir[b.direction]||0;
    const avail=b.limit_amount-spent;
    const pct=b.limit_amount?Math.min(100,Math.round(spent/b.limit_amount*100)):0;
    const col=pct>90?'#dc2626':pct>70?'#d97706':'#16a34a';
    return `<div class='budget-item'>
      <div class='brow'><span>${b.direction}</span>
        <button onclick='deleteBudgetLimit(${b.id})' style='background:none;border:none;cursor:pointer;color:#dc2626;font-size:12px'>✕</button>
      </div>
      <div class='bsub'>Limite: ${b.limit_amount.toLocaleString('fr-FR')} FCFA</div>
      <div class='bsub'>Engagé: ${spent.toLocaleString('fr-FR')} | Disponible: <strong style='color:${avail>=0?"#16a34a":"#dc2626"}'>${avail.toLocaleString('fr-FR')}</strong></div>
      <div class='progress-bar'><div class='progress-fill' style='width:${pct}%;background:${col}'></div></div>
    </div>`;
  }).join('');
}

async function deleteBudgetLimit(id){
  if(!confirm('Supprimer cette limite?')) return;
  const r=await api('/api/budget-limits/'+id,{method:'DELETE'});
  if(!r) return;
  toast('Supprimé');
  loadBudgets();
}

// ── Fiche ──────────────────────────────────────────────────────────────────
function openFiche(id){ window.open('/fiche/'+id,'_blank'); }

// ── Logout ─────────────────────────────────────────────────────────────────
async function logout(){
  await fetch('/api/logout',{method:'POST',credentials:'include'});
  window.location='/login';
}

// ── Directions filter ──────────────────────────────────────────────────────
async function loadDirections(){
  const year=document.getElementById('year').value;
  const r=await api(`/api/tx?year=${year}&q=&direction=`);
  if(!r) return;
  const data=await r.json();
  const dirs=[...new Set(data.map(t=>t.direction))].sort();
  const sel=document.getElementById('filter-dir');
  const cur=sel.value;
  sel.innerHTML='<option value="">Toutes directions</option>';
  dirs.forEach(d=>{const o=document.createElement('option');o.value=d;o.textContent=d;sel.appendChild(o);});
  sel.value=cur;
}

// ── Init ───────────────────────────────────────────────────────────────────
function loadAll(){ loadTx(); loadDirections(); }

initYears();
loadDashboard();
document.getElementById('year')?.addEventListener('change',()=>{loadDashboard();loadAll();});
document.getElementById('search')?.addEventListener('input',()=>{clearTimeout(window.__t);window.__t=setTimeout(loadTx,250);});
document.getElementById('filter-dir')?.addEventListener('change',loadTx);
</script>
</body>
</html>"""


LOGIN_HTML = """<!doctype html>
<html lang='fr'><head><meta charset='utf-8'/><meta name='viewport' content='width=device-width,initial-scale=1'/>
<title>Login – CAMTEL Budget</title>
<style>
body{font-family:'Segoe UI',system-ui,sans-serif;background:#f1f5f9;margin:0;display:flex;min-height:100vh;align-items:center;justify-content:center;}
.card{width:380px;background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:28px;box-shadow:0 4px 12px rgba(0,0,0,.06);}
.logo{background:#1f4d8f;color:#fff;width:44px;height:44px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:18px;margin-bottom:16px;}
h2{margin:0 0 4px;font-size:20px;}
.sub{color:#64748b;font-size:13px;margin-bottom:20px;}
label{display:block;font-size:12px;font-weight:600;color:#475569;margin-bottom:5px;}
input{width:100%;padding:10px 12px;border-radius:8px;border:1px solid #e2e8f0;font-size:14px;margin-bottom:14px;box-sizing:border-box;}
button{width:100%;padding:11px;border-radius:8px;background:#2563eb;color:#fff;border:none;cursor:pointer;font-size:14px;font-weight:600;}
.hint{color:#94a3b8;font-size:12px;margin-top:12px;text-align:center;}
</style></head>
<body>
<div class='card'>
  <div class='logo'>C</div>
  <h2>CAMTEL Budget</h2>
  <div class='sub'>Connectez-vous pour continuer</div>
  <form method='post' action='/api/login'>
    <label>Nom d'utilisateur</label>
    <input name='username' placeholder='admin' required autofocus/>
    <label>Mot de passe</label>
    <input name='password' placeholder='••••••••' type='password' required/>
    <button type='submit'>Se connecter</button>
  </form>
  <div class='hint'>Par défaut: admin / admin123</div>
</div>
</body></html>"""

# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    if not _get_user(request):
        return RedirectResponse("/login")
    return HTMLResponse(INDEX_HTML)


@app.get("/login", response_class=HTMLResponse)
def login_page():
    return HTMLResponse(LOGIN_HTML)


@app.post("/api/login")
def login(username: str = Form(...), password: str = Form(...)):
    if username != ADMIN_USER or password != ADMIN_PASS:
        return HTMLResponse(LOGIN_HTML.replace("Connectez-vous pour continuer", "Identifiants incorrects."), status_code=401)
    token = serializer.dumps({"u": username})
    resp = RedirectResponse("/", status_code=302)
    resp.set_cookie("session", token, httponly=True, samesite="lax")
    return resp


@app.post("/api/login/token")
def login_token(payload: dict):
    """JSON login for Lovable frontend — returns bearer token."""
    if payload.get("username") != ADMIN_USER or payload.get("password") != ADMIN_PASS:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = serializer.dumps({"u": payload["username"]})
    return {"token": token, "user": payload["username"]}


@app.post("/api/logout")
def logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie("session")
    return resp


# ── Transactions ──────────────────────────────────────────────────────────────

@app.get("/api/tx")
def list_tx(request: Request, year: int, q: str = "", direction: str = "", db: sqlite3.Connection = Depends(get_db)):
    require_login(request)
    ql = q.lower().strip()
    query = "SELECT * FROM transactions WHERE year=?"
    params = [year]
    if direction:
        query += " AND direction=?"
        params.append(direction)
    rows = db.execute(query + " ORDER BY id DESC", params).fetchall()
    result = [dict(r) for r in rows]
    if ql:
        result = [t for t in result if ql in t["code"].lower() or ql in t["title"].lower() or ql in t.get("budget_line","").lower()]
    return result


@app.post("/api/tx")
def create_tx(request: Request, payload: dict, db: sqlite3.Connection = Depends(get_db)):
    require_login(request)
    direction = (payload.get("direction") or "DRH").strip()
    doc = (payload.get("doc") or "NC").strip()
    budget_line = (payload.get("budget_line") or "").strip()
    title = (payload.get("title") or "").strip()
    nature = (payload.get("nature") or "DEPENSE COURANTE").strip()
    description = (payload.get("description") or "").strip()
    date = (payload.get("date") or "").strip()
    amount = int(payload.get("amount") or 0)
    year = int(payload.get("year") or 0)
    status = payload.get("status", "validated")

    if not year:
        raise HTTPException(400, "Year required")
    if not date:
        raise HTTPException(400, "Date required")

    code = (payload.get("code") or "").strip()
    if not code:
        cur = db.execute("SELECT COUNT(*) FROM transactions WHERE year=? AND direction=?", (year, direction)).fetchone()
        n = cur[0] + 1
        code = f"SP/{direction}/AA{year % 100:04d}/VD{n:04d}/T{n:05d}"

    cur = db.execute(
        "INSERT INTO transactions (code,direction,doc,budget_line,title,nature,description,date,amount,year,status) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (code, direction, doc, budget_line, title, nature, description, date, amount, year, status)
    )
    db.commit()
    row = db.execute("SELECT * FROM transactions WHERE id=?", (cur.lastrowid,)).fetchone()
    return dict(row)


@app.get("/api/tx/{tx_id}")
def get_tx(request: Request, tx_id: int, db: sqlite3.Connection = Depends(get_db)):
    require_login(request)
    row = db.execute("SELECT * FROM transactions WHERE id=?", (tx_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Not found")
    return dict(row)


@app.delete("/api/tx/{tx_id}")
def delete_tx(request: Request, tx_id: int, db: sqlite3.Connection = Depends(get_db)):
    require_login(request)
    db.execute("DELETE FROM transactions WHERE id=?", (tx_id,))
    db.commit()
    return {"ok": True}


# ── Budget limits ─────────────────────────────────────────────────────────────

@app.get("/api/budget-limits")
def list_budget_limits(request: Request, year: int, db: sqlite3.Connection = Depends(get_db)):
    require_login(request)
    rows = db.execute("SELECT * FROM budget_limits WHERE year=? ORDER BY direction", (year,)).fetchall()
    return [dict(r) for r in rows]


@app.post("/api/budget-limits")
def set_budget_limit(request: Request, payload: dict, db: sqlite3.Connection = Depends(get_db)):
    require_login(request)
    direction = payload.get("direction", "").strip().upper()
    year = int(payload.get("year") or 0)
    limit_amount = int(payload.get("limit_amount") or 0)
    if not direction or not year or not limit_amount:
        raise HTTPException(400, "direction, year, limit_amount required")
    db.execute(
        "INSERT INTO budget_limits (direction, year, limit_amount) VALUES (?,?,?) ON CONFLICT(direction,year) DO UPDATE SET limit_amount=excluded.limit_amount",
        (direction, year, limit_amount)
    )
    db.commit()
    row = db.execute("SELECT * FROM budget_limits WHERE direction=? AND year=?", (direction, year)).fetchone()
    return dict(row)


@app.delete("/api/budget-limits/{limit_id}")
def delete_budget_limit(request: Request, limit_id: int, db: sqlite3.Connection = Depends(get_db)):
    require_login(request)
    db.execute("DELETE FROM budget_limits WHERE id=?", (limit_id,))
    db.commit()
    return {"ok": True}


# ── Dashboard summary ─────────────────────────────────────────────────────────

@app.get("/api/dashboard")
def dashboard(request: Request, year: int, db: sqlite3.Connection = Depends(get_db)):
    require_login(request)
    txs = [dict(r) for r in db.execute("SELECT * FROM transactions WHERE year=?", (year,)).fetchall()]
    limits = [dict(r) for r in db.execute("SELECT * FROM budget_limits WHERE year=?", (year,)).fetchall()]

    by_dir = {}
    for t in txs:
        by_dir[t["direction"]] = by_dir.get(t["direction"], 0) + t["amount"]

    by_month = [0] * 12
    for t in txs:
        try:
            m = int(t["date"].split("-")[1]) - 1
            if 0 <= m < 12:
                by_month[m] += t["amount"]
        except Exception:
            pass

    total_limit = sum(l["limit_amount"] for l in limits)
    total_engaged = sum(t["amount"] for t in txs if t["status"] == "validated")
    total_pending = sum(t["amount"] for t in txs if t["status"] == "pending")

    return {
        "total_limit": total_limit,
        "total_engaged": total_engaged,
        "total_pending": total_pending,
        "available": total_limit - total_engaged - total_pending,
        "by_direction": by_dir,
        "by_month": by_month,
        "limits": limits,
        "tx_count": len(txs),
    }


# ── Fiche ──────────────────────────────────────────────────────────────────────

@app.get("/fiche/{tx_id}", response_class=HTMLResponse)
def fiche(request: Request, tx_id: int, db: sqlite3.Connection = Depends(get_db)):
    user = require_login(request)
    row = db.execute("SELECT * FROM transactions WHERE id=?", (tx_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Not found")
    t = dict(row)
    return HTMLResponse(f"""<!doctype html>
<html><head><meta charset='utf-8'/><title>Fiche {t['code']}</title>
<style>
body{{font-family:Arial,sans-serif;margin:24px;color:#1e293b;}}
h2{{margin:0 0 6px;font-size:18px;}}
.sub{{color:#64748b;font-size:13px;margin-bottom:18px;}}
.box{{border:1px solid #334155;border-radius:8px;padding:18px;}}
.row{{display:flex;justify-content:space-between;margin-bottom:10px;font-size:14px;}}
.row label{{color:#64748b;min-width:140px;}}
.amount{{font-size:20px;font-weight:700;color:#1f4d8f;margin:14px 0;}}
hr{{border:none;border-top:1px solid #e2e8f0;margin:14px 0;}}
small{{color:#94a3b8;font-size:12px;}}
@media print{{button{{display:none;}}}}
</style></head>
<body>
<button onclick='window.print()' style='padding:8px 16px;background:#2563eb;color:#fff;border:none;border-radius:6px;cursor:pointer;margin-bottom:16px'>🖨 Imprimer</button>
<h2>Fiche d'engagement budgétaire</h2>
<div class='sub'>CAMTEL – SAAF / Contrôle Budgétaire</div>
<div class='box'>
  <div class='row'><label>Code/Référence</label><strong>{t['code']}</strong></div>
  <div class='row'><label>Date</label><span>{t['date']}</span></div>
  <div class='row'><label>Direction</label><span>{t['direction']}</span></div>
  <div class='row'><label>Document</label><span>{t['doc']}</span></div>
  <div class='row'><label>Ligne budgétaire</label><span>{t['budget_line']}</span></div>
  <div class='row'><label>Nature</label><span>{t['nature']}</span></div>
  <div class='row'><label>Libellé</label><span>{t['title']}</span></div>
  <hr/>
  <div class='amount'>{t['amount']:,} FCFA</div>
  <hr/>
  <small>Généré par {APP_NAME} – Utilisateur: {user}</small>
</div>
</body></html>""")
