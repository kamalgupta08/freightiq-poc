"""
Part 2 -- Agentic Document Verification (the SU -> CG -> Customer loop).

This is deliberately NOT a new app. It reuses:
  - the same vision-extraction pattern from Part 1's document_agent.py
    (forced structured tool call, per-field confidence)
  - the same llm_client.get_client() provider switch (mock vs live)
  - the same freight.db and the same SQL guardrails, via the new
    `verifications` table added to schema.sql

What's new is the one thing Part 1 didn't have: a *rule set* to check
extracted fields against, and a *drafted reply* a human (CG) reviews and
sends -- the agent never sends anything itself.

Pipeline: trigger (mock inbox) -> extract (vision tool call) -> compare
(against booking data in `shipments` + a per-customer rule profile) ->
flag (match/mismatch/uncertain, never silently approving low-confidence
fields) -> draft (approval or amendment email) -> CG reviews/edits/sends
-> store (queryable via the Part 1 analytics agent).
"""
import base64
import json
import sqlite3
import uuid
from datetime import datetime, timezone

from agents.llm_client import get_client, MODEL
from agents.document_agent import render_to_images

# ---------------------------------------------------------------------------
# Mock inbox -- "watch a folder / simulate an inbox" per the assignment.
# Both documents are bundled in data/sample_su_docs/.
# ---------------------------------------------------------------------------
MOCK_INBOX = [
    {
        "email_id": "EML-1001",
        "from": "ops@meridian-exports-du.com",
        "from_name": "Meridian Exports Operations Desk (SU)",
        "subject": "Shipment Docs -- GC-2026-00004 -- Commercial Invoice & Packing List",
        "body": "Hi CG team, please find attached the commercial invoice and packing list "
                "for shipment GC-2026-00004. Kindly confirm and release to the customer.",
        "shipment_id": "GC-2026-00004",
        "attachment": "SU_TRADEDOC_GC-2026-00004.pdf",
        "received_at": "2026-07-29 09:14",
    },
    {
        "email_id": "EML-1002",
        "from": "ops@meridian-exports-du.com",
        "from_name": "Meridian Exports Operations Desk (SU)",
        "subject": "Shipment Docs -- GC-2026-00009 -- Commercial Invoice & Packing List",
        "body": "Hi CG team, attached are the docs for GC-2026-00009. Please process at your "
                "earliest as the customer is expecting this shipment soon.",
        "shipment_id": "GC-2026-00009",
        "attachment": "SU_TRADEDOC_GC-2026-00009.pdf",
        "received_at": "2026-07-29 11:02",
    },
]

# ---------------------------------------------------------------------------
# One customer, one rule set -- per the assignment's explicit scope.
# Fields with a DB counterpart (port_of_discharge, weight_kg) are checked
# against the actual Part 1 booking in `shipments`, not hardcoded here --
# that's the point: the booking IS the requirement for those fields.
# ---------------------------------------------------------------------------
CUSTOMER_RULES = {
    "Meridian FMCG Group": {
        "consignee_name": {"expected": "Meridian FMCG Group", "type": "exact"},
        "hs_code": {"expected": "1904", "type": "prefix",
                    "note": "Meridian's FMCG food-prep commodities must fall under HS heading 1904."},
        "port_of_loading": {"expected": "Nhava Sheva", "type": "exact"},
        "incoterm": {"expected": "CIF", "type": "exact",
                     "note": "Meridian's standing contract requires CIF terms on all shipments."},
        "description_of_goods": {"expected": "cereal", "type": "contains_ci"},
    }
}
WEIGHT_TOLERANCE_PCT = 3.0
LOW_CONFIDENCE_THRESHOLD = 0.7

EXTRACTION_TOOL = {
    "name": "extract_trade_doc_fields",
    "description": "Report the structured fields extracted from an SU trade document "
                    "(commercial invoice / packing list image).",
    "input_schema": {
        "type": "object",
        "properties": {
            "consignee_name": {"type": "string"},
            "hs_code": {"type": "string"},
            "port_of_loading": {"type": "string"},
            "port_of_discharge": {"type": "string"},
            "incoterm": {"type": "string"},
            "description_of_goods": {"type": "string"},
            "weight_kg": {"type": "number"},
            "field_confidence": {
                "type": "object",
                "description": "Confidence (0-1) for each of the 7 fields above, keyed by field name.",
            },
            "low_confidence_fields": {"type": "array", "items": {"type": "string"},
                                       "description": "Fields you are not confident about. Empty if none."},
        },
        "required": ["consignee_name", "hs_code", "port_of_loading", "port_of_discharge",
                     "incoterm", "description_of_goods", "weight_kg",
                     "field_confidence", "low_confidence_fields"],
    },
}

EXTRACTION_SYSTEM_PROMPT = """You are the extraction step of an Agentic Document Verification
system for a freight company. You are shown an image of a trade document (commercial invoice /
packing list) submitted by a Shipping Unit (SU). Extract the fields exactly as printed. If a
field is blurry, ambiguous, or you are not fully sure of the exact value, still return your best
reading AND add that field's name to low_confidence_fields with a lower confidence score --
never silently mark something as high-confidence just because a value is present."""


def extract_trade_doc(file_bytes: bytes, filename: str):
    """Returns (fields_dict, is_mock: bool, error_or_None)."""
    client, is_mock = get_client()
    try:
        images = render_to_images(file_bytes, filename)
    except Exception as e:
        return None, is_mock, f"Could not read this file as a PDF or image: {e}"

    content = [{"type": "text",
                "text": f"Extract the trade document fields from the attached page(s). "
                        f"Filename: {filename}"}]
    for png_bytes in images:
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png",
                       "data": base64.b64encode(png_bytes).decode("ascii")},
        })

    try:
        resp = client.messages.create(
            model=MODEL, system=EXTRACTION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
            tools=[EXTRACTION_TOOL],
            tool_choice={"type": "tool", "name": "extract_trade_doc_fields"},
            max_tokens=1024,
        )
    except Exception as e:
        return None, is_mock, f"Vision model call failed: {e}"

    tool_use = next((b for b in resp.content if b.type == "tool_use"), None)
    if tool_use is None:
        return None, is_mock, "Model did not return structured extraction output."
    return tool_use.input, is_mock, None


def _numeric_close(found, expected, tolerance_pct):
    try:
        found_f = float(str(found).replace(",", ""))
        expected_f = float(expected)
        if expected_f == 0:
            return found_f == 0
        return abs(found_f - expected_f) / abs(expected_f) * 100 <= tolerance_pct
    except (TypeError, ValueError):
        return False


def compare_fields(extracted: dict, shipment_row: dict, customer_rules: dict):
    """Field-by-field comparison. Returns a list of dicts:
    {field, found, expected, status ('match'|'mismatch'|'uncertain'), confidence, note}

    Confidence gates everything: a field the model wasn't confident about is
    ALWAYS surfaced as 'uncertain', even if the extracted text happens to
    match -- per the assignment: "it does not silently approve uncertain
    fields."
    """
    confidences = extracted.get("field_confidence", {}) or {}
    low_conf = set(extracted.get("low_confidence_fields", []) or [])
    results = []

    def add(field, found, expected, note_ok="", note_bad=""):
        conf = confidences.get(field, 1.0)
        if field in low_conf or conf < LOW_CONFIDENCE_THRESHOLD:
            results.append({"field": field, "found": found, "expected": expected,
                             "status": "uncertain", "confidence": conf,
                             "note": "Low extraction confidence -- verify against the original document manually."})
            return
        results.append({"field": field, "found": found, "expected": expected,
                         "status": "match" if True else "mismatch",  # placeholder, overwritten below
                         "confidence": conf, "note": ""})

    # 1) Fields checked against the customer rule profile
    rule = customer_rules.get(shipment_row["customer"], {})
    for field, spec in rule.items():
        found = extracted.get(field, "")
        expected = spec["expected"]
        conf = confidences.get(field, 1.0)
        if field in low_conf or conf < LOW_CONFIDENCE_THRESHOLD:
            status, note = "uncertain", "Low extraction confidence -- verify against the original document manually."
        elif spec["type"] == "exact":
            status = "match" if str(found).strip().lower() == str(expected).strip().lower() else "mismatch"
            note = spec.get("note", "") if status == "match" else \
                f"Customer requires exactly '{expected}'. {spec.get('note', '')}".strip()
        elif spec["type"] == "prefix":
            status = "match" if str(found).strip().startswith(str(expected)) else "mismatch"
            note = spec.get("note", "") if status == "match" else \
                f"Customer requires HS heading starting with '{expected}'. {spec.get('note', '')}".strip()
        elif spec["type"] == "contains_ci":
            status = "match" if str(expected).lower() in str(found).lower() else "mismatch"
            note = "" if status == "match" else f"Expected goods description to reference '{expected}'."
        else:
            status, note = "uncertain", "Unrecognized rule type."
        results.append({"field": field, "found": found, "expected": expected,
                         "status": status, "confidence": conf, "note": note})

    # 2) Fields checked against the actual Part 1 booking (shipments table)
    #    -- this is the linkage: the booking IS the requirement.
    found_port = extracted.get("port_of_discharge", "")
    expected_port = shipment_row["destination_port"]
    conf = confidences.get("port_of_discharge", 1.0)
    if "port_of_discharge" in low_conf or conf < LOW_CONFIDENCE_THRESHOLD:
        status, note = "uncertain", "Low extraction confidence -- verify against the original document manually."
    else:
        status = "match" if found_port.strip().lower() == expected_port.strip().lower() else "mismatch"
        note = "" if status == "match" else \
            f"This shipment was booked for delivery to {expected_port}, per the original booking."
    results.append({"field": "port_of_discharge", "found": found_port, "expected": expected_port,
                     "status": status, "confidence": conf, "note": note})

    found_weight = extracted.get("weight_kg", 0)
    expected_weight = shipment_row["weight_kg"]
    conf = confidences.get("weight_kg", 1.0)
    if "weight_kg" in low_conf or conf < LOW_CONFIDENCE_THRESHOLD:
        status, note = "uncertain", "Low extraction confidence -- verify against the original document manually."
    else:
        status = "match" if _numeric_close(found_weight, expected_weight, WEIGHT_TOLERANCE_PCT) else "mismatch"
        note = "" if status == "match" else \
            f"Booked weight was {expected_weight:,.1f} kg (±{WEIGHT_TOLERANCE_PCT:.0f}% tolerance)."
    results.append({"field": "weight_kg", "found": found_weight, "expected": f"{expected_weight:,.1f}",
                     "status": status, "confidence": conf, "note": note})

    return results


DRAFT_SYSTEM_PROMPT = """You are the drafting step of an Agentic Document Verification system.
You write the reply email from CG (Cargo/Control Group) back to the SU (Shipping Unit) who
submitted a trade document. You NEVER send the email yourself -- you only draft it for a human
to review and send. If the verification was clean, write a short approval. If there are
mismatches or uncertain fields, write a specific, professional amendment request listing each
one with what was found and what was expected. Do not sign off with a name, just end naturally."""


def draft_reply_email(shipment_id: str, su_sender: str, field_results: list, overall_status: str):
    client, is_mock = get_client()
    prompt = (
        f"Draft a reply email from CG to SU ({su_sender}) regarding shipment {shipment_id}.\n"
        f"Overall status: {overall_status}\n"
        f"Verification results (JSON): {json.dumps(field_results, default=str)}\n"
    )
    try:
        resp = client.messages.create(
            model=MODEL, system=DRAFT_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=600,
        )
    except Exception as e:
        return f"[Draft generation failed: {e}]", is_mock
    text = "".join(b.text for b in resp.content if b.type == "text")
    return text, is_mock


def store_verification(db_path: str, shipment_id: str, su_sender: str, email_subject: str,
                        document_filename: str, field_results: list, draft_email: str):
    overall_status = "issues" if any(f["status"] != "match" for f in field_results) else "clean"
    matched = sum(1 for f in field_results if f["status"] == "match")
    mismatched = sum(1 for f in field_results if f["status"] == "mismatch")
    uncertain = sum(1 for f in field_results if f["status"] == "uncertain")

    verification_id = f"VRF-{uuid.uuid4().hex[:10]}"
    conn = sqlite3.connect(db_path, timeout=5)
    conn.execute(
        """INSERT INTO verifications (
            verification_id, shipment_id, su_sender, email_subject, document_filename,
            overall_status, fields_checked, fields_matched, fields_mismatched, fields_uncertain,
            field_results_json, draft_email, final_email, cg_action, created_at, sent_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            verification_id, shipment_id, su_sender, email_subject, document_filename,
            overall_status, len(field_results), matched, mismatched, uncertain,
            json.dumps(field_results, default=str), draft_email, None, "pending",
            datetime.now(timezone.utc).isoformat(timespec="seconds"), None,
        ),
    )
    conn.commit()
    conn.close()
    return verification_id, overall_status


def mark_sent(db_path: str, verification_id: str, final_email: str):
    conn = sqlite3.connect(db_path, timeout=5)
    conn.execute(
        "UPDATE verifications SET final_email=?, cg_action='sent', sent_at=? WHERE verification_id=?",
        (final_email, datetime.now(timezone.utc).isoformat(timespec="seconds"), verification_id),
    )
    conn.commit()
    conn.close()


def get_shipment_row(db_path: str, shipment_id: str):
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM shipments WHERE shipment_id=?", (shipment_id,)).fetchone()
    conn.close()
    return dict(row) if row else None
