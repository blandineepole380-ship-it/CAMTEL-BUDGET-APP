"""
Kolo-Ride API Server
====================
The central brain. Connects WhatsApp Bot, USSD Gateway, 
Driver App, Admin Dashboard, and Payment Engine.

Deploy free on: Railway.app / Render.com / Heroku
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
import psycopg2.extras
import os
import uuid
import logging
from datetime import datetime

# Internal modules
from bot.whatsapp   import handle_whatsapp_message
from bot.ussd       import handle_ussd_request
from api.trips      import trip_bp
from api.drivers    import driver_bp
from api.payments   import payment_bp
from api.admin      import admin_bp
from utils.matching import match_rider_to_driver
from utils.pricing  import calculate_fare
from config.settings import Config

# ─── APP SETUP ────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config.from_object(Config)
CORS(app)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ─── BLUEPRINTS ───────────────────────────────────────────────────────────────
app.register_blueprint(trip_bp,    url_prefix="/trip")
app.register_blueprint(driver_bp,  url_prefix="/driver")
app.register_blueprint(payment_bp, url_prefix="/payment")
app.register_blueprint(admin_bp,   url_prefix="/admin")

# ─── DATABASE CONNECTION ──────────────────────────────────────────────────────
def get_db():
    return psycopg2.connect(
        os.environ.get("DATABASE_URL", Config.DATABASE_URL),
        cursor_factory=psycopg2.extras.RealDictCursor
    )

# ─── HEALTH CHECK ─────────────────────────────────────────────────────────────
@app.route("/")
def health():
    return jsonify({
        "service": "Kolo-Ride API",
        "status":  "running",
        "version": "1.0.0",
        "time":    datetime.utcnow().isoformat()
    })

# ─── WHATSAPP WEBHOOK ─────────────────────────────────────────────────────────
@app.route("/whatsapp", methods=["POST", "GET"])
def whatsapp_webhook():
    # Twilio verification handshake
    if request.method == "GET":
        return request.args.get("hub.challenge", ""), 200

    incoming = {
        "body":      request.form.get("Body", "").strip(),
        "from":      request.form.get("From", ""),       # e.g. whatsapp:+237612345678
        "latitude":  request.form.get("Latitude"),
        "longitude": request.form.get("Longitude"),
        "media_url": request.form.get("MediaUrl0"),      # voice notes / images
        "num_media": request.form.get("NumMedia", "0"),
    }
    log.info(f"WhatsApp in: {incoming['from']} → '{incoming['body'][:60]}'")

    reply = handle_whatsapp_message(incoming, get_db)
    return reply, 200, {"Content-Type": "text/xml"}

# ─── USSD WEBHOOK ─────────────────────────────────────────────────────────────
@app.route("/ussd", methods=["POST"])
def ussd_webhook():
    payload = {
        "session_id":   request.values.get("sessionId",    ""),
        "phone_number": request.values.get("phoneNumber",  ""),
        "text":         request.values.get("text",         ""),
        "service_code": request.values.get("serviceCode",  "*237#"),
        "network":      request.values.get("networkCode",  ""),   # MTN / Orange
    }
    log.info(f"USSD: {payload['phone_number']} text='{payload['text']}'")

    response = handle_ussd_request(payload, get_db)
    return response, 200, {"Content-Type": "text/plain"}

# ─── DRIVER LOCATION UPDATE (called by Flutter app every 15s) ─────────────────
@app.route("/driver/location", methods=["POST"])
def update_driver_location():
    data = request.get_json()
    driver_id = data.get("driver_id")
    lat       = data.get("latitude")
    lng       = data.get("longitude")
    status    = data.get("status", "online")

    if not all([driver_id, lat, lng]):
        return jsonify({"error": "Missing fields"}), 400

    conn = get_db()
    cur  = conn.cursor()
    cur.execute("""
        UPDATE drivers
        SET current_location = ST_MakePoint(%s, %s)::geography,
            status           = %s,
            last_seen        = NOW()
        WHERE id = %s
    """, (lng, lat, status, driver_id))
    conn.commit()
    conn.close()

    return jsonify({"ok": True})

# ─── MATCH ENDPOINT (direct API call, used by WhatsApp bot & USSD) ────────────
@app.route("/match", methods=["POST"])
def match():
    data            = request.get_json()
    rider_phone     = data.get("rider_phone")
    pickup_text     = data.get("pickup")
    destination_text = data.get("destination")

    result = match_rider_to_driver(rider_phone, pickup_text, destination_text, get_db)
    return jsonify(result)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
