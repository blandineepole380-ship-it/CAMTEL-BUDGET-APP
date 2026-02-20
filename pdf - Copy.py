from __future__ import annotations

import io
from datetime import datetime
from typing import List, Optional

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm


def _fmt_date(d: Optional[datetime]) -> str:
    if not d:
        return ""
    return d.strftime("%d/%m/%Y")


def build_fiche_pdf(txs: List[object], logo_path: Optional[str] = None) -> io.BytesIO:
    """2 transactions per A4. tx object is SQLAlchemy Transaction."""

    buff = io.BytesIO()
    c = canvas.Canvas(buff, pagesize=A4)
    width, height = A4

    # Header
    if logo_path:
        try:
            c.drawImage(logo_path, 15 * mm, height - 35 * mm, width=35 * mm, height=20 * mm, preserveAspectRatio=True, mask='auto')
        except Exception:
            pass

    c.setFont("Helvetica-Bold", 14)
    c.drawString(60 * mm, height - 20 * mm, "FICHE D'IMPUTATION BUDGETAIRE")
    c.setFont("Helvetica", 10)
    c.drawString(60 * mm, height - 27 * mm, "(2 transactions par page A4)")

    # Blocks
    top_y = height - 45 * mm
    block_h = 110 * mm

    for idx in range(2):
        y = top_y - idx * block_h
        if idx >= len(txs):
            break
        tx = txs[idx]

        c.setLineWidth(1)
        c.rect(10 * mm, y - (block_h - 10 * mm), width - 20 * mm, block_h - 15 * mm)

        c.setFont("Helvetica-Bold", 11)
        c.drawString(12 * mm, y - 8 * mm, f"Transaction {idx+1}")

        c.setFont("Helvetica", 9)
        c.drawString(12 * mm, y - 16 * mm, f"Année: {getattr(tx,'year','')}   Département: {getattr(tx,'department','')}   Doc: {getattr(tx,'doc_type','')}")
        c.drawString(12 * mm, y - 24 * mm, f"Code/Ref: {getattr(tx,'code_ref','')}   Date: {_fmt_date(getattr(tx,'date_doc',None))}")
        c.drawString(12 * mm, y - 32 * mm, f"Ligne budgétaire: {getattr(tx,'budget_line_code','')} - {getattr(tx,'budget_line_title','')}")

        c.setFont("Helvetica-Bold", 10)
        c.drawString(12 * mm, y - 42 * mm, f"Montant (FCFA): {getattr(tx,'amount',0.0):,.0f}")

        # OM details
        if getattr(tx, "doc_type", "") == "OM":
            c.setFont("Helvetica", 9)
            c.drawString(12 * mm, y - 52 * mm, f"OM - Date aller: {_fmt_date(getattr(tx,'om_date_aller',None))}   Date retour: {_fmt_date(getattr(tx,'om_date_retour',None))}")
            c.drawString(12 * mm, y - 60 * mm, f"Jours: {getattr(tx,'om_days',0)}   Montant/jour: {getattr(tx,'om_amount_per_day',0.0):,.0f}   Total: {getattr(tx,'amount',0.0):,.0f}")

        # BC details
        if getattr(tx, "doc_type", "") == "BC":
            c.setFont("Helvetica", 9)
            c.drawString(12 * mm, y - 52 * mm, f"BC - HT: {getattr(tx,'bc_ht',0.0):,.0f}   TVA 19.25%: {getattr(tx,'bc_tva',0.0):,.0f}")
            c.drawString(12 * mm, y - 60 * mm, f"IR ({getattr(tx,'bc_ir_rate',0.0)}%): {getattr(tx,'bc_ir',0.0):,.0f}   TTC: {getattr(tx,'bc_ttc',0.0):,.0f}   Net à payer: {getattr(tx,'bc_net',0.0):,.0f}")

        # Signature blocks
        c.setFont("Helvetica", 9)
        sig_y = y - 95 * mm
        c.drawString(12 * mm, sig_y, "Demandeur")
        c.drawString(70 * mm, sig_y, "Contrôle Budgétaire")
        c.drawString(140 * mm, sig_y, "Approbation")
        c.line(12 * mm, sig_y - 18 * mm, 55 * mm, sig_y - 18 * mm)
        c.line(70 * mm, sig_y - 18 * mm, 120 * mm, sig_y - 18 * mm)
        c.line(140 * mm, sig_y - 18 * mm, (width - 12 * mm), sig_y - 18 * mm)

    c.showPage()
    c.save()
    buff.seek(0)
    return buff
