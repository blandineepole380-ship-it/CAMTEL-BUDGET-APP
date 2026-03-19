-- ============================================================
-- Kolo-Ride Database Schema
-- PostgreSQL + PostGIS
-- Run once to initialize your database
-- ============================================================

-- Enable geospatial support
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- for gen_random_uuid()

-- ─── USERS (Riders) ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone_number        VARCHAR(20)  UNIQUE NOT NULL,   -- e.g. +2376XXXXXXXX
    full_name           VARCHAR(100),
    preferred_language  VARCHAR(10)  DEFAULT 'fr',      -- 'en', 'fr', 'pidgin'
    total_trips         INT          DEFAULT 0,
    is_blocked          BOOLEAN      DEFAULT FALSE,
    created_at          TIMESTAMPTZ  DEFAULT NOW()
);

-- ─── DRIVERS ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS drivers (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID         REFERENCES users(id) ON DELETE CASCADE,
    cni_number          VARCHAR(30)  UNIQUE NOT NULL,   -- Cameroon National ID
    momo_number         VARCHAR(20)  NOT NULL,          -- Payout account
    vehicle_plate       VARCHAR(20),
    vehicle_type        VARCHAR(30)  DEFAULT 'moto',    -- 'moto', 'car', 'minibus'
    is_verified         BOOLEAN      DEFAULT FALSE,
    is_blocked          BOOLEAN      DEFAULT FALSE,
    rating              DECIMAL(3,2) DEFAULT 5.0,
    total_trips         INT          DEFAULT 0,
    current_location    GEOGRAPHY(Point, 4326),         -- Real-time GPS
    status              VARCHAR(20)  DEFAULT 'offline', -- 'online', 'offline', 'busy'
    last_seen           TIMESTAMPTZ  DEFAULT NOW(),
    city                VARCHAR(50)  DEFAULT 'Buea',
    created_at          TIMESTAMPTZ  DEFAULT NOW()
);

-- ─── TRIPS ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS trips (
    id                  UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    rider_id            UUID         REFERENCES users(id),
    driver_id           UUID         REFERENCES drivers(id),

    -- Locations
    pickup_address      TEXT,
    pickup_coords       GEOGRAPHY(Point, 4326),
    destination_address TEXT,
    destination_coords  GEOGRAPHY(Point, 4326),

    -- Money (XAF)
    fare_amount         INT          NOT NULL,
    driver_payout       INT          GENERATED ALWAYS AS (ROUND(fare_amount * 0.90)) STORED,
    platform_cut        INT          GENERATED ALWAYS AS (ROUND(fare_amount * 0.10)) STORED,

    -- Payment
    payment_method      VARCHAR(20)  DEFAULT 'momo',    -- 'momo', 'orange', 'cash'
    payment_status      VARCHAR(20)  DEFAULT 'pending', -- 'pending', 'paid', 'failed'
    campay_reference    VARCHAR(100),                   -- For DGI tax audit trail

    -- E-Invoicing (required by Loi de Finances 2026)
    invoice_number      SERIAL       UNIQUE,

    -- Ratings
    rider_rating        SMALLINT     CHECK (rider_rating BETWEEN 1 AND 5),
    driver_rating       SMALLINT     CHECK (driver_rating BETWEEN 1 AND 5),

    -- Booking channel
    channel             VARCHAR(20)  DEFAULT 'whatsapp', -- 'whatsapp', 'ussd', 'app'

    -- Status
    status              VARCHAR(20)  DEFAULT 'requested',
    -- 'requested' → 'accepted' → 'ongoing' → 'completed' | 'cancelled'

    created_at          TIMESTAMPTZ  DEFAULT NOW(),
    completed_at        TIMESTAMPTZ
);

-- ─── SESSIONS (WhatsApp conversation state) ───────────────────────────────────
CREATE TABLE IF NOT EXISTS sessions (
    phone               VARCHAR(20)  PRIMARY KEY,
    state               VARCHAR(30)  DEFAULT 'idle',
    data                JSONB        DEFAULT '{}',
    updated_at          TIMESTAMPTZ  DEFAULT NOW()
);

-- ─── PAYOUTS (Driver earnings ledger) ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS payouts (
    id                  UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    driver_id           UUID         REFERENCES drivers(id),
    trip_id             UUID         REFERENCES trips(id),
    amount              INT          NOT NULL,
    momo_number         VARCHAR(20)  NOT NULL,
    campay_reference    VARCHAR(100),
    status              VARCHAR(20)  DEFAULT 'pending',
    created_at          TIMESTAMPTZ  DEFAULT NOW()
);

-- ─── LOCATION ALIASES (dynamic expansion of the alias engine) ────────────────
CREATE TABLE IF NOT EXISTS location_aliases (
    id                  SERIAL       PRIMARY KEY,
    alias_text          VARCHAR(200) UNIQUE NOT NULL,   -- e.g. "carrefour brique"
    latitude            DECIMAL(10,7) NOT NULL,
    longitude           DECIMAL(10,7) NOT NULL,
    city                VARCHAR(50),
    submitted_by        VARCHAR(20),                    -- driver phone who added it
    approved            BOOLEAN      DEFAULT FALSE,
    created_at          TIMESTAMPTZ  DEFAULT NOW()
);

-- ─── INDEXES ─────────────────────────────────────────────────────────────────

-- Find online drivers fast (most frequent query)
CREATE INDEX IF NOT EXISTS idx_drivers_status
    ON drivers(status)
    WHERE status = 'online';

-- Geospatial index for nearest-driver queries
CREATE INDEX IF NOT EXISTS idx_drivers_location
    ON drivers USING GIST(current_location);

-- User lookup by phone
CREATE INDEX IF NOT EXISTS idx_users_phone
    ON users(phone_number);

-- Trip history queries
CREATE INDEX IF NOT EXISTS idx_trips_rider
    ON trips(rider_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_trips_driver
    ON trips(driver_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_trips_status
    ON trips(status);

-- Admin dashboard revenue queries
CREATE INDEX IF NOT EXISTS idx_trips_date
    ON trips(created_at DESC);

-- Session lookup
CREATE INDEX IF NOT EXISTS idx_sessions_updated
    ON sessions(updated_at);

-- ─── AUTO-CLEANUP: Expire old sessions (30 minutes idle) ─────────────────────
CREATE OR REPLACE FUNCTION cleanup_expired_sessions()
RETURNS void AS $$
BEGIN
    DELETE FROM sessions
    WHERE updated_at < NOW() - INTERVAL '30 minutes';
END;
$$ LANGUAGE plpgsql;

-- ─── TRIGGER: Update driver rating after every trip ───────────────────────────
CREATE OR REPLACE FUNCTION update_driver_rating()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE drivers
    SET rating = (
        SELECT ROUND(AVG(rider_rating)::numeric, 2)
        FROM trips
        WHERE driver_id = NEW.driver_id
          AND rider_rating IS NOT NULL
    )
    WHERE id = NEW.driver_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_driver_rating
AFTER UPDATE OF rider_rating ON trips
FOR EACH ROW
WHEN (NEW.rider_rating IS NOT NULL)
EXECUTE FUNCTION update_driver_rating();

-- ─── TRIGGER: Increment trip counters on completion ───────────────────────────
CREATE OR REPLACE FUNCTION increment_trip_counts()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.status = 'completed' AND OLD.status != 'completed' THEN
        UPDATE users   SET total_trips = total_trips + 1 WHERE id = NEW.rider_id;
        UPDATE drivers SET total_trips = total_trips + 1 WHERE id = NEW.driver_id;
        NEW.completed_at = NOW();
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_trip_complete
BEFORE UPDATE OF status ON trips
FOR EACH ROW
EXECUTE FUNCTION increment_trip_counts();

-- ─── SEED DATA: Demo drivers for testing ─────────────────────────────────────
-- (Remove in production or use a migration tool like Alembic)

INSERT INTO users (phone_number, full_name, preferred_language)
VALUES
    ('+237612345001', 'Evariste Nkembe',  'fr'),
    ('+237612345002', 'Carine Tamba',     'fr'),
    ('+237612345003', 'Junior Mbutoh',    'pidgin'),
    ('+237612345004', 'Paul Bekolo',      'fr'),
    ('+237612345005', 'Estelle Fomba',    'en')
ON CONFLICT (phone_number) DO NOTHING;

INSERT INTO drivers (user_id, cni_number, momo_number, vehicle_plate, vehicle_type, is_verified, city)
SELECT
    u.id,
    d.cni,
    d.momo,
    d.plate,
    d.vtype,
    TRUE,
    d.city
FROM (VALUES
    ('+237612345001', 'CM001234567', '+237671111001', 'SW-1234-A', 'car',   'Buea'),
    ('+237612345002', 'CM001234568', '+237671111002', 'LT-5678-B', 'car',   'Buea'),
    ('+237612345003', 'CM001234569', '+237671111003', 'CE-9012-C', 'moto',  'Kribi'),
    ('+237612345004', 'CM001234570', '+237671111004', 'OU-3456-D', 'car',   'Bafoussam'),
    ('+237612345005', 'CM001234571', '+237671111005', 'SW-7890-E', 'car',   'Buea')
) AS d(phone, cni, momo, plate, vtype, city)
JOIN users u ON u.phone_number = d.phone
ON CONFLICT (cni_number) DO NOTHING;

-- ─── ADMIN VIEW: Revenue summary ─────────────────────────────────────────────
CREATE OR REPLACE VIEW admin_revenue_summary AS
SELECT
    DATE(created_at)                    AS date,
    COUNT(*)                            AS total_trips,
    SUM(fare_amount)                    AS gross_revenue,
    SUM(platform_cut)                   AS kolo_ride_revenue,
    SUM(driver_payout)                  AS driver_payouts,
    COUNT(*) FILTER (WHERE channel = 'ussd')      AS ussd_bookings,
    COUNT(*) FILTER (WHERE channel = 'whatsapp')  AS whatsapp_bookings,
    COUNT(*) FILTER (WHERE channel = 'app')       AS app_bookings,
    AVG(rider_rating)                   AS avg_rider_rating
FROM trips
WHERE status = 'completed'
GROUP BY DATE(created_at)
ORDER BY date DESC;

-- ─── ADMIN VIEW: Driver leaderboard ──────────────────────────────────────────
CREATE OR REPLACE VIEW driver_leaderboard AS
SELECT
    u.full_name,
    u.phone_number,
    d.city,
    d.rating,
    d.status,
    d.total_trips,
    d.is_verified,
    COALESCE(SUM(t.driver_payout), 0)  AS lifetime_earnings,
    COALESCE(SUM(t.driver_payout) FILTER (WHERE t.created_at >= CURRENT_DATE), 0) AS today_earnings
FROM drivers d
JOIN users u ON u.id = d.user_id
LEFT JOIN trips t ON t.driver_id = d.id AND t.status = 'completed'
GROUP BY u.full_name, u.phone_number, d.city, d.rating, d.status, d.total_trips, d.is_verified
ORDER BY today_earnings DESC;
