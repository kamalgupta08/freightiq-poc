"""
Thin factory over the LLM provider.

Design choice: both agents (analytics + document extraction) talk to a
`client` object that exposes a single method --
    client.messages.create(model=..., system=..., messages=..., tools=..., ...)
-- identical to the `anthropic` Python SDK's interface.

If ANTHROPIC_API_KEY is set, we return the real Anthropic client.
If it is not set, we return a MockClient (agents/mock_client.py) that
implements the same interface with deterministic, rule-based responses.

Why this matters for this assignment: it means the full pipeline (DB
wiring, SQL guardrails, chart rendering, extraction-review-store flow,
end-to-end linkage) can be built, run and verified without needing an
API key in hand, while the exact same agent code path runs against the
real model the moment a key is added. Nothing about the agent logic
changes between mock and live mode -- only which client answers the
`messages.create` call.
"""
import os

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")


def get_client():
    """Returns (client, is_mock: bool)."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        import anthropic
        return anthropic.Anthropic(api_key=api_key), False
    from agents.mock_client import MockClient
    return MockClient(), True
