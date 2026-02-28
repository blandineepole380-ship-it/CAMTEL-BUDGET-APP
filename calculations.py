"""
Auto Analytics Engine.
Every function reads directly from the database.
No hardcoded values. No in-memory arrays. No sample JSON.
Recalculates automatically whenever data changes.
"""
from typing import List
from sqlalchemy.orm import Session
from sqlalchemy import func

from app import models


# ── Core Balance Calculator ───────────────────────────────────────
def calculate_available_balance(db: Session, imputation: str, year: int) -> float:
    """
    Real-time available balance for a budget line:
    approved_amount  -  SUM(validated transactions)
    """
    bl = db.query(models.BudgetLine).filter_by(
        imputation=imputation, year=year
    ).first()
    if not bl:
        return 0.0

    engaged = db.query(
        func.coalesce(func.sum(models.Transaction.montant), 0)
    ).filter(
        models.Transaction.imputation == imputation,
        models.Transaction.year       == year,
        models.Transaction.status     == "validated",
    ).scalar() or 0.0

    return bl.budget_cp - engaged


def get_budget_status(db: Session, imputation: str, year: int,
                      new_amount: float = 0.0) -> str:
    """Returns 'OK' or 'DEPASSEMENT' considering current balance + new amount."""
    available = calculate_available_balance(db, imputation, year)
    return "OK" if (available - new_amount) >= 0 else "DEPASSEMENT"


# ── Dashboard Analytics ───────────────────────────────────────────
def get_dashboard_data(db: Session, dirs: List[str], year: int) -> dict:
    """
    Master dashboard — all KPIs, charts, progress cards.
    Reads entirely from DB. year=0 means all years.
    """
    if not dirs:
        return _empty_dashboard()

    tx_q = db.query(models.Transaction).filter(
        models.Transaction.direction.in_(dirs)
    )
    bl_q = db.query(models.BudgetLine).filter(
        models.BudgetLine.direction.in_(dirs)
    )
    if year:
        tx_q = tx_q.filter(models.Transaction.year == year)
        bl_q = bl_q.filter(models.BudgetLine.year  == year)

    txs = tx_q.all()
    bls = bl_q.all()

    # ── Core KPIs ────────────────────────────────────────────────
    total_budget  = sum(b.budget_cp for b in bls)
    validated_txs = [t for t in txs if t.status == "validated"]
    pending_txs   = [t for t in txs if t.status == "pending"]
    total_engage  = sum(t.montant for t in validated_txs)
    total_pending = sum(t.montant for t in pending_txs)
    total_dispo   = total_budget - total_engage

    # ── Engaged by direction ──────────────────────────────────────
    by_dir: dict = {}
    for t in validated_txs:
        by_dir[t.direction] = by_dir.get(t.direction, 0.0) + t.montant

    # ── Spending by month (12-slot array) ─────────────────────────
    by_month = [0.0] * 12
    for t in validated_txs:
        try:
            m = int(t.date_reception.split("-")[1]) - 1
            if 0 <= m <= 11:
                by_month[m] += t.montant
        except Exception:
            pass

    # ── Budget vs engaged per direction ──────────────────────────
    bl_by_dir: dict = {}
    for b in bls:
        d = b.direction
        if d not in bl_by_dir:
            bl_by_dir[d] = {"budget_cp": 0.0, "engage": by_dir.get(d, 0.0)}
        bl_by_dir[d]["budget_cp"] += b.budget_cp

    overdrawn = [
        {"direction": d, "montant": v["engage"] - v["budget_cp"]}
        for d, v in bl_by_dir.items()
        if v["engage"] > v["budget_cp"]
    ]

    # ── Recent transactions (last 15) ─────────────────────────────
    recent_q = db.query(models.Transaction).filter(
        models.Transaction.direction.in_(dirs)
    ).order_by(models.Transaction.id.desc())
    if year:
        recent_q = recent_q.filter(models.Transaction.year == year)
    recent = [_tx_dict(t) for t in recent_q.limit(15).all()]

    return {
        "total_budget":  total_budget,
        "total_engage":  total_engage,
        "total_pending": total_pending,
        "total_dispo":   total_dispo,
        "tx_count":      len(validated_txs),
        "pending_count": len(pending_txs),
        "by_dir":        by_dir,
        "by_month":      by_month,
        "bl_by_dir":     bl_by_dir,
        "overdrawn":     overdrawn,
        "recent":        recent,
    }


# ── Monthly / Annual Report ───────────────────────────────────────
def get_monthly_report(db: Session, dirs: List[str], year: int, month: int) -> dict:
    """
    Full report data for transactions + budgets.
    month=0 → full year report.
    """
    tx_q = db.query(models.Transaction).filter(
        models.Transaction.direction.in_(dirs),
        models.Transaction.year == year,
    )
    if month != 0:
        tx_q = tx_q.filter(
            func.strftime("%m", models.Transaction.date_reception) == f"{month:02d}"
        )
    txs = tx_q.order_by(models.Transaction.date_reception).all()

    bls = db.query(models.BudgetLine).filter(
        models.BudgetLine.direction.in_(dirs),
        models.BudgetLine.year == year,
    ).all()

    bl_map = {b.imputation: b for b in bls}

    # Group by imputation
    by_imp: dict = {}
    for t in txs:
        key = t.imputation or "NC"
        if key not in by_imp:
            by_imp[key] = {
                "intitule": t.intitule, "direction": t.direction,
                "nature": t.nature, "montant": 0.0, "count": 0,
            }
        by_imp[key]["montant"] += t.montant
        by_imp[key]["count"]   += 1

    rows = []
    for imp, data in sorted(by_imp.items()):
        bl = bl_map.get(imp)
        rows.append({
            "imputation": imp,
            "libelle":    bl.libelle   if bl else data["intitule"],
            "direction":  data["direction"],
            "nature":     data["nature"],
            "budget_cp":  bl.budget_cp if bl else 0.0,
            "engage":     data["montant"],
            "dispo":     (bl.budget_cp if bl else 0.0) - data["montant"],
            "count":      data["count"],
        })

    total_budget  = sum(b.budget_cp for b in bls)
    total_engage  = sum(t.montant for t in txs if t.status == "validated")
    total_pending = sum(t.montant for t in txs if t.status == "pending")

    return {
        "year":          year,
        "month":         month,
        "total_budget":  total_budget,
        "total_engage":  total_engage,
        "total_pending": total_pending,
        "total_dispo":   total_budget - total_engage,
        "rows":          rows,
        "transactions":  [_tx_dict(t) for t in txs],
    }


# ── Helpers ───────────────────────────────────────────────────────
def _tx_dict(t: models.Transaction) -> dict:
    return {
        "id":             t.id,
        "code_ref":       t.code_ref       or "",
        "date_reception": t.date_reception or "",
        "direction":      t.direction      or "",
        "imputation":     t.imputation     or "",
        "nature":         t.nature         or "",
        "intitule":       t.intitule       or "",
        "description":    t.description    or "",
        "montant":        t.montant        or 0.0,
        "year":           t.year,
        "status":         t.status         or "validated",
        "statut_budget":  t.statut_budget  or "OK",
        "created_by":     t.created_by     or "",
        "created_by_name":t.created_by_name or "",
        "designation":    t.designation    or "NC",
        "num_compte":     t.num_compte     or "",
        "num_compte_name":t.num_compte_name or "",
        "attachments":    t.attachments    or "[]",
        "departure_date": t.departure_date,
        "return_date":    t.return_date,
        "number_of_days": t.number_of_days,
        "amount_per_day": t.amount_per_day,
    }


def _empty_dashboard() -> dict:
    return {
        "total_budget": 0.0, "total_engage": 0.0,
        "total_pending": 0.0, "total_dispo": 0.0,
        "tx_count": 0, "pending_count": 0,
        "by_dir": {}, "by_month": [0.0] * 12,
        "bl_by_dir": {}, "overdrawn": [], "recent": [],
    }
