from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import datetime


# ── Auth ─────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    token: str
    role:  str
    name:  str

class UserCreate(BaseModel):
    username:   str
    password:   str
    full_name:  str = ""
    role:       str = "agent"
    directions: List[str] = []
    email:      str = ""

class UserUpdate(BaseModel):
    password:   Optional[str]       = None
    full_name:  Optional[str]       = None
    role:       Optional[str]       = None
    directions: Optional[List[str]] = None
    email:      Optional[str]       = None

class UserOut(BaseModel):
    id:        int
    username:  str
    full_name: str
    role:      str
    directions: str
    email:     str
    class Config:
        from_attributes = True


# ── Department ────────────────────────────────────────────────────
class DepartmentCreate(BaseModel):
    code: str
    name: str = ""

class DepartmentOut(BaseModel):
    id:   int
    code: str
    name: str
    class Config:
        from_attributes = True


# ── Fiscal Year ────────────────────────────────────────────────────
class FiscalYearOut(BaseModel):
    id:      int
    year:    int
    is_open: bool
    class Config:
        from_attributes = True


# ── Budget Lines ─────────────────────────────────────────────────
class BudgetLineCreate(BaseModel):
    year:       int
    direction:  str
    imputation: str
    libelle:    str   = ""
    nature:     str   = "DEPENSE COURANTE"
    budget_cp:  float = 0.0

class BudgetLineUpdate(BaseModel):
    libelle:   Optional[str]   = None
    nature:    Optional[str]   = None
    budget_cp: Optional[float] = None

class BudgetLineOut(BaseModel):
    id:         int
    year:       int
    direction:  str
    imputation: str
    libelle:    str
    nature:     str
    budget_cp:  float
    engaged:    float = 0.0
    available:  float = 0.0
    pct:        float = 0.0
    class Config:
        from_attributes = True


# ── Transactions ─────────────────────────────────────────────────
class TransactionCreate(BaseModel):
    code_ref:        str   = ""
    date_reception:  str
    direction:       str
    imputation:      str   = ""
    nature:          str   = "DEPENSE COURANTE"
    intitule:        str   = ""
    description:     str   = ""
    montant:         float
    year:            int
    status:          str   = "validated"
    designation:     str   = "NC"
    departure_date:  Optional[str]   = None
    return_date:     Optional[str]   = None
    number_of_days:  Optional[int]   = None
    amount_per_day:  Optional[float] = None
    num_compte:      str   = ""
    num_compte_name: str   = ""

class TransactionUpdate(BaseModel):
    date_reception:  Optional[str]   = None
    direction:       Optional[str]   = None
    imputation:      Optional[str]   = None
    nature:          Optional[str]   = None
    intitule:        Optional[str]   = None
    description:     Optional[str]   = None
    montant:         Optional[float] = None
    status:          Optional[str]   = None
    designation:     Optional[str]   = None
    departure_date:  Optional[str]   = None
    return_date:     Optional[str]   = None
    number_of_days:  Optional[int]   = None
    amount_per_day:  Optional[float] = None
    num_compte:      Optional[str]   = None
    num_compte_name: Optional[str]   = None


# ── Import Results ────────────────────────────────────────────────
class ImportResult(BaseModel):
    created: int        = 0
    updated: int        = 0
    skipped: int        = 0
    errors:  List[str]  = []


# ── Dashboard ────────────────────────────────────────────────────
class KpiOut(BaseModel):
    total_budget:  float
    total_engage:  float
    total_pending: float
    total_dispo:   float
    tx_count:      int
    pending_count: int
    by_dir:        dict
    by_month:      List[float]
    bl_by_dir:     dict
    overdrawn:     List[dict]
    recent:        List[dict]
