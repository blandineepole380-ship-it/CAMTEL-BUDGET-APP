from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import Base, engine, get_db
from .models import User, Transaction
from .auth import create_token, decode_token, hash_password, verify_password

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="CAMTEL Budget App")

# Ensure tables exist
Base.metadata.create_all(bind=engine)

# Mount static
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ------------------------
# Auth
# ------------------------
class LoginIn(BaseModel):
    username: str
    password: str


class LoginOut(BaseModel):
    username: str


def get_current_user(request: Request, db: Session) -> User:
    token = request.cookies.get("camtel_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not logged in")
    username = decode_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="Invalid session")
    user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def ensure_seed_user(db: Session):
    # Create a default admin if none exists (username: admin / password: admin123)
    existing = db.execute(select(User).limit(1)).scalar_one_or_none()
    if existing:
        return
    admin = User(username="admin", password_hash=hash_password("admin123"), is_active=True)
    db.add(admin)
    db.commit()


@app.get("/")
def home():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.post("/api/login", response_model=LoginOut)
def login(payload: LoginIn, response: Response, db: Session = Depends(get_db)):
    ensure_seed_user(db)
    user = db.execute(select(User).where(User.username == payload.username)).scalar_one_or_none()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Bad credentials")
    token = create_token(user.username)
    response.set_cookie(
        "camtel_token",
        token,
        httponly=True,
        samesite="lax",
        secure=False,  # Render terminates TLS; still OK, cookie is sent over HTTPS
        max_age=60 * 60 * 24,
    )
    return {"username": user.username}


@app.post("/api/logout")
def logout(response: Response):
    response.delete_cookie("camtel_token")
    return {"ok": True}


@app.get("/api/me", response_model=LoginOut)
def me(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    return {"username": user.username}


# ------------------------
# Budget lines (JSON file)
# ------------------------
@app.get("/api/budgets/{year}")
def budgets(year: int):
    # In this starter, budgets are stored as static JSON files: static/budgets_2025.json, etc.
    p = STATIC_DIR / f"budgets_{year}.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"No budgets file for {year}")
    import json

    return JSONResponse(json.loads(p.read_text(encoding="utf-8")))


# ------------------------
# Transactions
# ------------------------
class TransactionIn(BaseModel):
    year: int = Field(..., ge=2000, le=2100)
    direction: str
    doc: str
    budget_line: str
    title: str
    tx_date: date
    amount: float = Field(..., ge=0)
    code_ref: str | None = None

    date_aller: date | None = None
    date_retour: date | None = None
    days: int | None = None
    amount_per_day: float | None = None


class TransactionOut(TransactionIn):
    id: int
    locked: bool
    created_at: datetime


def _next_code_ref(db: Session, direction: str, tx_date: date) -> str:
    # Format: JD<DIR>-YYYYMMDD-XXX
    base = f"JD{direction}-{tx_date.strftime('%Y%m%d')}-"
    # Count existing for that day+direction
    like = f"{base}%"
    existing = db.execute(select(Transaction.code_ref).where(Transaction.code_ref.like(like))).scalars().all()
    n = len(existing) + 1
    return f"{base}{n:03d}"


@app.get("/api/transactions", response_model=list[TransactionOut])
def list_transactions(
    request: Request,
    year: int | None = None,
    direction: str | None = None,
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    q = select(Transaction)
    if year:
        q = q.where(Transaction.year == year)
    if direction:
        q = q.where(Transaction.direction == direction)
    q = q.order_by(Transaction.created_at.desc())
    rows = db.execute(q).scalars().all()
    out: list[dict[str, Any]] = []
    for t in rows:
        out.append(
            {
                "id": t.id,
                "year": t.year,
                "direction": t.direction,
                "doc": t.doc,
                "budget_line": t.budget_line,
                "title": t.title,
                "tx_date": t.tx_date,
                "amount": float(t.amount),
                "code_ref": t.code_ref,
                "date_aller": t.date_aller,
                "date_retour": t.date_retour,
                "days": t.days,
                "amount_per_day": float(t.amount_per_day) if t.amount_per_day is not None else None,
                "locked": t.locked,
                "created_at": t.created_at,
            }
        )
    return out


@app.post("/api/transactions", response_model=TransactionOut)
def create_transaction(payload: TransactionIn, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    code_ref = payload.code_ref
    if not code_ref:
        code_ref = _next_code_ref(db, payload.direction, payload.tx_date)

    tx = Transaction(
        year=payload.year,
        direction=payload.direction,
        doc=payload.doc,
        budget_line=payload.budget_line,
        title=payload.title,
        code_ref=code_ref,
        tx_date=payload.tx_date,
        amount=payload.amount,
        date_aller=payload.date_aller,
        date_retour=payload.date_retour,
        days=payload.days,
        amount_per_day=payload.amount_per_day,
        created_by=user.id,
        updated_at=datetime.utcnow(),
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return {
        "id": tx.id,
        "year": tx.year,
        "direction": tx.direction,
        "doc": tx.doc,
        "budget_line": tx.budget_line,
        "title": tx.title,
        "tx_date": tx.tx_date,
        "amount": float(tx.amount),
        "code_ref": tx.code_ref,
        "date_aller": tx.date_aller,
        "date_retour": tx.date_retour,
        "days": tx.days,
        "amount_per_day": float(tx.amount_per_day) if tx.amount_per_day is not None else None,
        "locked": tx.locked,
        "created_at": tx.created_at,
    }


@app.delete("/api/transactions/{tx_id}")
def delete_transaction(tx_id: int, request: Request, db: Session = Depends(get_db)):
    _ = get_current_user(request, db)
    tx = db.get(Transaction, tx_id)
    if not tx:
        raise HTTPException(status_code=404, detail="Not found")
    if tx.locked:
        raise HTTPException(status_code=400, detail="Locked")
    db.delete(tx)
    db.commit()
    return {"ok": True}
