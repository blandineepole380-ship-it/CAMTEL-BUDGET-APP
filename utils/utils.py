"""
Kolo-Ride Utility Modules
==========================
  - matching.py  → Find nearest driver & create trip
  - pricing.py   → Calculate fare from GPS coords
  - location.py  → Resolve text → GPS (the "Alias Engine")
"""

# ════════════════════════════════════════════════════════════════
#  utils/matching.py  — The core matching engine
# ════════════════════════════════════════════════════════════════

import uuid
import requests
import os
import logging
from math import radians, sin, cos, sqrt, atan2

log = logging.getLogger(__name__)

TWILIO_SID    = os.environ.get("TWILIO_SID", "")
TWILIO_TOKEN  = os.environ.get("TWILIO_TOKEN", "")
TWILIO_SMS_NO = os.environ.get("TWILIO_SMS_NO", "")
CAMPAY_USER   = os.environ.get("CAMPAY_USER", "")
CAMPAY_PASS   = os.environ.get("CAMPAY_PASS", "")
CAMPAY_ENV    = os.environ.get("CAMPAY_ENV", "DEV")   # "PROD" for live


def match_rider_to_driver(rider_phone, pickup_text, destination_text,
                           get_db, pickup_coords=None, dest_coords=None, fare=None):
    """
    Full matching pipeline:
    1. Find nearest available driver via PostGIS
    2. Create trip record in DB
    3. Notify driver by SMS
    4. Trigger MoMo payment push
    Returns a dict with success, driver info, ETA, invoice number.
    """
    from utils.location import resolve_location
    from utils.pricing  import calculate_fare

    # Resolve coords if not already provided
    if not pickup_coords:
        pickup_coords = resolve_location(pickup_text)
    if not dest_coords:
        dest_coords   = resolve_location(destination_text)
    if not pickup_coords or not dest_coords:
        return {"success": False, "reason": "unknown_location"}
    if not fare:
        fare = calculate_fare(pickup_coords, dest_coords)

    conn = get_db()

    # Step 1 — Find nearest driver
    drivers = find_nearest_drivers(pickup_coords, conn)
    if not drivers:
        conn.close()
        return {"success": False, "reason": "no_drivers"}

    best = drivers[0]

    # Step 2 — Ensure user exists
    user_id = ensure_user(rider_phone, conn)

    # Step 3 — Create trip record
    trip_id, invoice_no = create_trip(
        user_id, best["driver_id"],
        pickup_text, pickup_coords,
        destination_text, dest_coords,
        fare, conn
    )

    conn.close()

    # Step 4 — Notify driver by SMS (works even without internet on driver's side)
    notify_driver_sms(
        best["phone"], rider_phone,
        pickup_text, destination_text, fare, trip_id
    )

    # Step 5 — Trigger MoMo push
    _trigger_momo(rider_phone, fare, str(trip_id))

    eta_minutes = max(1, round(best["distance_m"] / 300))  # ~18 km/h in traffic

    return {
        "success":        True,
        "trip_id":        str(trip_id),
        "invoice_number": invoice_no,
        "driver_name":    best["name"],
        "driver_phone":   best["phone"],
        "eta_minutes":    eta_minutes,
        "fare":           fare,
    }


def find_nearest_drivers(pickup_coords, conn, radius_m=3000, limit=5):
    """PostGIS query for nearest online, verified drivers."""
    lat, lng = pickup_coords
    cur = conn.cursor()
    cur.execute("""
        SELECT
            d.id           AS driver_id,
            u.phone_number AS phone,
            u.full_name    AS name,
            ROUND(ST_Distance(
                d.current_location,
                ST_MakePoint(%s, %s)::geography
            )::numeric) AS distance_m
        FROM drivers d
        JOIN users u ON u.id = d.user_id
        WHERE d.status      = 'online'
          AND d.is_verified  = TRUE
          AND ST_DWithin(
                d.current_location,
                ST_MakePoint(%s, %s)::geography,
                %s
              )
        ORDER BY distance_m ASC
        LIMIT %s
    """, (lng, lat, lng, lat, radius_m, limit))
    rows = cur.fetchall()
    return [dict(r) for r in rows] if rows else []


def ensure_user(phone, conn):
    """Get or create a user record. Returns the user UUID."""
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE phone_number = %s", (phone,))
    row = cur.fetchone()
    if row:
        return row["id"]
    new_id = str(uuid.uuid4())
    cur.execute(
        "INSERT INTO users (id, phone_number) VALUES (%s, %s) RETURNING id",
        (new_id, phone)
    )
    conn.commit()
    return cur.fetchone()["id"]


def create_trip(rider_id, driver_id, pickup_text, pickup_coords,
                dest_text, dest_coords, fare, conn):
    """Inserts a trip row. Returns (trip_id, invoice_number)."""
    pickup_lat, pickup_lng = pickup_coords
    dest_lat,   dest_lng   = dest_coords
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO trips (
            rider_id, driver_id,
            pickup_address, pickup_coords,
            destination_address, destination_coords,
            fare_amount, status
        ) VALUES (
            %s, %s,
            %s, ST_MakePoint(%s, %s)::geography,
            %s, ST_MakePoint(%s, %s)::geography,
            %s, 'requested'
        )
        RETURNING id, invoice_number
    """, (
        rider_id, driver_id,
        pickup_text, pickup_lng, pickup_lat,
        dest_text,  dest_lng,   dest_lat,
        fare
    ))
    row = cur.fetchone()
    # Mark driver as busy
    cur.execute("UPDATE drivers SET status = 'busy' WHERE id = %s", (driver_id,))
    conn.commit()
    return row["id"], row["invoice_number"]


def notify_driver_sms(driver_phone, rider_phone, pickup, destination, fare, trip_id):
    """Send an SMS to the driver. Works without WhatsApp or internet."""
    if not TWILIO_SID:
        log.warning("Twilio not configured — skipping SMS")
        return
    from twilio.rest import Client
    client = Client(TWILIO_SID, TWILIO_TOKEN)
    body = (
        f"KOLO-RIDE ALERT!\n"
        f"Trip: {pickup} → {destination}\n"
        f"Fare: {fare} XAF\n"
        f"Rider: {rider_phone}\n"
        f"Reply YES to accept"
    )
    try:
        client.messages.create(body=body, from_=TWILIO_SMS_NO, to=driver_phone)
    except Exception as e:
        log.error(f"SMS failed: {e}")


def _trigger_momo(phone, amount, trip_id):
    """Push a MoMo payment request to the rider's phone."""
    if not CAMPAY_USER:
        log.warning("Campay not configured — skipping MoMo push")
        return
    try:
        import campay
        client = campay.Client({
            "app_username": CAMPAY_USER,
            "app_password": CAMPAY_PASS,
            "environment":  CAMPAY_ENV,
        })
        client.collect({
            "amount":             str(amount),
            "currency":           "XAF",
            "from":               phone,
            "description":        f"Kolo-Ride trip #{trip_id}",
            "external_reference": trip_id,
        })
    except Exception as e:
        log.error(f"MoMo push failed: {e}")


# ════════════════════════════════════════════════════════════════
#  utils/pricing.py  — Fare calculation
# ════════════════════════════════════════════════════════════════

def calculate_fare(pickup_coords, dest_coords):
    """
    Haversine distance → XAF fare.
    Base: 500 XAF + 200 XAF/km, rounded to nearest 50.
    """
    R = 6371000
    lat1, lon1 = map(radians, pickup_coords)
    lat2, lon2 = map(radians, dest_coords)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a    = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
    dist = R * 2 * atan2(sqrt(a), sqrt(1-a))

    base    = 500
    per_km  = 200
    raw     = base + (dist / 1000) * per_km
    return int(round(raw / 50) * 50)


# ════════════════════════════════════════════════════════════════
#  utils/location.py  — Text-to-GPS alias engine
# ════════════════════════════════════════════════════════════════

"""
This is your COMPETITIVE MOAT.
Add every neighbourhood, carrefour, landmark, and dirt road here.
Uber and Yango can't do this — they rely on Google Maps.
You do it with local knowledge.

FORMAT: "text alias" → (latitude, longitude)
Coordinates from OpenStreetMap (osm.org) — always free.
"""

LOCATION_ALIASES = {
    # ── BUEA ──────────────────────────────────────────────────────────────────
    "mile 17":                      (4.1483, 9.2309),
    "mile 16":                      (4.1512, 9.2380),
    "mile 14":                      (4.1389, 9.2500),
    "molyko":                       (4.1524, 9.2396),
    "molyko junction":              (4.1520, 9.2390),
    "ub junction":                  (4.1557, 9.2451),
    "university of buea":           (4.1560, 9.2435),
    "ub gate":                      (4.1558, 9.2450),
    "carrefour total buea":         (4.1547, 9.2402),
    "carrefour brique":             (4.1530, 9.2370),
    "seme beach":                   (4.0018, 9.1967),
    "great soppo":                  (4.1583, 9.2500),
    "check point buea":             (4.1560, 9.2420),
    "buea town":                    (4.1600, 9.2417),
    "muea":                         (4.1278, 9.2411),

    # ── DOUALA ────────────────────────────────────────────────────────────────
    "akwa":                         (4.0508, 9.7002),
    "bonanjo":                      (4.0453, 9.6929),
    "deido":                        (4.0553, 9.7067),
    "ndokoti":                      (4.0758, 9.7297),
    "marché central douala":        (4.0511, 9.7043),
    "rond point deido":             (4.0558, 9.7064),
    "douala airport":               (4.0061, 9.7194),
    "bonapriso":                    (4.0481, 9.6952),
    "bepanda":                      (4.0752, 9.7342),
    "makepe":                       (4.0631, 9.7431),
    "logbessou":                    (4.1025, 9.7519),

    # ── YAOUNDÉ ───────────────────────────────────────────────────────────────
    "mvan":                         (3.8440, 11.5160),
    "nlongkak":                     (3.8727, 11.5128),
    "bastos":                       (3.8867, 11.5083),
    "mvog-ada":                     (3.8534, 11.5231),
    "etoug-ebe":                    (3.8700, 11.4986),
    "marché mokolo":                (3.8678, 11.5083),
    "carrefour simbok":             (3.8270, 11.5300),
    "gare voyageurs yaounde":       (3.8701, 11.5148),
    "yaoundé airport":              (3.8364, 11.5234),
    "mvog-mbi":                     (3.8583, 11.5308),
    "carrefour warda":              (3.8650, 11.5220),
    "rond point nlongkak":          (3.8735, 11.5135),

    # ── KRIBI ─────────────────────────────────────────────────────────────────
    "kribi beach":                  (2.9398, 9.9073),
    "kribi port":                   (2.9504, 9.9050),
    "kribi marché":                 (2.9375, 9.9087),
    "grand batanga":                (2.8812, 9.8872),
    "campo beach":                  (2.3673, 9.8197),

    # ── BAFOUSSAM ─────────────────────────────────────────────────────────────
    "bafoussam marché":             (5.4767, 10.4167),
    "bafoussam centre":             (5.4767, 10.4167),
    "kouoptamo":                    (5.4840, 10.4263),
    "bafoussam airport":            (5.5369, 10.3561),

    # ── GAROUA ────────────────────────────────────────────────────────────────
    "garoua marché":                (9.2970, 13.3940),
    "garoua airport":               (9.3336, 13.3700),

    # ── NGAOUNDÉRÉ ────────────────────────────────────────────────────────────
    "ngaoundere gare":              (7.3223, 13.5823),
    "ngaoundere centre":            (7.3223, 13.5823),

    # ── BERTOUA ───────────────────────────────────────────────────────────────
    "bertoua centre":               (4.5786, 13.6859),
    "bertoua marché":               (4.5780, 13.6870),

    # ── EBOLOWA ───────────────────────────────────────────────────────────────
    "ebolowa centre":               (2.9000, 11.1500),
    "ebolowa marché":               (2.9010, 11.1510),

    # ── LIMBE ─────────────────────────────────────────────────────────────────
    "limbe beach":                  (4.0153, 9.2017),
    "limbe down beach":             (4.0142, 9.2003),
    "limbe motor park":             (4.0170, 9.2034),
    "botanical garden limbe":       (4.0131, 9.2025),
}


def resolve_location(text: str):
    """
    Converts a user-typed place name to (lat, lng).
    Uses fuzzy matching so typos still work.
    Returns None if not found.
    """
    if not text:
        return None

    normalized = text.strip().lower()

    # Exact match
    if normalized in LOCATION_ALIASES:
        return LOCATION_ALIASES[normalized]

    # Partial match (for typos and abbreviations)
    best_match = None
    best_score = 0
    for alias, coords in LOCATION_ALIASES.items():
        # Count how many words in the user input appear in the alias
        user_words  = set(normalized.split())
        alias_words = set(alias.split())
        overlap     = len(user_words & alias_words)
        if overlap > best_score:
            best_score = overlap
            best_match = coords

    if best_score >= 1:
        return best_match

    return None  # Unknown location


def add_location(text: str, lat: float, lng: float):
    """
    Dynamically add a new location alias at runtime.
    In production, also persist this to the DB.
    """
    LOCATION_ALIASES[text.strip().lower()] = (lat, lng)
    log.info(f"New alias added: '{text}' → ({lat}, {lng})")
