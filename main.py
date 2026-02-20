import os
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from sqlalchemy.exc import IntegrityError

from passlib.context import CryptContext
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./camtel_budget.db")
SECRET_KEY = os.getenv("SECRET_KEY", "change-me")
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "admin123")

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
signer = URLSafeTimedSerializer(SECRET_KEY, salt="camtel-budget-session")

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), default="user")      # admin/user
    department = Column(String(10), default="BUM") # BUM/DIG/DRH

class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by = Column(String(100), nullable=False)

    year = Column(Integer, default=lambda: datetime.utcnow().year, index=True)
    department = Column(String(10), nullable=False)
    doc_type = Column(String(10), nullable=False)   # OM/BC/OTHER

    code_ref = Column(String(50), nullable=True)
    direction = Column(String(50), nullable=True)
    doc = Column(String(100), nullable=True)

    budget_line = Column(String(200), nullable=False)
    amount_fcfa = Column(Float, default=0.0)
    status = Column(String(30), default="Draft")
    tx_date = Column(String(20), default=lambda: datetime.utcnow().strftime("%Y-%m-%d"))

    # OM
    date_aller = Column(String(20), nullable=True)
    date_retour = Column(String(20), nullable=True)
    days = Column(Integer, nullable=True)
    amount_per_day = Column(Float, nullable=True)
    om_total = Column(Float, nullable=True)

    # BC
    ht = Column(Float, nullable=True)
    tva = Column(Float, nullable=True)
    ir_rate = Column(Float, nullable=True)
    total_tax = Column(Float, nullable=True)
    net_a_payer = Column(Float, nullable=True)
    ttc = Column(Float, nullable=True)

Base.metadata.create_all(engine)

def db_dep() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def hash_pw(p: str) -> str:
    return pwd_ctx.hash(p)

def verify_pw(p: str, h: str) -> bool:
    return pwd_ctx.verify(p, h)

def ensure_admin(db: Session):
    admin = db.query(User).filter(User.username == ADMIN_USER).first()
    if not admin:
        admin = User(username=ADMIN_USER, password_hash=hash_pw(ADMIN_PASS), role="admin", department="BUM")
        db.add(admin)
        db.commit()

def get_current_user(request: Request, db: Session = Depends(db_dep)) -> User:
    token = request.cookies.get("session")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    try:
        payload = signer.loads(token, max_age=60*60*24*7)
    except (SignatureExpired, BadSignature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    username = payload.get("u")
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return user

def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(403, "Admin only")
    return user

def apply_om_calc(t: dict) -> dict:
    try:
        da, dr = t.get("date_aller"), t.get("date_retour")
        apd = float(t.get("amount_per_day") or 0)
        if da and dr:
            d1 = datetime.strptime(da, "%Y-%m-%d").date()
            d2 = datetime.strptime(dr, "%Y-%m-%d").date()
            days = (d2 - d1).days + 1
            if days < 0: days = 0
            t["days"] = days
            t["om_total"] = days * apd
    except Exception:
        pass
    return t

def apply_bc_tax(t: dict) -> dict:
    try:
        ht = float(t.get("ht") or 0)
        ir = float(t.get("ir_rate") or 0)
        tva = round(ht * 0.1925, 2)
        ir_amt = round(ht * ir, 2)
        total_tax = round(tva + ir_amt, 2)
        ttc = round(ht + tva, 2)
        net = round(ttc - ir_amt, 2)
        t["tva"] = tva
        t["total_tax"] = total_tax
        t["ttc"] = ttc
        t["net_a_payer"] = net
    except Exception:
        pass
    return t

app = FastAPI(title="CAMTEL Budget App")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"]
)

BASE_DIR = os.path.dirname(__file__)
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(TEMPLATES_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

@app.on_event("startup")
def _startup():
    db = SessionLocal()
    try:
        ensure_admin(db)
    finally:
        db.close()

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    token = request.cookies.get("session")
    if token:
        try:
            signer.loads(token, max_age=60*60*24*7)
            return RedirectResponse("/app", status_code=302)
        except Exception:
            pass
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/app", response_class=HTMLResponse)
def app_ui(request: Request, user: User = Depends(get_current_user)):
    return templates.TemplateResponse("app.html", {"request": request, "user": user})

@app.post("/api/login")
async def login(request: Request, db: Session = Depends(db_dep)):
    data = await request.json()
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_pw(password, user.password_hash):
        return JSONResponse({"ok": False, "error": "Invalid username or password"}, status_code=401)
    token = signer.dumps({"u": user.username})
    resp = JSONResponse({"ok": True, "role": user.role, "department": user.department})
    resp.set_cookie("session", token, httponly=True, samesite="lax", max_age=60*60*24*7)
    return resp

@app.post("/api/logout")
def logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie("session")
    return resp

@app.get("/api/transactions")
def list_transactions(
    year: int = datetime.utcnow().year,
    department: Optional[str] = None,
    doc_type: Optional[str] = None,
    q: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(db_dep),
):
    dept = department or user.department
    if user.role != "admin":
        dept = user.department
    qry = db.query(Transaction).filter(Transaction.year == year, Transaction.department == dept)
    if doc_type and doc_type != "All":
        qry = qry.filter(Transaction.doc_type == doc_type)
    if q:
        like = f"%{q}%"
        qry = qry.filter((Transaction.code_ref.like(like)) | (Transaction.doc.like(like)) | (Transaction.budget_line.like(like)))
    rows = qry.order_by(Transaction.created_at.desc()).limit(500).all()
    return [{
        "id": r.id, "created_at": r.created_at.isoformat(), "created_by": r.created_by,
        "year": r.year, "department": r.department, "doc_type": r.doc_type,
        "code_ref": r.code_ref, "direction": r.direction, "doc": r.doc,
        "budget_line": r.budget_line, "amount_fcfa": r.amount_fcfa, "status": r.status, "tx_date": r.tx_date,
        "date_aller": r.date_aller, "date_retour": r.date_retour, "days": r.days, "amount_per_day": r.amount_per_day, "om_total": r.om_total,
        "ht": r.ht, "tva": r.tva, "ir_rate": r.ir_rate, "total_tax": r.total_tax, "net_a_payer": r.net_a_payer, "ttc": r.ttc,
    } for r in rows]

@app.post("/api/transactions")
async def create_transaction(request: Request, user: User = Depends(get_current_user), db: Session = Depends(db_dep)):
    data = await request.json()
    data = apply_om_calc(apply_bc_tax(data))
    dept = data.get("department") or user.department
    if user.role != "admin":
        dept = user.department
    tx = Transaction(
        created_by=user.username,
        year=int(data.get("year") or datetime.utcnow().year),
        department=dept,
        doc_type=(data.get("doc_type") or "OM"),
        code_ref=data.get("code_ref"),
        direction=data.get("direction"),
        doc=data.get("doc"),
        budget_line=(data.get("budget_line") or "N/A"),
        amount_fcfa=float(data.get("amount_fcfa") or 0),
        status=(data.get("status") or "Draft"),
        tx_date=(data.get("tx_date") or datetime.utcnow().strftime("%Y-%m-%d")),
        date_aller=data.get("date_aller"),
        date_retour=data.get("date_retour"),
        days=data.get("days"),
        amount_per_day=data.get("amount_per_day"),
        om_total=data.get("om_total"),
        ht=data.get("ht"),
        tva=data.get("tva"),
        ir_rate=data.get("ir_rate"),
        total_tax=data.get("total_tax"),
        net_a_payer=data.get("net_a_payer"),
        ttc=data.get("ttc"),
    )
    db.add(tx)
    db.commit()
    return {"ok": True, "id": tx.id}

@app.put("/api/transactions/{tx_id}")
async def update_transaction(tx_id: int, request: Request, user: User = Depends(get_current_user), db: Session = Depends(db_dep)):
    tx = db.query(Transaction).filter(Transaction.id == tx_id).first()
    if not tx:
        raise HTTPException(404, "not found")
    if user.role != "admin" and tx.department != user.department:
        raise HTTPException(403, "forbidden")
    data = await request.json()
    data = apply_om_calc(apply_bc_tax(data))
    for field in [
        "year","doc_type","code_ref","direction","doc","budget_line","amount_fcfa","status","tx_date",
        "date_aller","date_retour","days","amount_per_day","om_total","ht","tva","ir_rate","total_tax","net_a_payer","ttc"
    ]:
        if field in data:
            setattr(tx, field, data[field])
    db.commit()
    return {"ok": True}

@app.delete("/api/transactions/{tx_id}")
def delete_transaction(tx_id: int, user: User = Depends(get_current_user), db: Session = Depends(db_dep)):
    tx = db.query(Transaction).filter(Transaction.id == tx_id).first()
    if not tx:
        return {"ok": True}
    if user.role != "admin" and tx.department != user.department:
        raise HTTPException(403, "forbidden")
    db.delete(tx)
    db.commit()
    return {"ok": True}

@app.post("/api/fiche/pdf")
async def fiche_pdf(request: Request, user: User = Depends(get_current_user), db: Session = Depends(db_dep)):
    data = await request.json()
    ids = data.get("ids") or []
    if not ids:
        raise HTTPException(400, "ids required")
    rows = []
    for i in ids:
        tx = db.query(Transaction).filter(Transaction.id == int(i)).first()
        if tx and (user.role == "admin" or tx.department == user.department):
            rows.append(tx)

    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    out_path = os.path.join(STATIC_DIR, f"fiche_{user.username}_{int(datetime.utcnow().timestamp())}.pdf")
    c = canvas.Canvas(out_path, pagesize=A4)
    width, height = A4

    def draw_one(y_top, tx: Transaction):
        left = 40
        c.setFont("Helvetica-Bold", 12)
        c.drawString(left, y_top, "CAMTEL - FICHE BUDGET")
        c.setFont("Helvetica", 10)
        c.drawString(left, y_top-18, f"Department: {tx.department}    DocType: {tx.doc_type}    Date: {tx.tx_date}")
        c.drawString(left, y_top-34, f"Code/Ref: {tx.code_ref or ''}    Doc: {tx.doc or ''}    Direction: {tx.direction or ''}")
        c.drawString(left, y_top-50, f"Budget line: {tx.budget_line}")
        c.drawString(left, y_top-66, f"Amount (FCFA): {tx.amount_fcfa:,.0f}    Status: {tx.status}")
        c.setFont("Helvetica", 9)
        c.drawString(left, y_top-95, "Prepared by: ____________________")
        c.drawString(left+260, y_top-95, "Approved by: ____________________")
        c.line(left, y_top-110, width-left, y_top-110)

    y_positions = [height-60, height/2+20]
    for idx, tx in enumerate(rows):
        if idx % 2 == 0 and idx != 0:
            c.showPage()
        draw_one(y_positions[idx % 2], tx)
    c.save()
    return {"ok": True, "url": f"/static/{os.path.basename(out_path)}"}

@app.get("/health")
def health():
    return {"ok": True}
