
import os, json, hashlib
from datetime import datetime, date
from typing import Optional, List, Any, Dict

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from itsdangerous import URLSafeSerializer, BadSignature

from sqlalchemy import create_engine, Column, Integer, String, Float, Date, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader

APP_SECRET = os.environ.get("APP_SECRET", "change-me-please")
serializer = URLSafeSerializer(APP_SECRET, salt="camtel-budget")

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if not DATABASE_URL:
    # local fallback (works on a single PC)
    DATABASE_URL = "sqlite:///./camtel_budget.db"

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, future=True, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(60), unique=True, nullable=False)
    password_hash = Column(String(200), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class Txn(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True)
    code_ref = Column(String(80), nullable=False)
    year = Column(Integer, nullable=False)
    direction = Column(String(30), nullable=False)
    doc = Column(String(10), nullable=False)  # OM/BC/NC
    budget_line = Column(Text, nullable=False)
    title = Column(Text, nullable=False)
    date = Column(Date, nullable=False)
    amount = Column(Float, nullable=False)
    status = Column(String(20), default="OPEN")
    extra_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

BUDGETS_PATH = os.path.join(os.path.dirname(__file__), "budgets_2025.json")
with open(BUDGETS_PATH, "r", encoding="utf-8") as f:
    BUDGETS = json.load(f)

def _hash_password(pw: str) -> str:
    # simple salted sha256 (ok for internal demo; can upgrade to bcrypt later)
    salt = "camtel_salt_v1"
    return hashlib.sha256((salt + pw).encode("utf-8")).hexdigest()

def _get_user_from_cookie(request: Request) -> Optional[str]:
    token = request.cookies.get("camtel_session")
    if not token:
        return None
    try:
        data = serializer.loads(token)
        return data.get("u")
    except BadSignature:
        return None

def require_login(request: Request) -> str:
    u = _get_user_from_cookie(request)
    if not u:
        raise HTTPException(status_code=401, detail="Not logged in")
    return u

def ensure_admin_seed():
    # seed default admin if none exists
    with SessionLocal() as db:
        if db.query(User).count() == 0:
            db.add(User(username="admin", password_hash=_hash_password("admin123")))
            db.commit()

ensure_admin_seed()

app = FastAPI(title="CAMTEL Budget App")
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    u = _get_user_from_cookie(request)
    if not u:
        return templates.TemplateResponse("login.html", {"request": request})
    return templates.TemplateResponse("app.html", {"request": request, "username": u})

@app.post("/api/login")
def api_login(username: str = Form(...), password: str = Form(...)):
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == username).first()
        if not user or user.password_hash != _hash_password(password):
            raise HTTPException(status_code=401, detail="Invalid credentials")
    token = serializer.dumps({"u": username, "ts": datetime.utcnow().isoformat()})
    resp = JSONResponse({"ok": True})
    # cookie for 7 days
    resp.set_cookie("camtel_session", token, max_age=7*24*3600, httponly=True, samesite="lax")
    return resp

@app.post("/api/logout")
def api_logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie("camtel_session")
    return resp

@app.get("/api/budgets")
def api_budgets(request: Request, year: int = 2025, direction: Optional[str] = None, q: Optional[str] = None):
    require_login(request)
    items = [b for b in BUDGETS if int(year)==2025]  # file is 2025 for now
    if direction and direction != "ALL":
        items = [b for b in items if b["direction"] == direction]
    if q:
        qq = q.lower()
        items = [b for b in items if qq in b["budget_line"].lower() or qq in b["title"].lower() or qq in b["account"]]
    return {"items": items}

@app.get("/api/directions")
def api_directions(request: Request):
    require_login(request)
    dirs = sorted({b["direction"] for b in BUDGETS})
    return {"items": dirs}

@app.get("/api/transactions")
def api_transactions(request: Request, year: int = 2025, doc: Optional[str] = None, q: Optional[str] = None):
    require_login(request)
    with SessionLocal() as db:
        qs = db.query(Txn).filter(Txn.year == year)
        if doc and doc != "ALL":
            qs = qs.filter(Txn.doc == doc)
        rows = qs.order_by(Txn.created_at.desc()).all()
    def to_dict(t: Txn):
        return {
            "id": t.id,
            "code_ref": t.code_ref,
            "year": t.year,
            "direction": t.direction,
            "doc": t.doc,
            "budget_line": t.budget_line,
            "title": t.title,
            "date": t.date.isoformat(),
            "amount": t.amount,
            "status": t.status,
            "extra": json.loads(t.extra_json or "{}"),
        }
    items = [to_dict(r) for r in rows]
    if q:
        qq = q.lower()
        items = [it for it in items if qq in it["code_ref"].lower() or qq in it["title"].lower() or qq in it["budget_line"].lower()]
    return {"items": items}

@app.post("/api/transactions")
def api_create_txn(
    request: Request,
    year: int = Form(...),
    direction: str = Form(...),
    doc: str = Form(...),
    budget_line: str = Form(...),
    title: str = Form(...),
    date_str: str = Form(...),
    amount: float = Form(...),
    code_ref: Optional[str] = Form(None),
    extra_json: Optional[str] = Form(None),
):
    u = require_login(request)
    try:
        d = datetime.fromisoformat(date_str).date()
    except Exception:
        raise HTTPException(status_code=400, detail="Bad date")

    # generate code/ref like JDDRH-YYYYMMDD-001 (simple)
    if not code_ref or not code_ref.strip():
        prefix = f"JD{direction}"
        ymd = d.strftime("%Y%m%d")
        with SessionLocal() as db:
            count = db.query(Txn).filter(Txn.direction==direction, Txn.date==d).count()
        code_ref = f"{prefix}-{ymd}-{count+1:03d}"

    extra = {}
    if extra_json:
        try:
            extra = json.loads(extra_json)
        except Exception:
            extra = {}

    with SessionLocal() as db:
        t = Txn(
            code_ref=code_ref.strip(),
            year=int(year),
            direction=direction,
            doc=doc,
            budget_line=budget_line,
            title=title,
            date=d,
            amount=float(amount),
            status="OPEN",
            extra_json=json.dumps(extra, ensure_ascii=False),
        )
        db.add(t)
        db.commit()
        db.refresh(t)
    return {"ok": True, "id": t.id}

@app.delete("/api/transactions/{txn_id}")
def api_delete_txn(request: Request, txn_id: int):
    require_login(request)
    with SessionLocal() as db:
        t = db.query(Txn).filter(Txn.id==txn_id).first()
        if not t:
            raise HTTPException(status_code=404, detail="Not found")
        db.delete(t)
        db.commit()
    return {"ok": True}

@app.get("/api/fiche.pdf")
def api_fiche_pdf(request: Request, ids: str):
    require_login(request)
    id_list = [int(x) for x in ids.split(",") if x.strip().isdigit()]
    if not (1 <= len(id_list) <= 2):
        raise HTTPException(status_code=400, detail="Select 1 or 2 transactions")
    with SessionLocal() as db:
        rows = db.query(Txn).filter(Txn.id.in_(id_list)).all()
        # keep exact order selected
        rows_map = {r.id: r for r in rows}
        rows = [rows_map[i] for i in id_list if i in rows_map]
    if not rows:
        raise HTTPException(status_code=404, detail="No transactions found")

    out_path = os.path.join("/tmp", f"fiche_{datetime.utcnow().timestamp()}.pdf")

    c = canvas.Canvas(out_path, pagesize=A4)
    w, h = A4

    # background watermark logo + year
    try:
        logo_bg = ImageReader(os.path.join(os.path.dirname(__file__), "static", "img", "logo_round.png"))
        c.saveState()
        c.setFillAlpha(0.08)
        c.drawImage(logo_bg, x=60*mm, y=90*mm, width=90*mm, height=90*mm, mask="auto")
        c.restoreState()
    except Exception:
        pass

    def draw_one(tx: Txn, top_y: float):
        # header band
        c.setFillColor(colors.HexColor("#0B6FB8"))
        c.rect(10*mm, top_y-10*mm, w-20*mm, 10*mm, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(12*mm, top_y-7*mm, f"FICHE D'ENGAGEMENT - {tx.year}   |   {tx.doc}   |   {tx.direction}")

        # logo top-left
        try:
            logo_top = ImageReader(os.path.join(os.path.dirname(__file__), "static", "img", "logo_top.png"))
            c.drawImage(logo_top, x=w-55*mm, y=top_y-22*mm, width=45*mm, height=12*mm, mask="auto")
        except Exception:
            pass

        c.setFillColor(colors.black)
        c.setFont("Helvetica", 9)

        y = top_y-18*mm
        left = 12*mm
        right = w-12*mm

        def label_val(label, val, yy):
            c.setFont("Helvetica-Bold", 9); c.drawString(left, yy, label)
            c.setFont("Helvetica", 9); c.drawString(left+35*mm, yy, str(val))

        label_val("Code/Ref:", tx.code_ref, y)
        label_val("Date:", tx.date.strftime("%d/%m/%Y"), y-5*mm)
        label_val("Ligne budgétaire:", tx.budget_line[:70], y-10*mm)
        c.setFont("Helvetica", 9)
        c.drawString(left+35*mm, y-14*mm, tx.budget_line[70:140])

        label_val("Objet:", tx.title, y-20*mm)
        label_val("Montant (FCFA):", f"{tx.amount:,.0f}".replace(",", " "), y-25*mm)

        # signature boxes (like sample)
        box_y = top_y-55*mm
        box_h = 18*mm
        box_w = (w-20*mm)/3
        labels = ["Initiateur", "Chef de Service", "Directeur"]
        for i,lab in enumerate(labels):
            x0 = 10*mm + i*box_w
            c.setStrokeColor(colors.black); c.rect(x0, box_y, box_w, box_h, fill=0, stroke=1)
            c.setFont("Helvetica-Bold", 9); c.drawString(x0+2*mm, box_y+box_h-5*mm, lab)
            c.setFont("Helvetica", 8); c.drawString(x0+2*mm, box_y+2*mm, "Nom / Signature / Date")

        # separator line
        c.setStrokeColor(colors.grey)
        c.line(10*mm, top_y-60*mm, w-10*mm, top_y-60*mm)

    # positions: top half and bottom half
    top1 = h-10*mm
    draw_one(rows[0], top1)
    if len(rows) == 2:
        draw_one(rows[1], top1-140*mm)

    c.showPage()
    c.save()

    return FileResponse(out_path, media_type="application/pdf", filename="fiche.pdf")

