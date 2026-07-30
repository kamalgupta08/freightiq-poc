"""
Deterministic stand-in for the Anthropic client, used when no
ANTHROPIC_API_KEY is configured. Implements the same
`.messages.create(...)` surface the real SDK exposes, so
analytics_agent.py and document_agent.py do not need to know or care
which one they're talking to.

Two things are mocked:
  1. The Agentic Analytics tool-use loop: given a natural-language
     question, decide whether to call `run_sql`, call
     `ask_clarification`, or (on a second pass, once a tool_result is
     present) summarize the query result in plain English.
  2. The Vision Document Agent's structured extraction tool call --
     returns canned, realistic field values for the four bundled
     sample invoices, and a generic low-confidence stub for anything
     else, so the review/store/query flow can be exercised end-to-end
     without a real vision model.

This is intentionally simple keyword matching, not an attempt to
imitate real language understanding -- it exists purely so the
reviewer can run and click through the entire app with zero setup.
Real natural-language generality only shows up once ANTHROPIC_API_KEY
is set and agents/llm_client.py routes to the real SDK instead.
"""
import json
import re
import uuid


class Block:
    def __init__(self, type_, **kw):
        self.type = type_
        for k, v in kw.items():
            setattr(self, k, v)


class Response:
    def __init__(self, content, stop_reason):
        self.content = content
        self.stop_reason = stop_reason


# ---------------------------------------------------------------------------
# Sample-invoice extraction stubs (see data/generate_sample_invoices.py)
# ---------------------------------------------------------------------------
CANNED_EXTRACTIONS = {
    "MSK-INV-88213": dict(invoice_number="MSK-INV-88213", shipment_reference="GC-2026-00004",
                           carrier="Maersk", invoice_date="2026-07-14", due_date="2026-08-13",
                           currency="USD", freight_charges=3574.10, fuel_surcharge=339.55,
                           customs_duty=142.20, other_charges=114.83, total_amount=4170.68,
                           field_confidence_avg=0.95, low_confidence_fields=[]),
    "MSK-INV-88490": dict(invoice_number="MSK-INV-88490", shipment_reference="GC-2026-00007",
                           carrier="Maersk", invoice_date="2026-07-11", due_date="2026-08-10",
                           currency="USD", freight_charges=2733.29, fuel_surcharge=228.99,
                           customs_duty=63.11, other_charges=57.39, total_amount=3082.78,
                           field_confidence_avg=0.96, low_confidence_fields=[]),
    "ONE-INV-51027": dict(invoice_number="ONE-INV-51027", shipment_reference="GC-2026-00009",
                           carrier="ONE Line", invoice_date="2026-07-18", due_date="2026-08-17",
                           currency="USD", freight_charges=2984.51, fuel_surcharge=268.31,
                           customs_duty=95.02, other_charges=68.40, total_amount=3416.24,
                           field_confidence_avg=0.93, low_confidence_fields=["customs_duty"]),
    "LHC-INV-70915": dict(invoice_number="LHC-INV-70915", shipment_reference="GC-2026-00014",
                           carrier="Lufthansa Cargo", invoice_date="2026-07-20", due_date="2026-08-19",
                           currency="USD", freight_charges=5220.66, fuel_surcharge=522.07,
                           customs_duty=157.55, other_charges=96.76, total_amount=5997.04,
                           field_confidence_avg=0.91, low_confidence_fields=["other_charges"]),
}


def _mock_extract_invoice(user_text):
    m = re.search(r"Filename:\s*([^\n|]+)", user_text)
    stem = None
    if m:
        stem = m.group(1).strip()
        for key in CANNED_EXTRACTIONS:
            if key in stem:
                return CANNED_EXTRACTIONS[key]
    # Unknown document -> honest low-confidence stub, flagged for manual review
    return dict(invoice_number="UNKNOWN", shipment_reference=None, carrier="Unknown",
                invoice_date=None, due_date=None, currency="USD",
                freight_charges=0.0, fuel_surcharge=0.0, customs_duty=0.0, other_charges=0.0,
                total_amount=0.0, field_confidence_avg=0.35,
                low_confidence_fields=["invoice_number", "carrier", "invoice_date", "total_amount"])


# ---------------------------------------------------------------------------
# Part 2: SU trade-document extraction stubs (see data/generate_sample_trade_docs.py)
# ---------------------------------------------------------------------------
CANNED_TRADE_DOC_EXTRACTIONS = {
    "SU_TRADEDOC_GC-2026-00004": dict(
        consignee_name="Meridian FMCG Group", hs_code="1904.10",
        port_of_loading="Nhava Sheva", port_of_discharge="Jebel Ali", incoterm="CIF",
        description_of_goods="Breakfast cereal products, retail-packed cartons",
        weight_kg=14884.6,
        field_confidence={"consignee_name": 0.97, "hs_code": 0.95, "port_of_loading": 0.96,
                           "port_of_discharge": 0.96, "incoterm": 0.98,
                           "description_of_goods": 0.93, "weight_kg": 0.95},
        low_confidence_fields=[],
    ),
    "SU_TRADEDOC_GC-2026-00009": dict(
        consignee_name="Meridian FMC Group Pvt Ltd", hs_code="1904.20",
        port_of_loading="Nhava Sheva", port_of_discharge="Antwerp", incoterm="FOB",
        description_of_goods="Cereal-based snack products, cartons",
        weight_kg=18500.0,
        field_confidence={"consignee_name": 0.94, "hs_code": 0.92, "port_of_loading": 0.95,
                           "port_of_discharge": 0.93, "incoterm": 0.96,
                           "description_of_goods": 0.55, "weight_kg": 0.91},
        low_confidence_fields=["description_of_goods"],
    ),
}


def _mock_extract_trade_doc(user_text):
    m = re.search(r"Filename:\s*([^\n|]+)", user_text)
    if m:
        stem = m.group(1).strip()
        for key in CANNED_TRADE_DOC_EXTRACTIONS:
            if key in stem:
                return CANNED_TRADE_DOC_EXTRACTIONS[key]
    return dict(
        consignee_name="Unknown", hs_code="Unknown", port_of_loading="Unknown",
        port_of_discharge="Unknown", incoterm="Unknown",
        description_of_goods="Unable to read document clearly", weight_kg=0.0,
        field_confidence={"consignee_name": 0.3, "hs_code": 0.3, "port_of_loading": 0.3,
                           "port_of_discharge": 0.3, "incoterm": 0.3,
                           "description_of_goods": 0.3, "weight_kg": 0.3},
        low_confidence_fields=["consignee_name", "hs_code", "port_of_loading",
                                "port_of_discharge", "incoterm", "description_of_goods", "weight_kg"],
    )


def _mock_draft_reply(user_text):
    """No-tools text completion: parse the verification JSON + overall_status
    embedded in the prompt and generate a grounded (not hallucinated) email
    from the actual field results, mirroring what a real model is asked to do."""
    status_m = re.search(r"Overall status:\s*(\w+)", user_text)
    overall_status = status_m.group(1) if status_m else "issues"
    json_m = re.search(r"Verification results \(JSON\):\s*(\[.*?\])\s*\n", user_text, re.DOTALL)
    try:
        field_results = json.loads(json_m.group(1)) if json_m else []
    except Exception:
        field_results = []
    shipment_m = re.search(r"shipment\s+(GC-[\w-]+)", user_text)
    shipment_id = shipment_m.group(1) if shipment_m else "the referenced shipment"

    if overall_status == "clean":
        return (
            f"Hi,\n\nThanks for sending over the documentation for shipment {shipment_id}. "
            f"We've reviewed the Commercial Invoice & Packing List and all fields check out against "
            f"the customer's requirements (consignee, HS code, ports, Incoterm, weight, and goods "
            f"description all match).\n\nThis is cleared to proceed to the customer. No action needed "
            f"on your end.\n\nBest,\nCG Team"
        )

    lines = [f"Hi,\n\nWe've reviewed the documentation for shipment {shipment_id} and found the "
              f"following that needs correcting before we can clear this to the customer:\n"]
    for f in field_results:
        if f.get("status") in ("mismatch", "uncertain"):
            tag = "MISMATCH" if f["status"] == "mismatch" else "NEEDS VERIFICATION"
            lines.append(f"- [{tag}] {f['field']}: found \"{f['found']}\", expected \"{f['expected']}\". {f.get('note', '')}")
    lines.append("\nPlease resend corrected documentation at your earliest convenience so we can "
                  "re-verify and release to the customer.\n\nBest,\nCG Team")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Analytics NL -> SQL rules (mock mode only)
# ---------------------------------------------------------------------------
RULES = [
    (["highest average freight cost", "average freight cost", "avg freight cost"],
     "SELECT carrier, ROUND(AVG(quoted_cost_usd),2) AS avg_quoted_cost_usd, COUNT(*) AS n_shipments "
     "FROM shipments GROUP BY carrier ORDER BY avg_quoted_cost_usd DESC LIMIT 20",
     "Average quoted freight cost grouped by carrier, highest first."),

    (["delay reason", "delayed", "delays"],
     "SELECT delay_reason, COUNT(*) AS n_shipments FROM shipments "
     "WHERE status='Delayed' GROUP BY delay_reason ORDER BY n_shipments DESC LIMIT 20",
     "Count of delayed shipments grouped by delay reason."),

    (["total quoted", "total freight cost", "cost by mode", "cost by transport mode"],
     "SELECT mode, carrier, ROUND(SUM(quoted_cost_usd),2) AS total_quoted_cost_usd, COUNT(*) AS n_shipments "
     "FROM shipments GROUP BY mode, carrier ORDER BY mode, total_quoted_cost_usd DESC LIMIT 30",
     "Total quoted freight cost grouped by transport mode and carrier."),

    (["nhava sheva", "jebel ali"],
     "SELECT shipment_id, carrier, status, delay_days, delay_reason, etd, eta, ata FROM shipments "
     "WHERE origin_port='Nhava Sheva' AND destination_port='Jebel Ali' AND status='Delayed' LIMIT 50",
     "Delayed shipments on the Nhava Sheva -> Jebel Ali lane."),

    (["average transit time", "transit time by carrier", "avg transit"],
     "SELECT carrier, ROUND(AVG(transit_days_actual),1) AS avg_transit_days, COUNT(*) AS n_shipments "
     "FROM shipments WHERE mode='Ocean' AND transit_days_actual IS NOT NULL "
     "GROUP BY carrier ORDER BY avg_transit_days LIMIT 20",
     "Average actual transit days by carrier, ocean shipments only."),

    (["just show maersk and msc", "maersk and msc", "only maersk"],
     "SELECT carrier, ROUND(AVG(transit_days_actual),1) AS avg_transit_days, COUNT(*) AS n_shipments "
     "FROM shipments WHERE mode='Ocean' AND carrier IN ('Maersk','MSC') AND transit_days_actual IS NOT NULL "
     "GROUP BY carrier ORDER BY avg_transit_days LIMIT 20",
     "Same transit-time comparison, filtered to Maersk and MSC only (follow-up refinement)."),

    (["invoiced amount is higher", "invoiced more than quoted", "over quote", "invoice vs quote", "over the quote"],
     "SELECT i.invoice_number, i.shipment_id, s.carrier, s.quoted_cost_usd, i.total_amount, "
     "ROUND(i.total_amount - s.quoted_cost_usd,2) AS variance_usd "
     "FROM invoices i JOIN shipments s ON i.shipment_id = s.shipment_id "
     "WHERE i.total_amount > s.quoted_cost_usd ORDER BY variance_usd DESC LIMIT 50",
     "Stored invoices where the invoiced total exceeds the originally quoted shipment cost."),

    (["total invoiced amount by carrier", "invoiced amount by carrier", "total invoiced"],
     "SELECT carrier, ROUND(SUM(total_amount),2) AS total_invoiced_usd, COUNT(*) AS n_invoices "
     "FROM invoices GROUP BY carrier ORDER BY total_invoiced_usd DESC LIMIT 20",
     "Total invoiced amount grouped by carrier, from stored (reviewed) invoices."),

    (["pending review", "not yet reviewed", "awaiting review"],
     "SELECT invoice_number, shipment_id, carrier, total_amount, low_confidence_fields "
     "FROM invoices WHERE reviewed_by_user=0 LIMIT 50",
     "Invoices stored but not yet confirmed by a human reviewer."),

    (["break that down by carrier", "split by carrier", "by carrier as well"],
     "SELECT mode, carrier, ROUND(SUM(quoted_cost_usd),2) AS total_quoted_cost_usd, COUNT(*) AS n_shipments "
     "FROM shipments GROUP BY mode, carrier ORDER BY mode, total_quoted_cost_usd DESC LIMIT 30",
     "Total quoted cost broken down by mode and carrier (follow-up refinement)."),

    (["discrepanc", "flagged", "amendment", "issues found", "came back with issues"],
     "SELECT verification_id, shipment_id, su_sender, fields_mismatched, fields_uncertain, cg_action "
     "FROM verifications WHERE overall_status='issues' ORDER BY created_at DESC LIMIT 50",
     "Verification runs that came back with discrepancies (amendment required)."),

    (["verification", "su documents", "trade doc"],
     "SELECT verification_id, shipment_id, su_sender, overall_status, fields_mismatched, "
     "fields_uncertain, cg_action FROM verifications ORDER BY created_at DESC LIMIT 50",
     "All SU document verification runs (Part 2), most recent first."),
]

CLARIFY_TRIGGERS = [
    "q3", "quarter", "how's", "how is", "customer satisfaction", "nps", "csat",
    "sentiment", "profit margin", "headcount",
]


def _infer_sql(question):
    q = question.lower()
    for trigger in CLARIFY_TRIGGERS:
        if trigger in q:
            return None
    for keywords, sql, explanation in RULES:
        if any(k in q for k in keywords):
            return sql, explanation
    return None


def _last_user_text(messages):
    for msg in reversed(messages):
        if msg["role"] == "user" and isinstance(msg["content"], str):
            return msg["content"]
        if msg["role"] == "user" and isinstance(msg["content"], list):
            texts = [b.get("text") for b in msg["content"] if isinstance(b, dict) and b.get("type") == "text"]
            if texts:
                return texts[-1]
    return ""


def _find_last_tool_result(messages):
    """Only the VERY LAST message can be a fresh tool_result belonging to
    the current turn. Scanning further back (as an earlier version of this
    function did) finds tool_results from PRIOR questions in the same
    session -- since `messages` accumulates across the whole conversation
    to support follow-up refinement -- and wrongly synthesizes an answer
    from stale data instead of running new SQL for the new question."""
    if not messages:
        return None
    last = messages[-1]
    if last["role"] == "user" and isinstance(last["content"], list):
        for b in last["content"]:
            if isinstance(b, dict) and b.get("type") == "tool_result":
                return b
    return None


class _Messages:
    def create(self, model, system, messages, tools=None, max_tokens=1024, tool_choice=None, **kw):
        tool_names = {t["name"] for t in (tools or [])}

        # --- Vision extraction path -------------------------------------
        if "extract_invoice_fields" in tool_names:
            user_text = _last_user_text(messages)
            fields = _mock_extract_invoice(user_text)
            block = Block(
                "tool_use", id=f"toolu_{uuid.uuid4().hex[:12]}",
                name="extract_invoice_fields", input=fields,
            )
            return Response([block], "tool_use")

        # --- Part 2: trade-document extraction path ----------------------
        if "extract_trade_doc_fields" in tool_names:
            user_text = _last_user_text(messages)
            fields = _mock_extract_trade_doc(user_text)
            block = Block(
                "tool_use", id=f"toolu_{uuid.uuid4().hex[:12]}",
                name="extract_trade_doc_fields", input=fields,
            )
            return Response([block], "tool_use")

        # --- Part 2: plain-text reply drafting (no tools at all) ---------
        if not tools:
            user_text = _last_user_text(messages)
            text = _mock_draft_reply(user_text)
            return Response([Block("text", text=text)], "end_turn")

        # --- Analytics path ----------------------------------------------
        last_tool_result = _find_last_tool_result(messages)
        if last_tool_result is not None:
            # Second pass: synthesize a grounded final answer from the
            # actual tool result content (never invent numbers).
            try:
                payload = json.loads(last_tool_result["content"])
            except Exception:
                payload = {}
            text = _summarize_result(payload)
            return Response([Block("text", text=text)], "end_turn")

        question = _last_user_text(messages)
        inferred = _infer_sql(question)
        if inferred is None:
            clar_block = Block(
                "tool_use", id=f"toolu_{uuid.uuid4().hex[:12]}",
                name="ask_clarification",
                input={"question": (
                    "I can't map that to a field in the freight database (shipments/invoices). "
                    "Could you rephrase using a concrete metric or dimension -- e.g. cost, "
                    "transit time, delay reason, carrier, or invoice status?"
                )},
            )
            return Response([clar_block], "tool_use")

        sql, explanation = inferred
        sql_block = Block(
            "tool_use", id=f"toolu_{uuid.uuid4().hex[:12]}",
            name="run_sql", input={"sql": sql, "explanation": explanation},
        )
        return Response([sql_block], "tool_use")


def _summarize_result(payload):
    if payload.get("error"):
        return f"The query could not be run safely: {payload['error']}. Please rephrase the question."
    columns = payload.get("columns", [])
    rows = payload.get("rows", [])
    row_count = payload.get("row_count", len(rows))
    if row_count == 0:
        return ("No rows in the freight database match this question. I'm not going to guess -- "
                "try a broader time window, a different carrier, or check the field name.")
    preview = rows[:5]
    lines = [", ".join(f"{c}={v}" for c, v in zip(columns, r)) for r in preview]
    more = f" (+{row_count - len(preview)} more rows in the table below)" if row_count > len(preview) else ""
    return (
        f"Based on {row_count} matching row(s) from the freight database:\n"
        + "\n".join(f"- {line}" for line in lines) + more +
        "\n\nThis answer is grounded strictly in the query result shown above (see the SQL used for full transparency)."
    )


class MockClient:
    def __init__(self):
        self.messages = _Messages()
