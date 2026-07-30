-- FreightIQ data model
-- Two tables: structured shipment operations data (the "data lake"),
-- and invoices, which is populated ONLY by the Vision Document Agent
-- after a human reviews the extraction. This is the join point between
-- Part A (Agentic Analytics) and Part B (Vision Document Agent).

CREATE TABLE IF NOT EXISTS shipments (
    shipment_id           TEXT PRIMARY KEY,
    booking_date          TEXT NOT NULL,
    customer              TEXT NOT NULL,
    carrier               TEXT NOT NULL,
    mode                  TEXT NOT NULL CHECK (mode IN ('Ocean','Air','Road')),
    container_type        TEXT,
    origin_country        TEXT NOT NULL,
    origin_port           TEXT NOT NULL,
    destination_country   TEXT NOT NULL,
    destination_port      TEXT NOT NULL,
    etd                   TEXT,
    eta                   TEXT,
    atd                   TEXT,
    ata                   TEXT,
    transit_days_planned  INTEGER,
    transit_days_actual   INTEGER,
    quoted_cost_usd       REAL NOT NULL,
    weight_kg             REAL,
    volume_cbm            REAL,
    status                TEXT NOT NULL CHECK (status IN ('Delivered','In Transit','Delayed','Cancelled')),
    delay_days            INTEGER DEFAULT 0,
    delay_reason          TEXT
);

-- Populated exclusively via the Vision Document Agent's "store" step.
CREATE TABLE IF NOT EXISTS invoices (
    invoice_id              TEXT PRIMARY KEY,
    invoice_number          TEXT,
    shipment_id             TEXT REFERENCES shipments(shipment_id),
    carrier                 TEXT,
    invoice_date            TEXT,
    due_date                TEXT,
    currency                TEXT,
    freight_charges         REAL,
    fuel_surcharge          REAL,
    customs_duty            REAL,
    other_charges           REAL,
    total_amount            REAL,
    extraction_confidence   REAL,       -- 0-1, model self-reported, averaged across fields
    low_confidence_fields   TEXT,       -- comma-separated field names flagged for review
    source_filename         TEXT,
    extracted_at             TEXT,
    reviewed_by_user        INTEGER DEFAULT 0  -- 1 once a human has confirmed/edited the extraction
);

CREATE INDEX IF NOT EXISTS idx_invoices_shipment ON invoices(shipment_id);
CREATE INDEX IF NOT EXISTS idx_shipments_carrier ON shipments(carrier);
CREATE INDEX IF NOT EXISTS idx_shipments_status ON shipments(status);

-- Part 2: Agentic Document Verification (SU -> CG -> Customer workflow).
-- One row per trade-document verification run. Queryable from the same
-- Agentic Analytics layer used in Part 1 -- this is the "end-to-end
-- linkage" requirement applied to a second document type.
CREATE TABLE IF NOT EXISTS verifications (
    verification_id     TEXT PRIMARY KEY,
    shipment_id          TEXT REFERENCES shipments(shipment_id),
    su_sender            TEXT,        -- Shipping Unit contact who sent the doc
    email_subject        TEXT,
    document_filename    TEXT,
    overall_status       TEXT CHECK (overall_status IN ('clean','issues')),
    fields_checked        INTEGER,
    fields_matched        INTEGER,
    fields_mismatched     INTEGER,
    fields_uncertain      INTEGER,
    field_results_json    TEXT,       -- full field-by-field detail (found/expected/status/confidence)
    draft_email           TEXT,       -- agent-generated reply, before CG edits
    final_email           TEXT,       -- what CG actually sent (nullable until sent)
    cg_action             TEXT DEFAULT 'pending' CHECK (cg_action IN ('pending','sent')),
    created_at            TEXT,
    sent_at               TEXT
);

CREATE INDEX IF NOT EXISTS idx_verifications_shipment ON verifications(shipment_id);
