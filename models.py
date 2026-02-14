from datetime import datetime, date
from sqlalchemy import String, Integer, DateTime, Date, Numeric, ForeignKey, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    direction: Mapped[str] = mapped_column(String(10), index=True)
    doc: Mapped[str] = mapped_column(String(10), index=True)
    budget_line: Mapped[str] = mapped_column(String(50), index=True)
    title: Mapped[str] = mapped_column(String(200))
    code_ref: Mapped[str] = mapped_column(String(50), index=True)
    tx_date: Mapped[date] = mapped_column(Date)

    amount: Mapped[float] = mapped_column(Numeric(18, 2))  # TTC or amount

    # Optional OM travel fields
    date_aller: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_retour: Mapped[date | None] = mapped_column(Date, nullable=True)
    days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    amount_per_day: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)

    # Audit
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
