"""
Vision Document Agent.

Flow: Upload (PDF or image) -> render to image(s) -> vision-model
extraction into a strict structured schema (forced via tool_choice,
not free-text parsing) -> user reviews/edits in the UI -> on confirm,
write to the `invoices` table via a parameterized insert (no free-form
SQL here -- this path never lets the model write anything itself).

Extraction uncertainty is a first-class citizen: the model must report
a confidence score and flag any field it is not confident about, and
the UI will not let those rows enter the analytics layer un-reviewed.
"""
import base64
import io
import json
import sqlite3
import uuid
from datetime import datetime, timezone

import fitz  # PyMuPDF
from PIL import Image

from agents.llm_client import get_client, MODEL

EXTRACTION_TOOL = {
    "name": "extract_invoice_fields",
    "description": "Report the structured fields extracted from a freight invoice image.",
    "input_schema": {
        "type": "object",
        "properties": {
            "invoice_number": {"type": "string"},
            "shipment_reference": {"type": ["string", "null"],
                                    "description": "The shipment/booking reference printed on the "
                                                    "invoice, if present, e.g. 'GC-2026-00004'."},
            "carrier": {"type": "string"},
            "invoice_date": {"type": ["string", "null"], "description": "YYYY-MM-DD if determinable."},
            "due_date": {"type": ["string", "null"], "description": "YYYY-MM-DD if determinable."},
            "currency": {"type": "string"},
            "freight_charges": {"type": "number"},
            "fuel_surcharge": {"type": "number"},
            "customs_duty": {"type": "number"},
            "other_charges": {"type": "number"},
            "total_amount": {"type": "number"},
            "field_confidence_avg": {"type": "number",
                                      "description": "Your average confidence (0-1) across all "
                                                      "extracted fields."},
            "low_confidence_fields": {"type": "array", "items": {"type": "string"},
                                       "description": "Names of fields you are NOT confident about "
                                                       "(e.g. blurry, occluded, ambiguous format). "
                                                       "Empty list if none."},
        },
        "required": ["invoice_number", "carrier", "currency", "total_amount",
                      "field_confidence_avg", "low_confidence_fields"],
    },
}

SYSTEM_PROMPT = """You are the Vision Document Agent for FreightIQ, a freight/logistics
operations product. You are shown an image of a freight invoice (it may be a photo or a
scanned/rendered PDF page). Extract the fields exactly as printed. Do not invent values you
cannot see. If a field is missing, unreadable, or ambiguous, still return your best-guess
value AND add that field's name to low_confidence_fields -- never silently guess with high
confidence. Numbers should be plain floats (no currency symbols or thousands separators)."""


def render_to_images(file_bytes: bytes, filename: str, max_pages=2):
    """Returns a list of PNG bytes -- one per page (PDFs) or a single entry (images)."""
    lower = filename.lower()
    images = []
    if lower.endswith(".pdf"):
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        for page in doc[:max_pages]:
            pix = page.get_pixmap(dpi=150)
            images.append(pix.tobytes("png"))
        doc.close()
    else:
        img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        images.append(buf.getvalue())
    return images


def extract_invoice(file_bytes: bytes, filename: str):
    """Returns (fields_dict, is_mock: bool, error_or_None)."""
    client, is_mock = get_client()
    try:
        images = render_to_images(file_bytes, filename)
    except Exception as e:
        return None, is_mock, f"Could not read this file as a PDF or image: {e}"

    content = [{"type": "text",
                "text": f"Extract the freight invoice fields from the attached page(s). "
                        f"Filename: {filename}"}]
    for png_bytes in images:
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png",
                       "data": base64.b64encode(png_bytes).decode("ascii")},
        })

    try:
        resp = client.messages.create(
            model=MODEL, system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
            tools=[EXTRACTION_TOOL],
            tool_choice={"type": "tool", "name": "extract_invoice_fields"},
            max_tokens=1024,
        )
    except Exception as e:
        return None, is_mock, f"Vision model call failed: {e}"

    tool_use = next((b for b in resp.content if b.type == "tool_use"), None)
    if tool_use is None:
        return None, is_mock, "Model did not return structured extraction output."

    return tool_use.input, is_mock, None


def store_invoice(db_path: str, fields: dict, source_filename: str) -> str:
    """Parameterized insert only -- the document agent never executes free-form SQL."""
    invoice_id = f"INV-{uuid.uuid4().hex[:10]}"
    conn = sqlite3.connect(db_path, timeout=5)
    conn.execute(
        """INSERT INTO invoices (
            invoice_id, invoice_number, shipment_id, carrier, invoice_date, due_date, currency,
            freight_charges, fuel_surcharge, customs_duty, other_charges, total_amount,
            extraction_confidence, low_confidence_fields, source_filename, extracted_at,
            reviewed_by_user
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            invoice_id,
            fields.get("invoice_number"),
            fields.get("shipment_reference"),
            fields.get("carrier"),
            fields.get("invoice_date"),
            fields.get("due_date"),
            fields.get("currency"),
            fields.get("freight_charges", 0.0),
            fields.get("fuel_surcharge", 0.0),
            fields.get("customs_duty", 0.0),
            fields.get("other_charges", 0.0),
            fields.get("total_amount", 0.0),
            fields.get("field_confidence_avg"),
            ",".join(fields.get("low_confidence_fields") or []),
            source_filename,
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            1,  # only reachable after the UI's human-review confirm step
        ),
    )
    conn.commit()
    conn.close()
    return invoice_id
