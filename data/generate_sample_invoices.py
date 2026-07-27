"""
Generates realistic-looking freight invoice PDFs for demo purposes.
These are the sample documents fed into the Vision Document Agent.

Each invoice deliberately has a total that differs from the shipment's
quoted_cost_usd in the shipments table -- so the end-to-end analytics
question "how much are we over/under quote on invoiced freight cost"
has real signal once the invoice is extracted and stored.

Run: python data/generate_sample_invoices.py
"""
import os
import random
from datetime import date, timedelta

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

random.seed(7)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "data", "sample_invoices")

INVOICES = [
    dict(shipment_id="GC-2026-00004", carrier="Maersk", customer="Meridian FMCG Group",
         quoted=3188.29, invoice_no="MSK-INV-88213"),
    dict(shipment_id="GC-2026-00007", carrier="Maersk", customer="Aster Electronics",
         quoted=2677.68, invoice_no="MSK-INV-88490"),
    dict(shipment_id="GC-2026-00009", carrier="ONE Line", customer="Meridian FMCG Group",
         quoted=2914.27, invoice_no="ONE-INV-51027"),
    dict(shipment_id="GC-2026-00014", carrier="Lufthansa Cargo", customer="Nimbus Auto Components",
         quoted=5490.08, invoice_no="LHC-INV-70915"),
]

CARRIER_ADDR = {
    "Maersk": ("Maersk Line A/S", "Esplanaden 50, 1098 Copenhagen K, Denmark"),
    "ONE Line": ("Ocean Network Express Pte. Ltd.", "7 Straits View, Marina One East Tower, Singapore"),
    "Lufthansa Cargo": ("Lufthansa Cargo AG", "Frankfurt Airport Center, 60546 Frankfurt, Germany"),
}


def build_invoice(inv):
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("title", parent=styles["Heading1"], fontSize=16, spaceAfter=2)
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=8.5, textColor=colors.grey)
    normal = styles["Normal"]

    carrier_name, carrier_addr = CARRIER_ADDR[inv["carrier"]]
    invoice_date = date(2026, 7, random.randint(10, 20))
    due_date = invoice_date + timedelta(days=30)

    freight = round(inv["quoted"] * random.uniform(0.95, 1.18), 2)
    fuel = round(freight * random.uniform(0.06, 0.11), 2)
    customs = round(random.uniform(40, 180), 2)
    other = round(random.uniform(25, 120), 2)
    total = round(freight + fuel + customs + other, 2)

    fname = os.path.join(OUT_DIR, f"{inv['invoice_no']}.pdf")
    doc = SimpleDocTemplate(fname, pagesize=A4, topMargin=20 * mm, bottomMargin=20 * mm)
    story = []

    story.append(Paragraph(carrier_name, title_style))
    story.append(Paragraph(carrier_addr, small))
    story.append(Spacer(1, 10 * mm))
    story.append(Paragraph("FREIGHT INVOICE", ParagraphStyle("h2", parent=styles["Heading2"])))
    story.append(Spacer(1, 4 * mm))

    meta = [
        ["Invoice Number:", inv["invoice_no"], "Invoice Date:", invoice_date.isoformat()],
        ["Shipment Reference:", inv["shipment_id"], "Due Date:", due_date.isoformat()],
        ["Bill To:", inv["customer"], "Currency:", "USD"],
    ]
    meta_table = Table(meta, colWidths=[38 * mm, 48 * mm, 30 * mm, 34 * mm])
    meta_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 8 * mm))

    charges = [
        ["Charge Description", "Amount (USD)"],
        ["Ocean/Air Freight Charges", f"{freight:,.2f}"],
        ["Fuel / BAF Surcharge", f"{fuel:,.2f}"],
        ["Customs Clearance Fee", f"{customs:,.2f}"],
        ["Documentation & Handling", f"{other:,.2f}"],
        ["TOTAL DUE", f"{total:,.2f}"],
    ]
    charge_table = Table(charges, colWidths=[110 * mm, 40 * mm])
    charge_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3864")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("LINEABOVE", (0, -1), (-1, -1), 1, colors.black),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(charge_table)
    story.append(Spacer(1, 10 * mm))
    story.append(Paragraph(
        f"Please remit payment to {carrier_name} referencing invoice number {inv['invoice_no']}. "
        f"Queries regarding this invoice should quote shipment reference {inv['shipment_id']}.",
        normal))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("This is a system-generated invoice for demo/testing purposes only.", small))

    doc.build(story)
    return fname, dict(inv, invoice_date=invoice_date.isoformat(), due_date=due_date.isoformat(),
                        freight=freight, fuel=fuel, customs=customs, other=other, total=total)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    results = []
    for inv in INVOICES:
        fname, meta = build_invoice(inv)
        results.append((fname, meta))
        print(f"Generated {fname}  (total ${meta['total']:,.2f}, quoted ${inv['quoted']:,.2f})")
    return results


if __name__ == "__main__":
    main()
