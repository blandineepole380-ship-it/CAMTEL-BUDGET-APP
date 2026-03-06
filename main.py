"""
KPI Manager — Single-file FastAPI app for Render deployment
All logic in one file to simplify deployment.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import os, json

app = FastAPI(
    title="KPI Manager API",
    version="1.0.0",
    docs_url=None,  # disable default docs so we can serve custom
)

# Fix blank /docs — use unpkg CDN for Swagger UI assets
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse

@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui():
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title="KPI Manager API",
        swagger_js_url="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js",
        swagger_css_url="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css",
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── In-memory store (replace with PostgreSQL later) ──────────────────────
db_processes = []
db_kpis      = []
db_periods   = []
db_entries   = []
db_actions   = []
_id          = {"p": 1, "k": 1, "per": 1, "e": 1, "a": 1}

# ── Models ────────────────────────────────────────────────────────────────
class ProcessIn(BaseModel):
    code: str
    name: str
    owner: Optional[str] = None

class KPIIn(BaseModel):
    process_id: int
    name: str
    formula_type: str = "ratio"   # ratio | count | inverse | percentage
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
        if formula == "ratio":
            return round((actual / obj) * 100, 1) if obj else 0
        elif formula == "percentage":
            return round(actual, 1)
        elif formula == "count":
            if target == 0: return 100.0 if actual == 0 else 0.0
            return round(max(0, (1 - (actual - target) / target) * 100), 1)
        elif formula == "inverse":
            return round(min(100, (target / actual) * 100), 1) if actual else 100
    except: return None

def get_color(score, target=100):
    if score is None: return "gray"
    if score >= 100:  return "green"
    if score >= 85:   return "amber"
    return "red"

# ── Routes ─────────────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {"status": "ok", "message": "KPI Manager API", "version": "1.0.0",
            "docs": "/docs", "timestamp": datetime.utcnow().isoformat()}

@app.get("/api/health")
def health():
    return {"status": "healthy"}

# Processes
@app.get("/api/processes")
def list_processes(): return db_processes

@app.post("/api/processes")
def create_process(data: ProcessIn):
    p = {"id": _id["p"], **data.model_dump(), "active": True, "created_at": str(datetime.utcnow())}
    db_processes.append(p); _id["p"] += 1
    return p

# KPIs
@app.get("/api/kpis")
def list_kpis(process_id: Optional[int] = None):
    if process_id: return [k for k in db_kpis if k["process_id"] == process_id]
    return db_kpis

@app.post("/api/kpis")
def create_kpi(data: KPIIn):
    k = {"id": _id["k"], **data.model_dump(), "active": True, "created_at": str(datetime.utcnow())}
    db_kpis.append(k); _id["k"] += 1
    return k

# Periods
@app.get("/api/periods")
def list_periods(): return db_periods

@app.post("/api/periods")
def create_period(data: PeriodIn):
    for p in db_periods:
        if p["year"] == data.year and p["month"] == data.month:
            raise HTTPException(400, "Period already exists")
    p = {"id": _id["per"], **data.model_dump(), "status": "open",
         "created_at": str(datetime.utcnow())}
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

# Entries
@app.post("/api/entries")
def save_entry(data: EntryIn):
    kpi = next((k for k in db_kpis if k["id"] == data.kpi_id), None)
    if not kpi: raise HTTPException(404, "KPI not found")

    score = calc_score(kpi["formula_type"], data.actual_value,
                       data.objective_value, kpi["target_value"])
    color = get_color(score)

    # update existing
    for e in db_entries:
        if e["kpi_id"] == data.kpi_id and e["period_id"] == data.period_id:
            e.update({**data.model_dump(), "calculated_score": score,
                      "status_color": color, "updated_at": str(datetime.utcnow())})
            return e

    entry = {"id": _id["e"], **data.model_dump(), "calculated_score": score,
             "status_color": color, "status": "draft",
             "created_at": str(datetime.utcnow()), "updated_at": str(datetime.utcnow())}
    db_entries.append(entry); _id["e"] += 1
    return entry

@app.get("/api/entries/period/{period_id}")
def get_entries(period_id: int):
    return [e for e in db_entries if e["period_id"] == period_id]

# Summary
@app.get("/api/reports/summary/{period_id}")
def get_summary(period_id: int):
    period = next((p for p in db_periods if p["id"] == period_id), None)
    if not period: raise HTTPException(404, "Period not found")

    entries_map = {e["kpi_id"]: e for e in db_entries if e["period_id"] == period_id}
    proc_map    = {p["id"]: p for p in db_processes}

    rows = []
    for kpi in db_kpis:
        e     = entries_map.get(kpi["id"])
        score = e["calculated_score"] if e else None
        color = e["status_color"]     if e else "gray"
        proc  = proc_map.get(kpi["process_id"], {})
        rows.append({
            "kpi_name":    kpi["name"],
            "process_name": proc.get("name", "—"),
            "objective":   e["objective_value"] if e else None,
            "actual":      e["actual_value"]    if e else None,
            "score":       score,
            "color":       color,
            "comment":     e["comment"] if e else None,
        })

    achieved     = sum(1 for r in rows if r["color"] == "green")
    at_risk      = sum(1 for r in rows if r["color"] == "amber")
    not_achieved = sum(1 for r in rows if r["color"] == "red")
    missing      = sum(1 for r in rows if r["color"] == "gray")
    total        = len(rows)

    return {
        "period":           period,
        "total_kpis":       total,
        "achieved":         achieved,
        "at_risk":          at_risk,
        "not_achieved":     not_achieved,
        "missing":          missing,
        "achievement_rate": round(achieved / total * 100, 1) if total else 0,
        "top_kpis":         sorted([r for r in rows if r["score"]], key=lambda x: -x["score"])[:5],
        "bottom_kpis":      sorted([r for r in rows if r["score"]], key=lambda x: x["score"])[:5],
        "kpis":             rows,
    }

# Actions
@app.post("/api/reports/actions")
def create_action(data: ActionIn):
    a = {"id": _id["a"], **data.model_dump(), "status": "open",
         "created_at": str(datetime.utcnow())}
    db_actions.append(a); _id["a"] += 1
    return a

@app.get("/api/reports/actions/{period_id}")
def get_actions(period_id: int):
    return [a for a in db_actions if a["period_id"] == period_id]

@app.get("/api/reports/generate-pptx/{period_id}")
def generate_pptx_info(period_id: int):
    return {
        "message": "PowerPoint generation requires Node.js + pptxgenjs.",
        "setup": "Run locally with the full kpi-backend package for .pptx export.",
        "summary_url": f"/api/reports/summary/{period_id}"
    }
