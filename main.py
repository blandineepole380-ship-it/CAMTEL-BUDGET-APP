from __future__ import annotations

import os
import sys
sys.path.insert(0, os.path.dirname(__file__))  # ensure `app/` is importable
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import FastAPI, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sqlalchemy.orm import Session
from sqlalchemy import func

from db import SessionLocal, init_db
import models
from security import verify_password, hash_password, create_access_token, decode_token
from pdf import build_fiche_pdf

APP_NAME = "CAMTEL Budget App"

app = FastAPI(title=APP_NAME)

BASE_DIR = os.path.dirname(__file__)
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

# Always mount static, but ONLY if directory exists (prevent the error you had)
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

templates = Jinja2Templates(directory=TEMPLATES_DIR)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.on_event("startup")
def _startup():
    init_db()
    # seed admin user if configured and not exists
    admin_user = os.getenv("ADMIN_USERNAME")
    admin_pass = os.getenv("ADMIN_PASSWORD")
    if admin_user and admin_pass:
        db = SessionLocal()
        try:
            u = db.query(models.User).filter(models.User.username == admin_user).first()
            if not u:
                u = models.User(
                    username=admin_user,
                    password_hash=hash_password(admin_pass),
                    role=models.UserRole.admin,
                    is_active=True,
                )
                db.add(u)
                db.commit()
        finally:
            db.close()


# ---------------- Auth helpers ----------------

def current_user(request: Request, db: Session = Depends(get_db)) -> models.User:
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not logged in")
    data = decode_token(token)
    if not data or "sub" not in data:
        raise HTTPException(status_code=401, detail="Invalid token")
    u = db.query(models.User).filter(models.User.id == int(data["sub"])).first()
    if not u or not u.is_active:
        raise HTTPException(status_code=401, detail="User not found")
    return u


def require_admin(u: models.User = Depends(current_user)) -> models.User:
    if u.role != models.UserRole.admin:
        raise HTTPException(status_code=403, detail="Admin only")
    return u


# ---------------- Pages ----------------

@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    # if logged in => go to transactions
    token = request.cookies.get("access_token")
    if token:
        try:
            decode_token(token)
            return RedirectResponse(url="/transactions", status_code=302)
        except Exception:
            pass
    return RedirectResponse(url="/login", status_code=302)


@app.get("/login", response_class=HTMLResponse)
def login_get(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "app_name": APP_NAME})


@app.post("/login")
def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    u = db.query(models.User).filter(models.User.username == username).first()
    if not u or not verify_password(password, u.password_hash) or not u.is_active:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "app_name": APP_NAME, "error": "Invalid username or password"},
            status_code=401,
        )

    token = create_access_token(subject=str(u.id))
    resp = RedirectResponse(url="/transactions", status_code=302)
    resp.set_cookie("access_token", token, httponly=True, samesite="lax")
    return resp


@app.get("/logout")
def logout():
    resp = RedirectResponse(url="/login", status_code=302)
    resp.delete_cookie("access_token")
    return resp


@app.get("/admin/users", response_class=HTMLResponse)
def admin_users(request: Request, db: Session = Depends(get_db), me: models.User = Depends(require_admin)):
    users = db.query(models.User).order_by(models.User.username).all()
    return templates.TemplateResponse(
        "admin_users.html",
        {"request": request, "app_name": APP_NAME, "me": me, "users": users},
    )


@app.post("/admin/users/create")
def admin_users_create(
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    db: Session = Depends(get_db),
    me: models.User = Depends(require_admin),
):
    if db.query(models.User).filter(models.User.username == username).first():
        raise HTTPException(status_code=400, detail="Username already exists")
    u = models.User(
        username=username,
        password_hash=hash_password(password),
        role=models.UserRole(role),
        is_active=True,
    )
    db.add(u)
    db.commit()
    return RedirectResponse(url="/admin/users", status_code=302)


@app.get("/admin/budget-lines", response_class=HTMLResponse)
def admin_budget_lines(request: Request, db: Session = Depends(get_db), me: models.User = Depends(require_admin)):
    year = int(request.query_params.get("year", datetime.now().year))
    lines = (
        db.query(models.BudgetLine)
        .filter(models.BudgetLine.year == year)
        .order_by(models.BudgetLine.department, models.BudgetLine.code)
        .all()
    )

    engaged_rows = (
        db.query(models.Transaction.budget_line_id, func.coalesce(func.sum(models.Transaction.amount), 0.0))
        .filter(models.Transaction.year == year)
        .group_by(models.Transaction.budget_line_id)
        .all()
    )
    engaged_map = {bid: float(total) for bid, total in engaged_rows}
    return templates.TemplateResponse(
        "admin_budget_lines.html",
        {"request": request, "app_name": APP_NAME, "me": me, "year": year, "lines": lines},
    )


@app.post("/admin/budget-lines/create")
def admin_budget_lines_create(
    year: int = Form(...),
    department: str = Form(...),
    code: str = Form(...),
    title: str = Form(...),
    cp: float = Form(...),
    db: Session = Depends(get_db),
    me: models.User = Depends(require_admin),
):
    bl = models.BudgetLine(year=year, department=department, code=code, title=title, cp=cp)
    db.add(bl)
    db.commit()
    return RedirectResponse(url=f"/admin/budget-lines?year={year}", status_code=302)


@app.get("/transactions", response_class=HTMLResponse)
def transactions_list(
    request: Request,
    db: Session = Depends(get_db),
    me: models.User = Depends(current_user),
):
    year = int(request.query_params.get("year", datetime.now().year))
    dept = request.query_params.get("dept", "")
    doc = request.query_params.get("doc", "")
    q = request.query_params.get("q", "").strip()

    query = db.query(models.Transaction).filter(models.Transaction.year == year)

    # Department filter: BUM/DIG/DRH
    if dept:
        query = query.filter(models.Transaction.department == dept)

    if doc:
        query = query.filter(models.Transaction.doc_type == doc)

    if q:
        like = f"%{q}%"
        query = query.filter(
            (models.Transaction.code_ref.ilike(like))
            | (models.Transaction.title.ilike(like))
            | (models.Transaction.budget_line_code.ilike(like))
        )

    txs = query.order_by(models.Transaction.created_at.desc()).limit(500).all()

    # dropdown data
    years = [y[0] for y in db.query(models.Transaction.year).distinct().order_by(models.Transaction.year.desc()).all()]
    if year not in years:
        years = [year] + years

    departments = ["", "BUM", "DIG", "DRH"]
    docs = ["", "OM", "BC", "AUTRE"]

    return templates.TemplateResponse(
        "transactions.html",
        {
            "request": request,
            "app_name": APP_NAME,
            "me": me,
            "year": year,
            "dept": dept,
            "doc": doc,
            "q": q,
            "years": years,
            "departments": departments,
            "docs": docs,
            "txs": txs,
        },
    )


@app.get("/transactions/new", response_class=HTMLResponse)
def transactions_new_get(
    request: Request,
    db: Session = Depends(get_db),
    me: models.User = Depends(current_user),
):
    year = int(request.query_params.get("year", datetime.now().year))
    department = request.query_params.get("dept", "BUM")

    # Budget lines filtered by department
    lines = (
        db.query(models.BudgetLine)
        .filter(models.BudgetLine.year == year)
        .filter(models.BudgetLine.department == department)
        .order_by(models.BudgetLine.code)
        .all()
    )

    return templates.TemplateResponse(
        "transaction_new.html",
        {
            "request": request,
            "app_name": APP_NAME,
            "me": me,
            "year": year,
            "department": department,
            "lines": lines,
            "engaged_map": engaged_map,
        },
    )


@app.post("/transactions/new")
def transactions_new_post(
    me: models.User = Depends(current_user),
    db: Session = Depends(get_db),
    year: int = Form(...),
    department: str = Form(...),
    doc_type: str = Form(...),
    budget_line_id: int = Form(...),
    code_ref: str = Form(""),
    title: str = Form(""),
    date_doc: str = Form(""),
    # OM fields
    date_aller: str = Form(""),
    date_retour: str = Form(""),
    amount_per_day: float = Form(0.0),
    # BC fields
    ht: float = Form(0.0),
    ir_rate: float = Form(0.0),
    # Other doc type amount
    amount_other: float = Form(0.0),
):
    bl = db.query(models.BudgetLine).filter(models.BudgetLine.id == budget_line_id).first()
    if not bl:
        raise HTTPException(status_code=400, detail="Budget line not found")

    # Parse dates
    def parse_date(s: str) -> Optional[datetime]:
        s = (s or "").strip()
        if not s:
            return None
        return datetime.fromisoformat(s)

    d_doc = parse_date(date_doc)
    d_aller = parse_date(date_aller)
    d_retour = parse_date(date_retour)

    tx = models.Transaction(
        year=year,
        department=department,
        doc_type=doc_type,
        budget_line_id=bl.id,
        budget_line_code=bl.code,
        budget_line_title=bl.title,
        code_ref=code_ref,
        title=title,
        date_doc=d_doc,
        created_by=me.username,
    )

    # OM auto-calculation
    if doc_type == "OM":
        tx.om_date_aller = d_aller
        tx.om_date_retour = d_retour
        tx.om_amount_per_day = amount_per_day
        if d_aller and d_retour:
            days = (d_retour.date() - d_aller.date()).days + 1
            if days < 0:
                days = 0
            tx.om_days = days
            tx.amount = round(days * amount_per_day, 2)
        else:
            tx.om_days = 0
            tx.amount = 0.0

    # BC Cameroon tax system
    elif doc_type == "BC":
        tx.bc_ht = ht
        tx.bc_tva_rate = 0.1925
        tx.bc_ir_rate = ir_rate
        tva = round(ht * 0.1925, 2)
        ir = round(ht * (ir_rate / 100.0), 2) if ir_rate else 0.0
        total_tax = round(tva + ir, 2)
        ttc = round(ht + tva, 2)
        net = round(ttc - ir, 2)
        tx.bc_tva = tva
        tx.bc_ir = ir
        tx.bc_total_tax = total_tax
        tx.bc_ttc = ttc
        tx.bc_net = net
        tx.amount = net

    else:
        # Other doc type: manual amount
        tx.amount = float(amount_other or 0.0)

    db.add(tx)
    db.commit()

    return RedirectResponse(url=f"/transactions?year={year}&dept={department}", status_code=302)

@app.post("/transactions/delete")
def transactions_delete(
    me: models.User = Depends(current_user),
    db: Session = Depends(get_db),
    tx_id: int = Form(...),
):
    tx = db.query(models.Transaction).filter(models.Transaction.id == tx_id).first()
    if not tx:
        raise HTTPException(status_code=404, detail="Not found")
    # only admin can delete
    if me.role != models.UserRole.admin:
        raise HTTPException(status_code=403, detail="Admin only")
    year = tx.year
    dept = tx.department
    db.delete(tx)
    db.commit()
    return RedirectResponse(url=f"/transactions?year={year}&dept={dept}", status_code=302)


@app.post("/fiche/pdf")
def fiche_pdf(
    request: Request,
    me: models.User = Depends(current_user),
    db: Session = Depends(get_db),
    tx_ids: str = Form(...),  # comma-separated ids in exact order
):
    ids = [int(x) for x in tx_ids.split(",") if x.strip().isdigit()]
    if len(ids) == 0:
        raise HTTPException(status_code=400, detail="Select at least 1 transaction")
    if len(ids) > 2:
        ids = ids[:2]

    txs = db.query(models.Transaction).filter(models.Transaction.id.in_(ids)).all()
    # preserve order
    tx_map = {t.id: t for t in txs}
    ordered = [tx_map[i] for i in ids if i in tx_map]

    pdf_bytes = build_fiche_pdf(ordered, logo_path=os.path.join(STATIC_DIR, "img", "logo.png"))

    return StreamingResponse(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "inline; filename=fiche.pdf"},
    )
