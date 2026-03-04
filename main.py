"""
CAMTEL Budget Management System — v10
Single-file deployment for Render
PostgreSQL (production) | SQLite (local dev)
"""
import os, io, csv, json, hashlib, logging, re as _re
from datetime import date
from contextlib import asynccontextmanager
from typing import Optional, List
import base64 as _b64

from fastapi import (FastAPI, Request, Depends, HTTPException,
                     UploadFile, File, Form, Response, Body)
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from itsdangerous import URLSafeSerializer, BadSignature
from sqlalchemy import (create_engine, func, or_, Column, Integer, String,
                        Float, Boolean, DateTime, Text, ForeignKey, UniqueConstraint)
from sqlalchemy.orm import sessionmaker, declarative_base, Session, relationship
from sqlalchemy.sql import func as sqlfunc
from pydantic import BaseModel

# ══════════════════════════════════════════════════════════════════
# DATABASE
# ══════════════════════════════════════════════════════════════════
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./camtel.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
IS_SQLITE = DATABASE_URL.startswith("sqlite")

if IS_SQLITE:
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )
else:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=1800,
    )
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:    yield db
    finally: db.close()

# ══════════════════════════════════════════════════════════════════
# MODELS — all tables with FK relationships
# ══════════════════════════════════════════════════════════════════
class User(Base):
    __tablename__ = "users"
    id         = Column(Integer, primary_key=True, index=True)
    username   = Column(String(80),  unique=True, nullable=False, index=True)
    password   = Column(String(128), nullable=False)
    full_name  = Column(String(200), default="")
    role       = Column(String(20),  default="agent")
    directions = Column(Text,        default="[]")
    email      = Column(String(200), default="")
    is_active  = Column(Boolean,     default=True)
    created_at = Column(DateTime(timezone=True), server_default=sqlfunc.now())

class Department(Base):
    __tablename__ = "departments"
    id        = Column(Integer, primary_key=True, index=True)
    code      = Column(String(20), unique=True, nullable=False)
    name      = Column(String(200), default="")
    is_active = Column(Boolean, default=True)

class FiscalYear(Base):
    __tablename__ = "fiscal_years"
    id      = Column(Integer, primary_key=True, index=True)
    year    = Column(Integer, unique=True, nullable=False, index=True)
    is_open = Column(Boolean, default=True)

class BudgetLine(Base):
    __tablename__ = "budget_lines"
    __table_args__ = (UniqueConstraint("year", "direction", "imputation"),)
    id         = Column(Integer, primary_key=True, index=True)
    year       = Column(Integer, nullable=False, index=True)
    direction  = Column(String(50), nullable=False, index=True)
    imputation = Column(String(50), nullable=False, index=True)
    libelle    = Column(String(500), default="")
    nature     = Column(String(100), default="DEPENSE COURANTE")
    budget_cp  = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), server_default=sqlfunc.now())
    updated_at = Column(DateTime(timezone=True), onupdate=sqlfunc.now())

class Transaction(Base):
    __tablename__ = "transactions"
    id              = Column(Integer, primary_key=True, index=True)
    code_ref        = Column(String(100), default="", index=True)
    date_reception  = Column(String(20),  nullable=False, index=True)
    direction       = Column(String(50),  default="", index=True)
    imputation      = Column(String(50),  default="", index=True)
    nature          = Column(String(100), default="DEPENSE COURANTE")
    intitule        = Column(String(500), default="")
    description     = Column(Text,        default="")
    montant         = Column(Float,       default=0.0)
    year            = Column(Integer,     nullable=False, index=True)
    status          = Column(String(20),  default="validated")
    statut_budget   = Column(String(20),  default="OK")
    created_by      = Column(String(80),  default="")
    created_by_name = Column(String(200), default="")
    attachments     = Column(Text,        default="[]")
    designation     = Column(String(20),  default="NC")
    departure_date  = Column(String(20),  nullable=True)
    return_date     = Column(String(20),  nullable=True)
    number_of_days  = Column(Integer,     nullable=True)
    amount_per_day  = Column(Float,       nullable=True)
    num_compte      = Column(String(50),  default="")
    num_compte_name = Column(String(200), default="")
    created_at      = Column(DateTime(timezone=True), server_default=sqlfunc.now())
    updated_at      = Column(DateTime(timezone=True), onupdate=sqlfunc.now())

class PtaSubmission(Base):
    __tablename__ = "pta_submissions"
    id              = Column(Integer, primary_key=True, index=True)
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
    created_by      = Column(String(80),  default="")
    created_by_name = Column(String(200), default="")
    created_at      = Column(DateTime(timezone=True), server_default=sqlfunc.now())
    updated_at      = Column(DateTime(timezone=True), onupdate=sqlfunc.now())


# ══════════════════════════════════════════════════════════════════
# CONFIG & AUTH
# ══════════════════════════════════════════════════════════════════
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("camtel")

SECRET_KEY = os.environ.get("SECRET_KEY","camtel-secret-v10")
ADMIN_USER = os.environ.get("ADMIN_USER","admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS","admin123")
serializer = URLSafeSerializer(SECRET_KEY, salt="camtel-v5")

def _hash(p): return hashlib.sha256(p.encode()).hexdigest()

ALL_DIRS = [
    "BUM","BUT","BUF","DG","DRH","DICOM","DIRCAB","DCRA","DAMR","DC","DNQ",
    "DAS","DFA","DAJR","DAP","DR","DS","DSPI","DSIR","DOP","DT","DCF","DCRM","DRLM",
    "RRSM","RREM","RROM","RRNOM","RRSOM","RRAM","RRNM","RRENM","DCRF","DRLF","RRSF",
    "RREF","RROF","RRNOF","RRSOF","RRAF","RRNF","RRENF","DCRT","DRLT","RRNOT","RRENT"
]


PLAN_COMPTABLE = [
    # Class 2 - Immobilisations
    {"num":"21310000","nom":"Logiciels","cat":"Immobilisations incorporelles"},
    {"num":"24420001","nom":"Matériel informatique","cat":"Immobilisations corporelles"},
    # Class 4 - Comptes de tiers
    {"num":"40110000","nom":"Fournisseurs - achats biens et services","cat":"Fournisseurs"},
    {"num":"40210010","nom":"Fournisseurs - effets à payer","cat":"Fournisseurs"},
    {"num":"40410010","nom":"Fournisseurs - immobilisations incorporelles","cat":"Fournisseurs"},
    {"num":"40420010","nom":"Fournisseurs - immobilisations corporelles","cat":"Fournisseurs"},
    {"num":"40810020","nom":"Fournisseurs - factures non parvenues","cat":"Fournisseurs"},
    {"num":"42131150","nom":"Avance sur caisse","cat":"Comptes personnel"},
    {"num":"42860010","nom":"Frais de mission","cat":"Comptes personnel"},
    {"num":"44410020","nom":"TVA récupérable sur achats","cat":"TVA"},
    {"num":"44510000","nom":"TVA sur achats (immobilisations)","cat":"TVA"},
    {"num":"44520000","nom":"TVA sur factures fournisseurs","cat":"TVA"},
    {"num":"44710100","nom":"Impôt sur le revenu (IR)","cat":"Impôts"},
    # Class 5 - Trésorerie
    {"num":"57000000","nom":"Caisse","cat":"Trésorerie"},
    {"num":"52000000","nom":"Banque","cat":"Trésorerie"},
    # Class 6 - Charges
    {"num":"60420000","nom":"Carburant et lubrifiant","cat":"Charges"},
    {"num":"60550000","nom":"Achats fournitures de bureau","cat":"Charges"},
    {"num":"60570000","nom":"Frais hôtel et restauration","cat":"Charges"},
    {"num":"63280000","nom":"Services et frais divers","cat":"Charges"},
    {"num":"63840100","nom":"Frais de mission extérieur","cat":"Charges"},
    {"num":"66410200","nom":"Pension vieillesse CNPS","cat":"Charges de personnel"},
    {"num":"60550001","nom":"Papeterie et fournitures","cat":"Charges"},
    {"num":"60610000","nom":"Eau et électricité","cat":"Charges"},
    {"num":"63110000","nom":"Assurances","cat":"Charges"},
    {"num":"63210000","nom":"Loyers","cat":"Charges"},
    {"num":"63500000","nom":"Publicité","cat":"Charges"},
    {"num":"65800000","nom":"Frais divers de gestion","cat":"Charges"},
    {"num":"60420100","nom":"Entretien et réparations","cat":"Charges"},
    {"num":"64110000","nom":"Salaires et traitements","cat":"Charges de personnel"},
]


# ══════════════════════════════════════════════════════════════════
# ANALYTICS ENGINE — reads from DB, no hardcoded values
# ══════════════════════════════════════════════════════════════════
def _tx_dict(t):
    return {
        "id":t.id,"code_ref":t.code_ref or "","date_reception":t.date_reception or "",
        "direction":t.direction or "","imputation":t.imputation or "","nature":t.nature or "",
        "intitule":t.intitule or "","description":t.description or "","montant":t.montant or 0.0,
        "year":t.year,"status":t.status or "validated","statut_budget":t.statut_budget or "OK",
        "created_by":t.created_by or "","created_by_name":t.created_by_name or "",
        "designation":t.designation or "NC","num_compte":t.num_compte or "",
        "num_compte_name":t.num_compte_name or "","attachments":t.attachments or "[]",
        "departure_date":t.departure_date,"return_date":t.return_date,
        "number_of_days":t.number_of_days,"amount_per_day":t.amount_per_day,
    }

def calc_available(db, imputation, year):
    bl = db.query(BudgetLine).filter_by(imputation=imputation, year=year).first()
    if not bl: return 0.0
    eng = db.query(func.coalesce(func.sum(Transaction.montant),0)).filter(
        Transaction.imputation==imputation, Transaction.year==year,
        Transaction.status=="validated").scalar() or 0.0
    return bl.budget_cp - eng

def budget_status(db, imputation, year, new_amount=0.0):
    return "OK" if calc_available(db, imputation, year) - new_amount >= 0 else "DEPASSEMENT"

def dashboard_data(db, dirs, year):
    if not dirs: return {"total_budget":0,"total_engage":0,"total_pending":0,"total_dispo":0,
        "tx_count":0,"pending_count":0,"by_dir":{},"by_month":[0]*12,"bl_by_dir":{},"overdrawn":[],"recent":[]}
    tq = db.query(Transaction).filter(Transaction.direction.in_(dirs))
    bq = db.query(BudgetLine).filter(BudgetLine.direction.in_(dirs))
    if year: tq=tq.filter(Transaction.year==year); bq=bq.filter(BudgetLine.year==year)
    txs=tq.all(); bls=bq.all()
    val=[t for t in txs if t.status=="validated"]; pend=[t for t in txs if t.status=="pending"]
    total_b=sum(b.budget_cp for b in bls); total_e=sum(t.montant for t in val)
    total_p=sum(t.montant for t in pend)
    by_dir={}
    for t in val: by_dir[t.direction]=by_dir.get(t.direction,0)+t.montant
    by_month=[0.0]*12
    for t in val:
        try: m=int(t.date_reception.split("-")[1])-1; by_month[m]+=t.montant if 0<=m<=11 else 0
        except: pass
    bl_by_dir={}
    for b in bls:
        if b.direction not in bl_by_dir: bl_by_dir[b.direction]={"budget_cp":0,"engage":by_dir.get(b.direction,0)}
        bl_by_dir[b.direction]["budget_cp"]+=b.budget_cp
    overdrawn=[{"direction":d,"montant":v["engage"]-v["budget_cp"]} for d,v in bl_by_dir.items() if v["engage"]>v["budget_cp"]]
    recent=[_tx_dict(t) for t in db.query(Transaction).filter(Transaction.direction.in_(dirs)).order_by(Transaction.id.desc()).limit(15 if not year else 999).filter(Transaction.year==year if year else True).limit(15).all()]
    return {"total_budget":total_b,"total_engage":total_e,"total_pending":total_p,"total_dispo":total_b-total_e,
            "tx_count":len(val),"pending_count":len(pend),"by_dir":by_dir,"by_month":by_month,
            "bl_by_dir":bl_by_dir,"overdrawn":overdrawn,"recent":recent}

def monthly_report(db, dirs, year, month):
    tq=db.query(Transaction).filter(Transaction.direction.in_(dirs), Transaction.year==year)
    if month!=0: tq=tq.filter(func.strftime("%m",Transaction.date_reception)==f"{month:02d}")
    txs=tq.order_by(Transaction.date_reception).all()
    bls=db.query(BudgetLine).filter(BudgetLine.direction.in_(dirs), BudgetLine.year==year).all()
    bl_map={b.imputation:b for b in bls}
    by_imp={}
    for t in txs:
        k=t.imputation or "NC"
        if k not in by_imp: by_imp[k]={"intitule":t.intitule,"direction":t.direction,"nature":t.nature,"montant":0,"count":0}
        by_imp[k]["montant"]+=t.montant; by_imp[k]["count"]+=1
    rows=[{"imputation":imp,"libelle":bl_map[imp].libelle if imp in bl_map else d["intitule"],
           "direction":d["direction"],"nature":d["nature"],
           "budget_cp":bl_map[imp].budget_cp if imp in bl_map else 0,
           "engage":d["montant"],"dispo":(bl_map[imp].budget_cp if imp in bl_map else 0)-d["montant"],"count":d["count"]}
          for imp,d in sorted(by_imp.items())]
    tb=sum(b.budget_cp for b in bls); te=sum(t.montant for t in txs if t.status=="validated")
    return {"year":year,"month":month,"total_budget":tb,"total_engage":te,
            "total_pending":sum(t.montant for t in txs if t.status=="pending"),
            "total_dispo":tb-te,"rows":rows,"transactions":[_tx_dict(t) for t in txs]}

# ══════════════════════════════════════════════════════════════════
# CRUD HELPERS
# ══════════════════════════════════════════════════════════════════
def get_user(db, username):
    return db.query(User).filter(User.username == username, User.is_active.is_(True)).first()

def upsert_bl(db, year, direction, imputation, libelle, nature, budget_cp):
    ex=db.query(BudgetLine).filter_by(year=year,direction=direction,imputation=imputation).first()
    if ex:
        ex.libelle=libelle or ex.libelle; ex.nature=nature; ex.budget_cp=budget_cp
        db.commit(); return ex, False
    bl=BudgetLine(year=year,direction=direction,imputation=imputation,libelle=libelle,nature=nature,budget_cp=budget_cp)
    db.add(bl); db.commit(); db.refresh(bl); return bl, True

def get_or_create_dept(db, code):
    d=db.query(Department).filter_by(code=code.upper()).first()
    if not d: d=Department(code=code.upper(),name=code.upper()); db.add(d); db.commit(); db.refresh(d)
    return d

def get_or_create_fy(db, year):
    fy=db.query(FiscalYear).filter_by(year=year).first()
    if not fy: fy=FiscalYear(year=year); db.add(fy); db.commit(); db.refresh(fy)
    return fy

def available_years(db, dirs):
    from datetime import date as _date
    cur=_date.today().year
    ty=[r[0] for r in db.query(Transaction.year).filter(Transaction.direction.in_(dirs)).distinct().all()] if dirs else []
    by=[r[0] for r in db.query(BudgetLine.year).filter(BudgetLine.direction.in_(dirs)).distinct().all()] if dirs else []
    return sorted(set(ty+by+[cur,cur+1]),reverse=True)

def create_tx(db, data, username, name):
    year=int(data.get("year",date.today().year)); imp=data.get("imputation","")
    montant=float(data.get("montant",0)); sb=budget_status(db,imp,year,montant)
    direction=data.get("direction","X")
    if not data.get("code_ref"):
        n=db.query(func.count(Transaction.id)).filter_by(direction=direction,year=year).scalar() or 0
        data["code_ref"]=f"JD{direction}-{year}-{n+1:04d}"
    t=Transaction(
        code_ref=data["code_ref"],date_reception=data.get("date_reception",date.today().isoformat()),
        direction=direction,imputation=imp,nature=data.get("nature","DEPENSE COURANTE"),
        intitule=data.get("intitule",""),description=data.get("description",""),
        montant=montant,year=year,status=data.get("status","validated"),statut_budget=sb,
        created_by=username,created_by_name=name,designation=data.get("designation","NC"),
        departure_date=data.get("departure_date"),return_date=data.get("return_date"),
        number_of_days=data.get("number_of_days"),amount_per_day=data.get("amount_per_day"),
        num_compte=data.get("num_compte",""),num_compte_name=data.get("num_compte_name",""),
    )
    db.add(t); db.commit(); db.refresh(t); return t

# ══════════════════════════════════════════════════════════════════
# IMPORT HELPERS
# ══════════════════════════════════════════════════════════════════
def _decode_file(raw):
    for enc in ("utf-8-sig","utf-8","latin-1","cp1252"):
        try: return raw.decode(enc)
        except: pass
    raise HTTPException(400,"Cannot decode file")

def _clean_amount(s):
    s=str(s or "0").strip()
    for ch in ("\xa0","\u202f","\u00a0"," ","\t"): s=s.replace(ch,"")
    if s.count(",")>1: s=s.replace(",","")
    elif s.count(",")==1:
        p=s.split(",");
        if len(p[1])==3: s=s.replace(",","")
        else: s=s.replace(",",".")
    try: return float(s) if s and s not in ("-","") else 0.0
    except: return 0.0

def _norm_date(s):
    if not s: return date.today().isoformat()
    s=s.strip()
    if "/" in s:
        p=s.split("/")
        if len(p)==3:
            if len(p[2])==4: return f"{p[2]}-{int(p[1]):02d}-{int(p[0]):02d}"
            return f"{p[0]}-{int(p[1]):02d}-{int(p[2]):02d}"
    return s

def _find_header(lines):
    for i,line in enumerate(lines):
        up=line.upper()
        if "DIRECTION" in up and ("DATE" in up or "MONTANT" in up or "IMPUTATION" in up): return i
    return 0

def _read_excel(raw):
    try:
        import openpyxl
        wb=openpyxl.load_workbook(io.BytesIO(raw),read_only=True,data_only=True)
        ws=wb.active; rows=[list(r) for r in ws.iter_rows(values_only=True)]; wb.close()
    except ImportError:
        raise HTTPException(400,"openpyxl not installed")
    hi=0
    for i,row in enumerate(rows):
        if "DIRECTION" in [str(c or "").upper().strip() for c in row]: hi=i; break
    headers=[str(c or "").strip().upper() for c in rows[hi]]
    return headers, rows[hi+1:]

def _gcol(row, headers, *keys):
    for key in keys:
        for i,h in enumerate(headers):
            if key in h and i<len(row):
                v=row[i]
                if v is not None and str(v).strip(): return str(v).strip()
    return ""
def _is_numeric(s):
    if not s or s in ("-",""): return False
    clean = s.replace(',','').replace(' ','').replace('\xa0','').replace('\u202f','')
    try: float(clean); return True
    except: return False

def _parse_tx_row_camtel(row, headers):
    """
    Robust CAMTEL-format TX parser.
    Handles the unquoted-comma-in-NATURE-header column shift.
    Uses positional strategy: fixed cols for date/dir/imp, numeric scan for amount.
    """
    if not row or len(row) < 3: return None
    direction = row[1].strip().upper() if len(row) > 1 else ""
    if not direction or direction in ("DIRECTION","TOTAL","SOUS-TOTAL","","-"): return None
    
    date_r     = row[0].strip()
    imputation = row[2].strip() if len(row) > 2 else ""
    
    nature = "DEPENSE COURANTE"
    intitule = ""
    montant = 0.0
    code_ref = ""
    
    numeric_cols = []
    text_cols = []
    for i in range(3, len(row)):
        v = row[i].strip()
        if not v: continue
        amt = _clean_amount(v)
        if amt > 0:
            numeric_cols.append((i, amt))
        elif not _is_numeric(v):
            text_cols.append((i, v))
    
    if numeric_cols:
        montant = max(numeric_cols, key=lambda x: x[1])[1]
    
    for i, v in text_cols:
        vu = v.upper()
        if "CAPITAL" in vu: nature = "DEPENSE DE CAPITAL"; break
        if "COURANTE" in vu or "DEPENSE" in vu: nature = "DEPENSE COURANTE"; break
    
    for i, v in text_cols:
        vu = v.upper()
        if "CAPITAL" not in vu and "COURANTE" not in vu and "DEPENSE" not in vu and len(v) > 4:
            intitule = v; break
    
    lv = row[-1].strip() if row else ""
    if lv and not _is_numeric(lv) and lv.upper() != direction and len(lv) > 2:
        code_ref = lv
    
    return {
        'direction': direction, 'date': date_r, 'imputation': imputation,
        'nature': nature, 'intitule': intitule, 'montant': montant, 'code_ref': code_ref,
    }



# ══════════════════════════════════════════════════════════════════
# APP BOOTSTRAP
# ══════════════════════════════════════════════════════════════════
def init_db():
    try:
        Base.metadata.create_all(engine)
        log.info("Tables created/verified")
    except Exception as e:
        log.error("create_all failed: %s", e)
        return
    # Dispose all connections so fresh ones are used after DDL
    engine.dispose()
    # Seed admin user
    db = SessionLocal()
    try:
        from sqlalchemy import text as _text
        db.execute(_text("SELECT 1"))  # test connection
        existing = db.query(User).filter(User.username == ADMIN_USER, User.is_active.is_(True)).first()
        if not existing:
            # also check without is_active filter (user might exist but inactive)
            any_user = db.query(User).filter(User.username == ADMIN_USER).first()
            if not any_user:
                db.add(User(username=ADMIN_USER, password=_hash(ADMIN_PASS),
                            full_name="Administrateur", role="admin",
                            directions=json.dumps(ALL_DIRS)))
                db.commit()
                log.info("Admin user created: %s", ADMIN_USER)
            else:
                log.info("Admin user already exists (inactive): %s", ADMIN_USER)
        else:
            log.info("Admin user exists: %s", ADMIN_USER)
    except Exception as e:
        db.rollback(); log.error("init_db admin seed: %s", e)
    finally:
        db.close()
    # Seed departments
    db = SessionLocal()
    try:
        for code in ALL_DIRS:
            if not db.query(Department).filter(Department.code == code).first():
                db.add(Department(code=code, name=code))
        db.commit()
    except Exception as e:
        db.rollback(); log.error("init_db depts: %s", e)
    finally:
        db.close()
    # Seed fiscal year
    db = SessionLocal()
    try:
        yr = date.today().year
        if not db.query(FiscalYear).filter(FiscalYear.year == yr).first():
            db.add(FiscalYear(year=yr))
            db.commit()
    except Exception as e:
        db.rollback(); log.error("init_db fiscal: %s", e)
    finally:
        db.close()
    log.info("init_db complete — app ready")

@asynccontextmanager
async def lifespan(app):
    init_db()
    yield

app = FastAPI(title="CAMTEL Budget v10", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.exception_handler(Exception)
async def _exc(req, exc):
    import traceback
    log.error("ERROR: %s\n%s", exc, traceback.format_exc()[-400:])
    return JSONResponse(status_code=500, content={"error": str(exc)})

# ── Auth helpers ─────────────────────────────────────────────────
def _get_user(request):
    token = request.cookies.get("session") or ""
    auth  = request.headers.get("Authorization","")
    # Only override cookie with Bearer if token is non-empty
    if auth.startswith("Bearer "):
        bearer = auth[7:].strip()
        if bearer:
            token = bearer
    if not token: return None
    try:    return serializer.loads(token)
    except BadSignature: return None

def require_login(request):
    u = _get_user(request)
    if not u: raise HTTPException(401, "Not logged in")
    return u

def require_admin(request):
    u = require_login(request)
    if u.get("role") not in ("admin","dcf_dir","dcf_sub"): raise HTTPException(403,"Admin required")
    return u

def user_dirs(u):
    if u.get("role") in ("admin","dcf_dir","dcf_sub","agent_plus"): return ALL_DIRS
    try:    return json.loads(u.get("dirs") or u.get("directions","[]"))
    except: return []

# ── Pages ─────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
def home(): return HTMLResponse(APP_HTML)

@app.get("/login", response_class=HTMLResponse)
def login_page(): return HTMLResponse(LOGIN_HTML)

# ── Auth ──────────────────────────────────────────────────────────
@app.post("/api/login")
def do_login(username: str=Form(...), password: str=Form(...), db: Session=Depends(get_db)):
    u = get_user(db, username)
    if not u or u.password != _hash(password):
        return HTMLResponse(LOGIN_HTML, status_code=401)
    token = serializer.dumps({"u":u.username,"role":u.role,"name":u.full_name,"dirs":u.directions})
    r = RedirectResponse("/", status_code=302)
    r.set_cookie("session", token, httponly=True, samesite="lax", secure=not IS_SQLITE, max_age=86400*7)
    return r

@app.post("/api/login/token")
async def api_login(request: Request, db: Session=Depends(get_db)):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(422, "Invalid JSON body")
    u = get_user(db, payload.get("username",""))
    if not u or u.password != _hash(payload.get("password","")):
        raise HTTPException(401,"Invalid credentials")
    token = serializer.dumps({"u":u.username,"role":u.role,"name":u.full_name,"dirs":u.directions})
    return {"token":token,"role":u.role,"name":u.full_name}

@app.post("/api/logout")
def logout(response: Response):
    response.delete_cookie("session"); return {"ok":True}

@app.get("/api/me")
def api_me(request: Request, db: Session=Depends(get_db)):
    u = require_login(request)
    dirs = user_dirs(u)
    try:
        years = available_years(db, dirs)
    except Exception:
        years = [date.today().year, date.today().year + 1]
    default = years[0] if years else date.today().year
    return {**u, "direction_list":dirs, "available_years":years, "default_year":default}

# ── Dashboard ─────────────────────────────────────────────────────
@app.get("/api/dashboard")
def api_dashboard(request: Request, year: int=0, db: Session=Depends(get_db)):
    u = require_login(request)
    dirs = user_dirs(u)
    if not year: year = date.today().year
    try:
        return dashboard_data(db, dirs, year)
    except Exception as e:
        log.error("dashboard: %s", e)
        return {"total_budget":0,"total_engage":0,"total_dispo":0,"total_pending":0,
                "by_month":[0]*12,"by_dir":{},"bl_by_dir":{},"overdrawn":[],"recent":[]}

# ── Transactions ──────────────────────────────────────────────────
@app.get("/api/transactions/search")
def search_tx(request: Request, q: str="", direction: str="", year: int=0, db: Session=Depends(get_db)):
    try:
        u = require_login(request)
        dirs = user_dirs(u)
        qry = db.query(Transaction).filter(Transaction.direction.in_(dirs))
        if year: qry=qry.filter(Transaction.year==year)
        if direction and direction in dirs: qry=qry.filter(Transaction.direction==direction)
        if q: qry=qry.filter(or_(Transaction.code_ref.ilike(f"%{q}%"),Transaction.intitule.ilike(f"%{q}%"),
                                  Transaction.imputation.ilike(f"%{q}%"),Transaction.direction.ilike(f"%{q}%")))
        rows = qry.order_by(Transaction.date_reception.desc(),Transaction.id.desc()).limit(500).all()
        result = []
        for t in rows:
            d = _tx_dict(t)
            bl = db.query(BudgetLine).filter_by(imputation=t.imputation, year=t.year).first()
            d["budget_cp"] = bl.budget_cp if bl else 0
            d["bl_libelle"]= bl.libelle   if bl else ""
            result.append(d)
        return result

    except Exception as e:
        log.error("/api/transactions/search: %s", e)
        raise HTTPException(500, str(e))

@app.get("/api/transactions/{tx_id}")
def get_tx(request: Request, tx_id: int, db: Session=Depends(get_db)):
    require_login(request)
    t = db.get(Transaction, tx_id)
    if not t: raise HTTPException(404)
    return _tx_dict(t)

@app.get("/api/transactions")
def list_tx(request: Request, year: int=0, direction: str="", status: str="", q: str="", db: Session=Depends(get_db)):
    try:
        u = require_login(request)
        dirs = user_dirs(u)
        qry = db.query(Transaction).filter(Transaction.direction.in_(dirs))
        if year: qry=qry.filter(Transaction.year==year)
        if direction and direction in dirs: qry=qry.filter(Transaction.direction==direction)
        if status: qry=qry.filter(Transaction.status==status)
        if q: qry=qry.filter(or_(Transaction.code_ref.ilike(f"%{q}%"),Transaction.intitule.ilike(f"%{q}%"),Transaction.imputation.ilike(f"%{q}%")))
        return [_tx_dict(t) for t in qry.order_by(Transaction.date_reception.desc()).limit(500).all()]

    except Exception as e:
        log.error("/api/transactions: %s", e)
        raise HTTPException(500, str(e))

@app.post("/api/transactions")
async def create_tx_route(request: Request, db: Session=Depends(get_db)):
    payload = await request.json()
    try:
        u = require_login(request)
        t = create_tx(db, payload, u.get("u",""), u.get("name",""))
        return _tx_dict(t)

    except Exception as e:
        log.error("/api/transactions: %s", e)
        raise HTTPException(500, str(e))

@app.put("/api/transactions/{tx_id}")
async def update_tx(request: Request, tx_id: int, db: Session=Depends(get_db)):
    payload = await request.json()
    try:
        require_login(request)
        t = db.get(Transaction, tx_id)
        if not t: raise HTTPException(404)
        for k,v in payload.items():
            if hasattr(t,k): setattr(t,k,v)
        t.statut_budget = budget_status(db, t.imputation, t.year)
        db.commit(); db.refresh(t); return _tx_dict(t)

    except Exception as e:
        log.error("/api/transactions/{tx_id}: %s", e)
        raise HTTPException(500, str(e))

@app.delete("/api/transactions/{tx_id}")
def delete_tx(request: Request, tx_id: int, db: Session=Depends(get_db)):
    try:
        require_login(request)
        t = db.get(Transaction, tx_id)
        if t: db.delete(t); db.commit()
        return {"ok":True}

    except Exception as e:
        log.error("/api/transactions/{tx_id}: %s", e)
        raise HTTPException(500, str(e))

@app.post("/api/transactions/validate-batch")
async def validate_batch(request: Request, db: Session=Depends(get_db)):
    payload = await request.json()
    require_login(request)
    count=0
    for tid in payload.get("ids",[]):
        t=db.get(Transaction,int(tid))
        if t: t.status="validated"; count+=1
    db.commit(); return {"validated":count}

@app.post("/api/transactions/{tx_id}/attachments")
async def add_attachment(request: Request, tx_id: int, file: UploadFile=File(...), db: Session=Depends(get_db)):
    u = require_login(request)
    t = db.get(Transaction, tx_id)
    if not t: raise HTTPException(404)
    raw = await file.read()
    data = _b64.b64encode(raw).decode()
    atts = json.loads(t.attachments or "[]")
    att_id = len(atts)
    atts.append({"id":att_id,"name":file.filename,"type":file.content_type,"data":data[:50]+"..."})
    # Store full data in description field of a new tx-attachment record
    # For now store in JSON blob (attachments field stores index + data)
    import hashlib as _hl
    full_atts = json.loads(t.attachments or "[]")
    full_atts.append({"id":att_id,"name":file.filename,"type":file.content_type or "application/octet-stream","data":data})
    t.attachments = json.dumps(full_atts)
    db.commit()
    return {"id":att_id,"name":file.filename,"ok":True}

@app.get("/api/transactions/{tx_id}/attachments")
def list_attachments(request: Request, tx_id: int, db: Session=Depends(get_db)):
    require_login(request)
    t = db.get(Transaction, tx_id)
    if not t: raise HTTPException(404)
    atts = json.loads(t.attachments or "[]")
    return [{"id":a.get("id",i),"name":a["name"],"type":a.get("type","")} for i,a in enumerate(atts)]

@app.get("/api/transactions/{tx_id}/attachments/{att_idx}/download")
def download_attachment(request: Request, tx_id: int, att_idx: int, db: Session=Depends(get_db)):
    require_login(request)
    t = db.get(Transaction, tx_id)
    if not t: raise HTTPException(404)
    atts = json.loads(t.attachments or "[]")
    att = next((a for a in atts if a.get("id")==att_idx), None)
    if not att: raise HTTPException(404)
    raw = _b64.b64decode(att["data"])
    return StreamingResponse(iter([raw]), media_type=att.get("type","application/octet-stream"),
        headers={"Content-Disposition":f"attachment; filename={att['name']}"})

# ── Budget Lines ──────────────────────────────────────────────────
@app.get("/api/budget-lines")
def list_bl(request: Request, year: int=0, direction: str="", q: str="", db: Session=Depends(get_db)):
    try:
        u = require_login(request)
        dirs = user_dirs(u)
        qry = db.query(BudgetLine).filter(BudgetLine.direction.in_(dirs))
        if year: qry=qry.filter(BudgetLine.year==year)
        if direction and direction in dirs: qry=qry.filter(BudgetLine.direction==direction)
        if q: qry=qry.filter(or_(BudgetLine.imputation.ilike(f"%{q}%"),BudgetLine.libelle.ilike(f"%{q}%")))
        bls = qry.order_by(BudgetLine.direction,BudgetLine.imputation).all()
        result=[]
        for b in bls:
            eng=db.query(func.coalesce(func.sum(Transaction.montant),0)).filter(
                Transaction.imputation==b.imputation,Transaction.year==b.year,
                Transaction.status=="validated").scalar() or 0.0
            result.append({"id":b.id,"year":b.year,"direction":b.direction,"imputation":b.imputation,
                            "libelle":b.libelle,"nature":b.nature,"budget_cp":b.budget_cp,
                            "engaged":eng,"available":b.budget_cp-eng,
                            "pct":round(eng/b.budget_cp*100,1) if b.budget_cp else 0})
        return result

    except Exception as e:
        log.error("/api/budget-lines: %s", e)
        raise HTTPException(500, str(e))

@app.post("/api/budget-lines")
async def create_bl(request: Request, db: Session=Depends(get_db)):
    payload = await request.json()
    try:
        require_admin(request)
        bl,created = upsert_bl(db,payload["year"],payload["direction"],payload["imputation"],
                                payload.get("libelle",""),payload.get("nature","DEPENSE COURANTE"),
                                payload.get("budget_cp",0.0))
        return {"id":bl.id,"created":created}

    except Exception as e:
        log.error("/api/budget-lines: %s", e)
        raise HTTPException(500, str(e))

@app.put("/api/budget-lines/{bl_id}")
async def update_bl(request: Request, bl_id: int, db: Session=Depends(get_db)):
    payload = await request.json()
    try:
        require_admin(request)
        bl=db.get(BudgetLine,bl_id)
        if not bl: raise HTTPException(404)
        for k,v in payload.items():
            if hasattr(bl,k): setattr(bl,k,v)
        db.commit(); return {"ok":True}

    except Exception as e:
        log.error("/api/budget-lines/{bl_id}: %s", e)
        raise HTTPException(500, str(e))

@app.delete("/api/budget-lines/{bl_id}")
def delete_bl(request: Request, bl_id: int, db: Session=Depends(get_db)):
    try:
        require_admin(request)
        bl=db.get(BudgetLine,bl_id)
        if bl: db.delete(bl); db.commit()
        return {"ok":True}

# ── IMPORT ENDPOINTS ──────────────────────────────────────────────
    except Exception as e:
        log.error("/api/budget-lines/{bl_id}: %s", e)
        raise HTTPException(500, str(e))

@app.post("/api/import/transactions")
async def import_tx(request: Request, file: UploadFile=File(...), year: int=Form(...), db: Session=Depends(get_db)):
    u = require_login(request)
    if u.get("role") not in ("admin","dcf_dir","dcf_sub","agent_plus"):
        raise HTTPException(403,"Accès non autorisé")
    raw=await file.read(); fname=(file.filename or "").lower()
    created=0; errors=[]
    try:
        if fname.endswith((".xlsx",".xls")):
            headers,data_rows=_read_excel(raw)
            for ri,row in enumerate(data_rows,2):
                try:
                    direction=_gcol(row,headers,"DIRECTION").upper()
                    if not direction or direction in ("DIRECTION","TOTAL","SOUS-TOTAL",""): continue
                    montant=_clean_amount(_gcol(row,headers,"MONTANT","AMOUNT"))
                    date_r=_norm_date(_gcol(row,headers,"DATE ENGAGEMENT","DATE DE RECEPTION","DATE"))
                    intitule=_gcol(row,headers,"INTITULE DE LA COMMANDE","LIBELLE","INTITULE","ORDER TITLE")
                    imputation=_gcol(row,headers,"IMPUTATION COMPTABLE","IMPUTATION","ACCOUNTING")
                    nature_raw=_gcol(row,headers,"NATURE DE LA DEPENSE","NATURE")
                    nature="DEPENSE DE CAPITAL" if "CAPITAL" in nature_raw.upper() else "DEPENSE COURANTE"
                    code_ref=_gcol(row,headers,"CODE /REF","CODE_REF","REF") or f"IMP-{direction}-{year}-{ri:04d}"
                    sb=budget_status(db,imputation,year,montant)
                    db.add(Transaction(code_ref=code_ref,date_reception=date_r,direction=direction,
                        imputation=imputation,nature=nature,intitule=intitule,montant=montant,year=year,
                        status="validated",statut_budget=sb,created_by=u.get("u",""),created_by_name=u.get("name","IMPORT")))
                    created+=1
                except Exception as e: errors.append(f"Row {ri}: {e}")
        else:
            txt=_decode_file(raw).lstrip("\ufeff"); lines=txt.splitlines()
            hi=_find_header(lines)
            hdr_reader=csv.reader([lines[hi]])
            headers=[h.strip().upper() for h in next(hdr_reader)]
            for ri,row in enumerate(csv.reader(lines[hi+1:]),hi+2):
                try:
                    r=_parse_tx_row_camtel(row, headers)
                    if not r: continue
                    direction=r['direction']; montant=r['montant']
                    date_r=_norm_date(r['date']); intitule=r['intitule']
                    imputation=r['imputation']; nature=r['nature']
                    code_ref=r['code_ref'] or f"IMP-{direction}-{year}-{ri:04d}"
                    sb=budget_status(db,imputation,year,montant)
                    db.add(Transaction(code_ref=code_ref,date_reception=date_r,direction=direction,
                        imputation=imputation,nature=nature,intitule=intitule,montant=montant,year=year,
                        status="validated",statut_budget=sb,created_by=u.get("u",""),created_by_name=u.get("name","IMPORT")))
                    created+=1
                except Exception as e: errors.append(f"Row {ri}: {e}")
        db.commit()
    except HTTPException: raise
    except Exception as e: db.rollback(); raise HTTPException(500,f"Import rolled back: {e}")
    return {"created":created,"errors":errors[:20]}

@app.post("/api/import/budget-lines")
async def import_bl(request: Request, file: UploadFile=File(...), year: int=Form(0), db: Session=Depends(get_db)):
    u = require_login(request)
    if u.get("role") not in ("admin","dcf_dir","dcf_sub"):
        raise HTTPException(403,"Admin/DCF only")
    raw=await file.read(); fname=(file.filename or "").lower()
    created=updated=skipped=0; errors=[]
    try:
        if fname.endswith((".xlsx",".xls")):
            headers,data_rows=_read_excel(raw)
            for ri,row in enumerate(data_rows,2):
                try:
                    yr_raw=_gcol(row,headers,"YEAR","ANNEE","ANNÉE") or (str(year) if year else "")
                    dirn=_gcol(row,headers,"DIRECTION").upper()
                    imp=_gcol(row,headers,"IMPUTATION COMPTABLE","IMPUTATION","ACCOUNTING")
                    lib=_gcol(row,headers,"LIBELLE","DESCRIPTION","LABEL")
                    nat=_gcol(row,headers,"NATURE") or "DEPENSE COURANTE"
                    bcp_raw=_gcol(row,headers,"BUDGET CP","BUDGET_CP","APPROVED","MONTANT")
                    if not yr_raw or not dirn or not imp: skipped+=1; continue
                    _,wc=upsert_bl(db,int(float(yr_raw)),dirn,imp,lib,nat,_clean_amount(bcp_raw))
                    if wc: created+=1
                    else: updated+=1
                except Exception as e: errors.append(f"Row {ri}: {e}")
        else:
            txt=_decode_file(raw).lstrip("\ufeff"); reader=csv.DictReader(io.StringIO(txt))
            for ri,row in enumerate(reader,2):
                try:
                    yr_raw=(row.get("YEAR") or row.get("ANNEE") or row.get("year") or "").strip()
                    if not yr_raw and year: yr_raw=str(year)
                    dirn=(row.get("DIRECTION") or row.get("direction") or "").strip().upper()
                    imp=(row.get("IMPUTATION COMPTABLE") or row.get("IMPUTATION") or row.get("imputation") or row.get("ACCOUNTING ENTRY") or "").strip()
                    lib=(row.get("LIBELLE") or row.get("libelle") or row.get("DESCRIPTION") or "").strip()
                    nat=(row.get("NATURE") or row.get("nature") or "DEPENSE COURANTE").strip()
                    bcp_raw=str(row.get("BUDGET CP (FCFA)") or row.get("BUDGET CP") or row.get("budget_cp") or "0").strip()
                    if not yr_raw or not dirn or not imp: skipped+=1; continue
                    _,wc=upsert_bl(db,int(float(yr_raw)),dirn,imp,lib,nat,_clean_amount(bcp_raw))
                    if wc: created+=1
                    else: updated+=1
                except Exception as e: errors.append(f"Row {ri}: {e}")
        db.commit()
    except HTTPException: raise
    except Exception as e: db.rollback(); raise HTTPException(500,f"Import rolled back: {e}")
    return {"created":created,"updated":updated,"skipped":skipped,"errors":errors[:20]}

# ── Export ────────────────────────────────────────────────────────
@app.get("/api/export/transactions")
def export_tx(request: Request, year: int=0, direction: str="", db: Session=Depends(get_db)):
    try:
        u = require_login(request)
        dirs = user_dirs(u)
        qry = db.query(Transaction).filter(Transaction.direction.in_(dirs))
        if year: qry=qry.filter(Transaction.year==year)
        if direction and direction in dirs: qry=qry.filter(Transaction.direction==direction)
        rows = qry.order_by(Transaction.date_reception.desc()).all()
        out=io.StringIO(); w=csv.writer(out)
        w.writerow(["CODE REF","DATE","DIRECTION","IMPUTATION","NATURE","INTITULE","MONTANT","ANNEE","STATUT","STATUT BUDGET"])
        for t in rows: w.writerow([t.code_ref,t.date_reception,t.direction,t.imputation,t.nature,t.intitule,t.montant,t.year,t.status,t.statut_budget])
        fname=f"transactions_{year or 'all'}_{direction or 'all'}.csv"
        return StreamingResponse(iter([out.getvalue()]),media_type="text/csv",headers={"Content-Disposition":f"attachment; filename={fname}"})

    except Exception as e:
        log.error("/api/export/transactions: %s", e)
        raise HTTPException(500, str(e))

@app.get("/api/export/template-transactions")
def tpl_tx():
    out=io.StringIO(); w=csv.writer(out)
    w.writerow(["DATE ENGAGEMENT","DIRECTION","IMPUTATION COMPTABLE","NATURE DE LA DEPENSE","INTITULE DE LA COMMANDE","MONTANT","CODE /REF NUMBER"])
    w.writerow(["15/03/2025","DCF","604100","DEPENSE COURANTE","ACHAT FOURNITURES","250000","DCF-001"])
    w.writerow(["20/07/2025","DRH","622100","DEPENSE COURANTE","ENTRETIEN VEHICULE","180000","DRH-001"])
    return StreamingResponse(iter([out.getvalue()]),media_type="text/csv",headers={"Content-Disposition":"attachment; filename=template_transactions.csv"})

@app.get("/api/export/template-budget-lines")
def tpl_bl():
    out=io.StringIO(); w=csv.writer(out)
    w.writerow(["YEAR","DIRECTION","IMPUTATION COMPTABLE","LIBELLE","NATURE","BUDGET CP (FCFA)"])
    w.writerow(["2025","DCF","604100","FOURNITURES DE BUREAU","DEPENSE COURANTE","5000000"])
    w.writerow(["2025","DRH","622100","ENTRETIEN ET REPARATIONS","DEPENSE COURANTE","8000000"])
    return StreamingResponse(iter([out.getvalue()]),media_type="text/csv",headers={"Content-Disposition":"attachment; filename=template_budget_lines.csv"})

# ── Reports ───────────────────────────────────────────────────────
@app.get("/api/report/monthly")
def api_report(request: Request, year: int, month: int, db: Session=Depends(get_db)):
    try:
        u = require_login(request)
        data = monthly_report(db, user_dirs(u), year, month)
        MOIS=["Janvier","Février","Mars","Avril","Mai","Juin","Juillet","Août","Septembre","Octobre","Novembre","Décembre"]
        fname=f"rapport_annuel_{year}.csv" if month==0 else f"rapport_{year}_{month:02d}.csv"
        title=f"RAPPORT ANNUEL CAMTEL — {year}" if month==0 else f"RAPPORT MENSUEL CAMTEL — {MOIS[month-1].upper()} {year}"
        out=io.StringIO(); w=csv.writer(out)
        w.writerow([title]); w.writerow(["DIRECTION","IMPUTATION","LIBELLE","NATURE","BUDGET CP","ENGAGE","DISPONIBLE","NB TX"])
        for row in data["rows"]: w.writerow([row["direction"],row["imputation"],row["libelle"],row["nature"],row["budget_cp"],row["engage"],row["dispo"],row["count"]])
        w.writerow([]); w.writerow(["TOTAL BUDGET",data["total_budget"],"TOTAL ENGAGE",data["total_engage"],"DISPONIBLE",data["total_dispo"]])
        return StreamingResponse(iter([out.getvalue()]),media_type="text/csv",headers={"Content-Disposition":f"attachment; filename={fname}"})

# ── Users ─────────────────────────────────────────────────────────
    except Exception as e:
        log.error("/api/report/monthly: %s", e)
        raise HTTPException(500, str(e))

@app.get("/api/users")
def list_users(request: Request, db: Session=Depends(get_db)):
    try:
        require_admin(request)
        return [{"id":u.id,"username":u.username,"full_name":u.full_name,"role":u.role,
                 "directions":u.directions,"email":u.email}
                for u in db.query(User).filter(User.is_active.is_(True)).all()]

    except Exception as e:
        log.error("/api/users: %s", e)
        raise HTTPException(500, str(e))

@app.post("/api/users")
async def create_user_route(request: Request, db: Session=Depends(get_db)):
    payload = await request.json()
    require_admin(request)
    try:
        u=User(username=payload["username"],password=_hash(payload.get("password","changeme")),
               full_name=payload.get("full_name",""),role=payload.get("role","agent"),
               directions=json.dumps(payload.get("directions",[])),email=payload.get("email",""))
        db.add(u); db.commit(); return {"id":u.id,"ok":True}
    except Exception: db.rollback(); raise HTTPException(400,"Username exists")

@app.put("/api/users/{uid}")
async def update_user_route(request: Request, uid: int, db: Session=Depends(get_db)):
    payload = await request.json()
    try:
        require_admin(request)
        u=db.get(User,uid)
        if not u: raise HTTPException(404)
        if payload.get("password"): u.password=_hash(payload["password"])
        for k in ("full_name","role","email"):
            if k in payload: setattr(u,k,payload[k])
        if "directions" in payload:
            u.directions=json.dumps(payload["directions"]) if isinstance(payload["directions"],list) else payload["directions"]
        db.commit(); return {"ok":True}

    except Exception as e:
        log.error("/api/users/{uid}: %s", e)
        raise HTTPException(500, str(e))

@app.delete("/api/users/{uid}")
def delete_user_route(request: Request, uid: int, db: Session=Depends(get_db)):
    try:
        require_admin(request)
        u=db.get(User,uid)
        if u: u.is_active=False; db.commit()
        return {"ok":True}


# ── Plan Comptable & PTA Planning ─────────────────────────────────
    except Exception as e:
        log.error("/api/users/{uid}: %s", e)
        raise HTTPException(500, str(e))

@app.get("/api/plan-comptable")
def api_plan_comptable(request: Request, q: str="", designation: str=""):
    require_login(request)
    results = PLAN_COMPTABLE.copy()
    # If designation given, put suggested accounts first
    if designation and designation in DESIGNATION_ACCOUNTS:
        priority = DESIGNATION_ACCOUNTS[designation]
        def sort_key(x):
            try: return priority.index(x["num"])
            except: return 999
        results.sort(key=sort_key)
    if q:
        ql = q.lower()
        results = [r for r in results if ql in r["num"].lower() or ql in r["nom"].lower()]
    return results


# ── FICHE DCF ─────────────────────────────────────────────

# ── BUDGET PLANNING API ──────────────────────────────────

@app.get("/api/planning/reference")
def api_planning_ref(request: Request, entity: str="", q: str=""):
    """Return reference data for PTA form dropdowns"""
    require_login(request)
    result = {
        "sp_map": SP_MAP,
        "actions_map": ACTIONS_MAP,
        "activites_map": ACTIVITES_MAP,
    }
    # Taches filtered by entity
    if entity and entity in TACHES_BY_ENTITY:
        result["taches"] = TACHES_BY_ENTITY[entity]
    else:
        result["taches"] = {k: {"nom": v["nom"], "btype": v["type"]} for k, v in TACHES_MAP.items()}
    # Search filter
    if q:
        ql = q.lower()
        result["taches"] = {k: v for k, v in result["taches"].items()
                            if ql in k.lower() or ql in v["nom"].lower()}
    return result

@app.get("/api/planning/master-data")
def planning_master_data(request: Request, db: Session=Depends(get_db)):
    return api_planning_ref(request, db)

@app.get("/api/planning/accounts")
def api_planning_accounts(request: Request, q: str=""):
    """Return CAMTEL accounts for dropdown"""
    require_login(request)
    if q:
        ql = q.lower()
        filtered = [a for a in CAMTEL_ACCOUNTS if ql in a["num"].lower() or ql in a["nom"].lower()]
        return filtered[:100]
    return CAMTEL_ACCOUNTS[:200]

@app.get("/api/planning/budget-refs")
def api_budget_refs(request: Request, entity: str="", year: int=0):
    """Return historical budget lines for cross-reference"""
    require_login(request)
    result = BUDGET_REFS
    if entity: result = [r for r in result if r["entity"] == entity]
    return result[:200]

@app.get("/api/planning/submissions")
def api_pta_list(request: Request, year: int=0, direction: str="", db=Depends(get_db)):
    try:
        u = require_login(request)
        dirs = user_dirs(u)
        conditions = []
        params = []
        if year: conditions.append("year=?"); params.append(year)
        if direction and direction in dirs:
            conditions.append("direction=?"); params.append(direction)
        else:
            ph = ",".join("?"*len(dirs)) if dirs else "NULL"
            conditions.append(f"direction IN ({ph})")
            params += dirs
        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        rows = [dict(r) for r in db.execute(f"SELECT * FROM pta_submissions {where} ORDER BY direction,sp_code,tache_code", params).fetchall()]
        return rows

    except Exception as e:
        log.error("/api/planning/submissions: %s", e)
        raise HTTPException(500, str(e))

@app.post("/api/planning/submissions")
async def api_pta_create(request: Request, db=Depends(get_db)):
    payload = await request.json()
    try:
        u = require_login(request)
        if u.get("role") == "viewer": raise HTTPException(403,"Lecture seule")
        dirs = user_dirs(u)
        direction = payload.get("direction","").strip().upper()
        if direction not in dirs: raise HTTPException(403,"Direction non autorisée")
        year = int(payload.get("year", date.today().year + 1))
        qte = float(payload.get("qte",1) or 1)
        pu = float(payload.get("pu",0) or 0)
        montant_ae = float(payload.get("montant_ae",0) or 0)
        montant_cp = float(payload.get("montant_cp",0) or 0)
        # Auto-calculate if qte and pu given
        if qte > 0 and pu > 0: montant_ae = qte * pu
        if montant_cp == 0: montant_cp = montant_ae
        pta = PtaSubmission(
            direction=direction, year=year,
            sp_code=payload.get("sp_code",""), action_code=payload.get("action_code",""),
            action_nom=payload.get("action_nom",""), activite_code=payload.get("activite_code",""),
            activite_nom=payload.get("activite_nom",""), tache_code=payload.get("tache_code",""),
            tache_nom=payload.get("tache_nom",""), compte=payload.get("compte",""),
            nature=payload.get("nature","DEPENSE COURANTE"), budget_type=payload.get("budget_type","OPEX"),
            qte=qte, pu=pu, montant_ae=montant_ae, montant_cp=montant_cp,
            mensualisation=payload.get("mensualisation","ANNUEL"), status=payload.get("status","draft"),
            created_by=u.get("u",""), created_by_name=u.get("name",""))
        db.add(pta); db.commit(); db.refresh(pta)
        return {"id":pta.id,"direction":pta.direction,"year":pta.year,"status":pta.status,
                "montant_ae":pta.montant_ae,"montant_cp":pta.montant_cp,"compte":pta.compte}
    except Exception as e:
        log.error("/api/planning/submissions: %s", e)
        raise HTTPException(500, str(e))

@app.put("/api/planning/submissions/{pid}")
async def api_pta_update(request: Request, pid: int, db=Depends(get_db)):
    payload = await request.json()
    u = require_login(request)
    if u.get("role") == "viewer": raise HTTPException(403,"Lecture seule")
    qte = float(payload.get("qte",1) or 1)
    pu = float(payload.get("pu",0) or 0)
    montant_ae = float(payload.get("montant_ae",0) or 0)
    montant_cp = float(payload.get("montant_cp",0) or 0)
    if qte > 0 and pu > 0: montant_ae = qte * pu
    if montant_cp == 0: montant_cp = montant_ae
    db.execute("""UPDATE pta_submissions SET 
        sp_code=?,action_code=?,action_nom=?,activite_code=?,activite_nom=?,
        tache_code=?,tache_nom=?,compte=?,nature=?,budget_type=?,qte=?,pu=?,
        montant_ae=?,montant_cp=?,mensualisation=?,status=?,updated_at=datetime('now')
        WHERE id=?""",
        (payload.get("sp_code",""),payload.get("action_code",""),payload.get("action_nom",""),
         payload.get("activite_code",""),payload.get("activite_nom",""),
         payload.get("tache_code",""),payload.get("tache_nom",""),
         payload.get("compte",""),payload.get("nature","DEPENSE COURANTE"),
         payload.get("budget_type","OPEX"),qte,pu,montant_ae,montant_cp,
         payload.get("mensualisation","ANNUEL"),payload.get("status","draft"),pid))
    db.commit()
    return {"ok":True}

@app.delete("/api/planning/submissions/{pid}")
def api_pta_delete(request: Request, pid: int, db=Depends(get_db)):
    u = require_login(request)
    if u.get("role") not in ("admin","dcf_dir","dcf_sub","agent","agent_plus"):
        raise HTTPException(403,"Accès refusé")
    db.execute("DELETE FROM pta_submissions WHERE id=?", (pid,))
    db.commit()
    return {"ok":True}

@app.get("/api/planning/export/{year}")
def api_pta_export(request: Request, year: int, direction: str="", btype: str="", db=Depends(get_db)):
    """Export PTA submissions to CSV (OPEX/CAPEX format)"""
    u = require_login(request)
    dirs = user_dirs(u)
    sql = "SELECT * FROM pta_submissions WHERE year=?"
    params = [year]
    if direction and direction in dirs: sql += " AND direction=?"; params.append(direction)
    elif dirs:
        ph = ",".join("?"*len(dirs))
        sql += f" AND direction IN ({ph})"; params += dirs
    if btype: sql += " AND budget_type=?"; params.append(btype)
    sql += " ORDER BY direction,sp_code,budget_type,action_code,tache_code"
    rows = [dict(r) for r in db.execute(sql, params).fetchall()]
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["CODES ENTITES","SOUS PROGRAMME","ACTIONS CODE","ACTIONS LIBELLE","ACTIVITES CODE","ACTIVITES LIBELLE",
                "TACHES CODE","TACHES LIBELLE","COMPTES","NATURES","QTE","PU","MONTANT AE","MONTANT CP",
                "MENSUALISATION","TYPE BUDGET","STATUT","INITIÉ PAR","DATE"])
    for r in rows:
        w.writerow([r["direction"],r.get("sp_code",""),r.get("action_code",""),r.get("action_nom",""),
                    r.get("activite_code",""),r.get("activite_nom",""),
                    r["tache_code"],r["tache_nom"],r["compte"],r["nature"],
                    r["qte"],r["pu"],r["montant_ae"],r["montant_cp"],
                    r.get("mensualisation",""),r["budget_type"],r["status"],
                    r.get("created_by_name",""),r.get("created_at","")])
    out.seek(0)
    fname = f"PTA_{direction or 'ALL'}_{year}_{btype or 'ALL'}.csv"
    return StreamingResponse(iter([out.getvalue()]),media_type="text/csv",
                             headers={"Content-Disposition":f"attachment; filename={fname}"})

@app.get("/api/planning/summary/{year}")
def api_pta_summary(request: Request, year: int, db=Depends(get_db)):
    try:
        """Summary by direction and type for monitoring"""
        u = require_login(request)
        dirs = user_dirs(u)
        ph = ",".join("?"*len(dirs)) if dirs else "NULL"
        rows = db.execute(
            f"""SELECT direction, budget_type, status,
                COUNT(*) as nb_lignes, SUM(montant_ae) as total_ae, SUM(montant_cp) as total_cp
                FROM pta_submissions WHERE year=? AND direction IN ({ph})
                GROUP BY direction,budget_type,status ORDER BY direction""",
            [year]+dirs).fetchall() if dirs else []
        return [dict(r) for r in rows]

    except Exception as e:
        log.error("/api/planning/summary/{year}: %s", e)
        raise HTTPException(500, str(e))

@app.post("/api/planning/import")
async def api_pta_import(request: Request, file: UploadFile=File(...), year: int=Form(...), 
                          direction: str=Form(...), db=Depends(get_db)):
    """Import OPEX/CAPEX CSV into planning submissions"""
    u = require_login(request)
    if u.get("role") not in ("admin","dcf_dir","dcf_sub","agent_plus"): raise HTTPException(403,"Accès refusé")
    raw = await file.read()
    content = None
    for enc in ("utf-8-sig","utf-8","latin-1","cp1252"):
        try: content = raw.decode(enc); break
        except: pass
    if not content: raise HTTPException(400,"Cannot decode file")
    reader = csv.reader(io.StringIO(content))
    rows = list(reader)
    created = 0; errors = []
    
    # Detect if it's a standard CAPEX/OPEX file (2 header rows) or our export format
    if len(rows) > 2 and rows[0][0].strip() == "CODES ENTITES":
        # Standard CAMTEL CAPEX/OPEX format
        btype = "CAPEX" if any("CAPEX" in r[0] for r in rows[:5]) else "OPEX"
        for i, r in enumerate(rows[2:], 3):
            if not r or not r[0].strip(): continue
            def g(idx): return r[idx].strip().replace("","'").replace("","Œ") if len(r)>idx else ""
            tache_code = g(8); tache_nom = g(9)
            if not tache_code: continue
            compte = g(10); nature = g(11)
            try:
                montant_ae = float(g(14).replace(",","").replace(" ",""))
            except: montant_ae = 0
            cp2025 = 0
            try: cp2025 = float(g(18).replace(",","").replace(" ",""))
            except: pass
            ent = g(3) or direction
            db.execute("""INSERT INTO pta_submissions 
                (direction,year,sp_code,action_code,action_nom,activite_code,activite_nom,
                 tache_code,tache_nom,compte,nature,budget_type,qte,pu,montant_ae,montant_cp,
                 status,created_by,created_by_name)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1,?,?,?,?,?,?)""",
                (ent,year,g(1),g(4),g(5),g(6),g(7),tache_code,tache_nom,
                 compte,nature,btype,montant_ae,cp2025,"validated",u.get("u",""),u.get("name","")))
            created += 1
    else:
        # Our export format
        for i, r in enumerate(rows[1:], 2):
            if not r or not r[0].strip(): continue
            def g(idx): return r[idx].strip() if len(r)>idx else ""
            try:
                db.execute("""INSERT INTO pta_submissions 
                    (direction,year,sp_code,action_code,action_nom,activite_code,activite_nom,
                     tache_code,tache_nom,compte,nature,budget_type,qte,pu,montant_ae,montant_cp,
                     mensualisation,status,created_by,created_by_name)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (g(0),year,g(1),g(2),g(3),g(4),g(5),g(6),g(7),g(8),g(9),
                     g(15),float(g(10) or 0),float(g(11) or 0),
                     float(g(12) or 0),float(g(13) or 0),g(14),g(16),u.get("u",""),u.get("name","")))
                created += 1
            except Exception as e: errors.append(f"Row {i}: {e}")
    db.commit()
    return {"created": created, "errors": errors[:10]}


@app.get("/fiche-imputation", response_class=HTMLResponse)
def fiche_imputation(request: Request, ids: str, db=Depends(get_db)):
    require_login(request)
    tx_ids=[int(i.strip()) for i in ids.split(",") if i.strip().isdigit()]
    txs=[]
    for tid in tx_ids[:20]:
        t=db.get(Transaction, tid)
        if t: txs.append(dict(t))
    pages="".join(_fiche_imputation_block(t) for t in txs)
    n=len(txs)
    css=IMP_CSS_STR
    head=f"<!doctype html><html lang='fr'><head><meta charset='utf-8'/><title>Fiche d'Imputation</title><style>{css}</style></head><body>"
    nav=f"<div class='noprint'><button onclick='window.print()'>\U0001F5A8 Imprimer</button><button onclick='window.close()' style='background:#64748b'>Fermer</button><span style='color:#93c5fd;font-size:12px'>{n} fiche(s)</span></div>"
    return HTMLResponse(head+nav+pages+"</body></html>")


def _fiche_imputation_block(t):
    LOGO = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAPoAAAD8CAYAAABetbkgAAAABGdBTUEAALGPC/xhBQAAACBjSFJNAAB6JgAAgIQAAPoAAACA6AAAdTAAAOpgAAA6mAAAF3CculE8AAAABmJLR0QAAAAAAAD5Q7t/AAAACXBIWXMAAAsTAAALEwEAmpwYAAAAB3RJTUUH6QYLBBMDWjEqvwAANXNJREFUeNrtnXd4VNXWh99T5kyv6Y2E0Js0qVIUKdJEsVzrtaJeEFC/iyIqgh17AxQb9n6lI2ClKAoKIk06SIBAQnqbdr4/AoEIJAFSJsl+n4eHQGb2Obv89lprVxAIBAKBQCAQCAQCgUAgEAgEAoFAIBAIBAKBQCAQCAQCgUAgEAgEAoFAIBAIBAKBQCAQCAQCgUAgEAgEAoFAIBAIBAKBQCAQCAQCgUAgEAgEAoFAIBAIBAKBQCAQCAQCgUAgEAgEgupAEkVwEiZ9JfH9RyYikxy06m6nSQcL+Tl2Dv1tJxi0IEn2k5SdF8jE6iwgtlEmezbls/X3PLatyUEil28+CIiCFQCQ3Fbh2gcSCAQ8bP7lD/73YkAIvarzf8fzBqwuD+7IRKIbJpGb2ZSwmMYYTDF4C8JQVA8mixNZMRIMyoCMrisnpiTpgL/4b8lHUX4OvqIsFDUdRU0lfd8ukLagB3ew/Y9dKOp+XrunkNyMoGj59YCweIlr7g8nsWUnnBGDsTn7kZv5Oz98+m8+fMxb1Y9X612Bt+qucvn/RWKytSQivgOK2hmLozm6Ho1mchMWI4MEkgQmS+nvKnJFy9OM2ebAbIsDQNchtlHxb3y+PCLiD+It3M4Ly/6gMG8VmQfXsO7HvXz+bL5QRB3jtmccNG7fBnf0RZht/TGaW6FqViQJCvLWE/Tr1fEa9UPo516kMPi2BMJiu+MI64Nm6oLBmISiWpHl0l6NrheLvFL9BumY86QZrUBDjJaG2Nx9Cfi9RDZIJbHlGvpc8z1ZaT/w59ItfPiYEH1tZfhdRroMboozoh9W50BMlg6oBg/SUUOhF7ezIz8KoZ+tW373DBcNWnbFGT4Ms70PmjEJWTGUEvI/hS1VYzQjSaAaNFRDAkZzAjbXUDwxB4lrvIruw+awb/s3bPhpD7NeFvF9qNP/JgPdhiQQ2aAnNvcQTNbzMGjRyIp0YluTqk/hdVjoEhM+TiCu8WCcEf/CZDkXxWA9pYClEBqmkBUJozkKo3kIFsdFeGK2k3zOfLoN/ZwNK9bw3qQioaiQQmbczChiG3XBGTEQi70PBmMSsqKetF3VYFtT65TAH/gkgYTmV+IM+zeapQWKopb0pLUJXQdFVTHbmmGyNMPuuZ7IBvM5p/dbbPr5V96a4BUaq8F2dvMTDpp1aocneiAWR3+M5uYoBnOJkE+nvUnVo/66IfSx06Noeu5VeKJvwWhphfyPUTOplk0uHN9gJBk0UwQG441YnUMJi51Ly+6vs375at550C90V03c8byFxJbN8ET3x+oahGZui8HgPBZ3Hw24pYq3N10PUpBbLVaodk+vXfOgmU4XDSQ89i4sjm4oqnrSuLsuoevgKzpAzuH3+HvzDCYN31HtAV99oc81Bs6/qiER8edjdQ7GZO2CqkWeMIB7pvW4f/sbjDz3P0CVj8HUXos+8YumJLYahyPsKgyarZTA66rIOZI/zRSNO3ocZvtAXl75LH/9+iVTx+QJZVYCg0fInHN+NNENz8MZPgSTtReaKQFZUUqJtDLaWDAYqK5OuvYJfeRLRpp3Hk543P2Y7W1qbMS8hsLDkoYmyxIWextik1/D4enHY/Oe5MEhG4VSzwiZUS+7adCyA57oQdhcfTEYm6KoWqgNqtUPod/zRgzNu47DHXULBs1RKi6qTxwfw6uaGWfEdRgt7Xj558ksfm8286b7hHYrwL/us9KxXyvc0Rdhsg7AZGmNqjnOaFBNCL2SeGpxe2IbTcHmuhBZkUvPSdZTJOmYG2m2tSYm+Q2Gj21Dmx4v8OS1mULJJ+H25zTimzYmPO4CrK7BmCydUTVP6bj7NAfVhNArgV5XyQz7z0XENnoGk7VlqcYtKF0OBqMLV+QEmnVqwqRZDzDpkp2igIDulyj0+3c8kQk9sLkGY7L1wKDFl1rMcrIQqQ4R2kLvMljlynuuITz+SUyW2PoTi58hxbG7iiP8ahqdE83zP97DPb3X1suySGwucfHocJLPORdnxGDMtgvRTI1KrYysRwYjdIU+fKzGgJvvwBM9CYPRLVR8Gq68LIPNfQGqNpMpS0ZxX78V9aUE+M8LdhJbFm8isToHYLK0QjFY6sqgWt0S+nmXagy4aSRhsY+gGuxCwWfgyhfH7W1JbPk2U5aM5r5+S6ir8+2DRpjoMbwJnph+WB2DMFraY9A8pRez1G9CT+gXXqtx5biRhMVNLhZ5PRxVr0xM1qYktpzK09+M4t6+i+tMvvpcq9Lj0gSiEntjcw/GZO1+ZBOJXCqUEWFeCAr9vEsV/nXfbXhijrPkoqIqQeyNSWg+lSlLbua+fstqr7ivk+k0IJK4xl2xuQZjcZ6PwdgQWVZOGncLkYeo0K976ErcUZNQDXbRG1eB2Bu0eIWnv7mJe/uuqVVx9w2POGnZrT3hcQMw2/qjmZujqOb6HnfXTqFPWXwh7qgnMRjDRIVVUexusrYltvELPPn1Tdx/UWhPvY142kzj9i1whPXH6hqA2doB1eAQcXdtFvrj81sQ3+xpTNZEUSVVxREPyeroTXTSE9z5yp28Ojo9pF6x7/UaPS9LIjyuN3bPEEzWrkc2kSDi7tou9FEve4hr+igWRwdRHVXrAZdse3VGXEGbnjvod+Nklsys2b3tFofM3TNiiG7YDbtnCGZrb1QtvmQnonDN64DQk89R6NB3NA7PJWLFWzW577oOsqLgjhnFwJv/ZMnMT6r9PSKTJK57wEV8s3Nxhg/GYu+LZm6MrBjr42KWui/00dMGYveMRlYUUbHVKHYAzegkOmkiD3+5icmX/VEtz77hERvNOrciLHoAVtcAjOZzUDWbGFSry0J/4JN4IhMmoJnChMhrCLO9BcltH+Ket27h+VuyquQZV/xXo03PxoTH98HmGojJ2hlVCyvZRKKLMzPqrtDjmigktf4PZnu3Wtd7l9sp1ZIFPkfzYXMNpUn764FXKy3tIXeotLsgluiGPbC7h2C09kAzxSHLJy5mER18HRb62Ne64Qy7udRoam0QxvE/+71F6PqxW1YkWUE1aCViD/UGfDReV1QNV+QYHp27lIeGrjubFBn3bjgxDTvjjhqI2XYhBmOjE47XFq55PRH6tQ9ZiWowFoMpOuStdTAIQX8u3qJd6MGdZKRuQzPtwR2VxsE92XgLAyWCMVlVwmKdpKVEo6iNcYY3RdeTMZpjkU6xcitU4nWTtQlxje+k73Wj+eaD0ztS+rqJdtqe3wZXxEAsjgEYLa1QVEtdPLyhCgjWXaF3HTIAq2tgcUMIMTf3qGh9RYcpyl9NbuYPBPwr2LBiG7kZaaz+2semX8tvuZfcKWN1W2jWKR5PTCdsrv6YrL1Lua+hIvij72H3XMng22fzzQfzy/3OqFdMRCU2JSz2QuzuQZisHTFo7rM6EbU+IisZ1SX26hX62NecuCJGoBqsITcAp+vgLUwhL+sr0lM+Y/Oqtbw1Ppcz2fE169UgkAtsBjbT59pP6X1lU2KSrsAedjVGS+NKOUm0Mq26wegkLHYkI6Ys5437ThyYa3WeyqVjEohJ7n3kJpLuGLSoE47WPs6TF5Rb9tV25Ff1Cr1Jh76Y7b1CIkY7vqPxFWWQc/gTDux+gxVf/cn81yv3vPTvPvTy3YfrCY/byKhXPiS+6a04w29EM0WElHW3OPpwzvnDgPcAaHeBTL8bImjQvCs299DiE1HNSSiK4ZThjqCex+g3PGLF7vk3qsESMu5qMKhTkLOSQ38/yvL/fcsXz1ftKrG0lCCTh2+h95UTGHLHImKSJ2FxnIcsS9UumOOfp+sQ8BdQlL8JRdG56n4XnQa0wxU5CLO9L5qpBYpqEoNqQujl06ZnJ8z2niHjrgYDXjIPvsvO9Y/z6BW7q/X5P37m58fPvmXyrK3EN5uEK/I6FMVQrWKXJAj4/XgLd1GQ+z05h+exY90KOlzYisG3zcJkbYdqcIpBNSH00xp2wBV5KQatZo+EOioknzeXw/uf5o/vX2DaXbk19j4PX7KH6x++mx7DUwmPG4OiWipf7P8Y8AwGdfzeQxTkrCDz0DxSd//Ab4v2sGhmcbjyVUYrJKn3CWUmLLcQerk8+GkDrM7+Nbqe/XiRZxyYzIqvXgmJ20nfn5xFbuYjDLrVS1jseGRFq9wyOlLmAV82BXlrKchZyOEDi/l59iZmTy0o1xUXAhdCrzCRiT3QTI1rrOEcFU7AX0hm6pOsnPsy700KnRtJv3qpAHfUs3S7OJywmDuKR7LPcupR14vDE2/hX+RlLyEnbQE71v/OKyMzEXe1CaFXOs4IA46wAchKza2rL47JdTIPvskPn7zMh4+H3rXDb0/IIaH5I5gsSdjcg07jRs7SnWcgEMBXmEJh/o9kp81j/87lrP32AAvfCormLoRedYx9LQ7N1LlmXUAd8rK/4a9VT/Lh47khWxuTh6fyxMKHadimGWZbowq58JIEehB83jQKclaRm7WAtL3fsmLWdhbPFPeoC6pJ6DbnOWimBjWj7yNCKSpM4cDOSTx9w76Qr5EJA1czdfVzRCe9iKJqZeYt4C/AW7Ce3MwFpO9bxJbf/uSdB/KEay6ofqFHNuiKoppqzGUPBIJkHXqNcX1+rjW1svHnT7C5huIMH3jC7wJ+H76inRTkfktW2jz+3vwrs19KZ9s6IW5BDQn9P8/bkKSONTraXpDzG3+tmlmrrNzU0Rk0WT4di6MHBs1OMKjjK9pPQe5P5GXOJy3lR+ZM3cNvSwKiCQtqXuiuqAjMtiYl1rW6CfgDZB16h+du2VvrambTyu+xe+ZiNCeQfXgOaSlLSN21maljikSzFYSW0B3hyUB4DQTngATego2k7p5bK2vm9f/mktz2Hrav9TJjXIZoqoLQFXpkQkNUYw3cnXZkJDoncx6PXL631tbOff1SRRMVVAZVe8RLQW6Tkvi8uvF5Mzi8f6GoYoGgKoU++DYFmyuxxuJzn3cbqbs2iioWCKpS6PHNjFid0TW2UKYofzUv3CZiW4GgSoWeccCOt9BVI7kK+IMU5a+hGs/kEgjOAKn2Cz0szoau22qk+PRgPqm7t4t2JAhtM6v4a7/Q4xpbUBRrzfSTch6xjfaJliQIaTzRGbVf6GariiTXzI61wrxM0lJyRUsShK7TLoHBWG0rG6tOiPHNzBiMNXM+nLcok40/F4rWJBBUtdCNFgWomcsT9aCf7HQxECcQVLnrfryLUlOukUAgqGKh67o4OVQgqPNCP7inEF9RQY3kSlFtNDxHE9UrEFS10DNTvQT8vhrJldnmolV3k6hegaCqhZ6+v5BgoKYsupOM1AhRvQJBVQt9/858dD2vRnKlBy2gJ4vqFQiqWugFOTmohuwasugakQ2ai+oVCKpa6K175AHp1T7yrusU39MtdeCGR8yiigWCqhT6pEv9HD6wu9pzdHT+3GxrR8NzEkUVCwRVu2BGR1F31FjOVEMckQnniSoWCKp+Zdw2Ar7qvy1E10FRFazOYQy/yyqqWSCEXpXs/HMnwcDhGnPfLfae9BzerVbWzLh3Y3hx+XAe/rIhLbspoqkKQlfojrC/8ftr7hRWVXPhibmZmx6rfYNySS0HEdv4A5p3Wcg9bz7P80svZMQzLtFkBWckhSpNfcLALN7evBaL/dwayZ0kgcUxiLbnXwAsqDW1csfzThxhV6CZzEAzTNZmOCNuIjLhd87tN4f9OxezeeUWPpkiLlEUhESMHqAwdzUBf81tGTUYnYTF3cO979WelXItu/fFbO9ZqsMyaHZs7t5ENHiW5l0WMuCWt3hxxZWMmxlLdexCFAihl0l+zqoaidOPx+o4n0Zt76RROzXka2TMVDfuyNtQDZYT1iDoOsiyhMkSjyviOuKbvkf7PvN5c8NjPLXoPG6dIgYeawV6HRT6799uozD/j5orUx1kRcEddSdjp18S8m2gedersTjOL7Hk/wxFjv9ZNRixONoRFnM/yW3n0PvKL5i6+g4mfdWYwXeoQlChypFLTQKBYN0R+kePZZOXtYRgDXnvR8WhmTxENniSZ3/oEbL1/+TXnfFE31N8L/pp9PqSXJw/u/siohu+SvMuX3PZ2Fd5Yelg7no9XAgrBAn4/BzclVV3hA6QnfY9fm9ajReu0dKY6KRXmTy7Q8hV/Pj340lo9jhGS6OSXv9MvBdFUTBZGuGOvp2E5p/S6aI5zFg3gSlL2nPDI0ahsFDx3vUg3qJA3RL6mm/XU5i3sqQx1lRcJElgdbalUdsZPP1t95Cp9IlfhNOs8+NYnX2LPZAzLKMS1/5IXlXNitXZjfD4x2nYZiF9rvmQab9dz8QvEmjaUczNh4QPX5eE/vGT+WQemkXA76+5s9ykY2KwOjsS3+RNXlw+FE9MzTb4e96MpGGbKTjDr0WSj3SEUuW2H1kGzRSFM/wyohLfpEXXrxn/wTM88935jHjaIfRW96m+aZn92xdTlB8Clx7qR+fXWxDX5E2eWHAPd8/w1MirTPqqBW17v4Yz/AZkpXpOzFVUDbOtJe7ou0lqNYteV8zitTVjeXxBC0DCV1RIwB8o5XmJs/+E63BavLbmASITH0MOoWnfQMBHXuY3HNj5LN9+uIJF7xRV+TNvedJEuz4DCYt9GLOtbcnV0tXm7fzDawgGgvi8KeRnL+HQ369hsjbHET4Ys60HBi0GWRHz9JWNr8jLvu3XMbb759XxuOp1W88dcAh39CBUg7tGzns/cUAEZFlBMzfBETaYph0b0XXoYRKaHWTt95V/L9b5Vxm4/dkOtOoxCU/0/ZgsiSUxebWWhfTPMpBQDU70oMz+HW8yvv8ygvo8LLYFoG9DD6pIkhtZNpd6z1Cow9pKMBAgJ+N/fP3Wxmqu8WpqYTPWTSQ8flLoWPXjrJuug68wncL8ZWSlzSZ11wr2bN7Lew8XcqYjZD0vV+gyKIz4pp1xhF2G1TUAzRQTMgI5Kla/r5D9O0Yyuss7J9TZzU/YaNmtDY6wgdhc/dHMrVFUS0kehOBD3qJXf+1Mnp1M0w5zMNtbhXQDCfj9+L17yc9ZhyyvJXXPBgzadoyWw/zxYz77tvrY+lsRGQeLFwg076wRFquSfI5Gm1429m6JxRXRBKuzIwZTF4ympigGa6mRcUJI7DmHv+LXBTfy6ujsMtvLf98OJ65JJ5wRg7DYL8RgbISiGoRyhdBPZPrvo4ls8DyKGpqrt/7ZAelBCAS8SHIe/qJsCvMOEwzmIys5SFLgiCtmQdfNKKoViyMcSbKBbkExhO401tF8FhWkkLL1Su7p9VOFv3vTEwoJTeOISuyJzT0Uk6U7BmNcqXheWPqQEXrNCG3DTx9jcw3B7ukfkpVwQhwqgyprgIZicWO01P4jqo6KMBjwk5n6Mvf0Wnla339nQgDYA3zIxSM/p/OgRoTFXojNNQST9VwUgwdZFioPEWrG2vy6IJ9elx/A6hyEolpCuuevqxbp6Eh/bsZCtqx+iBVf5Z9xWn+tCvDdR2nMf/1XbO7ZGLRv0YMpIJmRcCErmrDs/6CaB+Nqzq1c9+Meugy2YbH3KO75QyhmrS8U5e9gz6YxTL5sW+XV6w9evnl/L0s//5HohrPQ9eUEfBlIkg1ZcSFJihjEq09Cz80I0q7PBpzhbTGYGosev5pddr8vj7SU+7mn1/wq6kTg5zn5LJ65na2/LcLmmQP8BroXSXIiybZ6PT9fb4QOsPTzPLoN24bN1RfV4BKDN1Wu8qNxeZDDB6aycu5LVbJe4J+kpej8PDubr99ej2KYj6IuQJI2oQclJNmNLFvq3fx8HZ9HP/k7vPLL9UQ3fAWD5hBirwaLnnN4DutXjODpfx+s0Xof8YyZJu1b44ocgMUxEKOlDarBVi/qv06vjDsVWWmbaNrRiNnWHVlRRLxehSLPz1nF7o2jePSK3TX+Pr8v8bHkvRTmTl9GfLOvkKTlQDpgO+Leq3VW9PXKdT/K35sDtOj6O87wKIyW9kiSJCx7FVCYt509m0YyYeDvIfduv8wvYPHM7Wz86Rsi4mcBv6HrhSC5kGUH0nFTdXWhbdRLoQP8NKuIZp1X4fAkY7S0qP6NHnWcooIU0lLGck+vxSH9nof36yz7MoeFb25AVuahavNB3wi6jCS5kGRLnZifr7dCB1jxVS5NOq7EGdEao7mREHulxYPppO39L6M6fVGr3nvTyiA/fJLO/NdXY3XMxmBaDPpudN14ZBDPWGvbRjAQIDfjfyysj0IvtuxZdOi3CoutNZo5SYi9EkR+aO843hz/Ift3BGttPtYt9fHN+/uYO305DVp8hR5chh5MK56mk92l5udrh9D9ZB76gkXvbKqfQgf4/uM02vb5GYstGaOliYjZzxBvYSqH/r6XSZe8z/a1gTqTr5XzCln87g4Kcr5BNswiGFhFMJCPJDmQZTuyHPrr7f2+AvZsepeln++sv0IH+OGTdBq1W44jLB6jpQWyLMR+OhTm7eHQ3rHc2flT8rODdTKPO9bpLP9fDl+/vZHMgwuwOOYDG9GDOpLsQlasIRvPB/yF7N/+Ccu+3FW/hQ7w85wsGrf/EbvbhtHctnjqTXBSjnaCug4FOetI2X4nd523AAjWi/zv3hhk6efpLHjjN8Ji5xDwLyEY2Fm8zl52I0uhFc8H/EWk7vpUCP2Y2PNo2W0pmikfo6UDimIWqj6FyIOBIHmZi9i1fiTj+/9MTVwJEgqs+dbH9x/vY/6M5UQnzUJVfyAYTAOsSLITSTbU+Hp7IfSTsPx/Xrb+vpJzem5F1dqgGiLEIN1xjVSSwOfN5fD+6Wxbcy+TL9suer8jrPq6kEUzd/HT3O9IbDWLgH8Vul4cz0uKs1Q8L4QeAqSnBJk/YzPtL1yKyRyBwdi4xJWvj4I/3lUvzNvM/u33s+Krl5l2V6ZQ90nIz9ZZ+nkuX7+1CYtjAcHAXCTpT3R0JMmNJFuRSi24p0pXZwqhl8N3Hx0kptES7J50DFpzFNVVr6z78Vbc780jK+0TdvwxhvEDvuXPZX6h6AqwflmQHz/LYP6MNUjybCyOr9GDu4oPwZRdyIqpyl17IfQKsPrrQvJzf8UduRTNaEfVGqEohnoj8GAgSH7276TufoDflzzH87fuE+o9Qzat9PPN+weYO/0nklp/hR78nkDgIJJkPbIoR60LQq/9JnD0q1aanDsYT/QYzLbOJQcV1hULf3w+9KBOUcEuMlJnsmv9TKb8e49QahXQoIXMZXdHkNiyK86IIZht52MwJpY6BPNs21dRQRZ/fH8pT1zzvRD66XDvu1EktrwUV+RNmKwdQvbgyTMSexC8hbvIyfiUAzvf591Jm9m6OiAUWQ206KZy9f2JuCJ6YfcMwuLofuRSi7PTjhD6WeZn3DtRJLUehiPsGsy2c1EMtef88X++XyAQoCh/C7kZ/+Pgno/58YvNLJkpBF5TXHmvmVbdmxDZoB9W1yBMlg4YNBfS8QP3FRzEE0KvJO581U1ym564oy/D4rgAgxaaRxGf7Ghpvy+DgrxVZKd9Requhcy4929SdwWF0kKImx5z0LRTO8JjB2B19kcztzytSy2E0CuZy+7S6NC/MWGxfTDb+mOydMRgjEaS5ZARuq6D35uJr2gj+TnfkXFgMbs3/sHUMdlCUaHuQ0oS4z+IICqpC3bPYCz2C9BMyciKKoReU279bc+aiG/SGE9MZ2yuHhiMbdHMycUbIZTKFX5ZPXogoINeSFHBXvTgRrIOrSAn42f279jA3Nez2P67sN610so/oRLbKJ7YRr2wuYZisp6HQYs6qScphF5N9L5CoVmXMFp0TUYPtiYyoQ3ewkaY7UkYtAiCQQuKYkZWz2wKsngaTMfvK0SS8tH1THIz96CZtpOVthFvwZ8c3r+NVYv28fVbXqGSOsawO410HdoET3RfLI5BmKznoqruknheCL3GkOk+zMyV99rIOhRJMBhLQrMorI4IstLCCPg9qJodzeRA13UUVcHu9lCQm0tRQQGSJBHweykqyESSsrA501AMh9i9KZW8zP1EJR7g57lZzJ+RR3aaGFCrT57kHS/YadS2De7IgVgcA9DMrfH7vKz74VKeuOY7IfRQqiyQ6XWFTJP2MsEguCKh28UK29YE2bpaR1bh0F6dr98K4C0MUl83lAhOTcd+MudfHUZiyy6ohl7s/PNDnrnxD1EwAkFdJTJRJipRbLsWCAQCgUAgEAgEAoFAIBAIBAKBQCAQCAQCgUAgEAgEAoFAIBAIBAKBQCAQCAQCQS1G7EcXCCqTWZkyMA7oCJz6gBFdlzmw8zP+0+HLUv9/3qUyV4/XMNtllrxfxCdPVsohJaqoGYGg0o1nb2BgBT67CTgm9KcWN8FsuxKbuyUGk0z3YfvodNFcdq9fxsujzkrwsqgXQa3g4pEm7p4RzQtL69JhDcdOIXpxRQ8i4l9BVgwc3v8yWYeeIBjYiCf6QVr1uIMO/c4q38KiC0LTKl49wUBkgygatWuGonbEFdETXfehqP8GcupUbid86Mbuvpe87Hloxv04PDcRCBRSkPM7+3dMIbrhZK59YDW/L/lFCF1Qu0luZ+CaCR6sjuaEx3dEVjphsbdDNSSgGqxHTk/9g7o4rmTztMVgcrB5ySf0u/6/7Nuh4yvaiifmJha9cwPRDddicQwAhNAFtZhH53akQYvRqIZ2aOYkFMVx1neb1Sb8XjeaMZ+stEyQJOzudgT8TcjL/INPnvqb4Xelkp/tOdLJ6ULogtqJ1dkWu+cG5OOGjOrLffcABuNuCvMcNGieCATJOTyL3Mw/iEp8gP+80Jicw82QlZ84i5OFxWCcIAQiculEh1yqRzO/S7/YSFHBepJajyErbQ0+748E/MvIz32fJh2vQpKj2b/j67N5hBC6QFDTLHyzkP07nkKWPXgLh+P3tkfV/oVEK1wRvcg5/CSPXrFNCF0gqO1MunQXf60eQ3baLNxRycQ2ak9B3lb2br2Dsd2XnG3yIkYXCEKFZ2/KAD458qdSERZdIKgHCKELBELoAoGgLlBbY3SJUa+YMBijiIiPo1FbDyargeJ5Rom8zCK2/JZGdvpejOY0nrreS2Xebtqmt0z/6+1ISgJNOsQSlWgreXb6vjw2/rwX+JuvXsllx9pgyfdeXG4gtrEJzXTquSNdh8P7fbx0RyHrlha/c/GOKEsFOmY/UMAlruLv3fS4hjM8lgYtkkhs6UJRi7+fk1HEX6sOkJm6i+8/zmDDT8Fyy3vsdA1ZiSGheRKJLVwohmNpbf4lhcK8XayYlc3KuadO6+bHZS642oLdcywf2ekBstJMp2GY7MzKLC7rYwSA/JJ8l5eXW6do2N3hOMMTaNw+DJvbeKztZHnZtiaNjAMp6NIhXrq9iDpwM27tEvrNT5ho3KE14bH9MFp6YLI0RScczWgHlJLKMtl8tOiajaykU5C7idfXLuXg39+w9IvNLHnXe8bP/8+LJpLPaYszfBhWV28UJQnF4AbMJc92hhfS6aJ0/L7tNOu0mNTds1i1aDNzXg0A3YEpgKmMxqMA84CHOLbNMRKYCcQAwTLqcgnJzv9j7HQXjdr1x+a+GIu9C7IchaxYSzoKi91H6/MyCQR20vaC70jf9yWbfl7Luw/7T0h19NRwGrW7CHfkJRitbZGkKGS1dFpteh0mGNhJiy6LGTbqC9Z8v5HPppxst1UUMA1ILsmH3aNjdYZXcGVrY2Ahpbd/KhQvDR0J+E75zfhmCjc/3pCY5D6Ybf0w21qj65EYjHbgmJEwWf0065SNJKdRmLuZ19b+wMHdS9j481988pRPCL0qGTpS5fx/dSUsZgQWx0WoWgSyLJ1gCSVJQtdBUQ0oahgQhmZqit19Ma6ofcQ2ms8FV73F7Km/8cu809n2J/Hk162JbDAGu2cYBi3iyNrrE5+taiZULQ6Iw+LoiSN8BJEN3qF191cBB9AOMJbzvPWohuP/rQGtgPgyv6UHt7NgcVc69BuP1dkfRTWVWniiH+lbissnAojAYu+MI+zfuCJexxM7jRdGpAEQ11RmzLQLiE66D6uzF6rBeEJ5H0srCojCbO2C3XMDnpjpxDeZwfO3ZpT+DhrQAmh2rGQlUCrcDM1Am5P8/2FO3VNITPyiAQnNbsHmvgrNlIyiKmW0HRVF9QAejOam2D1DcEWkENdkDu36vMb4/htqo4UPfaHf/2EkSa1H4466HYMxoqTh/nOJ5NGf/7miStdBViSM5jg0021YXUO46dFpDBs5nQmDDpf7/IEjNAbe/C8iEydiNDc+6fNP9mxdB1mWMFkS0eInYnN35uCun5CkYAVyreM/A+Ph83UksdUHmKzJJ11ZdrKykSQwmmOJSJiIydqCR2b/HxOH7WfCR9cQFjsFkyX25PI5WVqyhNGSSHjcY5gs5/DonHE8dPG+4ySnV6tIhtxh4MJrhxLZ4EHM9nYnGIeKtR0ZkzUBo2UUVucAXvppCut++JC3JhQIoVcWj85tSWLLp7G5ByLLcpkN7ZS2+B+dgckSS2SDSVhd7Zjw8XieuHr7Kb87/n0zDduMxR1zH5rRdVrPP75DkBUZi30QcU17oBiMVVZeBi0e7TSSP/4dFVXBEf4vGrTwM3XVj0TEPYZmjjrDtFTsYVfToKXCxC9G88jlh6q97YyZaqRl9zvxxExAM3nObCRIKul3i9uOtTFxjV/CYm9MMPgk7zyYVVuEHrqj7o/Oa0liq9exewYjy3KJq3i2FAtPxea6nOadpzHh40Yn/Vz/m1USW48kLG4imtF1xs8/3lpoJkel5qU8K3s63zvqgTjCriIq6aXTEvmp0rK7ryCuyRhsruo1KDdMNtG6512Ex01GM3nOvryP68RUzUJY7D10v+RhbphsE0I/GybNakhii2nY3T1KGk5lbXI4Pj27pz/NOz/NPW+GnfC5i268jLCYB1AN5krfSRWKGzZKBKqoqAZLJaUl44q8lQc+6VStbbrbsBF4oh9C1awl1rhyy8iAJ3oU5116B7Vkijr0XvL6h20ktZyI3dO7uIKqYLvi8VbW6hpG03NvLzWYM3l2C6IbPoRmcoesMEPJIygrLc0UTVTi1aUsY1Xy7Hfn4468H1WzFltyqXwP759/jv/dqcSuqBrOiP/y/NILhNDPhG5Dr8Dm/ldJgZ5N4yjPZdN1UBQFV8RtPD6/LQAN2xiIbzIGs61VpTwj1KjM961IWsWx7QVM+CiGYFCvMrXbnDp3zwgnKul+jJaYU3ZcR99ZD+oU5u8k48BM9mwax96/xrBn030cPvAuhXk7CAb1Y23wFJ2Y0RxFRPz/MeplV6hXe2gNxk34KA5X5Khy3eWjv9N1CPjzKcrfhrdgG5LsJRg0Y7I2x2RJRlYMFbI6RnMiUUlXAWu5dUpHbO5LS7wJKjDoFvD78BbupiD3L2Q5h2BQxWBMxGxrjqLaKz38qAh+Xw55WX8QDKSg6xpmWxtMlkZIsnTa7+L3FVCQ8yd+3050XcVkbY3J2qRkvKG8tIyWJOKaNGTHuh3AAYqnGYNH6lJH161IkrsC7+QDDlF65F4BDvH1TJ3G7YdjcZxfZsckSeD35ZGZ+hZ7t07jfy9uY92Px6ZaG7ZRuG5iUxJbjsUddSOKaiwzj2b7BTQ9tz/wmRB6RYlvOgSjpV2ZbuTRQg8GdQpyfiZ194tkpC7j/cmZ7FofoGknlavvjyCm4VCcEaMxWZudclrp+MEWo+VCLh0bSUzyZWimqAq5mroORfnbOLz/FQ7smsd3Hx1g+f98WBwytz9np0HzToTFjcLmHICsqNUidl2Hwrz17N85ifXLvuPtCXk0aCEzYkoDYhuPwxV5A4pqqHB6hXnbSd39CNvXLuTlkVk4wiXGTk8gseVduKNHoChaBfJlIistmU+e+pnBt13DsQUq4PcGSNt3NdGJz1TA2G8FrgByS1WerBTgLXDiDL8WRVXLbDcBfz7pKQ8ze+o0Frxx4hTZzj8DPHrFJq4cN46+1+cQHncXchkT/Ypqwhl+OZf932y+fK5ICL08Rjxjxea++ITFDCeNkYKQnf4lezb9HxMv3lPq91tW+Zg8fA8wjUdmr6BRu1ewOHqcMM0WDEIwkIe3YAfeol9I37eQVufZMNv6VUiMug552b+ya/2dPDh4dSkrk58NL4woAhZy5yu/ck7viYTFjURRqrC8j3gf3sK97Nk8ivv6Li351Z5N8NDFW7jp8XH0vtKNM/yyCuXRW5hOyra7+b/ec0v+LzsNHr1iGyOensB5l4bhDL+qAmmp2N2RgM71yftO+O0Ly9KpmFPvA/ZyiSv7hN+8uKIfRkuHcttN1qH3WPzeVBa8UVjmkz57JoekNk9gtrfC5hp4yjxKEphtXWnVvRFfPrdRCL08IhOSS6x5eeTnrGT/9ntPEPk/W/7EYWt5YsH/kdzuY0yWZIKBIH5fOkX5G/AVLSd9/1IO7d3At+8f4LclQR6bdz6q1rBC71BUsJt9W+/hwcGryvzcq6PTufWpSfQYHokz4qqqs+hHGnJe1pfc13f5ST/yzgOZtOr+FjbXAFSDrXzPIH8RC2YsOunv37g3m2adZ2BzDkTVnOW+m6ppZX7gbIvFbDsPVbOVE4Icwlu0kBsfieK6h5QK1EWAQ3sXY7H3LdMLUrVY4pu0BoTQyyWxVfMjyzLLixcLSd/3IvdftLNicf+gVbz+x4sUWfqQn/sd6SkrSUvZwou3Z/PPVVrxzVqiKI5y0wwGIevQTO7t+1OF3uHN8Rk0PfcFLI7eaKaYKivDYNBH6q6fOPV6eDBoGwgGDwFliyIY0Mk4sJJvP/SWYSU34fOmlC90vWpHLcdO17C5zi2/tWtuohJnEPDrFe5ww2INSJJSZocoKwqF+S1EjF4hgyQ1rFDs6CvayOZfvz8tn/ajx1+j1XmvM22sj7KWYPoKE5CV8gfOvAUHSEuZxeks5/z06bXc+coyDMYrqzBODxAMZpf5icMHCvHEZJW7gk7Xg+RmlH1RQmZqgMiEmo9L01LsKGpMBVYrqhRvrKn4eMfRBZmnahNHB1qtjgaE8JnzoTK9JlGYF12hgi/I3cS3H6afVuo/fuZj2tjytqoq+LwRZQ4EHutsdvHL/L9P6x1+W+wlGPilGkqyvDLUKy2xUFlfYLE78fsclV+WUsXz6ooM492tISv0EBp11yv2LjmHD/DXr4EqkkjF7rcy2dJI35d92k8Iiz2MoArMlSrXqNEq3oGn4IyUQnVjW+07YcZgNNe4i+T3GvEVGU77ewW5hlq3wEZwWlGicN3LKyFJyitxz8vqOZ3hyVw61nRaqd/zlpGRL8fQfVhZI7/BkncoNxL2x9Hr8tPfEZV1qLEQQxVQmFuEJHlFQdQG193m3luhWEgxtKHtBU346qV1FU47pmE3ohKfo8ugbVz74FJyMn5h2+9bWfhWDilbgyVCt7n3VWhRi8nakMSWHYG9FX6HcTPDcYT1rFc3kFSbuVKyMGiZ5X4uP/sHVG06milYoXQrvsBJBlIonu2QhdDL4vCBHVideRiM1jI/ZzTFEdf4Wpp12shfq/zlpnvlfRYi4m/G7ukAdMDuuYLwonTim/5FlyE/kZe1jOy0tUwclkLmwR2YbT5UQ9luuaKacYTfyJ2v/sCrd1ZsT3LDNsMwWjoKVVYB61fk0fPy7bhNXcs0FpISwZbVv/DgkN2nE4Ef+VOxzmFWZkgWUej0PtnpGwkG95df7DK4Im5hzLTh5cbqNpdC7ytuxOY+thJMliWM5nBsrvMIjxtHfNNPaXruN8zc8hoFOVkEAwcrNPhicw2iVfdRdB6klfv5R+f2xB11H4qqiRi9Cli1MEBRwa/lWmCjuSWRDUYQ17Ti4yuPzO7I25unM3XVKJ5f2oGrxjvRDLXOLQsdiz7v9f0ktvwJzdS4XHfJYAwjLO45pv9u5/dvPuWNe3NP+Mztz7s4p9ctRDaYgGqwnNgIjvxbNZhRtaYEgwFSd79AdPLvaKa4cl06RdWISBjPLU+a6XPNqzx1XeoJn7v+YSPtLxxAdNKTmKxNKhSaCM6M9JTlhMWkHtuncJI6k2UJd/Qo7v9gG8/c9AG7N5TtEU6e1YCk1o9h9wzAFRHE7ztMVOJG+lyzEl/RMnZt+IO9W1L5+Imy12cIoR/H6q+9ZKd/id1zeYUOPjBZ4olIeJmew4fRrs88UndtRte9gJHopNY4wi7B4uiJohpPLrDjz3cLQkHu9zx3yyZeXTUHq2PgKTdHHE1L10E12ImIH4/V0YfX1s4iddda/L4c9KBCREIyzoiLsDoHYdBcQolVzF+rN5HQfBkG4+VlLmwxaC6iEp/j/g8bsGX1Wzx/674TRHrJaCPdLu5MTPJD2Nx9i297VWQ0JRzN1AuLoxcB3xjCYnfToutaug55l7HdFwqhV5Rta37EFfEtjvCh5Vq+YqFZcIQPxeoaRGSDPCSC6MjIsrVkc0xFtrv6itJITym+7+rvTQtwR67F6jy3zO8efyKLzd0di6MbYbF5SPjRkZAkC4pqEBa8mnh/UgEd+76Hxd4fg9Fx0ro7+m+D0UNkwkTs7kuYsW4JGQfXI0kF6LqC0RyHJ7obRksvNFPkKbcYF5/22wyDMZmCnEXCdT8dXhmVxbPfP4fZ3hnNFFWu0I4NjikoOE4q4rKEdnRHU07GZ8x+tXjV2pR/72PqqukYLVNRDaYKvcPRk2ZlxSYUV4P8+vUS+oZ/gTvy5lLHcZ/UjVcUrM72mO3tCY8LcOzwARlJlk552vA/215B7nK2rZ0b6kUTelMB/71gOen7XsDvKzrlCR8VoaKWND/nN1K2vsiKWcfmYdd8+xnZaZ+iByuWjrDaocFHjxWyZ9MzFOSuqXB9yXKx6GVFPfK3VO7S16Nt0luQxqG/ny05C18I/bQIsO7HaeRlvkUwGDwrsZdHYd4e9m2/n4kXby31/2+Oz2XXhkfJyVx+7OghMVpeK5h06WZSto2nKH9PlT2j+ACLAjJSp/DSyMW1oVhCcwns9LtzWLf0YbIOvUHA7600i3m8WAtyd3Dw79GM6/PNST/7yOXbObBjDHmZv5U6uupsnvvPwwcFVcO4Pkv4e8sYigp2n7Tuzxa/N4+0lKdZ9uU0dv3pF0I/G567JY0NK+7l0N5H8Bamn6XCj/XEwUCQnIxlpGy9iTFd51LWtMi9fdewZ/PN5Bz+Dj2on3aHox/3XL83k8yDPxDwi6WaVY/Of8+fS+quG8jP+YVgsPRlDGdjKArz93Bg13/57qOn+ODR/NpSIKG9qeXZm7N558Gn2bPxWnIOL8HvK6x4RR3/uSODbkX5f5O270n++vVq/nvB0grV+oSB69j86w1kpL6It/BwuccB/9PFK95au4UDu0eTvm8qwUBQ6LBaCDKm249sWXUV6fuep6jg4ImnCusVF7jPm0VW2ofs3nA5U26YwadTCmtTYYT+3Wu/zPPxy7xFjJ72K0069McZdiVmezcUNaLUoX0nu0wQHQK+fLyF2yjIXcj+nR8z/7UN/Dz39NytJ67ey4Cbx9P3uvlEJtyAyXYhqhaNopx4CurRZwcDAXzePeRlzmH/jhk8OGQjLy6/mIrtvJM40+Pl9HLTr+yRQ6lSPldVB0FPGr6Li0eOp8fwz/FEX43V1R9VS0Q1mEsefNK2AwT8Rfh9KeRnf0dG6qes/W4F708uqIGyqwdCP8orIzOAT7nlybkkNGtEbOMO6HorFEMjnOFRGDStpLn4CgvIPLQHRd1EzuE/SN29hvcmpZKy9cz3sS9628uit7/lX/ctp2W35sQkdyEYbIfN1Qiby1VScQU5WWSnbwHpNw7uXsFvS7Yz+9WjHcufwN3llLsEbCbgP97cZAATAXs5ZsiPVO65ZTkUX90cWU5aQYqvIy6L3AqmBVDWsVsrkRhdTsOXgIPA6VvSOdN8zJm2ki5DV3PRjbE4I9rhCGtHMNAcZ0QcRvOxa68DPi+ZB/cRDG6lqGANB/es4Y/v9zBnmq/CXS1MBxZR9vp4CVhZXfKp3fNCZrvE0P8YGDRCxRUhlWQpdVeQ2a/6WPBGgKpcmpjUWuGmxwy0PV8pefaWVQFevMPHvm0BBKGMRI/hKtc9pBLdUC6pv+w0nXnTfXz2rJ9aeD2yQCAQCAQCgUAgEAgEAoFAIBAIBAKBQCAQCAQCgUAgEAgEAoFAIBAIBAKBQCAQCAQCgUAgEAgEAoFAIBAIBAKBQCAQCAQCgUAgEAgEAoFAIBAIBAKBQCAQCAQCgUAgEAgEAoFAIBAIBAKBQCAQCAQCgUAgEAgEAoFAIBAIBAKBQCAQCAQCgUAgEAgEAoFAIBAIBAKBQCAQCAQCgUAgEAgEAoFAIBAIBAKBQHBy/h9HKk31zPQdiwAAACV0RVh0ZGF0ZTpjcmVhdGUAMjAyNS0wNi0xMVQwNDoxOTowMiswMDowMJm6T0YAAAAldEVYdGRhdGU6bW9kaWZ5ADIwMjUtMDYtMTFUMDQ6MTk6MDIrMDA6MDDo5/f6AAAAAElFTkSuQmCC"
    designation = t.get("designation") or "NC"
    montant = float(t.get("montant") or 0)
    code_ref = t.get("code_ref","")
    dirn = t.get("direction","")
    intitule = t.get("intitule","") or t.get("description","") or ""
    num_compte = t.get("num_compte","") or ""
    date_r = t.get("date_reception","")
    amt_str = fmt_fcfa(montant)
    entries=[]
    if designation=="OM":
        nd=t.get("number_of_days","") or ""
        apd=t.get("amount_per_day","") or ""
        apd_s=fmt_fcfa(apd) if apd else ""
        entries=[
            {"num":"6057","lib":f"FM {dirn} — {intitule} ({nd} jr(s) x {apd_s} FCFA/jr)","deb":amt_str,"cre":""},
            {"num":"42860010","lib":f"Engagement FM {code_ref}","deb":"","cre":amt_str},
        ]
    elif designation=="NC":
        entries=[
            {"num":num_compte or "6...........","lib":f"NC — {intitule}","deb":amt_str,"cre":""},
            {"num":"42131150","lib":f"Avance/NC {code_ref} — {dirn}","deb":"","cre":amt_str},
        ]
    elif designation=="BC":
        entries=[
            {"num":num_compte or "60..........","lib":f"BC — {intitule}","deb":amt_str,"cre":""},
            {"num":"40110000","lib":f"Fournisseur BC {code_ref}","deb":"","cre":amt_str},
        ]
    elif designation=="LC":
        entries=[
            {"num":num_compte or "63..........","lib":f"LC — {intitule}","deb":amt_str,"cre":""},
            {"num":"40110000","lib":f"Fournisseur LC {code_ref}","deb":"","cre":amt_str},
        ]
    else:  # MARCHE
        entries=[
            {"num":num_compte or "60/24.......","lib":f"MARCHE — {intitule}","deb":amt_str,"cre":""},
            {"num":"40420010","lib":f"Fournisseur Marché {code_ref}","deb":"","cre":amt_str},
        ]
    n_empty=max(15-len(entries),8)
    rows=""
    for e in entries:
        rows+=f"<tr><td class='num'>{e['num']}</td><td>{e['lib']}</td><td class='debit'>{e['deb']}</td><td class='credit'>{e['cre']}</td></tr>"
    for _ in range(n_empty):
        rows+="<tr><td class='num'>&nbsp;</td><td>&nbsp;</td><td class='debit'>&nbsp;</td><td class='credit'>&nbsp;</td></tr>"
    return (
        "<div class='page'>"
        f"<div class='imp-logo'><img src='{LOGO}' alt='CAMTEL'/></div>"
        "<div class='imp-title'><h1>FICHE D\'IMPUTATION</h1></div>"
        "<div class='service-doc'>Service de la Documentation</div>"
        f"<div class='imp-meta'>"
        f"<div class='imp-meta-item'><span class='imp-meta-label'>DATE</span>&nbsp;<span class='imp-meta-val'>{date_r}</span></div>"
        f"<div class='imp-meta-item'><span class='imp-meta-label'>PIÈCE N°</span>&nbsp;<span class='imp-meta-val'>{code_ref}</span></div>"
        "</div>"
        "<table class='imp-table'><thead><tr>"
        "<th style='width:26%'>N° DE COMPTE</th><th style='width:46%'>LIBELLÉ</th>"
        "<th style='width:14%'>DÉBIT</th><th style='width:14%'>CRÉDIT</th>"
        f"</tr></thead><tbody>{rows}</tbody></table>"
        f"<div class='imp-totals'><span>TOTAL DÉBIT : {amt_str} FCFA</span><span>TOTAL CRÉDIT : {amt_str} FCFA</span></div>"
        "</div>"
    )



@app.get("/fiche", response_class=HTMLResponse)
def fiche(request: Request, ids: str, db=Depends(get_db)):
    u = require_login(request)
    tx_ids=[int(i.strip()) for i in ids.split(",") if i.strip().isdigit()]
    txs=[]
    for tid in tx_ids[:20]:
        t=db.get(Transaction, tid)
        if t: txs.append(dict(t))
    pages=[]
    for i in range(0,len(txs),2):
        pair=txs[i:i+2]
        blocks="".join(_fiche_block(t,db) for t in pair)
        if len(pair)==1: blocks+="<div style='height:5mm'></div>"
        pages.append(f"<div class='page'>{blocks}</div>")
    FICHE_CSS="""
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:Arial,Helvetica,sans-serif;font-size:9pt;color:#000;background:#e5e7eb;}
.noprint{padding:8px 12px;background:#1e3a8a;display:flex;gap:8px;align-items:center;position:sticky;top:0;z-index:99;}
.noprint button{padding:7px 16px;background:#00b0e8;color:#fff;border:none;border-radius:5px;cursor:pointer;font-weight:800;font-size:12px;}
.noprint button.cl{background:#475569;}
/* Each page holds exactly 2 fiches */
.page{width:210mm;height:297mm;padding:5mm 7mm;display:flex;flex-direction:column;gap:3mm;page-break-after:always;background:#fff;}
.fiche{border:2px solid #003e7e;padding:3mm 4mm;flex:1;display:flex;flex-direction:column;position:relative;overflow:hidden;}
/* Watermark */
.wm{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%) rotate(-20deg);pointer-events:none;z-index:0;user-select:none;}
/* All content above watermark */
.fhdr,.sec,.box,.amt-box,.solde-box,.dispo,.att-box,.initby,.signs{position:relative;z-index:1;}
/* Header */
.fhdr{display:flex;align-items:center;gap:5px;padding-bottom:2mm;border-bottom:2.5px solid #003e7e;margin-bottom:2mm;}
.flogo{background:linear-gradient(135deg,#003e7e,#00b0e8);border-radius:5px;padding:3px;flex-shrink:0;}
.ftitle{flex:1;}
.ftitle h1{font-size:8.5pt;font-weight:900;color:#003e7e;line-height:1.2;}
.ftitle p{font-size:7pt;color:#64748b;margin-top:1px;}
.fref{text-align:right;font-size:7.5pt;font-weight:700;color:#003e7e;flex-shrink:0;white-space:nowrap;}
/* Bilingual section headers */
.sec{background:#003e7e;color:#fff;padding:1.5px 5px;font-size:7.5pt;font-weight:900;text-transform:uppercase;margin:1.5mm 0 1mm;letter-spacing:.05em;}
.sec .en{font-weight:900;}
.sec .fr{font-weight:400;opacity:.85;}
.sec .sep{margin:0 4px;opacity:.5;}
/* Info box */
.box{border:1px solid #334155;padding:1.5mm 3mm;margin-bottom:1mm;}
.r{display:flex;border-bottom:1px dotted #e2e8f0;padding:1px 0;align-items:flex-start;}
.r:last-child{border-bottom:none;}
.rl{color:#334155;min-width:140px;font-size:7.5pt;flex-shrink:0;padding-right:4px;}
.rv{flex:1;font-size:8pt;word-break:break-word;}
.mono{font-family:"Courier New",monospace;font-weight:700;}
.small{font-size:7pt;}
/* Amount box */
.amt-box{background:linear-gradient(135deg,#f0f7ff,#e0effe);border:2px solid #003e7e;padding:2mm 3mm;margin:1.5mm 0;text-align:center;}
.amt-lbl{font-size:7pt;font-weight:800;color:#475569;letter-spacing:.12em;text-transform:uppercase;}
.amt-val{font-size:15pt;font-weight:900;color:#003e7e;letter-spacing:1px;margin-top:1mm;font-family:"Courier New",monospace;}
/* Balance table */
.solde-box{border:1px solid #334155;padding:1.5mm 3mm;margin:1mm 0;}
.solde-r{display:flex;justify-content:space-between;padding:1px 0;font-size:8pt;border-bottom:1px dotted #f1f5f9;align-items:center;}
.solde-r:last-child{border-bottom:none;}
.solde-r.final{font-weight:900;font-size:9pt;margin-top:1mm;border-top:1.5px solid #334155;padding-top:1.5mm;}
/* Available / Disponible */
.dispo{border:2px solid #000;padding:1.5mm 4mm;display:flex;justify-content:space-between;align-items:center;margin:1.5mm 0;}
.dispo-lbl{font-weight:900;font-size:10pt;letter-spacing:.1em;}
.chks{display:flex;gap:14px;font-size:9.5pt;font-weight:800;}
.chk{display:flex;align-items:center;gap:5px;}
.chkb{width:13px;height:13px;border:2px solid #000;display:inline-flex;align-items:center;justify-content:center;font-size:9pt;font-weight:900;}
.chkb.ok{border-color:#16a34a;background:#dcfce7;color:#16a34a;}
.chkb.nok{border-color:#dc2626;background:#fee2e2;color:#dc2626;}
/* Attachments */
.att-box{border:1px dashed #334155;padding:1.5mm 3mm;margin:1mm 0;min-height:8mm;font-size:7.5pt;}
.att-item{padding:1px 0;color:#1e3a8a;font-weight:600;}
.att-meta{color:#64748b;font-weight:400;}
.att-none{color:#94a3b8;font-style:italic;font-size:7.5pt;}
/* Initiated by */
.initby{font-size:7.5pt;color:#475569;text-align:right;margin:1mm 0;}
/* Single signature box - BUDGET SERVICE/SAAF only */
.signs{margin-top:auto;}
.sign-only{border:1.5px solid #003e7e;padding:2mm 3mm;min-height:35mm;background:linear-gradient(180deg,#f8faff,#fff);}
.sign-only>label{font-size:8pt;font-weight:900;text-transform:uppercase;color:#003e7e;display:block;letter-spacing:.06em;border-bottom:1px solid #e2e8f0;padding-bottom:1.5mm;margin-bottom:1.5mm;}
@media print{
  .noprint{display:none!important;}
  body{background:#fff;}
  .page{padding:4mm 6mm;width:210mm;height:297mm;}
  @page{size:A4 portrait;margin:0;}
}"""
    return HTMLResponse(f"""<!doctype html><html lang='fr'><head><meta charset='utf-8'/>
<title>Fiches DCF</title><style>{FICHE_CSS}</style></head><body>
<div class='noprint'>
  <button onclick='window.print()'>🖨 Imprimer / PDF</button>
  <button onclick='window.close()' style='background:#64748b'>Fermer</button>
  <span style='font-size:12px;color:#64748b'>{len(txs)} fiche(s) — {len(pages)} page(s) A4</span>
</div>
{"".join(pages)}
</body></html>""")

def _fiche_block(t, db):
    import json as _json
    bl=db.query(BudgetLine).filter_by(imputation=t["imputation"],year=t["year"]).first()
    prevision=bl.budget_cp if bl else 0
    libelle_bl=bl.libelle if bl else (t["imputation"] or "—")
    eng_before=(db.query(func.coalesce(func.sum(Transaction.montant),0)).filter(
        Transaction.imputation==t["imputation"],Transaction.year==t["year"],
        Transaction.status=="validated",Transaction.id<t["id"]).scalar() or 0)
    solde_avant=prevision-eng_before; solde_apres=solde_avant-t["montant"]; dispo=solde_apres>=0
    gc="#16a34a" if dispo else "#dc2626"
    oui_chk=f"<div class='chkb ok'>✓</div>" if dispo else "<div class='chkb'></div>"
    non_chk=f"<div class='chkb nok'>✓</div>" if not dispo else "<div class='chkb'></div>"
    # Attachments
    try: atts=_json.loads(t.get("attachments") or "[]")
    except: atts=[]
    att_html="".join(f"<div class='att-item'>📎 {a['name']} <span class='att-meta'>({a.get('uploaded_by','')}, {a.get('uploaded_at','')})</span></div>" for a in atts) if atts else "<div class='att-none'>Aucun document joint / No supporting document attached</div>"
    return f"""
<div class='fiche'>
  <!-- Watermark logo -->
  <div class='wm'><img src='data:image/png;base64,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' style='width:220px;height:220px;object-fit:contain;opacity:.04' alt=''/></div>

  <!-- HEADER -->
  <div class='fhdr'>
    <div class='flogo'><img src='data:image/png;base64,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' style='width:38px;height:38px;object-fit:contain;filter:brightness(0) invert(1)' alt='CAMTEL'/></div>
    <div class='ftitle'>
      <h1>CAMTEL — {t.get("direction","—")} | BUDGET MONITORING SHEET / FICHE DE SUIVI BUDGÉTAIRE</h1>
      <p>SAAF / DCF / BUDGET CONTROL — CONTRÔLE BUDGÉTAIRE</p>
    </div>
    <div class='fref'>Réf: {t["code_ref"]}<br/>{t["date_reception"]}</div>
  </div>

  <!-- BUDGETARY ACCOUNT / COMPTE BUDGÉTAIRE -->
  <div class='sec'>
    <span class='en'>BUDGETARY ACCOUNT</span> <span class='sep'>|</span>
    <span class='fr'>COMPTE BUDGÉTAIRE</span>
  </div>
  <div class='box'>
    <div class='r'>
      <span class='rl'><b>Account forecast / Prévision:</b></span>
      <span class='rv mono'><b>{fmt_fcfa(prevision)} FCFA</b></span>
    </div>
    <div class='r'>
      <span class='rl'>Accounting note – Opening balance / Note comptabilité – Solde initial:</span>
      <span class='rv mono'>{fmt_fcfa(prevision)} FCFA</span>
    </div>
  </div>

  <!-- REFERENCE / DESCRIPTION / COMMITMENT -->
  <div class='sec'>
    <span class='en'>REFERENCE / DESCRIPTION / COMMITMENT</span> <span class='sep'>|</span>
    <span class='fr'>RÉFÉRENCE / LIBELLÉ / ENGAGEMENT</span>
  </div>
  <div class='box'>
    <div class='r'><span class='rl'>Account ref. / Réf. compte:</span><span class='rv mono small'>{t["imputation"]}</span></div>
    <div class='r'><span class='rl'>Code / File Ref. / Réf. dossier:</span><span class='rv'><b>{t["code_ref"]}</b></span></div>
    <div class='r'><span class='rl'>Direction:</span><span class='rv'><b>{t["direction"]}</b></span></div>
    <div class='r'><span class='rl'>Date:</span><span class='rv'>{t["date_reception"]}</span></div>
    <div class='r'><span class='rl'>Nature:</span><span class='rv'>{t["nature"]}</span></div>
    <div class='r'><span class='rl'>Label(s) / Libellé(s):</span><span class='rv'><b>{libelle_bl}</b></span></div>
    <div class='r'><span class='rl'>Object / Description / Objet:</span><span class='rv'>{t["description"] or t["intitule"] or "—"}</span></div>
  </div>

  <!-- AMOUNT / MONTANT -->
  <div class='amt-box'>
    <div class='amt-lbl'>AMOUNT OF COMMITMENT / MONTANT DE L'ENGAGEMENT</div>
    <div class='amt-val'>{fmt_fcfa(t["montant"])} FCFA</div>
  </div>

  <!-- BALANCE TABLE / TABLEAU DES SOLDES -->
  <div class='solde-box'>
    <div class='solde-r'>
      <span>Balance before commitment / Solde avant engagement:</span>
      <span class='mono'>{fmt_fcfa(solde_avant)} FCFA</span>
    </div>
    <div class='solde-r'>
      <span>Commitment / Engagement:</span>
      <span class='mono'>- {fmt_fcfa(t["montant"])} FCFA</span>
    </div>
    <div class='solde-r final'>
      <span>FINAL ACCOUNT BALANCE / SOLDE FINAL DU COMPTE:</span>
      <span class='mono' style='color:{gc}'>{fmt_fcfa(solde_apres)} FCFA</span>
    </div>
  </div>

  <!-- AVAILABLE / DISPONIBLE -->
  <div class='dispo'>
    <div class='dispo-lbl'>AVAILABLE / DISPONIBLE</div>
    <div class='chks'>
      <div class='chk'>{oui_chk} YES / OUI</div>
      <div class='chk'>{non_chk} NO / NON</div>
    </div>
  </div>

  <!-- SUPPORTING DOCUMENTS / PIÈCES JUSTIFICATIVES -->
  <div class='sec'>
    <span class='en'>SUPPORTING DOCUMENTS</span> <span class='sep'>|</span>
    <span class='fr'>PIÈCES JUSTIFICATIVES</span>
  </div>
  <div class='att-box'>{att_html}</div>

  <!-- SIGNATURE -->
  <div class='initby'>Initiated by / Initié par : <b>{t.get("created_by_name") or t.get("created_by","—")}</b></div>
  <div class='signs'>
    <div class='sign sign-only'>
      <label>VISA BUDGET SERVICE / SAAF — CONTRÔLEUR BUDGÉTAIRE</label>
      <div style='display:grid;grid-template-columns:1fr 1fr;gap:4mm;margin-top:2mm'>
        <div>
          <div style='font-size:7pt;color:#475569;font-weight:700'>NAME / NOM:</div>
          <div style='border-bottom:1px solid #334155;height:10mm;margin-top:1mm'></div>
        </div>
        <div>
          <div style='font-size:7pt;color:#475569;font-weight:700'>DATE:</div>
          <div style='border-bottom:1px solid #334155;height:10mm;margin-top:1mm'></div>
        </div>
      </div>
      <div style='margin-top:2mm'>
        <div style='font-size:7pt;color:#475569;font-weight:700'>SIGNATURE / CACHET:</div>
        <div style='border-bottom:1px solid #334155;height:14mm;margin-top:1mm'></div>
      </div>
    </div>
  </div>
</div>"""



















































# ── Version / Health ──────────────────────────────────────────────
@app.get("/version")
def version(db: Session=Depends(get_db)):
    try:
        stats={"users":db.query(func.count(User.id)).scalar(),
               "transactions":db.query(func.count(Transaction.id)).scalar(),
               "budget_lines":db.query(func.count(BudgetLine.id)).scalar()}
    except Exception as e: stats={"error":str(e)}
    return {"version":"v10-single-file-sqlalchemy","status":"ok","db":stats}


























LOGIN_HTML = '<!DOCTYPE html>\n<html lang="fr">\n<head>\n<meta charset="UTF-8">\n<meta name="viewport" content="width=device-width,initial-scale=1">\n<title>CAMTEL Budget — Connexion</title>\n<style>\n*{box-sizing:border-box;margin:0;padding:0}\nbody{min-height:100vh;display:flex;align-items:center;justify-content:center;\n  background:linear-gradient(135deg,#020810 0%,#0a1f4e 50%,#020810 100%);\n  font-family:"Segoe UI",system-ui,sans-serif;color:#e2eaff}\n.box{background:rgba(8,18,50,.92);border:1px solid rgba(0,180,255,.2);border-radius:16px;\n  padding:40px 36px;width:360px;box-shadow:0 20px 60px rgba(0,0,0,.6)}\n.logo{text-align:center;margin-bottom:28px}\n.logo h1{font-size:20px;font-weight:800;color:#00d4ff;letter-spacing:.5px}\n.logo p{font-size:11px;color:#7aaccc;margin-top:4px}\n.fld{margin-bottom:16px}\n.fld label{display:block;font-size:10px;font-weight:700;color:#7aaccc;\n  text-transform:uppercase;letter-spacing:.08em;margin-bottom:5px}\n.fld input{width:100%;padding:10px 12px;background:rgba(0,15,50,.8);\n  color:#e2eaff;border:1.5px solid rgba(0,100,200,.3);border-radius:8px;\n  font-size:13px;font-family:inherit;transition:border-color .2s}\n.fld input:focus{outline:none;border-color:#00d4ff;box-shadow:0 0 0 3px rgba(0,180,255,.12)}\n.btn{width:100%;padding:11px;background:linear-gradient(135deg,#0d3a7a,#1a5aa0);\n  color:#fff;border:none;border-radius:8px;font-size:13px;font-weight:700;\n  cursor:pointer;transition:all .2s;margin-top:4px}\n.btn:hover{background:linear-gradient(135deg,#1a5aa0,#0080cc)}\n.btn:disabled{opacity:.6;cursor:not-allowed}\n.err{background:rgba(220,38,38,.15);border:1px solid rgba(220,38,38,.4);\n  color:#fca5a5;padding:8px 12px;border-radius:6px;font-size:12px;margin-top:10px;text-align:center}\n.ver{text-align:center;margin-top:18px;font-size:10px;color:#3a5a7a}\n</style>\n</head>\n<body>\n<div class="box">\n  <div class="logo">\n    <h1>📊 CAMTEL Budget</h1>\n    <p>Système de gestion budgétaire</p>\n  </div>\n  <div class="fld">\n    <label>Identifiant</label>\n    <input type="text" id="u" placeholder="admin" autocomplete="username" autofocus>\n  </div>\n  <div class="fld">\n    <label>Mot de passe</label>\n    <input type="password" id="p" placeholder="••••••••" autocomplete="current-password"\n      onkeydown="if(event.key===\'Enter\')doLogin()">\n  </div>\n  <div id="err"></div>\n  <button class="btn" id="lbtn" onclick="doLogin()">Se connecter</button>\n  <div class="ver">v10 — Single-file deployment</div>\n</div>\n<script>\nasync function doLogin(){\n  const u=document.getElementById(\'u\').value.trim();\n  const p=document.getElementById(\'p\').value;\n  const btn=document.getElementById(\'lbtn\');\n  const errEl=document.getElementById(\'err\');\n  if(!u||!p){errEl.innerHTML=\'<div class="err">Veuillez saisir identifiant et mot de passe.</div>\';return;}\n  btn.disabled=true;btn.textContent=\'Connexion...\';errEl.innerHTML=\'\';\n  try{\n    const r=await fetch(\'/api/login/token\',{\n      method:\'POST\',\n      headers:{\'Content-Type\':\'application/json\'},\n      credentials:\'include\',\n      body:JSON.stringify({username:u,password:p})\n    });\n    if(r.ok){\n      const d=await r.json();\n      sessionStorage.setItem(\'camtel_token\',d.token);\n      sessionStorage.setItem(\'camtel_role\',d.role);\n      window.location=\'/\';\n    } else {\n      errEl.innerHTML=\'<div class="err">❌ Identifiants incorrects. Vérifiez et réessayez.</div>\';\n      btn.disabled=false;btn.textContent=\'Se connecter\';\n    }\n  }catch(e){\n    errEl.innerHTML=\'<div class="err">❌ Erreur réseau. Vérifiez votre connexion.</div>\';\n    btn.disabled=false;btn.textContent=\'Se connecter\';\n  }\n}\n</script>\n</body>\n</html>\n'

APP_HTML = '<!DOCTYPE html>\n<html lang="fr">\n<head>\n<meta charset="UTF-8">\n<meta name="viewport" content="width=device-width,initial-scale=1">\n<title>CAMTEL Budget v10</title>\n<style>\n:root{--navy:#020a1a;--camtel:#00d4ff;--green:#00e676;--red:#ff4444;--yel:#ffb300;\n  --bg:#060d1a;--card:#0d1b35;--bdr:rgba(0,160,240,.2);--txt:#e2eaff;--muted:#7a9cc0}\n*{box-sizing:border-box;margin:0;padding:0}\nbody{font-family:"Segoe UI",system-ui,sans-serif;background:var(--bg);color:var(--txt);font-size:13px;min-height:100vh}\ninput,select,textarea{background:rgba(4,12,38,.92)!important;color:#c8daf0!important;\n  border:1px solid rgba(0,120,200,.35)!important;border-radius:6px;font-family:inherit;font-size:12px}\ninput:focus,select:focus{outline:none;border-color:var(--camtel)!important;box-shadow:0 0 0 2px rgba(0,180,255,.12)!important}\nheader{background:linear-gradient(135deg,#020810,#0a1f4e,#0d3060);color:#fff;padding:0 14px;height:58px;\n  display:flex;align-items:center;gap:10px;position:sticky;top:0;z-index:200;\n  box-shadow:0 2px 20px rgba(0,180,255,.2);border-bottom:1px solid rgba(0,180,255,.15)}\n.hbrand h1{font-size:14px;font-weight:800;color:#00d4ff}\n.hbrand p{font-size:9px;color:#5a8aaa}\nnav{display:flex;gap:3px;margin:0 8px;flex-wrap:wrap}\nnav button{background:rgba(0,80,180,.2);color:rgba(200,225,255,.75);border:1px solid rgba(0,150,255,.15);\n  padding:5px 10px;border-radius:5px;cursor:pointer;font-size:11px;font-weight:600;transition:all .15s}\nnav button:hover{background:rgba(0,120,220,.35);color:#fff}\nnav button.active{background:rgba(0,140,255,.3);color:#00d4ff;border-color:rgba(0,200,255,.4)}\n.upill{background:rgba(255,255,255,.1);padding:3px 9px;border-radius:20px;font-size:11px;\n  display:flex;align-items:center;gap:5px;white-space:nowrap}\n.ml{margin-left:auto}\n.btn-logout{background:#dc2626;color:#fff;border:none;padding:5px 11px;border-radius:6px;\n  cursor:pointer;font-size:11px;font-weight:700;margin-left:6px}\n.wrap{max-width:100%;padding:10px 14px}\n.krow{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:12px}\n.kpi{background:linear-gradient(135deg,rgba(10,28,60,.95),rgba(15,35,75,.9));\n  border:1px solid rgba(0,180,255,.2);border-radius:12px;padding:14px 16px;\n  box-shadow:0 4px 20px rgba(0,0,0,.5)}\n.kpi label{font-size:9px;text-transform:uppercase;letter-spacing:.08em;color:#7aaccc;font-weight:700}\n.kpi .val{font-size:20px;font-weight:800;margin-top:4px}\n.kpi.kb .val{color:#4499ff}.kpi.kr .val{color:#ff4444}.kpi.ky .val{color:#ffb300}.kpi.kg .val{color:#00e676}\n.gbar{display:flex;align-items:center;gap:8px;margin-bottom:10px;\n  background:rgba(0,12,40,.75);border:1px solid rgba(0,120,255,.15);border-radius:8px;padding:8px 12px;flex-wrap:wrap}\n.gbar label{font-size:10px;font-weight:700;color:#7aaccc;text-transform:uppercase}\n.gbar select,.gbar input[type=number]{padding:5px 8px;border-radius:5px;min-width:80px}\n.tab-content{display:none}.tab-content.active{display:block}\n.card{background:rgba(8,18,45,.88);border:1px solid var(--bdr);border-radius:12px;\n  overflow:hidden;margin-bottom:10px;box-shadow:0 4px 20px rgba(0,0,0,.4)}\n.ch{padding:10px 14px;border-bottom:1px solid var(--bdr);display:flex;align-items:center;\n  justify-content:space-between;background:linear-gradient(90deg,rgba(0,30,90,.9),rgba(0,20,60,.95))}\n.ch h2{font-size:12px;font-weight:700;color:#80ccee}\n.cb{padding:12px}\n.g2{display:grid;grid-template-columns:1fr 1fr;gap:10px}\n.btn{padding:6px 12px;border-radius:7px;border:none;cursor:pointer;font-size:11px;font-weight:700;\n  font-family:inherit;transition:all .15s;display:inline-flex;align-items:center;gap:4px}\n.bp{background:linear-gradient(135deg,#0d3a7a,#1a5aa0);color:#fff}\n.bp:hover{background:#0080cc}.bs{background:#374151;color:#e5e7eb}.bs:hover{background:#4b5563}\n.bd{background:#dc2626;color:#fff}.bd:hover{background:#b91c1c}\n.bg{background:#065f46;color:#d1fae5}.bg:hover{background:#047857}\n.alrt{padding:8px 11px;border-radius:6px;font-size:11px;margin-bottom:8px;border-left:3px solid}\n.alrt-r{background:rgba(220,38,38,.1);color:#fca5a5;border-color:#dc2626}\n.alrt-y{background:rgba(180,100,0,.15);color:#fcd34d;border-color:#f59e0b}\n.alrt-g{background:rgba(0,80,30,.2);color:#6ee7b7;border-color:#00e676}\n.alrt-b{background:rgba(30,64,175,.15);color:#93c5fd;border-color:#3b82f6}\n.prg{height:5px;background:rgba(0,40,100,.4);border-radius:3px;overflow:hidden;margin-top:4px}\n.prf{height:100%;border-radius:3px;background:linear-gradient(90deg,#0080ff,#00d4ff)}\ntable{width:100%;border-collapse:collapse;font-size:11px}\nth{background:rgba(0,20,60,.8);color:#80b8e0;font-weight:700;padding:7px 8px;\n  text-align:left;border-bottom:1px solid var(--bdr);white-space:nowrap}\ntd{padding:6px 8px;border-bottom:1px solid rgba(0,60,120,.15);vertical-align:middle}\ntr:hover td{background:rgba(0,80,180,.06)}\n.badge{display:inline-block;padding:2px 7px;border-radius:10px;font-size:10px;font-weight:700}\n.b-ok{background:rgba(0,150,60,.2);color:#6ee7b7;border:1px solid rgba(0,200,80,.3)}\n.b-dep{background:rgba(220,38,38,.15);color:#fca5a5;border:1px solid rgba(220,38,38,.3)}\n.b-pend{background:rgba(180,100,0,.15);color:#fcd34d;border:1px solid rgba(240,160,0,.3)}\n.fld{margin-bottom:10px}.fld label{display:block;font-size:10px;font-weight:700;\n  color:#80aacc;margin-bottom:3px;text-transform:uppercase;letter-spacing:.04em}\n.fld input,.fld select,.fld textarea{width:100%;padding:7px 9px;border-radius:6px;\n  border:1.5px solid rgba(0,100,200,.35)!important}\n.fr{display:grid;gap:8px}.fc2{grid-template-columns:1fr 1fr}.fc3{grid-template-columns:1fr 1fr 1fr}\n.mbg{display:none;position:fixed;inset:0;background:rgba(5,15,40,.7);z-index:300;\n  align-items:flex-start;justify-content:center;padding-top:30px;overflow-y:auto}\n.mbg.open{display:flex}\n.modal{background:rgba(6,15,48,.97);border:1px solid var(--bdr);border-radius:13px;\n  width:min(640px,96vw);max-height:88vh;overflow-y:auto;box-shadow:0 20px 60px rgba(0,0,0,.6)}\n.mh{padding:11px 15px;border-bottom:1px solid var(--bdr);display:flex;align-items:center;\n  justify-content:space-between;background:rgba(0,20,60,.8);position:sticky;top:0;z-index:1}\n.mh h3{font-size:13px;font-weight:700}.mb{padding:16px}\n.mf{padding:10px 15px;border-top:1px solid var(--bdr);display:flex;gap:7px;\n  justify-content:flex-end;background:rgba(0,15,50,.8)}\n/* Drop zone */\n.dropzone{display:block;border:2px dashed rgba(0,180,100,.4);border-radius:10px;padding:24px;\n  text-align:center;cursor:pointer;background:rgba(0,60,20,.08);transition:all .2s;margin-bottom:10px}\n.dropzone:hover{border-color:rgba(0,230,118,.65);background:rgba(0,60,20,.2)}\n.dropzone .dz-icon{font-size:36px;margin-bottom:8px;pointer-events:none}\n.dropzone .dz-label{font-size:12px;font-weight:700;color:#80d4b0;pointer-events:none}\n.dropzone .dz-hint{font-size:10px;color:#5a8aaa;margin-top:3px;pointer-events:none}\n.dropzone .dz-name{margin-top:8px;font-size:12px;color:#00e676;font-weight:700;pointer-events:none;min-height:18px}\n.dropzone.bl-zone{border-color:rgba(0,120,255,.3);background:rgba(0,40,100,.08)}\n.dropzone.bl-zone:hover{border-color:rgba(0,180,255,.6);background:rgba(0,40,100,.2)}\n.dropzone.bl-zone .dz-label{color:#80b8e0}\n.dropzone.bl-zone .dz-name{color:#00d4ff}\n</style>\n</head>\n<body>\n\n<header>\n  <div class="hbrand"><h1>📊 CAMTEL Budget</h1><p>Gestion budgétaire v10</p></div>\n  <nav>\n    <button id="nav-dashboard" onclick="showTab(\'dashboard\')" class="active">🏠 Tableau de bord</button>\n    <button id="nav-transactions" onclick="showTab(\'transactions\')">📋 Transactions</button>\n    <button id="nav-budgetlines" onclick="showTab(\'budgetlines\')">💰 Budget</button>\n    <button id="nav-import" onclick="showTab(\'import\')">⬆ Import/Export</button>\n    <button id="nav-planning" onclick="showTab(\'planning\')">📅 Planning PTA</button>\n    <button id="nav-users" onclick="showTab(\'users\')" class="admin-only">👥 Utilisateurs</button>\n  </nav>\n  <div class="ml" style="display:flex;align-items:center;gap:8px">\n    <div class="upill"><span id="h-role">—</span> · <span id="h-name">—</span></div>\n    <button class="btn-logout" onclick="logout()">Déconnexion</button>\n  </div>\n</header>\n\n<div class="wrap">\n\n<!-- GBAR -->\n<div class="gbar" id="g-bar">\n  <label>Année</label>\n  <select id="g-year" onchange="onYearChange()"></select>\n  <label style="margin-left:8px">Direction</label>\n  <select id="g-dir" onchange="onDirChange()">\n    <option value="">Toutes</option>\n  </select>\n  <button class="btn bs" style="margin-left:auto;padding:4px 10px;font-size:11px" onclick="reloadAll()">🔄 Actualiser</button>\n</div>\n\n<!-- ════════ DASHBOARD ════════ -->\n<div id="tab-dashboard" class="tab-content active">\n  <div class="krow">\n    <div class="kpi kb"><label>Budget CP Total</label><div class="val" id="k-bud">—</div><div style="font-size:10px;color:#5a8aaa;margin-top:2px">FCFA</div></div>\n    <div class="kpi kr"><label>Cumul Engagé</label><div class="val" id="k-eng">—</div><div style="font-size:10px;color:#5a8aaa;margin-top:2px">FCFA</div></div>\n    <div class="kpi ky"><label>En Attente Validation</label><div class="val" id="k-pend">—</div><div style="font-size:10px;color:#5a8aaa;margin-top:2px">FCFA</div></div>\n    <div class="kpi kg"><label>Disponible</label><div class="val" id="k-dispo">—</div><div style="font-size:10px;color:#5a8aaa;margin-top:2px">FCFA</div></div>\n  </div>\n  <div class="g2">\n    <div class="card">\n      <div class="ch"><h2>📊 Taux d\'exécution par direction</h2></div>\n      <div class="cb" id="db-dirs">Chargement...</div>\n    </div>\n    <div class="card">\n      <div class="ch"><h2>⚠️ Imputations en dépassement</h2></div>\n      <div class="cb" id="db-overdraw">Chargement...</div>\n    </div>\n  </div>\n  <div class="card">\n    <div class="ch"><h2>🕐 Transactions récentes</h2></div>\n    <div class="cb">\n      <table><thead><tr><th>Date</th><th>Direction</th><th>Imputation</th><th>Intitulé</th><th>Montant</th><th>Statut</th></tr></thead>\n      <tbody id="db-recent"></tbody></table>\n    </div>\n  </div>\n</div>\n\n<!-- ════════ TRANSACTIONS ════════ -->\n<div id="tab-transactions" class="tab-content">\n  <div class="card">\n    <div class="ch">\n      <h2>📋 Transactions</h2>\n      <div style="display:flex;gap:6px">\n        <input id="tx-search" placeholder="Rechercher..." style="padding:4px 8px;width:180px" oninput="searchTx()">\n        <button class="btn bp viewer-hide" onclick="openModal(\'m-new-tx\')">+ Nouvelle TX</button>\n      </div>\n    </div>\n    <div class="cb">\n      <table>\n        <thead><tr><th>Date</th><th>Direction</th><th>Imputation</th><th>Intitulé</th><th>Montant</th><th>Statut Budget</th><th>Validation</th><th>Actions</th></tr></thead>\n        <tbody id="tx-tbody"></tbody>\n      </table>\n      <div id="tx-empty" style="text-align:center;padding:20px;color:#5a8aaa;display:none">Aucune transaction trouvée.</div>\n    </div>\n  </div>\n</div>\n\n<!-- ════════ BUDGET LINES ════════ -->\n<div id="tab-budgetlines" class="tab-content">\n  <div class="card">\n    <div class="ch">\n      <h2>💰 Lignes budgétaires</h2>\n      <button class="btn bp admin-only" onclick="openModal(\'m-new-bl\')">+ Nouvelle ligne</button>\n    </div>\n    <div class="cb">\n      <table>\n        <thead><tr><th>Année</th><th>Direction</th><th>Imputation</th><th>Libellé</th><th>Nature</th><th>Budget CP</th><th>Engagé</th><th>Disponible</th><th>Actions</th></tr></thead>\n        <tbody id="bl-tbody"></tbody>\n      </table>\n      <div id="bl-empty" style="text-align:center;padding:20px;color:#5a8aaa;display:none">Aucune ligne budgétaire trouvée.</div>\n    </div>\n  </div>\n</div>\n\n<!-- ════════ IMPORT / EXPORT ════════ -->\n<div id="tab-import" class="tab-content">\n  <div class="g2">\n\n    <!-- IMPORT TRANSACTIONS -->\n    <div class="card">\n      <div class="ch" style="background:linear-gradient(90deg,rgba(0,50,15,.9),rgba(0,30,10,.95))">\n        <h2 style="color:#6ee7b7">⬆ Import Transactions</h2>\n      </div>\n      <div class="cb">\n        <div class="alrt alrt-g" style="font-size:10px;margin-bottom:10px">\n          <strong>✅ Compatible CAMTEL CSV/Excel</strong><br>\n          Colonnes: DATE ENGAGEMENT · DIRECTION · IMPUTATION · MONTANT · INTITULE<br>\n          <span style="opacity:.8">La ligne "SITUATION DES ENGAGEMENTS..." est ignorée automatiquement.</span>\n        </div>\n        <div class="fld" style="margin-bottom:10px">\n          <label>Année *</label>\n          <input type="number" id="imp-tx-year" value="2025" min="2020" max="2035" style="width:120px;padding:8px">\n        </div>\n\n        <!-- FILE INPUT — hidden but reachable via label -->\n        <input type="file" id="imp-tx-file" accept=".csv,.xlsx,.xls,.txt"\n          style="position:absolute;width:1px;height:1px;opacity:0;overflow:hidden;pointer-events:none"\n          onchange="onFileSel(this,\'imp-tx-name\',\'imp-tx-area\')">\n        <label for="imp-tx-file" id="imp-tx-area" class="dropzone">\n          <div class="dz-icon">📂</div>\n          <div class="dz-label">Cliquez ici pour choisir un fichier CSV ou Excel</div>\n          <div class="dz-hint">CSV, XLSX, XLS — UTF-8, Latin-1 acceptés</div>\n          <div class="dz-name" id="imp-tx-name"></div>\n        </label>\n\n        <div style="display:flex;gap:8px;margin-top:4px;flex-wrap:wrap">\n          <button class="btn bp" style="padding:9px 18px" id="imp-tx-btn" onclick="importTx()">⬆ Importer</button>\n          <button class="btn bs" style="padding:9px 14px" onclick="dlTemplate(\'transactions\')">⬇ Template CSV</button>\n        </div>\n        <div id="imp-tx-result" style="margin-top:10px"></div>\n      </div>\n    </div>\n\n    <!-- IMPORT BUDGET LINES -->\n    <div class="card">\n      <div class="ch" style="background:linear-gradient(90deg,rgba(0,30,80,.9),rgba(0,15,55,.95))">\n        <h2 style="color:#93c5fd">⬆ Import Lignes Budgétaires</h2>\n      </div>\n      <div class="cb">\n        <div class="alrt alrt-b" style="font-size:10px;margin-bottom:10px">\n          <strong>Colonnes requises:</strong> YEAR · DIRECTION · IMPUTATION COMPTABLE · LIBELLE · NATURE · BUDGET CP (FCFA)<br>\n          <span style="opacity:.8">Pour créer/mettre à jour le budget 2025, 2026, 2027...</span>\n        </div>\n\n        <!-- FILE INPUT — hidden but reachable via label -->\n        <input type="file" id="imp-bl-file" accept=".csv,.xlsx,.xls,.txt"\n          style="position:absolute;width:1px;height:1px;opacity:0;overflow:hidden;pointer-events:none"\n          onchange="onFileSel(this,\'imp-bl-name\',\'imp-bl-area\')">\n        <label for="imp-bl-file" id="imp-bl-area" class="dropzone bl-zone">\n          <div class="dz-icon">📊</div>\n          <div class="dz-label">Cliquez ici pour choisir un fichier budget</div>\n          <div class="dz-hint">CSV, XLSX, XLS — UTF-8, Latin-1 acceptés</div>\n          <div class="dz-name" id="imp-bl-name"></div>\n        </label>\n\n        <div class="fld" style="margin:8px 0 10px">\n          <label>Année (si absente du fichier)</label>\n          <input type="number" id="imp-bl-year" value="2025" min="2020" max="2035" style="width:120px;padding:8px">\n        </div>\n        <div style="display:flex;gap:8px;flex-wrap:wrap">\n          <button class="btn bp bl-admin-btn" style="padding:9px 18px" id="imp-bl-btn" onclick="importBL()">⬆ Importer budget</button>\n          <button class="btn bs" style="padding:9px 14px" onclick="dlTemplate(\'budget-lines\')">⬇ Template CSV</button>\n        </div>\n        <div id="imp-bl-result" style="margin-top:10px"></div>\n      </div>\n    </div>\n  </div>\n\n  <!-- EXPORTS -->\n  <div class="card">\n    <div class="ch"><h2>⬇ Exports</h2></div>\n    <div class="cb" style="display:flex;gap:8px;flex-wrap:wrap">\n      <button class="btn bs" onclick="dlExport(\'transactions\')">⬇ Transactions CSV</button>\n      <button class="btn bs" onclick="dlExport(\'report\')">⬇ Rapport mensuel</button>\n    </div>\n  </div>\n</div>\n\n<!-- ════════ PLANNING PTA ════════ -->\n<div id="tab-planning" class="tab-content">\n  <div class="card">\n    <div class="ch">\n      <h2>📅 Planning PTA / Budget prévisionnel</h2>\n      <button class="btn bp viewer-hide" onclick="openModal(\'m-new-pta\')">+ Nouvelle soumission</button>\n    </div>\n    <div class="cb">\n      <table>\n        <thead><tr><th>Année</th><th>Direction</th><th>Imputation</th><th>Libellé</th><th>Montant AE</th><th>Montant CP</th><th>Statut</th><th>Actions</th></tr></thead>\n        <tbody id="pta-tbody"></tbody>\n      </table>\n      <div id="pta-empty" style="text-align:center;padding:20px;color:#5a8aaa;display:none">Aucune soumission PTA trouvée.</div>\n    </div>\n  </div>\n</div>\n\n<!-- ════════ USERS ════════ -->\n<div id="tab-users" class="tab-content admin-only">\n  <div class="card">\n    <div class="ch">\n      <h2>👥 Gestion des utilisateurs</h2>\n      <button class="btn bp" onclick="openModal(\'m-new-user\')">+ Nouvel utilisateur</button>\n    </div>\n    <div class="cb">\n      <table>\n        <thead><tr><th>Identifiant</th><th>Nom complet</th><th>Rôle</th><th>Directions</th><th>Statut</th><th>Actions</th></tr></thead>\n        <tbody id="usr-tbody"></tbody>\n      </table>\n    </div>\n  </div>\n</div>\n\n</div><!-- /wrap -->\n\n<!-- ════ MODALS ════ -->\n\n<!-- New Transaction -->\n<div class="mbg" id="m-new-tx"><div class="modal">\n  <div class="mh"><h3>Nouvelle transaction</h3><button class="btn bs" onclick="closeModal(\'m-new-tx\')">✕</button></div>\n  <div class="mb">\n    <div class="fr fc2">\n      <div class="fld"><label>Direction *</label><select id="tx-dir"><option value="">— Choisir —</option></select></div>\n      <div class="fld"><label>Imputation comptable *</label><input type="text" id="tx-imp" placeholder="604100"></div>\n    </div>\n    <div class="fld"><label>Intitulé *</label><input type="text" id="tx-int" placeholder="Libellé de la transaction"></div>\n    <div class="fr fc2">\n      <div class="fld"><label>Montant (FCFA) *</label><input type="number" id="tx-mnt" min="0" placeholder="0"></div>\n      <div class="fld"><label>Date *</label><input type="date" id="tx-dat"></div>\n    </div>\n    <div class="fr fc2">\n      <div class="fld"><label>Nature</label>\n        <select id="tx-nat"><option value="DEPENSE COURANTE">Dépense courante</option><option value="DEPENSE DE CAPITAL">Dépense de capital</option></select></div>\n      <div class="fld"><label>Réf. / Code</label><input type="text" id="tx-ref" placeholder="TX-2025-001"></div>\n    </div>\n  </div>\n  <div class="mf">\n    <button class="btn bs" onclick="closeModal(\'m-new-tx\')">Annuler</button>\n    <button class="btn bp" onclick="saveTx()">💾 Enregistrer</button>\n  </div>\n</div></div>\n\n<!-- New Budget Line -->\n<div class="mbg" id="m-new-bl"><div class="modal">\n  <div class="mh"><h3>Nouvelle ligne budgétaire</h3><button class="btn bs" onclick="closeModal(\'m-new-bl\')">✕</button></div>\n  <div class="mb">\n    <div class="fr fc3">\n      <div class="fld"><label>Année *</label><input type="number" id="bl-yr" min="2020" max="2035"></div>\n      <div class="fld"><label>Direction *</label><select id="bl-dir"><option value="">— Choisir —</option></select></div>\n      <div class="fld"><label>Imputation *</label><input type="text" id="bl-imp" placeholder="604100"></div>\n    </div>\n    <div class="fld"><label>Libellé</label><input type="text" id="bl-lib"></div>\n    <div class="fr fc2">\n      <div class="fld"><label>Nature</label>\n        <select id="bl-nat"><option value="DEPENSE COURANTE">Dépense courante</option><option value="DEPENSE DE CAPITAL">Dépense de capital</option></select></div>\n      <div class="fld"><label>Budget CP (FCFA) *</label><input type="number" id="bl-bcp" min="0" placeholder="0"></div>\n    </div>\n  </div>\n  <div class="mf">\n    <button class="btn bs" onclick="closeModal(\'m-new-bl\')">Annuler</button>\n    <button class="btn bp" onclick="saveBL()">💾 Enregistrer</button>\n  </div>\n</div></div>\n\n<!-- New PTA -->\n<div class="mbg" id="m-new-pta"><div class="modal">\n  <div class="mh"><h3>Nouvelle soumission PTA</h3><button class="btn bs" onclick="closeModal(\'m-new-pta\')">✕</button></div>\n  <div class="mb">\n    <div class="fr fc3">\n      <div class="fld"><label>Année *</label><input type="number" id="pta-yr" min="2020" max="2035"></div>\n      <div class="fld"><label>Direction *</label><select id="pta-dir"><option value="">— Choisir —</option></select></div>\n      <div class="fld"><label>Imputation *</label><input type="text" id="pta-imp" placeholder="604100"></div>\n    </div>\n    <div class="fld"><label>Libellé</label><input type="text" id="pta-lib"></div>\n    <div class="fr fc2">\n      <div class="fld"><label>Montant AE (FCFA)</label><input type="number" id="pta-ae" min="0" placeholder="0"></div>\n      <div class="fld"><label>Montant CP (FCFA)</label><input type="number" id="pta-cp" min="0" placeholder="0"></div>\n    </div>\n  </div>\n  <div class="mf">\n    <button class="btn bs" onclick="closeModal(\'m-new-pta\')">Annuler</button>\n    <button class="btn bp" onclick="savePTA()">💾 Enregistrer</button>\n  </div>\n</div></div>\n\n<!-- New User -->\n<div class="mbg" id="m-new-user"><div class="modal">\n  <div class="mh"><h3 id="usr-modal-title">Nouvel utilisateur</h3><button class="btn bs" onclick="closeModal(\'m-new-user\')">✕</button></div>\n  <div class="mb">\n    <div class="fr fc2">\n      <div class="fld"><label>Identifiant *</label><input type="text" id="usr-uname"></div>\n      <div class="fld"><label>Nom complet *</label><input type="text" id="usr-fname"></div>\n    </div>\n    <div class="fr fc2">\n      <div class="fld"><label>Mot de passe</label><input type="password" id="usr-pass" placeholder="Laisser vide = inchangé"></div>\n      <div class="fld"><label>Email</label><input type="email" id="usr-email"></div>\n    </div>\n    <div class="fr fc2">\n      <div class="fld"><label>Rôle *</label>\n        <select id="usr-role">\n          <option value="viewer">Lecteur</option><option value="agent">Agent</option>\n          <option value="agent_plus">Agent+</option><option value="dcf_sub">DCF Adjoint</option>\n          <option value="dcf_dir">DCF Directeur</option><option value="admin">Administrateur</option>\n        </select>\n      </div>\n      <div class="fld"><label>Actif</label>\n        <select id="usr-active"><option value="1">Oui</option><option value="0">Non</option></select>\n      </div>\n    </div>\n    <div class="fld"><label>Directions (séparées par virgule, vide = toutes)</label><input type="text" id="usr-dirs" placeholder="DCF,DRH,DSPI"></div>\n  </div>\n  <div class="mf">\n    <button class="btn bs" onclick="closeModal(\'m-new-user\')">Annuler</button>\n    <button class="btn bp" onclick="saveUser()">💾 Enregistrer</button>\n  </div>\n</div></div>\n\n<script>\n// ═══════════════════════════════════════════════════════════\n// STATE\n// ═══════════════════════════════════════════════════════════\nconst S={user:null,year:new Date().getFullYear(),dir:\'\',editTxId:null,editBlId:null,editUserId:null};\nconst DIRS=[\'DCF\',\'DRH\',\'DSPI\',\'DGA\',\'DTA\',\'DTR\',\'DAF\',\'DJC\',\'DCMO\',\'DGO\',\'DRHN\',\'DRI\'];\n\n// ═══════════════════════════════════════════════════════════\n// AUTH\n// ═══════════════════════════════════════════════════════════\nconst _tok=()=>sessionStorage.getItem(\'camtel_token\')||\'\';\n\nasync function api(path,opts){\n  try{\n    const tok=_tok();\n    const headers={\n      ...(tok?{\'Authorization\':\'Bearer \'+tok}:{}),\n      ...(opts?.headers||{})\n    };\n    const r=await fetch(path,{...(opts||{}),headers,credentials:\'include\'});\n    if(r.status===401){sessionStorage.clear();window.location=\'/login\';return null;}\n    if(!r.ok){\n      const t=await r.text().catch(()=>\'\');\n      console.error(\'API\',r.status,path,t.slice(0,200));\n      return null;\n    }\n    return r;\n  }catch(e){console.error(\'NET\',path,e.message);return null;}\n}\n\nasync function logout(){\n  sessionStorage.clear();\n  await fetch(\'/api/logout\',{method:\'POST\',credentials:\'include\'}).catch(()=>{});\n  window.location=\'/login\';\n}\n\n// ═══════════════════════════════════════════════════════════\n// INIT\n// ═══════════════════════════════════════════════════════════\nasync function init(){\n  // Try token auth first, then cookie\n  const r=await api(\'/api/me\');\n  if(!r){window.location=\'/login\';return;}\n  S.user=await r.json();\n  S.year=S.user.default_year||new Date().getFullYear();\n\n  // Setup year selector\n  const ysel=document.getElementById(\'g-year\');\n  const years=S.user.available_years||[S.year];\n  ysel.innerHTML=years.map(y=>`<option value="${y}" ${y===S.year?\'selected\':\'\'}>${y}</option>`).join(\'\');\n\n  // Setup direction selectors\n  const dirs=S.user.direction_list||DIRS;\n  const dirSel=document.getElementById(\'g-dir\');\n  dirSel.innerHTML=\'<option value="">Toutes</option>\'+dirs.map(d=>`<option value="${d}">${d}</option>`).join(\'\');\n\n  // Fill modal direction dropdowns\n  [\'tx-dir\',\'bl-dir\',\'pta-dir\'].forEach(id=>{\n    const el=document.getElementById(id);\n    if(el) el.innerHTML=\'<option value="">— Choisir —</option>\'+dirs.map(d=>`<option value="${d}">${d}</option>`).join(\'\');\n  });\n\n  // Set today\'s date in TX form\n  document.getElementById(\'tx-dat\').value=new Date().toISOString().split(\'T\')[0];\n  document.getElementById(\'bl-yr\').value=S.year;\n  document.getElementById(\'pta-yr\').value=S.year;\n\n  // Header info\n  document.getElementById(\'h-name\').textContent=S.user.name||S.user.u||\'—\';\n  document.getElementById(\'h-role\').textContent=S.user.role||\'—\';\n\n  applyRole();\n  await reloadAll();\n}\n\n// ═══════════════════════════════════════════════════════════\n// ROLE VISIBILITY\n// ═══════════════════════════════════════════════════════════\nfunction applyRole(){\n  const role=S.user?.role||\'viewer\';\n  const isAdmin=[\'admin\'].includes(role);\n  const canCreate=[\'admin\',\'dcf_dir\',\'dcf_sub\'].includes(role);\n  const canImport=[\'admin\',\'dcf_dir\',\'dcf_sub\',\'agent_plus\'].includes(role);\n  const isViewer=role===\'viewer\';\n\n  document.querySelectorAll(\'.admin-only\').forEach(e=>e.style.display=isAdmin?\'\':\'none\');\n  document.querySelectorAll(\'.viewer-hide\').forEach(e=>e.style.display=isViewer?\'none\':\'\');\n  document.querySelectorAll(\'.bl-admin-btn\').forEach(e=>e.style.display=canCreate?\'\':\'none\');\n\n  const navImport=document.getElementById(\'nav-import\');\n  if(navImport) navImport.style.display=canImport?\'\':\'none\';\n}\n\n// ═══════════════════════════════════════════════════════════\n// TABS\n// ═══════════════════════════════════════════════════════════\nfunction showTab(name){\n  document.querySelectorAll(\'.tab-content\').forEach(e=>e.classList.remove(\'active\'));\n  document.querySelectorAll(\'nav button\').forEach(e=>e.classList.remove(\'active\'));\n  const tab=document.getElementById(\'tab-\'+name);\n  const btn=document.getElementById(\'nav-\'+name);\n  if(tab) tab.classList.add(\'active\');\n  if(btn) btn.classList.add(\'active\');\n}\n\nfunction openModal(id){document.getElementById(id).classList.add(\'open\');}\nfunction closeModal(id){document.getElementById(id).classList.remove(\'open\');}\n\n// ═══════════════════════════════════════════════════════════\n// FILTER\n// ═══════════════════════════════════════════════════════════\nfunction onYearChange(){S.year=parseInt(document.getElementById(\'g-year\').value);reloadAll();}\nfunction onDirChange(){S.dir=document.getElementById(\'g-dir\').value;reloadAll();}\n\n// ═══════════════════════════════════════════════════════════\n// RELOAD ALL\n// ═══════════════════════════════════════════════════════════\nasync function reloadAll(){\n  await Promise.all([loadDashboard(),loadTransactions(),loadBudgetLines(),loadPTA(),loadUsers()]);\n}\n\n// ═══════════════════════════════════════════════════════════\n// FORMAT HELPERS\n// ═══════════════════════════════════════════════════════════\nfunction fmt(n){\n  if(n==null||n===undefined||n===\'—\') return \'—\';\n  const v=parseFloat(n);\n  if(isNaN(v)) return \'—\';\n  if(Math.abs(v)>=1e9) return (v/1e9).toFixed(2)+\' Mrd\';\n  if(Math.abs(v)>=1e6) return (v/1e6).toFixed(2)+\' M\';\n  if(Math.abs(v)>=1e3) return (v/1e3).toFixed(0)+\' K\';\n  return v.toLocaleString(\'fr-FR\');\n}\nfunction fmtF(n){return fmt(n)+\' FCFA\';}\nfunction pct(a,b){return b>0?Math.min(100,(a/b*100)).toFixed(1)+\'%\':\'0%\';}\n\n// ═══════════════════════════════════════════════════════════\n// DASHBOARD\n// ═══════════════════════════════════════════════════════════\nasync function loadDashboard(){\n  const qs=`year=${S.year}${S.dir?\'&direction=\'+S.dir:\'\'}`;\n  const r=await api(\'/api/dashboard?\'+qs);\n  if(!r) return;\n  const d=await r.json();\n\n  document.getElementById(\'k-bud\').textContent=fmt(d.total_budget);\n  document.getElementById(\'k-eng\').textContent=fmt(d.total_engaged);\n  document.getElementById(\'k-pend\').textContent=fmt(d.total_pending);\n  document.getElementById(\'k-dispo\').textContent=fmt(d.total_available);\n\n  // Dirs\n  const dirsEl=document.getElementById(\'db-dirs\');\n  if(d.by_dir && Object.keys(d.by_dir).length){\n    dirsEl.innerHTML=Object.entries(d.by_dir).map(([dir,info])=>`\n      <div style="margin-bottom:10px">\n        <div style="display:flex;justify-content:space-between;margin-bottom:3px">\n          <strong>${dir}</strong>\n          <span style="color:#7aaccc;font-size:11px">${fmt(info.engaged)} / ${fmt(info.budget)}</span>\n        </div>\n        <div class="prg"><div class="prf" style="width:${pct(info.engaged,info.budget)}"></div></div>\n        <div style="font-size:10px;color:#5a8aaa;margin-top:2px">${pct(info.engaged,info.budget)} exécuté</div>\n      </div>`).join(\'\');\n  } else {\n    dirsEl.innerHTML=\'<div style="color:#5a8aaa;text-align:center;padding:10px">Aucune donnée</div>\';\n  }\n\n  // Overdrawn\n  const odEl=document.getElementById(\'db-overdraw\');\n  if(d.overdrawn && d.overdrawn.length){\n    odEl.innerHTML=d.overdrawn.map(o=>`\n      <div class="alrt alrt-r" style="margin-bottom:6px">\n        <strong>${o.imputation}</strong> · ${o.direction}<br>\n        <span style="font-size:10px">Budget: ${fmtF(o.budget)} — Engagé: ${fmtF(o.engaged)}</span>\n      </div>`).join(\'\');\n  } else {\n    odEl.innerHTML=\'<div class="alrt alrt-g">✅ Aucun dépassement budgétaire</div>\';\n  }\n\n  // Recent\n  const rEl=document.getElementById(\'db-recent\');\n  if(d.recent && d.recent.length){\n    rEl.innerHTML=d.recent.map(t=>`<tr>\n      <td>${t.date_reception||\'—\'}</td><td>${t.direction}</td><td>${t.imputation}</td>\n      <td>${(t.intitule||\'\').substring(0,40)}</td><td>${fmtF(t.montant)}</td>\n      <td><span class="badge ${t.statut_budget===\'DEPASSEMENT\'?\'b-dep\':\'b-ok\'}">${t.statut_budget}</span></td>\n    </tr>`).join(\'\');\n  } else {\n    rEl.innerHTML=\'<tr><td colspan="6" style="text-align:center;color:#5a8aaa;padding:12px">Aucune transaction récente</td></tr>\';\n  }\n}\n\n// ═══════════════════════════════════════════════════════════\n// TRANSACTIONS\n// ═══════════════════════════════════════════════════════════\nasync function loadTransactions(){\n  const qs=`year=${S.year}${S.dir?\'&direction=\'+S.dir:\'\'}`;\n  const r=await api(\'/api/transactions?\'+qs);\n  if(!r) return;\n  const txs=await r.json();\n  const tbody=document.getElementById(\'tx-tbody\');\n  const empty=document.getElementById(\'tx-empty\');\n  if(!txs.length){tbody.innerHTML=\'\';empty.style.display=\'block\';return;}\n  empty.style.display=\'none\';\n  tbody.innerHTML=txs.map(t=>`<tr>\n    <td>${t.date_reception||\'—\'}</td>\n    <td>${t.direction}</td>\n    <td>${t.imputation}</td>\n    <td title="${t.intitule||\'\'}">${(t.intitule||\'\').substring(0,35)}</td>\n    <td style="white-space:nowrap">${fmtF(t.montant)}</td>\n    <td><span class="badge ${t.statut_budget===\'DEPASSEMENT\'?\'b-dep\':\'b-ok\'}">${t.statut_budget||\'OK\'}</span></td>\n    <td><span class="badge ${t.status===\'validated\'?\'b-ok\':\'b-pend\'}">${t.status===\'validated\'?\'Validé\':\'En attente\'}</span></td>\n    <td style="white-space:nowrap">\n      <button class="btn bs bxs" onclick="editTx(${t.id})">✏️</button>\n      <button class="btn bd bxs" onclick="delTx(${t.id})">🗑</button>\n    </td>\n  </tr>`).join(\'\');\n}\nconst bxs=\'padding:2px 6px;font-size:11px;border-radius:4px\';\n\nasync function searchTx(){\n  const q=document.getElementById(\'tx-search\').value.trim();\n  if(!q){loadTransactions();return;}\n  const r=await api(\'/api/transactions/search?q=\'+encodeURIComponent(q)+\'&year=\'+S.year);\n  if(!r) return;\n  const txs=await r.json();\n  const tbody=document.getElementById(\'tx-tbody\');\n  tbody.innerHTML=txs.map(t=>`<tr>\n    <td>${t.date_reception||\'—\'}</td><td>${t.direction}</td><td>${t.imputation}</td>\n    <td>${(t.intitule||\'\').substring(0,35)}</td><td>${fmtF(t.montant)}</td>\n    <td><span class="badge ${t.statut_budget===\'DEPASSEMENT\'?\'b-dep\':\'b-ok\'}">${t.statut_budget||\'OK\'}</span></td>\n    <td><span class="badge ${t.status===\'validated\'?\'b-ok\':\'b-pend\'}">${t.status===\'validated\'?\'Validé\':\'En attente\'}</span></td>\n    <td><button class="btn bs" style="${bxs}" onclick="editTx(${t.id})">✏️</button>\n        <button class="btn bd" style="${bxs}" onclick="delTx(${t.id})">🗑</button></td>\n  </tr>`).join(\'\');\n}\n\nasync function saveTx(){\n  const dir=document.getElementById(\'tx-dir\').value;\n  const imp=document.getElementById(\'tx-imp\').value.trim();\n  const intitule=document.getElementById(\'tx-int\').value.trim();\n  const mnt=parseFloat(document.getElementById(\'tx-mnt\').value)||0;\n  const dat=document.getElementById(\'tx-dat\').value;\n  if(!dir||!imp||!intitule||!mnt){alert(\'Veuillez remplir tous les champs obligatoires.\');return;}\n  const body={direction:dir,imputation:imp,intitule,montant:mnt,date_reception:dat,\n    nature:document.getElementById(\'tx-nat\').value,\n    code_ref:document.getElementById(\'tx-ref\').value.trim(),\n    year:S.year,status:\'validated\'};\n  const method=S.editTxId?\'PUT\':\'POST\';\n  const path=S.editTxId?`/api/transactions/${S.editTxId}`:\'/api/transactions\';\n  const r=await api(path,{method,headers:{\'Content-Type\':\'application/json\'},body:JSON.stringify(body)});\n  if(r){closeModal(\'m-new-tx\');S.editTxId=null;await reloadAll();}\n  else alert(\'Erreur lors de la sauvegarde.\');\n}\n\nasync function editTx(id){\n  const r=await api(\'/api/transactions/\'+id);\n  if(!r) return;\n  const t=await r.json();\n  S.editTxId=id;\n  document.getElementById(\'tx-dir\').value=t.direction||\'\';\n  document.getElementById(\'tx-imp\').value=t.imputation||\'\';\n  document.getElementById(\'tx-int\').value=t.intitule||\'\';\n  document.getElementById(\'tx-mnt\').value=t.montant||0;\n  document.getElementById(\'tx-dat\').value=t.date_reception||\'\';\n  document.getElementById(\'tx-nat\').value=t.nature||\'DEPENSE COURANTE\';\n  document.getElementById(\'tx-ref\').value=t.code_ref||\'\';\n  openModal(\'m-new-tx\');\n}\n\nasync function delTx(id){\n  if(!confirm(\'Supprimer cette transaction ?\')) return;\n  const r=await api(\'/api/transactions/\'+id,{method:\'DELETE\'});\n  if(r) await reloadAll();\n  else alert(\'Erreur lors de la suppression.\');\n}\n\n// ═══════════════════════════════════════════════════════════\n// BUDGET LINES\n// ═══════════════════════════════════════════════════════════\nasync function loadBudgetLines(){\n  const qs=`year=${S.year}${S.dir?\'&direction=\'+S.dir:\'\'}`;\n  const r=await api(\'/api/budget-lines?\'+qs);\n  if(!r) return;\n  const bls=await r.json();\n  const tbody=document.getElementById(\'bl-tbody\');\n  const empty=document.getElementById(\'bl-empty\');\n  if(!bls.length){tbody.innerHTML=\'\';empty.style.display=\'block\';return;}\n  empty.style.display=\'none\';\n  tbody.innerHTML=bls.map(b=>`<tr>\n    <td>${b.year}</td><td>${b.direction}</td><td>${b.imputation}</td>\n    <td title="${b.libelle||\'\'}">${(b.libelle||\'\').substring(0,30)}</td>\n    <td style="font-size:10px">${b.nature===\'DEPENSE DE CAPITAL\'?\'Capital\':\'Courante\'}</td>\n    <td style="white-space:nowrap">${fmtF(b.budget_cp)}</td>\n    <td style="white-space:nowrap">${fmtF(b.engaged||0)}</td>\n    <td style="white-space:nowrap;color:${(b.available||0)<0?\'#ff4444\':\'#00e676\'}">${fmtF(b.available||b.budget_cp)}</td>\n    <td style="white-space:nowrap">\n      <button class="btn bs" style="${bxs}" onclick="editBL(${b.id})">✏️</button>\n      <button class="btn bd admin-only" style="${bxs}" onclick="delBL(${b.id})">🗑</button>\n    </td>\n  </tr>`).join(\'\');\n}\n\nasync function saveBL(){\n  const yr=parseInt(document.getElementById(\'bl-yr\').value);\n  const dir=document.getElementById(\'bl-dir\').value;\n  const imp=document.getElementById(\'bl-imp\').value.trim();\n  const lib=document.getElementById(\'bl-lib\').value.trim();\n  const bcp=parseFloat(document.getElementById(\'bl-bcp\').value)||0;\n  if(!yr||!dir||!imp){alert(\'Année, direction et imputation sont obligatoires.\');return;}\n  const body={year:yr,direction:dir,imputation:imp,libelle:lib,\n    nature:document.getElementById(\'bl-nat\').value,budget_cp:bcp};\n  const method=S.editBlId?\'PUT\':\'POST\';\n  const path=S.editBlId?`/api/budget-lines/${S.editBlId}`:\'/api/budget-lines\';\n  const r=await api(path,{method,headers:{\'Content-Type\':\'application/json\'},body:JSON.stringify(body)});\n  if(r){closeModal(\'m-new-bl\');S.editBlId=null;await reloadAll();}\n  else alert(\'Erreur lors de la sauvegarde.\');\n}\n\nasync function editBL(id){\n  const r=await api(\'/api/budget-lines/\'+id);\n  if(!r){\n    // Try from loaded list\n    const bls=document.querySelectorAll(\'#bl-tbody tr\');\n    return;\n  }\n  const b=await r.json();\n  S.editBlId=id;\n  document.getElementById(\'bl-yr\').value=b.year;\n  document.getElementById(\'bl-dir\').value=b.direction;\n  document.getElementById(\'bl-imp\').value=b.imputation;\n  document.getElementById(\'bl-lib\').value=b.libelle||\'\';\n  document.getElementById(\'bl-nat\').value=b.nature||\'DEPENSE COURANTE\';\n  document.getElementById(\'bl-bcp\').value=b.budget_cp||0;\n  openModal(\'m-new-bl\');\n}\n\nasync function delBL(id){\n  if(!confirm(\'Supprimer cette ligne budgétaire ?\')) return;\n  const r=await api(\'/api/budget-lines/\'+id,{method:\'DELETE\'});\n  if(r) await reloadAll();\n  else alert(\'Erreur lors de la suppression.\');\n}\n\n// ═══════════════════════════════════════════════════════════\n// PLANNING PTA\n// ═══════════════════════════════════════════════════════════\nasync function loadPTA(){\n  const qs=`year=${S.year}${S.dir?\'&direction=\'+S.dir:\'\'}`;\n  const r=await api(\'/api/planning/submissions?\'+qs);\n  if(!r) return;\n  const pts=await r.json();\n  const tbody=document.getElementById(\'pta-tbody\');\n  const empty=document.getElementById(\'pta-empty\');\n  if(!pts.length){tbody.innerHTML=\'\';empty.style.display=\'block\';return;}\n  empty.style.display=\'none\';\n  tbody.innerHTML=pts.map(p=>`<tr>\n    <td>${p.year}</td><td>${p.direction}</td><td>${p.imputation||\'—\'}</td>\n    <td>${(p.libelle||\'\').substring(0,30)}</td>\n    <td>${fmtF(p.montant_ae||0)}</td><td>${fmtF(p.montant_cp||0)}</td>\n    <td><span class="badge ${p.status===\'approved\'?\'b-ok\':p.status===\'rejected\'?\'b-dep\':\'b-pend\'}">${p.status||\'draft\'}</span></td>\n    <td>\n      <button class="btn bd" style="${bxs}" onclick="delPTA(${p.id})">🗑</button>\n    </td>\n  </tr>`).join(\'\');\n}\n\nasync function savePTA(){\n  const body={\n    year:parseInt(document.getElementById(\'pta-yr\').value),\n    direction:document.getElementById(\'pta-dir\').value,\n    imputation:document.getElementById(\'pta-imp\').value.trim(),\n    libelle:document.getElementById(\'pta-lib\').value.trim(),\n    montant_ae:parseFloat(document.getElementById(\'pta-ae\').value)||0,\n    montant_cp:parseFloat(document.getElementById(\'pta-cp\').value)||0,\n    status:\'draft\'\n  };\n  if(!body.year||!body.direction){alert(\'Année et direction sont obligatoires.\');return;}\n  const r=await api(\'/api/planning/submissions\',{method:\'POST\',headers:{\'Content-Type\':\'application/json\'},body:JSON.stringify(body)});\n  if(r){closeModal(\'m-new-pta\');await loadPTA();}\n  else alert(\'Erreur lors de la sauvegarde.\');\n}\n\nasync function delPTA(id){\n  if(!confirm(\'Supprimer cette soumission PTA ?\')) return;\n  const r=await api(\'/api/planning/submissions/\'+id,{method:\'DELETE\'});\n  if(r) await loadPTA();\n}\n\n// ═══════════════════════════════════════════════════════════\n// USERS\n// ═══════════════════════════════════════════════════════════\nasync function loadUsers(){\n  if(!S.user||S.user.role!==\'admin\') return;\n  const r=await api(\'/api/users\');\n  if(!r) return;\n  const users=await r.json();\n  document.getElementById(\'usr-tbody\').innerHTML=users.map(u=>`<tr>\n    <td><strong>${u.username}</strong></td>\n    <td>${u.full_name||\'—\'}</td>\n    <td><span class="badge b-ok">${u.role}</span></td>\n    <td style="font-size:10px">${(()=>{try{const d=JSON.parse(u.directions||\'[]\');return d.length?d.join(\', \'):\'Toutes\';}catch(e){return u.directions||\'Toutes\';}})()}</td>\n    <td><span class="badge ${u.is_active?\'b-ok\':\'b-dep\'}">${u.is_active?\'Actif\':\'Inactif\'}</span></td>\n    <td>\n      <button class="btn bs" style="${bxs}" onclick="editUser(${u.id})">✏️</button>\n      <button class="btn bd" style="${bxs}" onclick="delUser(${u.id})">🗑</button>\n    </td>\n  </tr>`).join(\'\');\n}\n\nasync function saveUser(){\n  const uname=document.getElementById(\'usr-uname\').value.trim();\n  const fname=document.getElementById(\'usr-fname\').value.trim();\n  const pass=document.getElementById(\'usr-pass\').value;\n  const email=document.getElementById(\'usr-email\').value.trim();\n  const role=document.getElementById(\'usr-role\').value;\n  const active=parseInt(document.getElementById(\'usr-active\').value);\n  const dirsRaw=document.getElementById(\'usr-dirs\').value.trim();\n  const dirs=dirsRaw?JSON.stringify(dirsRaw.split(\',\').map(d=>d.trim()).filter(Boolean)):\'[]\';\n  if(!uname||!fname){alert(\'Identifiant et nom complet sont obligatoires.\');return;}\n  const body={username:uname,full_name:fname,email,role,is_active:active,directions:dirs};\n  if(pass) body.password=pass;\n  const method=S.editUserId?\'PUT\':\'POST\';\n  const path=S.editUserId?`/api/users/${S.editUserId}`:\'/api/users\';\n  const r=await api(path,{method,headers:{\'Content-Type\':\'application/json\'},body:JSON.stringify(body)});\n  if(r){closeModal(\'m-new-user\');S.editUserId=null;await loadUsers();}\n  else alert(\'Erreur lors de la sauvegarde.\');\n}\n\nasync function editUser(id){\n  S.editUserId=id;\n  const r=await api(\'/api/users/\'+id);\n  if(!r) return;\n  const u=await r.json();\n  document.getElementById(\'usr-modal-title\').textContent=\'Modifier utilisateur\';\n  document.getElementById(\'usr-uname\').value=u.username;\n  document.getElementById(\'usr-fname\').value=u.full_name||\'\';\n  document.getElementById(\'usr-pass\').value=\'\';\n  document.getElementById(\'usr-email\').value=u.email||\'\';\n  document.getElementById(\'usr-role\').value=u.role||\'viewer\';\n  document.getElementById(\'usr-active\').value=u.is_active?\'1\':\'0\';\n  try{const d=JSON.parse(u.directions||\'[]\');document.getElementById(\'usr-dirs\').value=d.join(\',\');}\n  catch(e){document.getElementById(\'usr-dirs\').value=\'\';}\n  openModal(\'m-new-user\');\n}\n\nasync function delUser(id){\n  if(!confirm(\'Supprimer cet utilisateur ?\')) return;\n  const r=await api(\'/api/users/\'+id,{method:\'DELETE\'});\n  if(r) await loadUsers();\n}\n\n// ═══════════════════════════════════════════════════════════\n// IMPORT — FILE PICKER\n// ═══════════════════════════════════════════════════════════\nfunction onFileSel(input, nameId, areaId){\n  const f=input.files[0];\n  const nameEl=document.getElementById(nameId);\n  const area=document.getElementById(areaId);\n  if(!f){nameEl.textContent=\'\';return;}\n  nameEl.textContent=\'✓ \'+f.name+\' (\'+Math.round(f.size/1024)+\' KB)\';\n  if(area){\n    area.style.borderColor=\'rgba(0,230,118,.7)\';\n    area.style.background=\'rgba(0,60,20,.25)\';\n  }\n}\n\nasync function importTx(){\n  const f=document.getElementById(\'imp-tx-file\').files[0];\n  const yr=parseInt(document.getElementById(\'imp-tx-year\').value)||S.year;\n  const resEl=document.getElementById(\'imp-tx-result\');\n  if(!f){\n    resEl.innerHTML=\'<div class="alrt alrt-y">⚠️ Veuillez d\\\'abord sélectionner un fichier.</div>\';\n    return;\n  }\n  resEl.innerHTML=\'<div class="alrt alrt-b">🔄 Import en cours — <strong>\'+f.name+\'</strong> (\'+Math.round(f.size/1024)+\' KB)...</div>\';\n  document.getElementById(\'imp-tx-btn\').disabled=true;\n  try{\n    const fd=new FormData();\n    fd.append(\'file\',f);\n    fd.append(\'year\',String(yr));\n    const tok=_tok();\n    const headers=tok?{\'Authorization\':\'Bearer \'+tok}:{};\n    const r=await fetch(\'/api/import/transactions\',{method:\'POST\',headers,credentials:\'include\',body:fd});\n    if(!r.ok){\n      const t=await r.text().catch(()=>\'\');\n      let msg=\'Erreur serveur (\'+r.status+\').\';\n      try{const j=JSON.parse(t);msg=j.detail||j.error||msg;}catch(e){}\n      resEl.innerHTML=\'<div class="alrt alrt-r">❌ \'+msg+\'</div>\';\n    } else {\n      const d=await r.json();\n      resEl.innerHTML=\'<div class="alrt alrt-g">✅ Import terminé — <strong>\'+d.created+\' transactions créées</strong>\'+(d.errors&&d.errors.length?\' · \'+d.errors.length+\' erreurs\':\'\')+\' · Année \'+yr+\'</div>\';\n      document.getElementById(\'imp-tx-file\').value=\'\';\n      document.getElementById(\'imp-tx-name\').textContent=\'\';\n      document.getElementById(\'imp-tx-area\').style.borderColor=\'\';\n      document.getElementById(\'imp-tx-area\').style.background=\'\';\n      await reloadAll();\n    }\n  }catch(e){\n    resEl.innerHTML=\'<div class="alrt alrt-r">❌ Erreur réseau: \'+e.message+\'</div>\';\n  }\n  document.getElementById(\'imp-tx-btn\').disabled=false;\n}\n\nasync function importBL(){\n  const f=document.getElementById(\'imp-bl-file\').files[0];\n  const yr=parseInt(document.getElementById(\'imp-bl-year\').value)||S.year;\n  const resEl=document.getElementById(\'imp-bl-result\');\n  if(!f){\n    resEl.innerHTML=\'<div class="alrt alrt-y">⚠️ Veuillez d\\\'abord sélectionner un fichier.</div>\';\n    return;\n  }\n  resEl.innerHTML=\'<div class="alrt alrt-b">🔄 Import en cours — <strong>\'+f.name+\'</strong>...</div>\';\n  document.getElementById(\'imp-bl-btn\').disabled=true;\n  try{\n    const fd=new FormData();\n    fd.append(\'file\',f);\n    fd.append(\'year\',String(yr));\n    const tok=_tok();\n    const headers=tok?{\'Authorization\':\'Bearer \'+tok}:{};\n    const r=await fetch(\'/api/import/budget-lines\',{method:\'POST\',headers,credentials:\'include\',body:fd});\n    if(!r.ok){\n      const t=await r.text().catch(()=>\'\');\n      let msg=\'Erreur serveur (\'+r.status+\').\';\n      try{const j=JSON.parse(t);msg=j.detail||j.error||msg;}catch(e){}\n      resEl.innerHTML=\'<div class="alrt alrt-r">❌ \'+msg+\'</div>\';\n    } else {\n      const d=await r.json();\n      resEl.innerHTML=\'<div class="alrt alrt-g">✅ Import terminé — <strong>\'+d.created+\' créées, \'+d.updated+\' mises à jour</strong>\'+(d.errors&&d.errors.length?\' · \'+d.errors.length+\' erreurs\':\'\')+\' · Année \'+yr+\'</div>\';\n      document.getElementById(\'imp-bl-file\').value=\'\';\n      document.getElementById(\'imp-bl-name\').textContent=\'\';\n      document.getElementById(\'imp-bl-area\').style.borderColor=\'\';\n      document.getElementById(\'imp-bl-area\').style.background=\'\';\n      await reloadAll();\n    }\n  }catch(e){\n    resEl.innerHTML=\'<div class="alrt alrt-r">❌ Erreur réseau: \'+e.message+\'</div>\';\n  }\n  document.getElementById(\'imp-bl-btn\').disabled=false;\n}\n\nfunction dlTemplate(type){window.open(\'/api/export/template-\'+type,\'_blank\');}\nfunction dlExport(type){\n  if(type===\'report\') window.open(\'/api/report/monthly?year=\'+S.year,\'_blank\');\n  else window.open(\'/api/export/transactions?year=\'+S.year+(S.dir?\'&direction=\'+S.dir:\'\'),\'_blank\');\n}\n\n// ═══════════════════════════════════════════════════════════\n// BOOT\n// ═══════════════════════════════════════════════════════════\nwindow.addEventListener(\'DOMContentLoaded\', init);\n</script>\n</body>\n</html>\n'
