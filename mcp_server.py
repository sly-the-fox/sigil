"""Sigil Notary MCP Server — trust infrastructure for AI agents.

Wraps the Sigil Notary REST API as MCP tools so AI agents (Claude Code,
OpenHands, etc.) can create audit trails natively via the MCP protocol.

Configuration (environment variables):
    SIGIL_API_URL  — Notary API base URL (default: http://localhost:8100)
    SIGIL_API_KEY  — API key for authentication (required)
    SIGIL_AGENT_ID — Agent identity for chain queries (default: from key)
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import uuid

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "sigil-notary",
    instructions="Trust infrastructure for AI agents — hash-chained, Ed25519-signed audit trails",
)

API_URL = os.environ.get("SIGIL_API_URL", "http://localhost:8100")

if API_URL.startswith("http://"):
    from urllib.parse import urlparse

    _parsed = urlparse(API_URL)
    if _parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
        import logging

        logging.getLogger("sigil-notary").warning(
            "SIGIL_API_URL uses plain HTTP (%s). "
            "Use HTTPS in production to protect API keys and receipts in transit.",
            API_URL,
        )

_AGENT_ID_RE = re.compile(r"^[a-zA-Z0-9_\-\.]{1,128}$")
_ACTION_TYPE_RE = re.compile(r"^[a-zA-Z0-9_\-\.]{1,64}$")
_MAX_ACTION_SUMMARY = 512
_MAX_PAYLOAD_BYTES = 10240  # 10 KB
_MAX_CHAIN_LIMIT = 1000


class SigilAPIError(Exception):
    """Friendly error for API communication failures."""


def _get_api_key() -> str:
    key = os.environ.get("SIGIL_API_KEY", "")
    if not key:
        raise RuntimeError("SIGIL_API_KEY environment variable is required")
    return key


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=API_URL,
        headers={"Authorization": f"Bearer {_get_api_key()}"},
        timeout=10,
    )


def _validate_uuid(value: str) -> str:
    """Validate and return a canonical UUID string to prevent path injection."""
    return str(uuid.UUID(value))


def _validate_agent_id(value: str) -> str:
    """Validate agent_id format to prevent path injection."""
    if not _AGENT_ID_RE.match(value):
        raise ValueError(f"Invalid agent_id format: must match {_AGENT_ID_RE.pattern}")
    return value


def _call_api(method: str, path: str, **kwargs) -> dict:
    """Call the Sigil API with structured error handling."""
    try:
        with _client() as c:
            resp = getattr(c, method)(path, **kwargs)
            resp.raise_for_status()
            return resp.json()
    except httpx.ConnectError as exc:
        raise SigilAPIError(f"Sigil API unreachable at {API_URL}") from exc
    except httpx.TimeoutException as exc:
        raise SigilAPIError("Sigil API request timed out") from exc
    except httpx.HTTPStatusError as e:
        detail = ""
        with contextlib.suppress(Exception):
            detail = e.response.json().get("detail", "")
        raise SigilAPIError(f"Sigil API error: {e.response.status_code} {detail}") from e
    except json.JSONDecodeError as exc:
        raise SigilAPIError("Sigil API returned invalid response") from exc


@mcp.tool()
def attest_action(
    action_type: str,
    action_summary: str,
    payload: dict | None = None,
) -> str:
    """Record an action and get a signed, hash-chained receipt.

    Args:
        action_type: Category of action (e.g. "tool_call", "file_write", "api_request", "decision")
        action_summary: Human-readable description of what happened
        payload: Optional structured data about the action
    """
    if not _ACTION_TYPE_RE.match(action_type):
        return (
            "Error: action_type must be alphanumeric/underscores/dots, "
            f"max 64 chars (got {len(action_type)} chars)"
        )
    if len(action_summary) > _MAX_ACTION_SUMMARY:
        return (
            f"Error: action_summary exceeds {_MAX_ACTION_SUMMARY} "
            f"character limit ({len(action_summary)} chars)"
        )
    body = {
        "action_type": action_type,
        "payload": {**(payload or {}), "summary": action_summary},
    }
    body_bytes = len(json.dumps(body))
    if body_bytes > _MAX_PAYLOAD_BYTES:
        return (
            f"Error: request payload exceeds {_MAX_PAYLOAD_BYTES} byte limit ({body_bytes} bytes)"
        )
    try:
        data = _call_api("post", "/v1/attest", json=body)
    except SigilAPIError as e:
        return f"Error: {e}"
    receipt = data["receipt"]
    ts = receipt.get("timestamp", "")
    return (
        f"Receipt #{receipt['seq']} | {receipt['id']} | "
        f"{ts} | hash: {receipt['receipt_hash'][:16]}..."
    )


@mcp.tool()
def verify_receipt(receipt_id: str) -> str:
    """Verify a receipt's signature and chain integrity.

    Args:
        receipt_id: UUID of the receipt to verify
    """
    safe_id = _validate_uuid(receipt_id)
    try:
        data = _call_api("get", f"/v1/verify/{safe_id}")
    except SigilAPIError as e:
        return f"Error: {e}"
    status = "VALID" if data["valid"] and data["chain_valid"] else "INVALID"
    return f"{status} | signature={data['valid']} chain={data['chain_valid']}"


@mcp.tool()
def get_chain(limit: int = 100, after_seq: int = 0) -> str:
    """Retrieve the audit trail for this agent.

    Args:
        limit: Maximum number of receipts to return (default 100, max 1000)
        after_seq: Return receipts after this sequence number (pagination)
    """
    agent_id = _validate_agent_id(os.environ.get("SIGIL_AGENT_ID", "unknown"))
    clamped_limit = max(1, min(limit, _MAX_CHAIN_LIMIT))
    try:
        data = _call_api(
            "get",
            f"/v1/chain/{agent_id}",
            params={"limit": clamped_limit, "after_seq": after_seq},
        )
    except SigilAPIError as e:
        return f"Error: {e}"
    lines = [f"Chain: {data['agent_id']} ({data['length']} receipts)"]
    for r in data["receipts"]:
        ts = r.get("timestamp", "")
        lines.append(f"  #{r['seq']} {r['action_type']} [{ts}] — {r['receipt_hash'][:16]}...")
    return "\n".join(lines)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
