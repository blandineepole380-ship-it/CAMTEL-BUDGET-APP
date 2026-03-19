# 🚕 Kolo-Ride — API Server & WhatsApp Bot

Transport made for Cameroon. Works offline. Speaks Pidgin. Pays via MoMo.

---

## Architecture Overview

```
Rider (WhatsApp)  ─────┐
Rider (USSD *237#) ────┤──► Flask API Server ──► PostgreSQL + PostGIS
Rider (Lite App)   ────┘         │
                                  ├──► Campay (MTN MoMo / Orange Money)
Driver (Flutter App) ────────────┤──► Twilio (SMS alerts)
Admin (Dashboard) ───────────────┘──► Africa's Talking (USSD)
```

---

## Quick Start (5 Steps)

### Step 1 — Clone and install

```bash
git clone https://github.com/YOUR_USERNAME/kolo-ride.git
cd kolo-ride
pip install -r requirements.txt
```

### Step 2 — Set up environment

```bash
cp .env.example .env
# Edit .env with your real keys
nano .env
```

### Step 3 — Set up the database

Use [Supabase.com](https://supabase.com) for a free PostgreSQL + PostGIS database:

```bash
# Connect to your database and run the schema
psql $DATABASE_URL -f db/schema.sql
```

### Step 4 — Run locally

```bash
python api/server.py
# Server starts at http://localhost:5000
```

### Step 5 — Test it

```bash
# Test the health endpoint
curl http://localhost:5000/

# Test USSD flow (simulating Africa's Talking)
curl -X POST http://localhost:5000/ussd \
  -d "sessionId=TEST123&phoneNumber=+237612345678&text="

# Test booking (one level deep)
curl -X POST http://localhost:5000/ussd \
  -d "sessionId=TEST123&phoneNumber=+237612345678&text=1"
```

---

## Deploy to Production (Free on Railway.app)

1. Go to [railway.app](https://railway.app) and sign up
2. Click **New Project → Deploy from GitHub**
3. Select your `kolo-ride` repo
4. Add a **PostgreSQL** plugin (Railway provides it free)
5. Set your environment variables in the Railway dashboard
6. Railway auto-deploys — you get a URL like `https://kolo-ride-production.up.railway.app`

**Your webhooks will be:**
- WhatsApp: `https://your-url.railway.app/whatsapp`
- USSD:     `https://your-url.railway.app/ussd`

---

## Connect WhatsApp (Twilio Sandbox — Free to Test)

1. Go to [console.twilio.com](https://console.twilio.com)
2. Navigate to **Messaging → Try it out → Send a WhatsApp message**
3. Set the webhook URL to: `https://your-url.railway.app/whatsapp`
4. Send a WhatsApp message to the sandbox number to test

---

## Connect USSD (Africa's Talking Sandbox — Free)

1. Go to [account.africastalking.com](https://account.africastalking.com)
2. Create a USSD service in the sandbox
3. Set the callback URL to: `https://your-url.railway.app/ussd`
4. Use their sandbox simulator to test *237# flows

---

## Connect Campay (MoMo Payments)

1. Go to [campay.net](https://campay.net) and register your business
2. Get your API credentials from the dashboard
3. Add them to `.env` as `CAMPAY_USER` and `CAMPAY_PASS`
4. Change `CAMPAY_ENV=DEV` to `CAMPAY_ENV=PROD` when ready for real money

---

## API Endpoints

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/` | Health check |
| POST | `/whatsapp` | WhatsApp webhook (Twilio) |
| POST | `/ussd` | USSD webhook (Africa's Talking) |
| POST | `/driver/location` | Driver GPS update (Flutter app) |
| POST | `/driver/status` | Driver online/offline toggle |
| POST | `/match` | Manual trip matching |
| POST | `/trip/accept` | Driver accepts a trip |
| POST | `/trip/complete` | Driver completes a trip |
| GET | `/admin/summary` | Dashboard revenue data |

---

## Adding New Cities & Locations

Edit `utils/utils.py` in the `LOCATION_ALIASES` dictionary.
Add your city's key landmarks with coordinates from [osm.org](https://osm.org):

```python
LOCATION_ALIASES = {
    "my new location": (4.1234, 9.5678),  # lat, lng from OpenStreetMap
    ...
}
```

This is your **competitive moat** — Uber and Yango cannot do this without local knowledge.

---

## File Structure

```
kolo-ride/
├── api/
│   ├── server.py          # Main Flask app
│   ├── trips.py           # Trip CRUD endpoints
│   ├── drivers.py         # Driver management
│   ├── payments.py        # Campay integration
│   └── admin.py           # Dashboard data API
├── bot/
│   ├── whatsapp.py        # WhatsApp conversation engine
│   └── ussd.py            # USSD menu flow
├── utils/
│   ├── utils.py           # matching + pricing + location aliases
│   └── language.py        # EN / FR / Pidgin text strings
├── config/
│   └── settings.py        # Environment config
├── db/
│   └── schema.sql         # PostgreSQL + PostGIS schema
├── .env.example           # Environment template
├── requirements.txt       # Python dependencies
├── Dockerfile             # For containerized deployment
└── README.md              # This file
```

---

## Legal Compliance (Cameroon 2026)

- ✅ **E-Invoicing**: Every trip gets an `invoice_number` (required by DGI)
- ✅ **Campay audit trail**: `campay_reference` stored on every payment
- ✅ **Data minimization**: Only phone + location collected (no email required)
- ✅ **Local business**: Register at CFCE Cameroon to avoid non-resident tax
- ⚠️ **DPO required**: Once you pass 1,000 users, appoint a Data Protection Officer

---

*Built for Cameroon. Works in Buea, Kribi, Bafoussam, Garoua & beyond.*
*Supports MTN MoMo, Orange Money, USSD offline booking, and Pidgin.*
