"""
CRUD layer — all database read/write operations.
Every page queries the DB. No hardcoded values. No in-memory arrays.
"""
import json
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from app import models
from app.utils.calculations import get_budget_status


# ── Users ─────────────────────────────────────────────────────────
def get_user(db: Session, username: str) -> Optional[models.User]:
    return db.query(models.User).filter_by(username=username, is_active=True).first()


def get_users(db: Session) -> List[models.User]:
    return db.query(models.User).filter_by(is_active=True).all()


def create_user(db: Session, username: str, hashed_pw: str, full_name: str,
                role: str, directions: list, email: str) -> models.User:
    u = models.User(
        username=username, password=hashed_pw, full_name=full_name,
        role=role, directions=json.dumps(directions), email=email
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def update_user(db: Session, user: models.User, **kwargs) -> models.User:
    for k, v in kwargs.items():
        if hasattr(user, k) and v is not None:
            setattr(user, k, v)
    db.commit()
    db.refresh(user)
    return user


def deactivate_user(db: Session, uid: int) -> bool:
    u = db.get(models.User, uid)
    if u:
        u.is_active = False
        db.commit()
        return True
    return False


# ── Departments ───────────────────────────────────────────────────
def get_or_create_department(db: Session, code: str, name: str = "") -> models.Department:
    d = db.query(models.Department).filter_by(code=code.upper()).first()
    if not d:
        d = models.Department(code=code.upper(), name=name or code.upper())
        db.add(d)
        db.commit()
        db.refresh(d)
    return d


def get_departments(db: Session) -> List[models.Department]:
    return db.query(models.Department).filter_by(is_active=True).order_by(models.Department.code).all()


# ── Fiscal Years ──────────────────────────────────────────────────
def get_or_create_fiscal_year(db: Session, year: int) -> models.FiscalYear:
    fy = db.query(models.FiscalYear).filter_by(year=year).first()
    if not fy:
        fy = models.FiscalYear(year=year)
        db.add(fy)
        db.commit()
        db.refresh(fy)
    return fy


def get_fiscal_years(db: Session) -> List[int]:
    rows = db.query(models.FiscalYear.year).order_by(models.FiscalYear.year.desc()).all()
    return [r[0] for r in rows]


def get_available_years(db: Session, dirs: list) -> List[int]:
    """Years that have actual data (transactions or budget lines)."""
    from datetime import date
    cur = date.today().year
    ty = [r[0] for r in db.query(models.Transaction.year).filter(
        models.Transaction.direction.in_(dirs)).distinct().all()] if dirs else []
    by = [r[0] for r in db.query(models.BudgetLine.year).filter(
        models.BudgetLine.direction.in_(dirs)).distinct().all()] if dirs else []
    all_years = sorted(set(ty + by + [cur, cur + 1]), reverse=True)
    return all_years


# ── Budget Lines ──────────────────────────────────────────────────
def get_budget_lines(db: Session, dirs: list, year: int = 0,
                     direction: str = "", q: str = "") -> list:
    qry = db.query(models.BudgetLine).filter(models.BudgetLine.direction.in_(dirs))
    if year:      qry = qry.filter(models.BudgetLine.year == year)
    if direction and direction in dirs:
        qry = qry.filter(models.BudgetLine.direction == direction)
    if q:
        qry = qry.filter(or_(
            models.BudgetLine.imputation.ilike(f"%{q}%"),
            models.BudgetLine.libelle.ilike(f"%{q}%"),
            models.BudgetLine.direction.ilike(f"%{q}%"),
        ))
    bls = qry.order_by(models.BudgetLine.direction, models.BudgetLine.imputation).all()
    result = []
    for b in bls:
        engaged = db.query(
            func.coalesce(func.sum(models.Transaction.montant), 0)
        ).filter(
            models.Transaction.imputation == b.imputation,
            models.Transaction.year == b.year,
            models.Transaction.status == "validated"
        ).scalar() or 0.0
        result.append({
            "id": b.id, "year": b.year, "direction": b.direction,
            "imputation": b.imputation, "libelle": b.libelle,
            "nature": b.nature, "budget_cp": b.budget_cp,
            "engaged": engaged, "available": b.budget_cp - engaged,
            "pct": round(engaged / b.budget_cp * 100, 1) if b.budget_cp else 0,
        })
    return result


def upsert_budget_line(db: Session, year: int, direction: str, imputation: str,
                       libelle: str, nature: str, budget_cp: float) -> tuple:
    """Insert or update a budget line. Returns (record, created: bool)."""
    ex = db.query(models.BudgetLine).filter_by(
        year=year, direction=direction, imputation=imputation
    ).first()
    if ex:
        ex.libelle = libelle or ex.libelle
        ex.nature = nature
        ex.budget_cp = budget_cp
        db.commit()
        return ex, False
    bl = models.BudgetLine(year=year, direction=direction, imputation=imputation,
                           libelle=libelle, nature=nature, budget_cp=budget_cp)
    db.add(bl)
    db.commit()
    db.refresh(bl)
    return bl, True


# ── Transactions ──────────────────────────────────────────────────
def get_transactions(db: Session, dirs: list, year: int = 0, direction: str = "",
                     status: str = "", q: str = "", limit: int = 500) -> list:
    qry = db.query(models.Transaction).filter(models.Transaction.direction.in_(dirs))
    if year:      qry = qry.filter(models.Transaction.year == year)
    if direction and direction in dirs:
        qry = qry.filter(models.Transaction.direction == direction)
    if status:    qry = qry.filter(models.Transaction.status == status)
    if q:
        qry = qry.filter(or_(
            models.Transaction.code_ref.ilike(f"%{q}%"),
            models.Transaction.intitule.ilike(f"%{q}%"),
            models.Transaction.imputation.ilike(f"%{q}%"),
            models.Transaction.direction.ilike(f"%{q}%"),
        ))
    return qry.order_by(
        models.Transaction.date_reception.desc(),
        models.Transaction.id.desc()
    ).limit(limit).all()


def create_transaction(db: Session, data: dict, username: str, name: str) -> models.Transaction:
    year = int(data.get("year", 0))
    imp  = data.get("imputation", "")
    montant = float(data.get("montant", 0))
    sb = get_budget_status(db, imp, year, montant)

    # Auto code_ref
    if not data.get("code_ref"):
        direction = data.get("direction", "X")
        count = db.query(func.count(models.Transaction.id)).filter_by(
            direction=direction, year=year).scalar() or 0
        data["code_ref"] = f"JD{direction}-{year}-{count + 1:04d}"

    # Sync department/fiscal_year FK
    dept = get_or_create_department(db, data.get("direction",""))
    fy   = get_or_create_fiscal_year(db, year)

    t = models.Transaction(
        code_ref        = data["code_ref"],
        date_reception  = data.get("date_reception", ""),
        direction       = data.get("direction", ""),
        imputation      = imp,
        nature          = data.get("nature", "DEPENSE COURANTE"),
        intitule        = data.get("intitule", ""),
        description     = data.get("description", ""),
        montant         = montant,
        year            = year,
        status          = data.get("status", "validated"),
        statut_budget   = sb,
        created_by      = username,
        created_by_name = name,
        designation     = data.get("designation", "NC"),
        departure_date  = data.get("departure_date"),
        return_date     = data.get("return_date"),
        number_of_days  = data.get("number_of_days"),
        amount_per_day  = data.get("amount_per_day"),
        num_compte      = data.get("num_compte", ""),
        num_compte_name = data.get("num_compte_name", ""),
        department_id   = dept.id,
        fiscal_year_id  = fy.id,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def update_transaction(db: Session, t: models.Transaction, data: dict) -> models.Transaction:
    for k, v in data.items():
        if hasattr(t, k) and v is not None:
            setattr(t, k, v)
    t.statut_budget = get_budget_status(db, t.imputation, t.year, 0)
    db.commit()
    db.refresh(t)
    return t


def delete_transaction(db: Session, tx_id: int) -> bool:
    t = db.get(models.Transaction, tx_id)
    if t:
        db.delete(t)
        db.commit()
        return True
    return False


def validate_transactions(db: Session, ids: list) -> int:
    count = 0
    for tid in ids:
        t = db.get(models.Transaction, int(tid))
        if t:
            t.status = "validated"
            count += 1
    db.commit()
    return count
