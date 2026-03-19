"""
Kolo-Ride Language Module
==========================
All user-facing text in English, French, and Cameroon Pidgin.
Add more languages here as you expand.
"""

# ─── LANGUAGE DETECTION ───────────────────────────────────────────────────────

PIDGIN_MARKERS  = ["oya", "vif", "wetin", "i wan", "na", "weh", "eh", "how far", "for where", "di"]
FRENCH_MARKERS  = ["bonjour", "bonsoir", "je", "oui", "non", "où", "aller", "comment", "merci", "s'il"]

def detect_language(text: str) -> str | None:
    """Guess language from message content. Returns 'pidgin', 'fr', 'en', or None."""
    text_lower = text.lower()
    pidgin_hits = sum(1 for w in PIDGIN_MARKERS if w in text_lower)
    french_hits  = sum(1 for w in FRENCH_MARKERS  if w in text_lower)

    if pidgin_hits >= 2:
        return "pidgin"
    if french_hits >= 1:
        return "fr"
    if any(c in text_lower for c in ["the", "where", "please", "hi", "hello"]):
        return "en"
    return None


# ─── TEXT STRINGS ─────────────────────────────────────────────────────────────
# Each key maps to { "en": ..., "fr": ..., "pidgin": ... }

TEXTS = {

    "welcome": {
        "en": (
            "👋 Welcome to *Kolo-Ride* — transport that works for YOU!\n\n"
            "Type *Ride* to book a trip\n"
            "Type *Price* to see rates\n"
            "Type *Help* for assistance\n\n"
            "_We cover Buea, Kribi, Bafoussam & more_ 🇨🇲"
        ),
        "fr": (
            "👋 Bienvenue sur *Kolo-Ride* — transport fait pour vous!\n\n"
            "Tapez *Course* pour réserver\n"
            "Tapez *Prix* pour voir les tarifs\n"
            "Tapez *Aide* pour de l'assistance\n\n"
            "_On couvre Buea, Kribi, Bafoussam & plus_ 🇨🇲"
        ),
        "pidgin": (
            "👋 Welcome for *Kolo-Ride* — transport weh dey work for you!\n\n"
            "Type *Vif* make we carry you go\n"
            "Type *Price* to see how much e go cost\n"
            "Type *Help* if you get wahala\n\n"
            "_We dey Buea, Kribi, Bafoussam & more_ 🇨🇲"
        ),
    },

    "ask_pickup": {
        "en":     "📍 Where should we pick you up?\n\nSend your *location pin* or type a landmark (e.g. _Mile 17_, _Carrefour Total_)",
        "fr":     "📍 Où devons-nous vous prendre?\n\nEnvoyez votre *position GPS* ou tapez un lieu (ex: _Rond Point_, _Marché Central_)",
        "pidgin": "📍 For where you dey? Make you send your *location* or type the place (e.g. _Mile 17_, _Carrefour Total_)",
    },

    "got_location_ask_dest": {
        "en":     "✅ Got your location!\n\nNow, where are you going? Type the destination or send a location pin.",
        "fr":     "✅ Position reçue!\n\nOù allez-vous? Tapez la destination ou envoyez un pin GPS.",
        "pidgin": "✅ I don see where you dey!\n\nNow tell me, for where you wan go? Type the place or send pin.",
    },

    "got_pickup_ask_dest": {
        "en":     "✅ Pickup set: *{pickup}*\n\nNow where are you going?",
        "fr":     "✅ Départ: *{pickup}*\n\nOù allez-vous?",
        "pidgin": "✅ We go carry you from *{pickup}*\n\nFor where you wan go now?",
    },

    "confirm_trip": {
        "en": (
            "🚕 *Trip Summary*\n\n"
            "📍 From: {pickup}\n"
            "🏁 To:   {dest}\n"
            "💰 Fare: *{fare} XAF*\n\n"
            "Reply *Yes* to confirm or *Cancel* to stop."
        ),
        "fr": (
            "🚕 *Résumé du trajet*\n\n"
            "📍 Départ: {pickup}\n"
            "🏁 Arrivée: {dest}\n"
            "💰 Tarif: *{fare} XAF*\n\n"
            "Répondez *Oui* pour confirmer ou *Annuler* pour arrêter."
        ),
        "pidgin": (
            "🚕 *Your Ride Summary*\n\n"
            "📍 From: {pickup}\n"
            "🏁 Go: {dest}\n"
            "💰 Money: *{fare} XAF*\n\n"
            "Reply *Oya* to confirm or *Cancel* to stop."
        ),
    },

    "driver_found": {
        "en": (
            "✅ *Driver Found!*\n\n"
            "👤 {driver} is on the way\n"
            "⏱ ETA: ~{eta} minutes\n"
            "💰 Fare: {fare} XAF (MoMo prompt coming)\n"
            "🧾 Invoice: #{invoice}\n\n"
            "_Look out for the car with the Kolo-Ride sticker_ 🟢"
        ),
        "fr": (
            "✅ *Chauffeur trouvé!*\n\n"
            "👤 {driver} arrive\n"
            "⏱ Arrivée dans: ~{eta} minutes\n"
            "💰 Tarif: {fare} XAF (prompt MoMo arrive)\n"
            "🧾 Facture: #{invoice}\n\n"
            "_Cherchez la voiture avec le sticker Kolo-Ride_ 🟢"
        ),
        "pidgin": (
            "✅ *Driver don find!*\n\n"
            "👤 {driver} dey come your side\n"
            "⏱ E go reach for: ~{eta} minutes\n"
            "💰 Money: {fare} XAF (check your MoMo)\n"
            "🧾 Receipt: #{invoice}\n\n"
            "_Look for the motor weh get Kolo-Ride sticker_ 🟢"
        ),
    },

    "no_drivers": {
        "en":     "😞 No drivers available near you right now. Please try again in 5 minutes.",
        "fr":     "😞 Aucun chauffeur disponible près de vous. Réessayez dans 5 minutes.",
        "pidgin": "😞 No driver near you for now. Try again after 5 minutes — e go better.",
    },

    "location_not_found": {
        "en":     "🤔 We don't recognise *{place}* yet. Try a nearby landmark, or send your GPS pin directly.",
        "fr":     "🤔 Nous ne reconnaissons pas *{place}* encore. Essayez un lieu proche ou envoyez votre position GPS.",
        "pidgin": "🤔 We no know *{place}* yet. Try another place near there or send your location pin.",
    },

    "cancelled": {
        "en":     "❌ Booking cancelled. Type *Ride* whenever you're ready again.",
        "fr":     "❌ Réservation annulée. Tapez *Course* quand vous êtes prêt.",
        "pidgin": "❌ We don cancel am. Type *Vif* when you ready to go again.",
    },

    "trip_cancelled": {
        "en":     "Okay! Booking cancelled. Stay safe 🙏",
        "fr":     "D'accord! Réservation annulée. Bonne journée 🙏",
        "pidgin": "Oya, we don cancel am. Take care yourself 🙏",
    },

    "on_trip_status": {
        "en":     "🚗 You're on a ride with *{driver}* heading to *{dest}*.\n\nType *Arrived* when you get there to rate your trip.",
        "fr":     "🚗 Vous êtes en course avec *{driver}* vers *{dest}*.\n\nTapez *Arrivé* quand vous y êtes.",
        "pidgin": "🚗 You dey inside motor with *{driver}* going *{dest}*.\n\nType *We don reach* when you arrive.",
    },

    "rate_driver": {
        "en":     "🏁 Trip complete! How was *{driver}*?\n\nReply with a number: 5⭐ 4⭐ 3⭐ 2⭐ 1⭐",
        "fr":     "🏁 Course terminée! Comment était *{driver}*?\n\nRépondez avec un chiffre: 5⭐ 4⭐ 3⭐ 2⭐ 1⭐",
        "pidgin": "🏁 Una reach! How *{driver}* do you?\n\nSend number: 5⭐ 4⭐ 3⭐ 2⭐ 1⭐",
    },

    "thanks_rating": {
        "en":     "🙏 Thanks for your rating! Book another ride anytime — just type *Ride*.",
        "fr":     "🙏 Merci pour votre note! Réservez encore — tapez *Course*.",
        "pidgin": "🙏 Thank you! Next time you wan move, type *Vif*.",
    },

    "driver_contact": {
        "en":     "📞 Your driver *{driver}* will call you shortly, or check your SMS for their number.",
        "fr":     "📞 Votre chauffeur *{driver}* vous appellera sous peu.",
        "pidgin": "📞 *{driver}* go call you small time. Check your SMS too.",
    },

    "pricing_info": {
        "en": (
            "💰 *Kolo-Ride Rates (XAF)*\n\n"
            "• Base fare: 500 XAF\n"
            "• Per km: 200 XAF\n"
            "• Inter-city carpool: from 3,000 XAF\n\n"
            "_No surge pricing. Ever._ ✅\n\n"
            "Type *Ride* to book now."
        ),
        "fr": (
            "💰 *Tarifs Kolo-Ride (XAF)*\n\n"
            "• Tarif de base: 500 XAF\n"
            "• Par km: 200 XAF\n"
            "• Covoiturage inter-city: à partir de 3 000 XAF\n\n"
            "_Pas de surcharge. Jamais._ ✅\n\n"
            "Tapez *Course* pour réserver."
        ),
        "pidgin": (
            "💰 *Kolo-Ride Price (XAF)*\n\n"
            "• Start money: 500 XAF\n"
            "• For every km: 200 XAF\n"
            "• Long journey carpool: from 3,000 XAF\n\n"
            "_Price no go up when rain fall._ ✅\n\n"
            "Type *Vif* to book now."
        ),
    },

    "help": {
        "en": (
            "🆘 *Kolo-Ride Help*\n\n"
            "• Type *Ride* — book a trip\n"
            "• Type *Price* — see rates\n"
            "• Type *Cancel* — cancel anytime\n"
            "• Share your 📍 Location — we use it for pickup\n\n"
            "No data? Dial *237# for USSD booking\n"
            "Support: +237 6XX XXX XXX"
        ),
        "fr": (
            "🆘 *Aide Kolo-Ride*\n\n"
            "• Tapez *Course* — réserver\n"
            "• Tapez *Prix* — voir les tarifs\n"
            "• Tapez *Annuler* — annuler\n"
            "• Partagez votre 📍 Position — pour le départ\n\n"
            "Pas de data? Composez *237# pour réserver par USSD\n"
            "Support: +237 6XX XXX XXX"
        ),
        "pidgin": (
            "🆘 *Kolo-Ride Help*\n\n"
            "• Type *Vif* — make we carry you\n"
            "• Type *Price* — see money\n"
            "• Type *Cancel* — stop am\n"
            "• Send your 📍 location — we go pick you from there\n\n"
            "No data? Call *237# for USSD booking\n"
            "Problem? Call: +237 6XX XXX XXX"
        ),
    },
}


# ─── PUBLIC GETTER ─────────────────────────────────────────────────────────────

def get_text(key: str, lang: str) -> str:
    """Fetch a message string. Falls back to French if lang not found."""
    entry = TEXTS.get(key, {})
    return entry.get(lang) or entry.get("fr") or entry.get("en") or f"[{key}]"
