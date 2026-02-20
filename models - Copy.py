from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class UserRole(str, Enum):
    admin = "admin"
    user = "user"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(60), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default=UserRole.user.value)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class BudgetLine(Base):
    __tablename__ = "budget_lines"

    id = Column(Integer, primary_key=True)
    year = Column(Integer, index=True, nullable=False)
    department = Column(String(10), index=True, nullable=False)  # BUM/DIG/DRH
    code = Column(String(60), index=True, nullable=False)
    title = Column(String(255), nullable=False)
    cp = Column(Float, default=0.0)

    transactions = relationship("Transaction", back_populates="budget_line")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    year = Column(Integer, index=True, nullable=False)
    department = Column(String(10), index=True, nullable=False)
    doc_type = Column(String(10), index=True, nullable=False)  # OM/BC/AUTRE

    budget_line_id = Column(Integer, ForeignKey("budget_lines.id"), nullable=False)
    budget_line_code = Column(String(60), index=True)
    budget_line_title = Column(String(255))

    code_ref = Column(String(60), default="")
    title = Column(String(255), default="")
    date_doc = Column(DateTime, nullable=True)

    # computed final amount engaged
    amount = Column(Float, default=0.0)

    # OM
    om_date_aller = Column(DateTime, nullable=True)
    om_date_retour = Column(DateTime, nullable=True)
    om_days = Column(Integer, default=0)
    om_amount_per_day = Column(Float, default=0.0)

    # BC
    bc_ht = Column(Float, default=0.0)
    bc_tva_rate = Column(Float, default=0.1925)
    bc_tva = Column(Float, default=0.0)
    bc_ir_rate = Column(Float, default=0.0)  # percent
    bc_ir = Column(Float, default=0.0)
    bc_total_tax = Column(Float, default=0.0)
    bc_ttc = Column(Float, default=0.0)
    bc_net = Column(Float, default=0.0)

    status = Column(String(30), default="")
    created_by = Column(String(60), default="")

    budget_line = relationship("BudgetLine", back_populates="transactions")
