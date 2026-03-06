"""
KPI Manager — Single-file FastAPI app for Render deployment
Custom HTML docs page with zero external dependencies.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

app = FastAPI(title="KPI Manager API", version="1.0.0", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── In-memory store ───────────────────────────────────────────────────────
db_processes, db_kpis, db_periods, db_entries, db_actions = [], [], [], [], []
_id = {"p": 1, "k": 1, "per": 1, "e": 1, "a": 1}

# ── Models ────────────────────────────────────────────────────────────────
class ProcessIn(BaseModel):
    code: str
    name: str
    owner: Optional[str] = None

class KPIIn(BaseModel):
    process_id: int
    name: str
    formula_type: str = "ratio"
    target_value: float
    unit: str = "%"
    frequency: str = "monthly"
    evidence_required: Optional[str] = None
    owner: Optional[str] = None

class PeriodIn(BaseModel):
    year: int
    month: int

class EntryIn(BaseModel):
    kpi_id: int
    period_id: int
    objective_value: Optional[float] = None
    actual_value: Optional[float] = None
    comment: Optional[str] = None
    submitted_by: Optional[str] = None

class ActionIn(BaseModel):
    period_id: int
    kpi_id: Optional[int] = None
    issue: str
    corrective_action: str
    owner: str
    due_date: Optional[str] = None

# ── Calculator ─────────────────────────────────────────────────────────────
def calc_score(formula, actual, objective, target):
    if actual is None: return None
    obj = objective if objective else target
    try:
        if formula == "ratio":      return round((actual / obj) * 100, 1) if obj else 0
        elif formula == "percentage": return round(actual, 1)
        elif formula == "count":
            if target == 0: return 100.0 if actual == 0 else 0.0
            return round(max(0, (1 - (actual - target) / target) * 100), 1)
        elif formula == "inverse":  return round(min(100, (target / actual) * 100), 1) if actual else 100
    except: return None

def get_color(score):
    if score is None: return "gray"
    if score >= 100:  return "green"
    if score >= 85:   return "amber"
    return "red"

# ── Custom Docs Page (zero external deps) ─────────────────────────────────
@app.get("/docs", response_class=HTMLResponse, include_in_schema=False)
async def docs():
    return """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>KPI Manager API</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:'Segoe UI',sans-serif;background:#0a0d14;color:#e2e8f0;min-height:100vh}
  header{background:#1e2761;padding:24px 32px;border-bottom:3px solid #f5c518}
  header h1{font-size:24px;font-weight:900;color:#fff}
  header p{color:#cadcfc;font-size:13px;margin-top:4px}
  .badge{background:#f5c51822;color:#f5c518;border:1px solid #f5c51844;border-radius:4px;padding:2px 10px;font-size:11px;font-weight:700;margin-left:10px}
  main{max-width:960px;margin:0 auto;padding:32px 24px}
  .base-url{background:#151b2e;border:1px solid #1e2840;border-radius:10px;padding:14px 20px;margin-bottom:28px;font-size:14px;color:#cadcfc}
  .base-url span{color:#22c55e;font-weight:700;font-size:16px}
  .section{margin-bottom:32px}
  .section-title{font-size:11px;font-weight:700;color:#3b82f6;letter-spacing:2px;text-transform:uppercase;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid #1e2840}
  .endpoint{background:#151b2e;border:1px solid #1e2840;border-radius:12px;margin-bottom:10px;overflow:hidden}
  .ep-header{display:flex;align-items:center;gap:12px;padding:14px 18px;cursor:pointer;user-select:none}
  .ep-header:hover{background:#1a2235}
  .method{font-size:11px;font-weight:900;padding:4px 10px;border-radius:6px;min-width:52px;text-align:center;letter-spacing:1px}
  .GET{background:#22c55e22;color:#22c55e;border:1px solid #22c55e44}
  .POST{background:#3b82f622;color:#3b82f6;border:1px solid #3b82f644}
  .path{font-family:monospace;font-size:13px;color:#e2e8f0;font-weight:600}
  .desc{color:#64748b;font-size:12px;margin-left:auto}
  .ep-body{display:none;padding:0 18px 16px;border-top:1px solid #1e2840}
  .ep-body.open{display:block}
  .try-btn{background:#3b82f6;color:#fff;border:none;border-radius:8px;padding:8px 18px;font-size:13px;font-weight:700;cursor:pointer;margin-top:12px}
  .try-btn:hover{background:#2563eb}
  .input-row{margin-top:10px}
  .input-row label{font-size:11px;color:#64748b;font-weight:600;display:block;margin-bottom:4px;text-transform:uppercase;letter-spacing:0.5px}
  .input-row input,textarea{width:100%;background:#0a0d14;border:1px solid #1e2840;border-radius:8px;padding:10px 12px;color:#e2e8f0;font-size:13px;font-family:monospace;outline:none}
  .input-row input:focus,textarea:focus{border-color:#3b82f6}
  textarea{min-height:90px;resize:vertical}
  .result{margin-top:12px;background:#0a0d14;border:1px solid #1e2840;border-radius:8px;padding:14px;font-family:monospace;font-size:12px;color:#22c55e;white-space:pre-wrap;max-height:300px;overflow-y:auto;display:none}
  .result.error{color:#ef4444}
  .result.show{display:block}
  .status-dot{width:8px;height:8px;border-radius:50%;background:#22c55e;display:inline-block;margin-right:6px;animation:pulse 2s infinite}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
</style>
</head>
<body>
<header>
  <h1>⚡ KPI Manager API <span class="badge">v1.0.0</span></h1>
  <p><span class="status-dot"></span>Live · Monthly KPI tracking & reporting platform</p>
</header>
<main>
  <div class="base-url">Base URL: <span id="baseUrl"></span><script>document.getElementById('baseUrl').textContent=window.location.origin</script></div>

  <div class="section">
    <div class="section-title">📋 Processes</div>
    <div class="endpoint">
      <div class="ep-header" onclick="toggle(this)">
        <span class="method GET">GET</span><span class="path">/api/processes</span><span class="desc">List all processes</span>
      </div>
      <div class="ep-body">
        <button class="try-btn" onclick="call('GET','/api/processes',null,this)">▶ Try it</button>
        <pre class="result"></pre>
      </div>
    </div>
    <div class="endpoint">
      <div class="ep-header" onclick="toggle(this)">
        <span class="method POST">POST</span><span class="path">/api/processes</span><span class="desc">Create a process</span>
      </div>
      <div class="ep-body">
        <div class="input-row"><label>Body (JSON)</label>
        <textarea>{"code": "FIN", "name": "Mobilisation des Ressources Financières", "owner": "Direction Financière"}</textarea></div>
        <button class="try-btn" onclick="callWithBody('/api/processes',this)">▶ Try it</button>
        <pre class="result"></pre>
      </div>
    </div>
  </div>

  <div class="section">
    <div class="section-title">📊 KPIs</div>
    <div class="endpoint">
      <div class="ep-header" onclick="toggle(this)">
        <span class="method GET">GET</span><span class="path">/api/kpis</span><span class="desc">List all KPIs</span>
      </div>
      <div class="ep-body">
        <button class="try-btn" onclick="call('GET','/api/kpis',null,this)">▶ Try it</button>
        <pre class="result"></pre>
      </div>
    </div>
    <div class="endpoint">
      <div class="ep-header" onclick="toggle(this)">
        <span class="method POST">POST</span><span class="path">/api/kpis</span><span class="desc">Create a KPI</span>
      </div>
      <div class="ep-body">
        <div class="input-row"><label>Body (JSON)</label>
        <textarea>{"process_id": 1, "name": "Taux de réalisation des Recettes", "formula_type": "ratio", "target_value": 90, "unit": "%", "frequency": "monthly"}</textarea></div>
        <button class="try-btn" onclick="callWithBody('/api/kpis',this)">▶ Try it</button>
        <pre class="result"></pre>
      </div>
    </div>
  </div>

  <div class="section">
    <div class="section-title">📅 Periods</div>
    <div class="endpoint">
      <div class="ep-header" onclick="toggle(this)">
        <span class="method GET">GET</span><span class="path">/api/periods</span><span class="desc">List all periods</span>
      </div>
      <div class="ep-body">
        <button class="try-btn" onclick="call('GET','/api/periods',null,this)">▶ Try it</button>
        <pre class="result"></pre>
      </div>
    </div>
    <div class="endpoint">
      <div class="ep-header" onclick="toggle(this)">
        <span class="method POST">POST</span><span class="path">/api/periods</span><span class="desc">Open a new period</span>
      </div>
      <div class="ep-body">
        <div class="input-row"><label>Body (JSON)</label>
        <textarea>{"year": 2025, "month": 12}</textarea></div>
        <button class="try-btn" onclick="callWithBody('/api/periods',this)">▶ Try it</button>
        <pre class="result"></pre>
      </div>
    </div>
  </div>

  <div class="section">
    <div class="section-title">✏️ Data Entry</div>
    <div class="endpoint">
      <div class="ep-header" onclick="toggle(this)">
        <span class="method POST">POST</span><span class="path">/api/entries</span><span class="desc">Save KPI value (auto-calculates score)</span>
      </div>
      <div class="ep-body">
        <div class="input-row"><label>Body (JSON)</label>
        <textarea>{"kpi_id": 1, "period_id": 1, "objective_value": 100, "actual_value": 94, "comment": "Bon mois", "submitted_by": "Jean"}</textarea></div>
        <button class="try-btn" onclick="callWithBody('/api/entries',this)">▶ Try it</button>
        <pre class="result"></pre>
      </div>
    </div>
    <div class="endpoint">
      <div class="ep-header" onclick="toggle(this)">
        <span class="method GET">GET</span><span class="path">/api/entries/period/{id}</span><span class="desc">Get all entries for a period</span>
      </div>
      <div class="ep-body">
        <div class="input-row"><label>Period ID</label><input id="ep_period_id" value="1" type="number"></div>
        <button class="try-btn" onclick="call('GET','/api/entries/period/'+document.getElementById('ep_period_id').value,null,this)">▶ Try it</button>
        <pre class="result"></pre>
      </div>
    </div>
  </div>

  <div class="section">
    <div class="section-title">📈 Reports</div>
    <div class="endpoint">
      <div class="ep-header" onclick="toggle(this)">
        <span class="method GET">GET</span><span class="path">/api/reports/summary/{id}</span><span class="desc">Full monthly summary</span>
      </div>
      <div class="ep-body">
        <div class="input-row"><label>Period ID</label><input id="rp_period_id" value="1" type="number"></div>
        <button class="try-btn" onclick="call('GET','/api/reports/summary/'+document.getElementById('rp_period_id').value,null,this)">▶ Try it</button>
        <pre class="result"></pre>
      </div>
    </div>
    <div class="endpoint">
      <div class="ep-header" onclick="toggle(this)">
        <span class="method POST">POST</span><span class="path">/api/reports/actions</span><span class="desc">Add corrective action</span>
      </div>
      <div class="ep-body">
        <div class="input-row"><label>Body (JSON)</label>
        <textarea>{"period_id": 1, "issue": "Recettes en dessous de l'objectif", "corrective_action": "Relance commerciale intensive", "owner": "Direction Commerciale", "due_date": "31/01/2026"}</textarea></div>
        <button class="try-btn" onclick="callWithBody('/api/reports/actions',this)">▶ Try it</button>
        <pre class="result"></pre>
      </div>
    </div>
  </div>
</main>
<script>
function toggle(header){
  const body=header.nextElementSibling;
  body.classList.toggle('open');
}
async function call(method,path,body,btn){
  const result=btn.nextElementSibling;
  result.className='result show';
  result.textContent='Loading...';
  try{
    const opts={method,headers:{'Content-Type':'application/json'}};
    if(body) opts.body=JSON.stringify(body);
    const r=await fetch(window.location.origin+path,opts);
    const data=await r.json();
    result.textContent=JSON.stringify(data,null,2);
    result.className='result show'+(r.ok?'':' error');
  }catch(e){result.textContent='Error: '+e.message;result.className='result show error';}
}
function callWithBody(path,btn){
  const ta=btn.previousElementSibling.querySelector('textarea');
  try{const body=JSON.parse(ta.value);call('POST',path,body,btn);}
  catch(e){const r=btn.nextElementSibling;r.className='result show error';r.textContent='Invalid JSON: '+e.message;}
}
</script>
</body>
</html>"""

# ── API Routes ─────────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {"status": "ok", "message": "KPI Manager API", "version": "1.0.0",
            "docs": "/docs", "timestamp": datetime.utcnow().isoformat()}

@app.get("/api/health")
def health():
    return {"status": "healthy"}

@app.get("/api/processes")
def list_processes(): return db_processes

@app.post("/api/processes")
def create_process(data: ProcessIn):
    p = {"id": _id["p"], **data.model_dump(), "active": True, "created_at": str(datetime.utcnow())}
    db_processes.append(p); _id["p"] += 1
    return p

@app.get("/api/kpis")
def list_kpis(process_id: Optional[int] = None):
    if process_id: return [k for k in db_kpis if k["process_id"] == process_id]
    return db_kpis

@app.post("/api/kpis")
def create_kpi(data: KPIIn):
    k = {"id": _id["k"], **data.model_dump(), "active": True, "created_at": str(datetime.utcnow())}
    db_kpis.append(k); _id["k"] += 1
    return k

@app.get("/api/periods")
def list_periods(): return db_periods

@app.post("/api/periods")
def create_period(data: PeriodIn):
    for p in db_periods:
        if p["year"] == data.year and p["month"] == data.month:
            raise HTTPException(400, "Period already exists")
    p = {"id": _id["per"], **data.model_dump(), "status": "open", "created_at": str(datetime.utcnow())}
    db_periods.append(p); _id["per"] += 1
    return p

@app.post("/api/periods/{period_id}/lock")
def lock_period(period_id: int, closed_by: str = "admin"):
    for p in db_periods:
        if p["id"] == period_id:
            p["status"] = "locked"; p["closed_by"] = closed_by
            p["closed_at"] = str(datetime.utcnow())
            return p
    raise HTTPException(404, "Period not found")

@app.post("/api/entries")
def save_entry(data: EntryIn):
    kpi = next((k for k in db_kpis if k["id"] == data.kpi_id), None)
    if not kpi: raise HTTPException(404, "KPI not found")
    score = calc_score(kpi["formula_type"], data.actual_value, data.objective_value, kpi["target_value"])
    color = get_color(score)
    for e in db_entries:
        if e["kpi_id"] == data.kpi_id and e["period_id"] == data.period_id:
            e.update({**data.model_dump(), "calculated_score": score, "status_color": color,
                      "updated_at": str(datetime.utcnow())})
            return e
    entry = {"id": _id["e"], **data.model_dump(), "calculated_score": score,
             "status_color": color, "status": "draft", "created_at": str(datetime.utcnow()),
             "updated_at": str(datetime.utcnow())}
    db_entries.append(entry); _id["e"] += 1
    return entry

@app.get("/api/entries/period/{period_id}")
def get_entries(period_id: int):
    return [e for e in db_entries if e["period_id"] == period_id]

@app.get("/api/reports/summary/{period_id}")
def get_summary(period_id: int):
    period = next((p for p in db_periods if p["id"] == period_id), None)
    if not period: raise HTTPException(404, "Period not found")
    entries_map = {e["kpi_id"]: e for e in db_entries if e["period_id"] == period_id}
    proc_map = {p["id"]: p for p in db_processes}
    rows = []
    for kpi in db_kpis:
        e = entries_map.get(kpi["id"])
        score = e["calculated_score"] if e else None
        color = e["status_color"] if e else "gray"
        proc = proc_map.get(kpi["process_id"], {})
        rows.append({"kpi_name": kpi["name"], "process_name": proc.get("name", "—"),
                     "objective": e["objective_value"] if e else None,
                     "actual": e["actual_value"] if e else None,
                     "score": score, "color": color, "comment": e["comment"] if e else None})
    achieved = sum(1 for r in rows if r["color"] == "green")
    at_risk = sum(1 for r in rows if r["color"] == "amber")
    not_achieved = sum(1 for r in rows if r["color"] == "red")
    missing = sum(1 for r in rows if r["color"] == "gray")
    total = len(rows)
    return {"period": period, "total_kpis": total, "achieved": achieved, "at_risk": at_risk,
            "not_achieved": not_achieved, "missing": missing,
            "achievement_rate": round(achieved / total * 100, 1) if total else 0,
            "top_kpis": sorted([r for r in rows if r["score"]], key=lambda x: -x["score"])[:5],
            "bottom_kpis": sorted([r for r in rows if r["score"]], key=lambda x: x["score"])[:5],
            "kpis": rows}

@app.post("/api/reports/actions")
def create_action(data: ActionIn):
    a = {"id": _id["a"], **data.model_dump(), "status": "open", "created_at": str(datetime.utcnow())}
    db_actions.append(a); _id["a"] += 1
    return a

@app.get("/api/reports/actions/{period_id}")
def get_actions(period_id: int):
    return [a for a in db_actions if a["period_id"] == period_id]
