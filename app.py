"""
FreightIQ -- Agentic Analytics + Vision Document Intelligence
Streamlit POC for GoComet Agentic AI PM assignment, Part 1.

Run: streamlit run app.py
"""
import os
import sqlite3
import sys
from datetime import datetime

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents.llm_client import get_client, MODEL
from agents.analytics_agent import run_agentic_query
from agents.document_agent import extract_invoice, store_invoice, render_to_images

ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(ROOT, "db", "freight.db")
SAMPLE_DIR = os.path.join(ROOT, "data", "sample_invoices")

st.set_page_config(page_title="FreightIQ | Agentic Freight Intelligence", page_icon="🚢", layout="wide")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def db_stats():
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    n_ship = conn.execute("SELECT COUNT(*) FROM shipments").fetchone()[0]
    n_inv = conn.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
    conn.close()
    return n_ship, n_inv


def looks_like_date_col(name):
    return any(k in name.lower() for k in ["date", "month", "day", "etd", "eta", "atd", "ata"])


def maybe_chart(columns, rows):
    if not rows or len(columns) < 2:
        return None
    df = pd.DataFrame(rows, columns=columns)
    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    non_numeric_cols = [c for c in df.columns if c not in numeric_cols]
    if not numeric_cols or not non_numeric_cols:
        return None
    label_col = non_numeric_cols[0]
    value_col = numeric_cols[0]
    if df[label_col].nunique() > 30:
        return None
    chart_df = df[[label_col, value_col]].set_index(label_col)
    return chart_df


SAMPLE_QUESTIONS = [
    "Which carrier has the highest average freight cost?",
    "How many shipments are currently delayed, and what are the top delay reasons?",
    "What's the total quoted freight cost by transport mode this year?",
    "Now break that down by carrier as well",
    "Show me delayed shipments from Nhava Sheva to Jebel Ali",
    "What is the average transit time by carrier for ocean shipments?",
    "Now just show Maersk and MSC",
    "List the invoices where the invoiced amount is higher than the quoted cost, and by how much",
    "What's the total invoiced amount by carrier so far?",
    "Are there any invoices still pending review?",
]

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
_, is_mock = get_client()
n_ship, n_inv = db_stats()

with st.sidebar:
    st.markdown("### FreightIQ")
    st.caption("Agentic Analytics + Vision Document Intelligence, over a synthetic freight-ops data lake.")
    if is_mock:
        st.warning(
            "**Demo mode (no ANTHROPIC_API_KEY set).** The agent loop, SQL guardrails, storage and "
            "end-to-end linkage are all real -- only the model reasoning is a deterministic mock "
            "over a curated question set (see README). Set ANTHROPIC_API_KEY for fully general "
            "natural-language understanding.",
            icon="🧪",
        )
    else:
        st.success(f"**Live mode** -- using `{MODEL}` via the Anthropic API.", icon="✅")

    st.markdown("---")
    st.metric("Shipments in data lake", n_ship)
    st.metric("Invoices stored", n_inv)

    st.markdown("---")
    st.markdown("**Guardrails active**")
    st.caption(
        "- SQL: SELECT-only, table allowlist, row cap, read-only connection\n"
        "- No claim made without a grounding tool result\n"
        "- Ambiguous / out-of-schema questions trigger a clarifying question, not a guess\n"
        "- Extraction confidence is scored per document; low-confidence fields block silent storage"
    )

st.title("🚢 FreightIQ")
st.caption("An agentic analytics + document intelligence layer for freight operations data.")

tab_analytics, tab_docs, tab_about = st.tabs(
    ["📊 Agentic Analytics", "📄 Vision Document Agent", "ℹ️ About this POC"]
)

# ---------------------------------------------------------------------------
# TAB 1 -- Agentic Analytics
# ---------------------------------------------------------------------------
with tab_analytics:
    if "chat_log" not in st.session_state:
        st.session_state.chat_log = []
    if "agent_history" not in st.session_state:
        st.session_state.agent_history = []

    col_q, col_btn = st.columns([5, 1])
    with col_q:
        question = st.text_input(
            "Ask a question about shipments or invoices",
            key="question_input",
            placeholder="e.g. Which carrier has the highest average freight cost?",
        )
    with col_btn:
        st.write("")
        st.write("")
        ask_clicked = st.button("Ask", type="primary", width='stretch')

    with st.expander("Sample questions (click to try)"):
        cols = st.columns(2)
        for i, sq in enumerate(SAMPLE_QUESTIONS):
            if cols[i % 2].button(sq, key=f"sample_{i}"):
                question = sq
                ask_clicked = True

    if st.button("Start a new conversation (clears follow-up context)"):
        st.session_state.chat_log = []
        st.session_state.agent_history = []
        st.rerun()

    if ask_clicked and question:
        with st.spinner("Agent is working: interpreting question, querying the data lake..."):
            result = run_agentic_query(question, DB_PATH, history=st.session_state.agent_history)
        st.session_state.agent_history = result.messages
        st.session_state.chat_log.append({"question": question, "result": result})

    for entry in reversed(st.session_state.chat_log):
        q = entry["question"]
        r = entry["result"]
        st.markdown(f"**You:** {q}")
        if r.clarification:
            st.info(f"**Agent asks for clarification:** {r.clarification}")
        else:
            st.markdown(f"**Agent:** {r.answer}")
            for t in r.turns:
                if t.error:
                    st.error(f"Query blocked/failed: {t.error}")
                    continue
                with st.expander(f"Transparency: query used ({t.row_count} rows)"):
                    st.code(t.sql, language="sql")
                    st.caption(t.explanation)
                    df = pd.DataFrame(t.rows, columns=t.columns)
                    st.dataframe(df, width='stretch')
                    chart_df = maybe_chart(t.columns, t.rows)
                    if chart_df is not None:
                        st.bar_chart(chart_df)
        st.markdown("---")

# ---------------------------------------------------------------------------
# TAB 2 -- Vision Document Agent
# ---------------------------------------------------------------------------
with tab_docs:
    st.subheader("Upload a freight invoice (PDF or image)")
    st.caption(
        "The agent renders the document, extracts structured fields with a vision-capable model, "
        "flags anything it isn't confident about, and only writes to the queryable store once you confirm."
    )

    left, right = st.columns([1, 1])
    with left:
        uploaded = st.file_uploader("Upload PDF or image", type=["pdf", "png", "jpg", "jpeg"])
        st.markdown("**...or use a bundled sample invoice:**")
        sample_files = sorted(os.listdir(SAMPLE_DIR)) if os.path.isdir(SAMPLE_DIR) else []
        chosen_sample = st.selectbox("Sample invoices", ["-- none --"] + sample_files)

    file_bytes, filename = None, None
    if uploaded is not None:
        file_bytes, filename = uploaded.read(), uploaded.name
    elif chosen_sample != "-- none --":
        with open(os.path.join(SAMPLE_DIR, chosen_sample), "rb") as f:
            file_bytes, filename = f.read(), chosen_sample

    if file_bytes is not None:
        if st.session_state.get("last_doc_name") != filename:
            with st.spinner("Rendering document and running vision extraction..."):
                images = render_to_images(file_bytes, filename)
                fields, doc_is_mock, err = extract_invoice(file_bytes, filename)
            st.session_state["last_doc_name"] = filename
            st.session_state["last_doc_images"] = images
            st.session_state["last_doc_fields"] = fields
            st.session_state["last_doc_err"] = err

        images = st.session_state.get("last_doc_images")
        fields = st.session_state.get("last_doc_fields")
        err = st.session_state.get("last_doc_err")

        with right:
            if images:
                st.image(images[0], caption=filename, width='stretch')

        if err:
            st.error(f"Extraction failed: {err}")
        elif fields:
            low_conf = set(fields.get("low_confidence_fields") or [])
            conf = fields.get("field_confidence_avg", 0)
            st.markdown("### Review extracted fields")
            if low_conf:
                st.warning(f"Low-confidence fields flagged for review: {', '.join(low_conf)}")
            st.progress(min(max(conf, 0.0), 1.0), text=f"Model confidence: {conf:.0%}")

            with st.form("review_form"):
                c1, c2 = st.columns(2)
                invoice_number = c1.text_input("Invoice number", fields.get("invoice_number") or "")
                shipment_reference = c2.text_input(
                    "Shipment reference" + (" ⚠️" if "shipment_reference" in low_conf else ""),
                    fields.get("shipment_reference") or "")
                carrier = c1.text_input("Carrier", fields.get("carrier") or "")
                currency = c2.text_input("Currency", fields.get("currency") or "USD")
                invoice_date = c1.text_input("Invoice date", fields.get("invoice_date") or "")
                due_date = c2.text_input("Due date", fields.get("due_date") or "")
                freight_charges = c1.number_input("Freight charges", value=float(fields.get("freight_charges") or 0))
                fuel_surcharge = c2.number_input("Fuel surcharge", value=float(fields.get("fuel_surcharge") or 0))
                customs_duty = c1.number_input(
                    "Customs duty" + (" ⚠️" if "customs_duty" in low_conf else ""),
                    value=float(fields.get("customs_duty") or 0))
                other_charges = c2.number_input(
                    "Other charges" + (" ⚠️" if "other_charges" in low_conf else ""),
                    value=float(fields.get("other_charges") or 0))
                total_amount = st.number_input(
                    "Total amount" + (" ⚠️" if "total_amount" in low_conf else ""),
                    value=float(fields.get("total_amount") or 0))

                submitted = st.form_submit_button("Confirm & store (makes this queryable)", type="primary")
                if submitted:
                    confirmed = dict(
                        invoice_number=invoice_number, shipment_reference=shipment_reference or None,
                        carrier=carrier, currency=currency, invoice_date=invoice_date or None,
                        due_date=due_date or None, freight_charges=freight_charges,
                        fuel_surcharge=fuel_surcharge, customs_duty=customs_duty,
                        other_charges=other_charges, total_amount=total_amount,
                        field_confidence_avg=conf, low_confidence_fields=list(low_conf),
                    )
                    inv_id = store_invoice(DB_PATH, confirmed, filename)
                    st.success(
                        f"Stored as `{inv_id}`. It's now queryable -- try asking in the Analytics tab: "
                        f"\"What's the total invoiced amount by carrier so far?\" or "
                        f"\"List the invoices where the invoiced amount is higher than the quoted cost\"."
                    )
                    st.session_state["last_doc_name"] = None  # allow re-processing next time

    st.markdown("### Stored invoices (queryable via Analytics)")
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    df_inv = pd.read_sql_query(
        "SELECT invoice_id, invoice_number, shipment_id, carrier, invoice_date, total_amount, "
        "extraction_confidence, low_confidence_fields, reviewed_by_user, source_filename "
        "FROM invoices ORDER BY extracted_at DESC", conn)
    conn.close()
    st.dataframe(df_inv, width='stretch')

# ---------------------------------------------------------------------------
# TAB 3 -- About
# ---------------------------------------------------------------------------
with tab_about:
    st.markdown(
        """
FreightIQ is a proof of concept for an **agentic analytics + document intelligence layer**
over freight operations data -- the kind of read-only-data-lake problem GoComet's own
customers face daily (shipment visibility + freight invoice audit).

**Architecture**

- `agents/analytics_agent.py` -- a real tool-use loop against Claude: the model calls
  `run_sql` or `ask_clarification`, never free-text SQL that bypasses guardrails.
- `agents/sql_guard.py` -- SELECT-only, table allowlist, row cap, read-only DB connection.
- `agents/document_agent.py` -- vision extraction forced through a structured tool schema
  (`extract_invoice_fields`), not free-text JSON parsing; confidence is scored per document.
- `agents/mock_client.py` / `agents/llm_client.py` -- the exact same agent code runs against
  a deterministic mock (for offline testing/demo) or the real Anthropic API, decided purely
  by whether `ANTHROPIC_API_KEY` is set.
- `db/freight.db` -- SQLite, two tables: `shipments` (synthetic data lake) and `invoices`
  (populated only through the reviewed document-extraction flow).

See `PRD.md`/`PRD.docx` for the product rationale, personas, scope, and trust/safety design.
        """
    )
