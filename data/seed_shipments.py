"""
Generates a synthetic freight-operations dataset ("the data lake") and
initializes the SQLite database used by both agents.

Domain: global freight forwarding / logistics visibility (GoComet's own
space) -- ocean, air and road shipments across a network of lanes and
carriers, with realistic delay and cost-variance patterns baked in so
analytics questions have real signal to find.

Run: python data/seed_shipments.py
"""
import os
import random
import sqlite3
import sys
from datetime import date, timedelta

random.seed(42)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "db", "freight.db")
SCHEMA_PATH = os.path.join(ROOT, "schema.sql")

CARRIERS = {
    "Ocean": ["Maersk", "MSC", "CMA CGM", "Hapag-Lloyd", "ONE Line"],
    "Air": ["Emirates SkyCargo", "Lufthansa Cargo", "Qatar Airways Cargo"],
    "Road": ["VRL Logistics", "TCI Freight", "Safexpress"],
}

LANES = [
    ("India", "Nhava Sheva", "USA", "Los Angeles", "Ocean"),
    ("India", "Mundra", "Germany", "Hamburg", "Ocean"),
    ("India", "Chennai", "Netherlands", "Rotterdam", "Ocean"),
    ("China", "Shanghai", "India", "Nhava Sheva", "Ocean"),
    ("India", "Nhava Sheva", "UAE", "Jebel Ali", "Ocean"),
    ("India", "Mumbai", "UK", "Felixstowe", "Ocean"),
    ("India", "Bangalore", "USA", "Chicago", "Air"),
    ("India", "Delhi", "Germany", "Frankfurt", "Air"),
    ("India", "Mumbai", "UAE", "Dubai", "Air"),
    ("India", "Chennai", "Singapore", "Singapore", "Air"),
    ("India", "Delhi", "India", "Mumbai", "Road"),
    ("India", "Bangalore", "India", "Chennai", "Road"),
    ("India", "Pune", "India", "Ahmedabad", "Road"),
]

CUSTOMERS = [
    "Orion Apparel Exports", "Nimbus Auto Components", "Sagara Marine Foods",
    "Vertex Pharma Logistics", "Coral Textiles Ltd", "Aster Electronics",
    "Bluepeak Chemicals", "Meridian FMCG Group", "Ferro Industrial Parts",
    "Solstice Consumer Goods",
]

CONTAINER_TYPES = {"Ocean": ["20GP", "40GP", "40HC", "LCL"], "Air": ["Air-ULD"], "Road": ["FTL", "LTL"]}

DELAY_REASONS = ["Customs Hold", "Port Congestion", "Carrier Rollover", "Documentation Issue", "Weather"]

BASE_TRANSIT = {"Ocean": 24, "Air": 4, "Road": 2}
BASE_COST = {"Ocean": 2800, "Air": 6200, "Road": 650}


def make_shipment(i):
    origin_country, origin_port, dest_country, dest_port, mode = random.choice(LANES)
    carrier = random.choice(CARRIERS[mode])
    customer = random.choice(CUSTOMERS)
    container_type = random.choice(CONTAINER_TYPES[mode])

    booking_date = date(2026, 1, 1) + timedelta(days=random.randint(0, 200))
    transit_planned = BASE_TRANSIT[mode] + random.randint(-2, 4)
    etd = booking_date + timedelta(days=random.randint(2, 7))
    eta = etd + timedelta(days=transit_planned)

    # Delay model: ~28% of shipments run late, with a cause
    is_delayed = random.random() < 0.28
    delay_days = 0
    delay_reason = None
    if is_delayed:
        delay_days = random.randint(1, 9)
        delay_reason = random.choice(DELAY_REASONS)

    is_cancelled = random.random() < 0.03
    today = date(2026, 7, 22)

    atd = etd + timedelta(days=random.randint(0, 1))
    ata = eta + timedelta(days=delay_days)

    if is_cancelled:
        status = "Cancelled"
        atd_s = None
        ata_s = None
        transit_actual = None
    elif ata > today:
        status = "Delayed" if delay_days > 0 else "In Transit"
        atd_s = atd.isoformat()
        ata_s = None
        transit_actual = None
    else:
        status = "Delayed" if delay_days > 0 else "Delivered"
        atd_s = atd.isoformat()
        ata_s = ata.isoformat()
        transit_actual = (ata - atd).days

    base = BASE_COST[mode]
    quoted_cost = round(base * random.uniform(0.85, 1.35), 2)
    weight = round(random.uniform(300, 21000), 1) if mode != "Road" else round(random.uniform(2000, 18000), 1)
    volume = round(weight / random.uniform(150, 300), 2)

    return {
        "shipment_id": f"GC-2026-{i:05d}",
        "booking_date": booking_date.isoformat(),
        "customer": customer,
        "carrier": carrier,
        "mode": mode,
        "container_type": container_type,
        "origin_country": origin_country,
        "origin_port": origin_port,
        "destination_country": dest_country,
        "destination_port": dest_port,
        "etd": etd.isoformat(),
        "eta": eta.isoformat(),
        "atd": atd_s,
        "ata": ata_s,
        "transit_days_planned": transit_planned,
        "transit_days_actual": transit_actual,
        "quoted_cost_usd": quoted_cost,
        "weight_kg": weight,
        "volume_cbm": volume,
        "status": status,
        "delay_days": delay_days,
        "delay_reason": delay_reason,
    }


def main(n=320):
    os.makedirs(os.path.join(ROOT, "db"), exist_ok=True)
    fresh = not os.path.exists(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())

    count = conn.execute("SELECT COUNT(*) FROM shipments").fetchone()[0]
    if count > 0:
        print(f"shipments table already has {count} rows -- skipping reseed. "
              f"Delete db/freight.db to regenerate from scratch.")
        conn.close()
        return

    rows = [make_shipment(i) for i in range(1, n + 1)]
    cols = list(rows[0].keys())
    placeholders = ",".join(["?"] * len(cols))
    conn.executemany(
        f"INSERT INTO shipments ({','.join(cols)}) VALUES ({placeholders})",
        [tuple(r[c] for c in cols) for r in rows],
    )
    conn.commit()
    print(f"Seeded {n} shipments into {DB_PATH}")
    conn.close()


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 320
    main(n)
