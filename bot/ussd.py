"""
Kolo-Ride USSD Handler
=======================
Handles the *237# dial flow for users with no internet.
Works with Africa's Talking, MTN, or Orange USSD gateways.

Flow:
  *237# → Main Menu
       → 1. Book Ride → pickup → destination → confirm → MoMo push
       → 2. Price Check
       → 3. My Trips
       → 4. Help
"""

from utils.location  import resolve_location
from utils.pricing   import calculate_fare
from utils.matching  import match_rider_to_driver
import logging

log = logging.getLogger(__name__)

# ─── CON = "Continue" (more input needed)
# ─── END = "End session" (final message)

def handle_ussd_request(payload: dict, get_db) -> str:
    """Main USSD entry point. Returns a CON or END string."""

    phone    = payload["phone_number"]   # e.g. +2376XXXXXXXX
    text     = payload["text"]           # The full input chain, e.g. "1*Mile 17*Molyko*1"
    network  = payload.get("network", "")

    # Split the chain of inputs
    parts = text.split("*") if text else []
    depth = len(parts)

    # ── LEVEL 0: Main Menu ────────────────────────────────────────────────────
    if text == "":
        return (
            "CON Kolo-Ride 🚕\n"
            "1. Réserver/Book a Ride\n"
            "2. Prix/Price Check\n"
            "3. Mes Courses/My Trips\n"
            "4. Aide/Help"
        )

    # ── LEVEL 1: User chose from main menu ────────────────────────────────────
    if depth == 1:
        choice = parts[0]

        if choice == "1":
            return (
                "CON D'où partez-vous? / Pickup:\n"
                "(ex: Mile 17, Molyko, Rond Point)"
            )
        elif choice == "2":
            return (
                "END Tarifs Kolo-Ride:\n"
                "Base: 500 XAF\n"
                "+ 200 XAF/km\n"
                "Inter-city: dep. 3,000 XAF\n"
                "Pas de prix surge!"
            )
        elif choice == "3":
            conn = get_db()
            trips = get_recent_trips(phone, conn)
            conn.close()
            if not trips:
                return "END Vous n'avez pas encore de courses.\nType 'Ride' sur WhatsApp ou Dial *237#"
            lines = "\n".join(
                f"{t['created_at'].strftime('%d/%m')} {t['pickup_address']}→{t['destination_address']} {t['fare_amount']}XAF"
                for t in trips[:3]
            )
            return f"END Vos 3 dernières courses:\n{lines}"
        elif choice == "4":
            return (
                "END Aide Kolo-Ride:\n"
                "WhatsApp: wa.me/237XXXXXX\n"
                "Tel: +237 6XX XXX XXX\n"
                "Dial *237# pour book"
            )
        else:
            return "END Entrée invalide. Rappel *237# pour réessayer."

    # ── LEVEL 2: User entered pickup location ─────────────────────────────────
    if depth == 2 and parts[0] == "1":
        pickup_text = parts[1].strip()
        coords = resolve_location(pickup_text)

        if not coords:
            return (
                f"CON Lieu '{pickup_text}' non trouvé.\n"
                "Réessayez (ex: Molyko, UB Gate):"
            )
        return (
            "CON Destination?\n"
            "(ex: Mile 17, Carrefour Total)"
        )

    # ── LEVEL 3: User entered destination ────────────────────────────────────
    if depth == 3 and parts[0] == "1":
        pickup_text = parts[1].strip()
        dest_text   = parts[2].strip()

        pickup_coords = resolve_location(pickup_text)
        dest_coords   = resolve_location(dest_text)

        if not pickup_coords:
            return "END Lieu de départ inconnu. Réessayez *237#"
        if not dest_coords:
            return "END Destination inconnue. Réessayez *237#"

        fare = calculate_fare(pickup_coords, dest_coords)

        return (
            f"CON Trajet: {pickup_text}→{dest_text}\n"
            f"Prix: {fare} XAF\n"
            f"1. Confirmer (MoMo)\n"
            f"2. Annuler"
        )

    # ── LEVEL 4: User confirms or cancels ─────────────────────────────────────
    if depth == 4 and parts[0] == "1":
        pickup_text = parts[1].strip()
        dest_text   = parts[2].strip()
        answer      = parts[3].strip()

        if answer == "2":
            return "END Course annulée. Dial *237# pour réessayer."

        if answer == "1":
            pickup_coords = resolve_location(pickup_text)
            dest_coords   = resolve_location(dest_text)
            fare          = calculate_fare(pickup_coords, dest_coords)

            conn   = get_db()
            result = match_rider_to_driver(
                rider_phone      = phone,
                pickup_text      = pickup_text,
                destination_text = dest_text,
                get_db           = get_db,
                pickup_coords    = pickup_coords,
                dest_coords      = dest_coords,
                fare             = fare
            )
            conn.close()

            if result["success"]:
                return (
                    f"END Chauffeur trouvé!\n"
                    f"{result['driver_name']} arrive\n"
                    f"ETA: ~{result['eta_minutes']} min\n"
                    f"Prix: {fare} XAF\n"
                    f"Vérif MoMo pour payer\n"
                    f"Facture: #{result['invoice_number']}"
                )
            else:
                return (
                    "END Aucun chauffeur dispo.\n"
                    "Réessayez dans 5 min.\n"
                    "Dial *237#"
                )

        return "END Entrée invalide. Dial *237#"

    return "END Session invalide. Dial *237# pour recommencer."


# ─── DB HELPERS ───────────────────────────────────────────────────────────────

def get_recent_trips(phone: str, conn) -> list:
    cur = conn.cursor()
    cur.execute("""
        SELECT t.pickup_address, t.destination_address, t.fare_amount, t.created_at
        FROM trips t
        JOIN users u ON u.id = t.rider_id
        WHERE u.phone_number = %s
        ORDER BY t.created_at DESC
        LIMIT 3
    """, (phone,))
    return cur.fetchall() or []
