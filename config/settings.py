"""
config/settings.py — All environment variables in one place.
Copy .env.example to .env and fill in your real values.
"""

import os

class Config:
    # ── Database ──────────────────────────────────────────────────────────────
    # Format: postgresql://user:password@host:5432/kolo_ride
    DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:password@localhost:5432/kolo_ride")

    # ── Twilio (WhatsApp + SMS) ───────────────────────────────────────────────
    # Get from: console.twilio.com
    TWILIO_SID          = os.environ.get("TWILIO_SID",    "")
    TWILIO_TOKEN        = os.environ.get("TWILIO_TOKEN",  "")
    TWILIO_WHATSAPP_NO  = os.environ.get("TWILIO_WA_NO",  "whatsapp:+14155238886")
    TWILIO_SMS_NO       = os.environ.get("TWILIO_SMS_NO", "")

    # ── Campay (MTN MoMo + Orange Money) ─────────────────────────────────────
    # Get from: campay.net — Cameroonian payment gateway
    CAMPAY_USER         = os.environ.get("CAMPAY_USER",   "")
    CAMPAY_PASS         = os.environ.get("CAMPAY_PASS",   "")
    CAMPAY_ENV          = os.environ.get("CAMPAY_ENV",    "DEV")   # "PROD" for live

    # ── Africa's Talking (USSD Gateway) ──────────────────────────────────────
    # Get from: account.africastalking.com
    AT_API_KEY          = os.environ.get("AT_API_KEY",    "")
    AT_USERNAME         = os.environ.get("AT_USERNAME",   "sandbox")
    AT_USSD_CODE        = os.environ.get("AT_USSD_CODE",  "*237#")

    # ── Flask ─────────────────────────────────────────────────────────────────
    SECRET_KEY          = os.environ.get("SECRET_KEY",    "change-me-in-production")
    DEBUG               = os.environ.get("DEBUG",         "False") == "True"
