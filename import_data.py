"""
Import Engine — accepts .xlsx and .csv
- Detects file type automatically
- Validates columns
- Uses pandas for Excel, csv module for CSV
- Rolls back entire import if critical error
- Returns rows inserted + error list
"""
import io, csv
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, crud
from app.schemas import ImportResult
from app.utils.calculations import get_budget_status

router = APIRouter(prefix="/api/import", tags=["import"])

ROLE_IMPORT  = ("admin", "dcf_dir", "dcf_sub", "agent_plus")
ROLE_BUDGETS = ("admin", "dcf_dir", "dcf_sub")


# ── Helpers ───────────────────────────────────────────────────────
def _decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    raise HTTPException(400, "Cannot decode file — use UTF-8 or Latin-1")


def _clean_amount(s: str) -> float:
    """Parse FCFA amounts: '291,959,762' → 291959762   |   '99,50' → 99.50"""
    s = str(s or "0").strip()
    for ch in ("\xa0", "\u202f", "\u00a0", " ", "\t"):
        s = s.replace(ch, "")
    if s.count(",") > 1:
        s = s.replace(",", "")          # 291,959,762 → 291959762
    elif s.count(",") == 1:
        parts = s.split(",")
        if len(parts[1]) == 3:
            s = s.replace(",", "")      # 360,000 → 360000
        else:
            s = s.replace(",", ".")     # 99,50 → 99.50
    try:
        return float(s) if s and s not in ("-", "") else 0.0
    except ValueError:
        return 0.0


def _normalise_date(s: str) -> str:
    """DD/MM/YYYY → YYYY-MM-DD"""
    from datetime import date
    if not s:
        return date.today().isoformat()
    s = s.strip()
    if "/" in s:
        p = s.split("/")
        if len(p) == 3:
            if len(p[2]) == 4:
                return f"{p[2]}-{int(p[1]):02d}-{int(p[0]):02d}"
            return f"{p[0]}-{int(p[1]):02d}-{int(p[2]):02d}"
    return s


def _find_header_line(lines: list) -> int:
    """Skip title rows like 'SITUATION DES ENGAGEMENTS...', find real header."""
    for i, line in enumerate(lines):
        up = line.upper()
        if "DIRECTION" in up and ("DATE" in up or "MONTANT" in up or "IMPUTATION" in up):
            return i
    return 0


def _read_excel(raw: bytes) -> tuple:
    """Returns (headers: list, rows: list of lists)"""
    try:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        ws = wb.active
        all_rows = [list(r) for r in ws.iter_rows(values_only=True)]
        wb.close()
    except ImportError:
        try:
            import pandas as pd
            df = pd.read_excel(io.BytesIO(raw), header=None)
            all_rows = df.values.tolist()
        except ImportError:
            raise HTTPException(400, "Cannot read Excel — install openpyxl or pandas")

    # Find header row
    header_idx = 0
    for i, row in enumerate(all_rows):
        cells = [str(c or "").upper().strip() for c in row]
        if "DIRECTION" in cells:
            header_idx = i
            break

    headers = [str(c or "").strip().upper() for c in all_rows[header_idx]]
    data_rows = all_rows[header_idx + 1:]
    return headers, data_rows


def _gcol(row: list, headers: list, *keys) -> str:
    """Get cell value by matching header keyword."""
    for key in keys:
        for i, h in enumerate(headers):
            if key in h and i < len(row):
                v = row[i]
                if v is not None and str(v).strip():
                    return str(v).strip()
    return ""


# ── IMPORT TRANSACTIONS ──────────────────────────────────────────
@router.post("/transactions", response_model=ImportResult)
async def import_transactions(
    request: Request,
    file: UploadFile = File(...),
    year: int = Form(...),
    db: Session = Depends(get_db),
):
    from app.main import require_login
    u = require_login(request)
    if u.get("role") not in ROLE_IMPORT:
        raise HTTPException(403, "Accès non autorisé")

    raw      = await file.read()
    fname    = (file.filename or "").lower()
    created  = 0
    errors   = []

    try:
        # ── Excel ──────────────────────────────────────────────
        if fname.endswith((".xlsx", ".xls")):
            headers, data_rows = _read_excel(raw)
            for row_i, row in enumerate(data_rows, 2):
                try:
                    direction = _gcol(row, headers, "DIRECTION").upper()
                    if not direction or direction in ("DIRECTION", "TOTAL", "SOUS-TOTAL", ""):
                        continue
                    montant    = _clean_amount(_gcol(row, headers, "MONTANT", "AMOUNT"))
                    date_r     = _normalise_date(_gcol(row, headers, "DATE ENGAGEMENT", "DATE DE RECEPTION", "DATE"))
                    intitule   = _gcol(row, headers, "INTITULE DE LA COMMANDE", "LIBELLE", "INTITULE", "ORDER TITLE")
                    imputation = _gcol(row, headers, "IMPUTATION COMPTABLE", "IMPUTATION", "ACCOUNTING")
                    nature_raw = _gcol(row, headers, "NATURE DE LA DEPENSE", "NATURE")
                    nature     = "DEPENSE DE CAPITAL" if "CAPITAL" in nature_raw.upper() else "DEPENSE COURANTE"
                    code_ref   = _gcol(row, headers, "CODE /REF", "CODE_REF", "REF") or f"IMP-{direction}-{year}-{row_i:04d}"
                    sb         = get_budget_status(db, imputation, year, montant)
                    dept       = crud.get_or_create_department(db, direction)
                    fy         = crud.get_or_create_fiscal_year(db, year)
                    db.add(models.Transaction(
                        code_ref=code_ref, date_reception=date_r, direction=direction,
                        imputation=imputation, nature=nature, intitule=intitule,
                        montant=montant, year=year, status="validated", statut_budget=sb,
                        created_by=u.get("u", ""), created_by_name=u.get("name", "IMPORT"),
                        department_id=dept.id, fiscal_year_id=fy.id,
                    ))
                    created += 1
                except Exception as e:
                    errors.append(f"Row {row_i}: {e}")

        # ── CSV ────────────────────────────────────────────────
        else:
            txt    = _decode(raw).lstrip("\ufeff")
            lines  = txt.splitlines()
            hi     = _find_header_line(lines)
            reader = csv.DictReader(io.StringIO("\n".join(lines[hi:])))
            for row_i, row in enumerate(reader, hi + 2):
                try:
                    nr = {(k or "").strip().upper(): (v or "").strip()
                          for k, v in row.items() if k}
                    direction = nr.get("DIRECTION", "").upper()
                    if not direction or direction in ("DIRECTION", "TOTAL", "SOUS-TOTAL", "SITUATION"):
                        continue
                    montant    = _clean_amount(nr.get(" MONTANT  ") or nr.get("MONTANT") or nr.get("AMOUNT") or "0")
                    date_r     = _normalise_date(nr.get("DATE ENGAGEMENT") or nr.get("DATE DE RECEPTION") or nr.get("DATE") or "")
                    intitule   = (nr.get("INTITULE DE LA COMMANDE") or nr.get("LIBELLE") or
                                  nr.get("ORDER TITLE") or nr.get("INTITULE") or "")
                    imputation = (nr.get("IMPUTATION COMPTABLE") or nr.get("IMPUTATION") or
                                  nr.get("ACCOUNTING ENTRY") or "")
                    nature_raw = (nr.get("NATURE DE LA DEPENSE (DEPENSE COURANTE, DEPENSE DE CAPITAL)") or
                                  nr.get("NATURE DE LA DEPENSE") or nr.get("NATURE") or "")
                    nature     = "DEPENSE DE CAPITAL" if "CAPITAL" in nature_raw.upper() else "DEPENSE COURANTE"
                    code_ref   = (nr.get("CODE /REF NUMBER") or nr.get("CODE_REF") or
                                  f"IMP-{direction}-{year}-{row_i:04d}")
                    sb         = get_budget_status(db, imputation, year, montant)
                    dept       = crud.get_or_create_department(db, direction)
                    fy         = crud.get_or_create_fiscal_year(db, year)
                    db.add(models.Transaction(
                        code_ref=code_ref, date_reception=date_r, direction=direction,
                        imputation=imputation, nature=nature, intitule=intitule,
                        montant=montant, year=year, status="validated", statut_budget=sb,
                        created_by=u.get("u", ""), created_by_name=u.get("name", "IMPORT"),
                        department_id=dept.id, fiscal_year_id=fy.id,
                    ))
                    created += 1
                except Exception as e:
                    errors.append(f"Row {row_i}: {e}")

        db.commit()

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Import failed and rolled back: {e}")

    return ImportResult(created=created, errors=errors[:20])


# ── IMPORT BUDGET LINES ──────────────────────────────────────────
@router.post("/budget-lines", response_model=ImportResult)
async def import_budget_lines(
    request: Request,
    file: UploadFile = File(...),
    year: int = Form(0),
    db: Session = Depends(get_db),
):
    from app.main import require_login
    u = require_login(request)
    if u.get("role") not in ROLE_BUDGETS:
        raise HTTPException(403, "Accès non autorisé — Admin/DCF uniquement")

    raw     = await file.read()
    fname   = (file.filename or "").lower()
    created = updated = skipped = 0
    errors  = []

    try:
        # ── Excel ──────────────────────────────────────────────
        if fname.endswith((".xlsx", ".xls")):
            headers, data_rows = _read_excel(raw)
            for row_i, row in enumerate(data_rows, 2):
                try:
                    yr_raw  = _gcol(row, headers, "YEAR", "ANNEE", "ANNÉE") or (str(year) if year else "")
                    dirn    = _gcol(row, headers, "DIRECTION").upper()
                    imp     = _gcol(row, headers, "IMPUTATION COMPTABLE", "IMPUTATION", "ACCOUNTING")
                    lib     = _gcol(row, headers, "LIBELLE", "DESCRIPTION", "LABEL")
                    nat     = _gcol(row, headers, "NATURE") or "DEPENSE COURANTE"
                    bcp_raw = _gcol(row, headers, "BUDGET CP", "BUDGET_CP", "APPROVED", "MONTANT")
                    if not yr_raw or not dirn or not imp:
                        skipped += 1; continue
                    yr  = int(float(yr_raw))
                    bcp = _clean_amount(bcp_raw)
                    _, was_created = crud.upsert_budget_line(db, yr, dirn, imp, lib, nat, bcp)
                    if was_created: created += 1
                    else:           updated  += 1
                except Exception as e:
                    errors.append(f"Row {row_i}: {e}")

        # ── CSV ────────────────────────────────────────────────
        else:
            txt    = _decode(raw).lstrip("\ufeff")
            reader = csv.DictReader(io.StringIO(txt))
            for row_i, row in enumerate(reader, 2):
                try:
                    yr_raw  = (row.get("YEAR") or row.get("ANNEE") or row.get("year") or "").strip()
                    if not yr_raw and year:
                        yr_raw = str(year)
                    dirn    = (row.get("DIRECTION") or row.get("direction") or "").strip().upper()
                    imp     = (row.get("IMPUTATION COMPTABLE") or row.get("IMPUTATION") or
                               row.get("imputation") or row.get("ACCOUNTING ENTRY") or "").strip()
                    lib     = (row.get("LIBELLE") or row.get("libelle") or
                               row.get("DESCRIPTION") or "").strip()
                    nat     = (row.get("NATURE") or row.get("nature") or "DEPENSE COURANTE").strip()
                    bcp_raw = str(row.get("BUDGET CP (FCFA)") or row.get("BUDGET CP") or
                                  row.get("budget_cp") or row.get("Budget CP (FCFA)") or "0").strip()
                    if not yr_raw or not dirn or not imp:
                        skipped += 1; continue
                    yr  = int(float(yr_raw))
                    bcp = _clean_amount(bcp_raw)
                    _, was_created = crud.upsert_budget_line(db, yr, dirn, imp, lib, nat, bcp)
                    if was_created: created += 1
                    else:           updated  += 1
                except Exception as e:
                    errors.append(f"Row {row_i}: {e}")

        db.commit()

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Import failed and rolled back: {e}")

    return ImportResult(created=created, updated=updated, skipped=skipped, errors=errors[:20])
