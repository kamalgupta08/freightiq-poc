"""
Agentic Analytics Layer.

A real tool-use loop (not a single-shot "translate to SQL" prompt):
the model is given a `run_sql` tool and an `ask_clarification` tool,
decides which to call, receives the actual result back, and only then
produces a grounded natural-language answer. This is what lets it
handle follow-up refinements (filter / group / time window) across
turns using ordinary conversation state, and what lets it choose to
ask a clarifying question instead of guessing when the question is
ambiguous or out of schema.
"""
import json
from dataclasses import dataclass, field
from typing import Any

from agents.llm_client import get_client, MODEL
from agents.sql_guard import guard_sql, execute_readonly

MAX_STEPS = 4

SCHEMA_DESC = """
You can query a SQLite database called the "freight data lake" with exactly two tables.

TABLE shipments (one row per freight shipment / booking):
  shipment_id TEXT, booking_date TEXT (YYYY-MM-DD), customer TEXT, carrier TEXT,
  mode TEXT ('Ocean'|'Air'|'Road'), container_type TEXT,
  origin_country TEXT, origin_port TEXT, destination_country TEXT, destination_port TEXT,
  etd TEXT, eta TEXT, atd TEXT, ata TEXT,
  transit_days_planned INTEGER, transit_days_actual INTEGER,
  quoted_cost_usd REAL, weight_kg REAL, volume_cbm REAL,
  status TEXT ('Delivered'|'In Transit'|'Delayed'|'Cancelled'),
  delay_days INTEGER, delay_reason TEXT (NULL or one of
    'Customs Hold','Port Congestion','Carrier Rollover','Documentation Issue','Weather')

TABLE invoices (one row per freight invoice, populated ONLY after a human has
reviewed an extraction from the Vision Document Agent -- this is the join
point between document extraction and analytics):
  invoice_id TEXT, invoice_number TEXT, shipment_id TEXT (FK -> shipments.shipment_id, nullable),
  carrier TEXT, invoice_date TEXT, due_date TEXT, currency TEXT,
  freight_charges REAL, fuel_surcharge REAL, customs_duty REAL, other_charges REAL,
  total_amount REAL, extraction_confidence REAL, low_confidence_fields TEXT,
  source_filename TEXT, extracted_at TEXT, reviewed_by_user INTEGER (0 or 1)

Today's date for relative time questions: 2026-07-22.
"""

SYSTEM_PROMPT = f"""You are the Agentic Analytics Layer for FreightIQ, a freight/logistics
operations intelligence product. You answer business questions ONLY using data returned
by the `run_sql` tool against the schema below. You never state a number, trend, or fact
that is not directly present in a tool result.

{SCHEMA_DESC}

Rules:
- Only SELECT queries against `shipments` and/or `invoices` are possible -- the tool enforces this.
- If the question is ambiguous, uses a metric/field not in the schema (e.g. profit margin,
  customer satisfaction, headcount), or spans a time period you cannot resolve, call
  `ask_clarification` instead of guessing.
- Prefer aggregate queries (GROUP BY, AVG, SUM, COUNT) over dumping raw rows.
- After you get a tool result, write a short, direct, data-grounded answer. Do not
  editorialize beyond what the numbers show.
- Treat prior turns in this conversation as context for follow-up refinements
  (e.g. "now just show X", "break that down by Y", "last 30 days only").
"""

TOOLS = [
    {
        "name": "run_sql",
        "description": "Execute a read-only SQL SELECT query against the freight database "
                        "(shipments, invoices tables only) to gather the data needed to answer "
                        "the user's question.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "A single SELECT statement."},
                "explanation": {"type": "string",
                                "description": "One sentence: why this query answers the question."},
            },
            "required": ["sql", "explanation"],
        },
    },
    {
        "name": "ask_clarification",
        "description": "Use this when the question is ambiguous, references data not present in "
                        "the schema, or cannot be safely answered without guessing. Do NOT guess.",
        "input_schema": {
            "type": "object",
            "properties": {"question": {"type": "string"}},
            "required": ["question"],
        },
    },
]


@dataclass
class AgentTurn:
    sql: str
    explanation: str
    columns: list
    rows: list
    row_count: int
    error: str = None


@dataclass
class AgentResult:
    answer: str = None
    clarification: str = None
    turns: list = field(default_factory=list)
    messages: list = field(default_factory=list)
    is_mock: bool = False


def _content_to_plain(content):
    """Anthropic content blocks -> plain list-of-dicts (for storing in message history)."""
    out = []
    for b in content:
        if b.type == "text":
            out.append({"type": "text", "text": b.text})
        elif b.type == "tool_use":
            out.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
    return out


def run_agentic_query(question: str, db_path: str, history: list = None):
    """
    history: prior turns as a list of {"role": "user"/"assistant", "content": [...]}
             (already in Anthropic message format). Pass the `messages` from the
             previous AgentResult back in to support follow-up refinement.
    """
    client, is_mock = get_client()
    messages = list(history or [])
    messages.append({"role": "user", "content": [{"type": "text", "text": question}]})

    turns = []
    for _ in range(MAX_STEPS):
        resp = client.messages.create(
            model=MODEL, system=SYSTEM_PROMPT, messages=messages,
            tools=TOOLS, max_tokens=1024,
        )
        messages.append({"role": "assistant", "content": _content_to_plain(resp.content)})

        tool_uses = [b for b in resp.content if b.type == "tool_use"]
        if not tool_uses:
            text = "".join(b.text for b in resp.content if b.type == "text")
            return AgentResult(answer=text, turns=turns, messages=messages, is_mock=is_mock)

        tool_result_blocks = []
        clarification = None
        for tu in tool_uses:
            if tu.name == "ask_clarification":
                clarification = tu.input.get("question")
                continue
            if tu.name == "run_sql":
                sql = tu.input.get("sql", "")
                ok, safe_sql, err = guard_sql(sql)
                if not ok:
                    payload: dict[str, Any] = {"error": err}
                    turns.append(AgentTurn(sql=sql, explanation=tu.input.get("explanation", ""),
                                            columns=[], rows=[], row_count=0, error=err))
                else:
                    columns, rows, exec_err = execute_readonly(db_path, safe_sql)
                    if exec_err:
                        payload = {"error": exec_err}
                        turns.append(AgentTurn(sql=safe_sql, explanation=tu.input.get("explanation", ""),
                                                columns=[], rows=[], row_count=0, error=exec_err))
                    else:
                        payload = {"columns": columns, "rows": rows[:200], "row_count": len(rows)}
                        turns.append(AgentTurn(sql=safe_sql, explanation=tu.input.get("explanation", ""),
                                                columns=columns, rows=rows, row_count=len(rows)))
                tool_result_blocks.append({
                    "type": "tool_result", "tool_use_id": tu.id,
                    "content": json.dumps(payload, default=str),
                })

        if clarification:
            return AgentResult(clarification=clarification, turns=turns, messages=messages, is_mock=is_mock)

        messages.append({"role": "user", "content": tool_result_blocks})

    return AgentResult(
        answer="I couldn't resolve this within the agent's step budget -- try breaking the "
               "question into a simpler one.",
        turns=turns, messages=messages, is_mock=is_mock,
    )
