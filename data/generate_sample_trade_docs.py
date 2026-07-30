"""
Generates two sample SU (Shipping Unit) trade documents -- Commercial
Invoice & Packing List style PDFs -- used by Part 2's verification agent.

Both reference real shipments already in db/freight.db (see
data/seed_shipments.py), so the verification agent's "compare against
customer requirements" step can pull expected port/weight straight from
the Part 1 booking data, not just a hardcoded rule set.

  - MSK-INV-88213-style shipment GC-2026-00004 -> clean doc, everything matches
  - ONE-INV-51027-style shipment GC-2026-00009 -> doc with deliberate
    discrepancies (wrong consignee legal name, wrong Incoterm, wrong port
    of discharge, weight outside tolerance, one low-confidence field)

Run: python data/generate_sample_trade_docs.py
"""
import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "data", "sample_su_docs")

DOCS = [
    dict(
        filename="SU_TRADEDOC_GC-2026-00004.pdf",
        shipment_id="GC-2026-00004",
        su_name="Meridian Exports Operations Desk",
        consignee_name="Meridian FMCG Group",
        hs_code="1904.10",
        port_of_loading="Nhava Sheva",
        port_of_discharge="Jebel Ali",
        incoterm="CIF",
        description_of_goods="Breakfast cereal products, retail-packed cartons",
        weight_kg="14,884.6",
    ),
    dict(
        filename="SU_TRADEDOC_GC-2026-00009.pdf",
        shipment_id="GC-2026-00009",
        su_name="Meridian Exports Operations Desk",
        consignee_name="Meridian FMC Group Pvt Ltd",       # wrong legal entity name
        hs_code="1904.20",
        port_of_loading="Nhava Sheva",
        port_of_discharge="Antwerp",                        # wrong -- should be Rotterdam
        incoterm="FOB",                                      # wrong -- customer requires CIF
        description_of_goods="Cereal-based snack products, cartons (scan partially smudged)",
        weight_kg="18,500.0",                                 # wrong -- should be ~20,919.7
    ),
]


def build_doc(d):
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("title", parent=styles["Heading1"], fontSize=15, spaceAfter=2)
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=8.5, textColor=colors.grey)
    normal = styles["Normal"]

    fname = os.path.join(OUT_DIR, d["filename"])
    doc = SimpleDocTemplate(fname, pagesize=A4, topMargin=18 * mm, bottomMargin=18 * mm)
    story = []

    story.append(Paragraph(d["su_name"], title_style))
    story.append(Paragraph("Shipping Unit -- Export Documentation Desk", small))
    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph("COMMERCIAL INVOICE &amp; PACKING LIST", ParagraphStyle("h2", parent=styles["Heading2"])))
    story.append(Spacer(1, 4 * mm))

    meta = [
        ["Shipment Reference:", d["shipment_id"], "Port of Loading:", d["port_of_loading"]],
        ["Consignee:", d["consignee_name"], "Port of Discharge:", d["port_of_discharge"]],
        ["Incoterm:", d["incoterm"], "HS Code:", d["hs_code"]],
    ]
    meta_table = Table(meta, colWidths=[34 * mm, 55 * mm, 32 * mm, 39 * mm])
    meta_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 8 * mm))

    goods = [
        ["Description of Goods", "Weight (kg)"],
        [d["description_of_goods"], d["weight_kg"]],
    ]
    goods_table = Table(goods, colWidths=[110 * mm, 40 * mm])
    goods_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3864")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(goods_table)
    story.append(Spacer(1, 10 * mm))
    story.append(Paragraph(
        "We confirm the above particulars are true and correct to the best of our knowledge. "
        "Please process for onward clearance to the consignee.", normal))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("System-generated sample document for demo/testing purposes only.", small))

    doc.build(story)
    return fname


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for d in DOCS:
        fname = build_doc(d)
        print(f"Generated {fname}")


if __name__ == "__main__":
    main()
