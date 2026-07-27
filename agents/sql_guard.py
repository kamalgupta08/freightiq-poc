"""
Guardrails around the one privileged action the Analytics Agent can
take: executing SQL against the freight database.

Layered defense (any single layer failing does not expose write access):
  1. Statement shape  -- exactly one statement, must start with SELECT.
  2. Keyword denylist  -- no DDL/DML/PRAGMA/ATTACH keywords anywhere.
  3. Table allowlist   -- only `shipments` and `invoices` may be referenced.
  4. Row cap           -- a LIMIT is enforced even if the model forgets one.
  5. Connection-level  -- the SQLite connection itself is opened read-only
     (mode=ro) AND `PRAGMA query_only = ON`, so even a guard bypass could
     not mutate the database.
"""
import re
import sqlite3

ALLOWED_TABLES = {"shipments", "invoices"}
DENYLIST = [
    "insert", "update", "delete", "drop", "alter", "attach", "detach",
    "pragma", "create", "replace", "vacuum", "trigger", "exec", "grant",
    "reindex", "savepoint", "release",
]
DEFAULT_LIMIT = 500


def guard_sql(sql: str):
    """Returns (ok: bool, safe_sql_or_None, error_message_or_None)."""
    if not sql or not sql.strip():
        return False, None, "Empty query."

    statements = [s.strip() for s in sql.strip().rstrip(";").split(";") if s.strip()]
    if len(statements) != 1:
        return False, None, "Only a single SQL statement is allowed per call."
    stmt = statements[0]

    if not re.match(r"^\s*select\b", stmt, re.IGNORECASE):
        return False, None, "Only SELECT statements are allowed."

    lowered = stmt.lower()
    for word in DENYLIST:
        if re.search(rf"\b{word}\b", lowered):
            return False, None, f"Query contains a disallowed keyword: '{word}'."

    referenced_tables = set(re.findall(r"(?:from|join)\s+([a-zA-Z_][a-zA-Z0-9_]*)", lowered))
    disallowed = referenced_tables - ALLOWED_TABLES
    if disallowed:
        return False, None, f"Query references table(s) outside the allowlist: {sorted(disallowed)}."
    if not referenced_tables:
        return False, None, "Query does not reference an allowed table (shipments, invoices)."

    if not re.search(r"\blimit\s+\d+", lowered):
        stmt = f"{stmt}\nLIMIT {DEFAULT_LIMIT}"

    return True, stmt, None


def execute_readonly(db_path: str, sql: str):
    """Executes a guarded SELECT against a read-only connection.
    Returns (columns, rows, error_or_None)."""
    uri = f"file:{db_path}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=5)
        conn.execute("PRAGMA query_only = ON;")
        cur = conn.execute(sql)
        columns = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchall()
        conn.close()
        return columns, rows, None
    except Exception as e:
        return [], [], str(e)
