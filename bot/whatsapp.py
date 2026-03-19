"""
Kolo-Ride WhatsApp Bot
=======================
Handles all incoming WhatsApp messages.
Supports English, French, and Cameroon Pidgin.
Uses a simple state machine stored in the DB (no session memory needed).
"""

from twilio.twiml.messaging_response import MessagingResponse
from utils.matching  import match_rider_to_driver
from utils.location  import resolve_location
from utils.pricing   import calculate_fare
from utils.language  import detect_language, get_text
import logging

log = logging.getLogger(__name__)

# ─── CONVERSATION STATES ──────────────────────────────────────────────────────
# Stored per user phone in the `sessions` table
STATE_IDLE        = "idle"
STATE_ASK_PICKUP  = "ask_pickup"
STATE_ASK_DEST    = "ask_destination"
STATE_CONFIRM     = "confirm_trip"
STATE_ON_TRIP     = "on_trip"

# ─── PIDGIN KEYWORD DETECTION ─────────────────────────────────────────────────
PIDGIN_RIDE_WORDS  = ["vif", "move", "carry me", "where motor", "i wan go", "take me", "taxi"]
FRENCH_RIDE_WORDS  = ["réserver", "course", "aller", "trajet", "taxi", "voiture"]
ENGLISH_RIDE_WORDS = ["ride", "book", "trip", "car", "driver", "take me"]
CANCEL_WORDS       = ["cancel", "annuler", "stop", "no", "non", "nein"]
HELP_WORDS         = ["help", "aide", "how", "comment", "info", "?"]
RATING_WORDS       = ["rate", "noter", "rate driver"]

# ─── MAIN HANDLER ─────────────────────────────────────────────────────────────
def handle_whatsapp_message(incoming: dict, get_db) -> str:
    """
    Main entry point called by the Flask /whatsapp route.
    Returns a TwiML XML string for Twilio.
    """
    phone    = incoming["from"].replace("whatsapp:", "")
    body     = incoming["body"].lower().strip()
    lat      = incoming.get("latitude")
    lng      = incoming.get("longitude")

    conn     = get_db()

    # 1. Detect language preference
    lang     = detect_language(body) or get_user_language(phone, conn)

    # 2. Get current conversation state
    state    = get_session_state(phone, conn)
    session  = get_session_data(phone, conn)

    # 3. Handle cancellation at any point
    if any(w in body for w in CANCEL_WORDS) and state != STATE_IDLE:
        clear_session(phone, conn)
        reply = get_text("cancelled", lang)
        return build_reply(reply)

    # 4. Handle help at any point
    if any(w in body for w in HELP_WORDS):
        return build_reply(get_text("help", lang))

    # 5. Route by state
    if state == STATE_IDLE:
        reply = _handle_idle(phone, body, lat, lng, lang, conn)

    elif state == STATE_ASK_PICKUP:
        reply = _handle_pickup_input(phone, body, lat, lng, lang, session, conn)

    elif state == STATE_ASK_DEST:
        reply = _handle_destination_input(phone, body, lat, lng, lang, session, conn)

    elif state == STATE_CONFIRM:
        reply = _handle_confirmation(phone, body, lang, session, conn, get_db)

    elif state == STATE_ON_TRIP:
        reply = _handle_on_trip(phone, body, lang, session, conn)

    else:
        clear_session(phone, conn)
        reply = get_text("welcome", lang)

    conn.close()
    return build_reply(reply)


# ─── STATE HANDLERS ───────────────────────────────────────────────────────────

def _handle_idle(phone, body, lat, lng, lang, conn):
    """User is not in any flow. Detect intent."""

    # If they shared a GPS location directly
    if lat and lng:
        set_session(phone, conn, STATE_ASK_DEST, {"pickup_lat": lat, "pickup_lng": lng, "pickup_text": "Your location"})
        return get_text("got_location_ask_dest", lang)

    # If they said something ride-related
    all_ride_words = PIDGIN_RIDE_WORDS + FRENCH_RIDE_WORDS + ENGLISH_RIDE_WORDS
    if any(w in body for w in all_ride_words):
        set_session(phone, conn, STATE_ASK_PICKUP, {})
        return get_text("ask_pickup", lang)

    # Pricing inquiry
    if "price" in body or "prix" in body or "how much" in body or "combien" in body:
        return get_text("pricing_info", lang)

    # Default welcome
    return get_text("welcome", lang)


def _handle_pickup_input(phone, body, lat, lng, lang, session, conn):
    """User is telling us their pickup location."""

    # They shared a GPS pin
    if lat and lng:
        set_session(phone, conn, STATE_ASK_DEST, {
            **session,
            "pickup_lat":  float(lat),
            "pickup_lng":  float(lng),
            "pickup_text": "Your shared location"
        })
        return get_text("got_pickup_ask_dest", lang).format(pickup="your shared location")

    # They typed a name — try to resolve it
    coords = resolve_location(body)
    if coords:
        set_session(phone, conn, STATE_ASK_DEST, {
            **session,
            "pickup_lat":  coords[0],
            "pickup_lng":  coords[1],
            "pickup_text": body.title()
        })
        return get_text("got_pickup_ask_dest", lang).format(pickup=body.title())
    else:
        return get_text("location_not_found", lang).format(place=body)


def _handle_destination_input(phone, body, lat, lng, lang, session, conn):
    """User tells us destination."""

    dest_text = body.title()
    dest_coords = None

    if lat and lng:
        dest_coords = (float(lat), float(lng))
        dest_text   = "Shared destination"
    else:
        dest_coords = resolve_location(body)

    if not dest_coords:
        return get_text("location_not_found", lang).format(place=body)

    pickup_coords = (session["pickup_lat"], session["pickup_lng"])
    fare = calculate_fare(pickup_coords, dest_coords)

    set_session(phone, conn, STATE_CONFIRM, {
        **session,
        "dest_lat":   dest_coords[0],
        "dest_lng":   dest_coords[1],
        "dest_text":  dest_text,
        "fare":       fare
    })

    return get_text("confirm_trip", lang).format(
        pickup=session["pickup_text"],
        dest=dest_text,
        fare=fare
    )


def _handle_confirmation(phone, body, lang, session, conn, get_db):
    """User says yes/no to the fare quote."""

    YES_WORDS = ["yes", "oui", "ok", "confirm", "sure", "go", "oya", "correct", "1"]

    if any(w in body for w in YES_WORDS):
        # Trigger the matching engine
        result = match_rider_to_driver(
            rider_phone      = phone,
            pickup_text      = session["pickup_text"],
            destination_text = session["dest_text"],
            get_db           = get_db,
            pickup_coords    = (session["pickup_lat"], session["pickup_lng"]),
            dest_coords      = (session["dest_lat"],   session["dest_lng"]),
            fare             = session["fare"]
        )

        if result["success"]:
            set_session(phone, conn, STATE_ON_TRIP, {
                **session,
                "trip_id":     result["trip_id"],
                "driver_name": result["driver_name"],
                "driver_phone":result["driver_phone"],
                "eta_mins":    result["eta_minutes"]
            })
            return get_text("driver_found", lang).format(
                driver   = result["driver_name"],
                eta      = result["eta_minutes"],
                fare     = session["fare"],
                invoice  = result["invoice_number"]
            )
        else:
            clear_session(phone, conn)
            return get_text("no_drivers", lang)
    else:
        clear_session(phone, conn)
        return get_text("trip_cancelled", lang)


def _handle_on_trip(phone, body, lang, session, conn):
    """User is in an active trip. Handle mid-trip messages."""

    DONE_WORDS = ["arrived", "done", "finish", "arrivé", "fini", "we don reach"]

    if any(w in body for w in DONE_WORDS):
        clear_session(phone, conn)
        return get_text("rate_driver", lang).format(driver=session.get("driver_name", "your driver"))

    if any(str(n) in body for n in [1, 2, 3, 4, 5]):
        rating = next((str(n) for n in [5,4,3,2,1] if str(n) in body), "5")
        save_rating(session.get("trip_id"), int(rating), conn)
        clear_session(phone, conn)
        return get_text("thanks_rating", lang)

    # Driver contact
    if "call" in body or "phone" in body or "number" in body:
        return get_text("driver_contact", lang).format(driver=session.get("driver_name",""))

    return get_text("on_trip_status", lang).format(
        driver=session.get("driver_name",""),
        dest=session.get("dest_text","")
    )


# ─── SESSION HELPERS ──────────────────────────────────────────────────────────

def get_session_state(phone, conn):
    cur = conn.cursor()
    cur.execute("SELECT state FROM sessions WHERE phone = %s", (phone,))
    row = cur.fetchone()
    return row["state"] if row else STATE_IDLE

def get_session_data(phone, conn):
    import json
    cur = conn.cursor()
    cur.execute("SELECT data FROM sessions WHERE phone = %s", (phone,))
    row = cur.fetchone()
    if row and row["data"]:
        return json.loads(row["data"]) if isinstance(row["data"], str) else row["data"]
    return {}

def set_session(phone, conn, state, data):
    import json
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO sessions (phone, state, data, updated_at)
        VALUES (%s, %s, %s, NOW())
        ON CONFLICT (phone) DO UPDATE
          SET state = EXCLUDED.state,
              data  = EXCLUDED.data,
              updated_at = NOW()
    """, (phone, state, json.dumps(data)))
    conn.commit()

def clear_session(phone, conn):
    cur = conn.cursor()
    cur.execute("DELETE FROM sessions WHERE phone = %s", (phone,))
    conn.commit()

def get_user_language(phone, conn):
    cur = conn.cursor()
    cur.execute("SELECT preferred_language FROM users WHERE phone_number = %s", (phone,))
    row = cur.fetchone()
    return row["preferred_language"] if row else "fr"

def save_rating(trip_id, rating, conn):
    if not trip_id:
        return
    cur = conn.cursor()
    cur.execute("UPDATE trips SET rider_rating = %s WHERE id = %s", (rating, trip_id))
    conn.commit()

# ─── RESPONSE BUILDER ─────────────────────────────────────────────────────────

def build_reply(message: str) -> str:
    """Wraps a text reply in Twilio TwiML."""
    resp = MessagingResponse()
    resp.message(message)
    return str(resp)
