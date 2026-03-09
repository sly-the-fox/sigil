"""Tests for the Sigil Notary MCP server tool functions."""

from __future__ import annotations

import json
import sys
from types import ModuleType
from unittest.mock import patch

import httpx
import pytest

# ---------------------------------------------------------------------------
# Mock the mcp dependency so we can import mcp_server without it installed.
# ---------------------------------------------------------------------------

_fake_mcp = ModuleType("mcp")
_fake_mcp_server = ModuleType("mcp.server")
_fake_mcp_server_fastmcp = ModuleType("mcp.server.fastmcp")


class _FakeFastMCP:
    def __init__(self, *a, **kw):
        pass

    def tool(self):
        """Decorator that returns the function unchanged."""

        def decorator(fn):
            return fn

        return decorator

    def run(self):
        pass


_fake_mcp_server_fastmcp.FastMCP = _FakeFastMCP

sys.modules.setdefault("mcp", _fake_mcp)
sys.modules.setdefault("mcp.server", _fake_mcp_server)
sys.modules.setdefault("mcp.server.fastmcp", _fake_mcp_server_fastmcp)

# Now we can safely import mcp_server
import mcp_server as srv  # noqa: E402, I001


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MOCK_RECEIPT = {
    "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    "seq": 1,
    "agent_id": "test-agent",
    "action_type": "file_write",
    "receipt_hash": "abcdef1234567890abcdef1234567890",
    "signature": "sig_hex_data",
    "timestamp": "2026-03-08T12:00:00Z",
    "payload": {"summary": "wrote a file"},
}

MOCK_VERIFY = {"valid": True, "chain_valid": True}

MOCK_CHAIN = {
    "agent_id": "test-agent",
    "length": 2,
    "receipts": [
        {**MOCK_RECEIPT, "seq": 1},
        {**MOCK_RECEIPT, "seq": 2, "action_type": "tool_call"},
    ],
}


# ---------------------------------------------------------------------------
# attest_action
# ---------------------------------------------------------------------------


@patch.object(srv, "_call_api", return_value={"receipt": MOCK_RECEIPT})
def test_attest_action_success(mock_api):
    result = srv.attest_action("file_write", "wrote a file", {"path": "/tmp/x"})
    assert "Receipt #1" in result
    assert MOCK_RECEIPT["id"] in result
    mock_api.assert_called_once()


def test_attest_action_invalid_action_type_special_chars():
    result = srv.attest_action("bad action!@#", "summary")
    assert result.startswith("Error:")
    assert "alphanumeric" in result


def test_attest_action_action_type_too_long():
    result = srv.attest_action("a" * 65, "summary")
    assert result.startswith("Error:")
    assert "65 chars" in result


def test_attest_action_oversized_summary():
    result = srv.attest_action("test", "x" * 513)
    assert result.startswith("Error:")
    assert "character limit" in result


def test_attest_action_oversized_payload():
    big_payload = {"data": "x" * 11000}
    result = srv.attest_action("test", "ok", big_payload)
    assert result.startswith("Error:")
    assert "byte limit" in result


@patch.object(srv, "_call_api", return_value={"receipt": MOCK_RECEIPT})
def test_attest_action_hyphenated_type(mock_api):
    """Hyphens should be allowed in action_type after Fix 7."""
    result = srv.attest_action("api-request", "called an API")
    assert "Receipt #1" in result


# ---------------------------------------------------------------------------
# verify_receipt
# ---------------------------------------------------------------------------


@patch.object(srv, "_call_api", return_value=MOCK_VERIFY)
def test_verify_receipt_success(mock_api):
    result = srv.verify_receipt("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    assert "VALID" in result
    mock_api.assert_called_once()


def test_verify_receipt_invalid_uuid():
    with pytest.raises(ValueError):
        srv._validate_uuid("not-a-uuid")


def test_verify_receipt_path_traversal():
    with pytest.raises(ValueError):
        srv._validate_uuid("../../admin")


# ---------------------------------------------------------------------------
# get_chain
# ---------------------------------------------------------------------------


@patch.object(srv, "_call_api", return_value=MOCK_CHAIN)
@patch.dict("os.environ", {"SIGIL_AGENT_ID": "test-agent", "SIGIL_API_KEY": "k"})
def test_get_chain_success(mock_api):
    result = srv.get_chain(limit=50, after_seq=0)
    assert "test-agent" in result
    assert "2 receipts" in result
    mock_api.assert_called_once()


@patch.dict("os.environ", {"SIGIL_AGENT_ID": "../../bad", "SIGIL_API_KEY": "k"})
def test_get_chain_invalid_agent_id():
    with pytest.raises(ValueError, match="Invalid agent_id"):
        srv.get_chain()


@patch.object(srv, "_call_api", return_value=MOCK_CHAIN)
@patch.dict("os.environ", {"SIGIL_AGENT_ID": "test-agent", "SIGIL_API_KEY": "k"})
def test_get_chain_clamps_limit(mock_api):
    """Limit above _MAX_CHAIN_LIMIT gets clamped."""
    srv.get_chain(limit=5000)
    call_kwargs = mock_api.call_args
    assert call_kwargs[1]["params"]["limit"] == srv._MAX_CHAIN_LIMIT


# ---------------------------------------------------------------------------
# _call_api error paths
# ---------------------------------------------------------------------------


@patch.dict("os.environ", {"SIGIL_API_KEY": "test_key"})
def test_call_api_connect_error():
    with patch.object(srv, "_client") as mock_client_fn:
        ctx = mock_client_fn.return_value.__enter__.return_value
        ctx.get.side_effect = httpx.ConnectError("refused")
        with pytest.raises(srv.SigilAPIError, match="unreachable"):
            srv._call_api("get", "/v1/test")


@patch.dict("os.environ", {"SIGIL_API_KEY": "test_key"})
def test_call_api_timeout():
    with patch.object(srv, "_client") as mock_client_fn:
        ctx = mock_client_fn.return_value.__enter__.return_value
        ctx.get.side_effect = httpx.TimeoutException("timed out")
        with pytest.raises(srv.SigilAPIError, match="timed out"):
            srv._call_api("get", "/v1/test")


@patch.dict("os.environ", {"SIGIL_API_KEY": "test_key"})
def test_call_api_http_status_error():
    with patch.object(srv, "_client") as mock_client_fn:
        ctx = mock_client_fn.return_value.__enter__.return_value
        resp = httpx.Response(
            403, json={"detail": "Forbidden"}, request=httpx.Request("GET", "http://test")
        )
        ctx.get.side_effect = httpx.HTTPStatusError("403", response=resp, request=resp.request)
        with pytest.raises(srv.SigilAPIError, match="403"):
            srv._call_api("get", "/v1/test")


@patch.dict("os.environ", {"SIGIL_API_KEY": "test_key"})
def test_call_api_json_decode_error():
    with patch.object(srv, "_client") as mock_client_fn:
        ctx = mock_client_fn.return_value.__enter__.return_value
        ctx.get.side_effect = json.JSONDecodeError("bad", "", 0)
        with pytest.raises(srv.SigilAPIError, match="invalid response"):
            srv._call_api("get", "/v1/test")
