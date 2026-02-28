"""
Database models — every table with proper foreign keys and relationships.
"""
from sqlalchemy import (
    Column, Integer, String, Float, Boolean,
    DateTime, Text, ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


# ── Users & Roles ────────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id         = Column(Integer, primary_key=True, index=True)
    username   = Column(String(80),  unique=True, nullable=False, index=True)
    password   = Column(String(128), nullable=False)
    full_name  = Column(String(200), default="")
    role       = Column(String(20),  default="agent")   # admin|dcf_dir|dcf_sub|agent_plus|agent|viewer
    directions = Column(Text,        default="[]")       # JSON list of allowed directions
    email      = Column(String(200), default="")
    is_active  = Column(Boolean,     default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    transactions    = relationship("Transaction",   back_populates="creator",      lazy="dynamic")
    pta_submissions = relationship("PtaSubmission", back_populates="creator",      lazy="dynamic")
    attachments     = relationship("Attachment",    back_populates="uploaded_by_user", lazy="dynamic")


# ── Departments (Directions) ─────────────────────────────────────
class Department(Base):
    __tablename__ = "departments"

    id        = Column(Integer, primary_key=True, index=True)
    code      = Column(String(20),  unique=True, nullable=False)
    name      = Column(String(200), default="")
    is_active = Column(Boolean, default=True)

    budget_lines  = relationship("BudgetLine",   back_populates="department")
    transactions  = relationship("Transaction",  back_populates="department")


# ── Fiscal Years ─────────────────────────────────────────────────
class FiscalYear(Base):
    __tablename__ = "fiscal_years"

    id         = Column(Integer, primary_key=True, index=True)
    year       = Column(Integer, unique=True, nullable=False, index=True)
    is_open    = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    budget_lines = relationship("BudgetLine",  back_populates="fiscal_year")
    transactions = relationship("Transaction", back_populates="fiscal_year")


# ── Budget Lines ─────────────────────────────────────────────────
class BudgetLine(Base):
    __tablename__ = "budget_lines"
    __table_args__ = (UniqueConstraint("year", "direction", "imputation"),)

    id            = Column(Integer,     primary_key=True, index=True)
    year          = Column(Integer,     nullable=False, index=True)
    direction     = Column(String(50),  nullable=False, index=True)
    imputation    = Column(String(50),  nullable=False, index=True)
    libelle       = Column(String(500), default="")
    nature        = Column(String(100), default="DEPENSE COURANTE")
    budget_cp     = Column(Float,       default=0.0)
    department_id = Column(Integer,     ForeignKey("departments.id"), nullable=True)
    fiscal_year_id= Column(Integer,     ForeignKey("fiscal_years.id"), nullable=True)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())
    updated_at    = Column(DateTime(timezone=True), onupdate=func.now())

    department  = relationship("Department",  back_populates="budget_lines")
    fiscal_year = relationship("FiscalYear",  back_populates="budget_lines")
    transactions = relationship(
        "Transaction", back_populates="budget_line",
        primaryjoin="and_(foreign(Transaction.imputation)==BudgetLine.imputation, "
                    "foreign(Transaction.year)==BudgetLine.year)",
        overlaps="department,fiscal_year"
    )


# ── Transactions ─────────────────────────────────────────────────
class Transaction(Base):
    __tablename__ = "transactions"

    id              = Column(Integer,     primary_key=True, index=True)
    code_ref        = Column(String(100), default="",    index=True)
    date_reception  = Column(String(20),  nullable=False, index=True)
    direction       = Column(String(50),  default="",    index=True)
    imputation      = Column(String(50),  default="",    index=True)
    nature          = Column(String(100), default="DEPENSE COURANTE")
    intitule        = Column(String(500), default="")
    description     = Column(Text,        default="")
    montant         = Column(Float,       default=0.0)
    year            = Column(Integer,     nullable=False, index=True)
    status          = Column(String(20),  default="validated")   # validated|pending
    statut_budget   = Column(String(20),  default="OK")          # OK|DEPASSEMENT
    created_by      = Column(String(80),  ForeignKey("users.username", ondelete="SET NULL"), default="")
    created_by_name = Column(String(200), default="")
    attachments     = Column(Text,        default="[]")
    # OM / Mission
    designation     = Column(String(20),  default="NC")
    departure_date  = Column(String(20),  nullable=True)
    return_date     = Column(String(20),  nullable=True)
    number_of_days  = Column(Integer,     nullable=True)
    amount_per_day  = Column(Float,       nullable=True)
    num_compte      = Column(String(50),  default="")
    num_compte_name = Column(String(200), default="")
    department_id   = Column(Integer,     ForeignKey("departments.id"),  nullable=True)
    fiscal_year_id  = Column(Integer,     ForeignKey("fiscal_years.id"), nullable=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    updated_at      = Column(DateTime(timezone=True), onupdate=func.now())

    creator     = relationship("User",        back_populates="transactions",   foreign_keys=[created_by])
    department  = relationship("Department",  back_populates="transactions")
    fiscal_year = relationship("FiscalYear",  back_populates="transactions")
    budget_line = relationship(
        "BudgetLine", back_populates="transactions",
        primaryjoin="and_(Transaction.imputation==foreign(BudgetLine.imputation), "
                    "Transaction.year==foreign(BudgetLine.year))",
        overlaps="department,fiscal_year,transactions"
    )
    attachment_files = relationship("Attachment", back_populates="transaction", cascade="all, delete-orphan")


# ── Attachments ──────────────────────────────────────────────────
class Attachment(Base):
    __tablename__ = "attachments"

    id             = Column(Integer,     primary_key=True, index=True)
    transaction_id = Column(Integer,     ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False)
    filename       = Column(String(255), nullable=False)
    content_type   = Column(String(100), default="application/octet-stream")
    data           = Column(Text,        nullable=False)   # base64
    uploaded_by    = Column(String(80),  ForeignKey("users.username", ondelete="SET NULL"), nullable=True)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())

    transaction      = relationship("Transaction", back_populates="attachment_files")
    uploaded_by_user = relationship("User",        back_populates="attachments", foreign_keys=[uploaded_by])


# ── PTA Budget Planning Submissions ──────────────────────────────
class PtaSubmission(Base):
    __tablename__ = "pta_submissions"

    id              = Column(Integer,     primary_key=True, index=True)
    direction       = Column(String(50),  nullable=False, index=True)
    year            = Column(Integer,     nullable=False, index=True)
    sp_code         = Column(String(50),  default="")
    action_code     = Column(String(50),  default="")
    action_nom      = Column(String(500), default="")
    activite_code   = Column(String(50),  default="")
    activite_nom    = Column(String(500), default="")
    tache_code      = Column(String(50),  default="")
    tache_nom       = Column(String(500), default="")
    compte          = Column(String(50),  default="")
    nature          = Column(String(100), default="")
    budget_type     = Column(String(10),  default="OPEX")
    qte             = Column(Float,       default=1.0)
    pu              = Column(Float,       default=0.0)
    montant_ae      = Column(Float,       default=0.0)
    montant_cp      = Column(Float,       default=0.0)
    mensualisation  = Column(String(20),  default="ANNUEL")
    status          = Column(String(20),  default="draft")
    created_by      = Column(String(80),  ForeignKey("users.username", ondelete="SET NULL"), default="")
    created_by_name = Column(String(200), default="")
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    updated_at      = Column(DateTime(timezone=True), onupdate=func.now())

    creator = relationship("User", back_populates="pta_submissions", foreign_keys=[created_by])
