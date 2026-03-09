"""Tests for the Sigil Python SDK client."""

from __future__ import annotations

import httpx
import pytest
import respx

from sigil.client import AsyncSigilClient, SigilClient, SigilError, _parse_receipt

BASE_URL = "https://api.test.local"
API_KEY = "sg_test_key_123"

MOCK_RECEIPT = {
    "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    "seq": 1,
    "agent_id": "test-agent",
    "action_type": "file_write",
    "receipt_hash": "abcdef1234567890abcdef1234567890",
    "signature": "sig_hex_data",
    "timestamp": "2026-03-08T12:00:00Z",
    "payload": {"path": "/tmp/test.txt"},
}


@pytest.fixture
def client():
    c = SigilClient(api_key=API_KEY, base_url=BASE_URL)
    yield c
    c.close()


@respx.mock
def test_attest_success(client: SigilClient):
    respx.post(f"{BASE_URL}/v1/attest").mock(
        return_value=httpx.Response(200, json={"receipt": MOCK_RECEIPT})
    )
    receipt = client.attest("file_write", {"path": "/tmp/test.txt"})
    assert receipt.seq == 1
    assert receipt.action_type == "file_write"
    assert receipt.id == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


@respx.mock
def test_verify_success(client: SigilClient):
    rid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    respx.get(f"{BASE_URL}/v1/verify/{rid}").mock(
        return_value=httpx.Response(200, json={"valid": True, "chain_valid": True})
    )
    result = client.verify(rid)
    assert result.valid is True
    assert result.chain_valid is True


@respx.mock
def test_verify_invalid(client: SigilClient):
    rid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    respx.get(f"{BASE_URL}/v1/verify/{rid}").mock(
        return_value=httpx.Response(200, json={"valid": False, "chain_valid": False})
    )
    result = client.verify(rid)
    assert result.valid is False


@respx.mock
def test_get_chain_success(client: SigilClient):
    agent = "test-agent"
    respx.get(f"{BASE_URL}/v1/chain/{agent}").mock(
        return_value=httpx.Response(
            200,
            json={
                "agent_id": agent,
                "length": 2,
                "receipts": [
                    {**MOCK_RECEIPT, "seq": 1},
                    {**MOCK_RECEIPT, "seq": 2, "action_type": "tool_call"},
                ],
            },
        )
    )
    chain = client.get_chain(agent)
    assert chain.agent_id == agent
    assert chain.length == 2
    assert len(chain.receipts) == 2
    assert chain.receipts[1].action_type == "tool_call"


@respx.mock
def test_error_401(client: SigilClient):
    respx.post(f"{BASE_URL}/v1/attest").mock(
        return_value=httpx.Response(401, json={"detail": "Invalid API key"})
    )
    with pytest.raises(SigilError) as exc_info:
        client.attest("test")
    assert exc_info.value.status_code == 401


@respx.mock
def test_error_500(client: SigilClient):
    respx.post(f"{BASE_URL}/v1/attest").mock(
        return_value=httpx.Response(500, json={"detail": "Internal server error"})
    )
    with pytest.raises(SigilError) as exc_info:
        client.attest("test")
    assert exc_info.value.status_code == 500


@respx.mock
@pytest.mark.asyncio
async def test_async_attest():
    respx.post(f"{BASE_URL}/v1/attest").mock(
        return_value=httpx.Response(200, json={"receipt": {**MOCK_RECEIPT, "seq": 5}})
    )
    async with AsyncSigilClient(api_key=API_KEY, base_url=BASE_URL) as client:
        receipt = await client.attest("decision", {"choice": "deploy"})
        assert receipt.seq == 5


@respx.mock
@pytest.mark.asyncio
async def test_async_verify():
    rid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    respx.get(f"{BASE_URL}/v1/verify/{rid}").mock(
        return_value=httpx.Response(200, json={"valid": True, "chain_valid": True})
    )
    async with AsyncSigilClient(api_key=API_KEY, base_url=BASE_URL) as client:
        result = await client.verify(rid)
        assert result.valid is True


# --- Fix 2: Truncated error body ---


@respx.mock
def test_error_body_truncated(client: SigilClient):
    """Long non-JSON error bodies are truncated to 200 chars."""
    long_body = "x" * 500
    respx.post(f"{BASE_URL}/v1/attest").mock(return_value=httpx.Response(500, text=long_body))
    with pytest.raises(SigilError) as exc_info:
        client.attest("test")
    # The detail should be at most 200 chars, not the full 500
    assert len(str(exc_info.value)) < 300


# --- Fix 5: _parse_receipt validation ---


def test_parse_receipt_invalid_uuid():
    bad = {**MOCK_RECEIPT, "id": "not-a-uuid"}
    with pytest.raises(SigilError, match="invalid or missing id"):
        _parse_receipt(bad)


def test_parse_receipt_missing_id():
    bad = {k: v for k, v in MOCK_RECEIPT.items() if k != "id"}
    with pytest.raises(SigilError, match="invalid or missing id"):
        _parse_receipt(bad)


def test_parse_receipt_negative_seq():
    bad = {**MOCK_RECEIPT, "seq": -1}
    with pytest.raises(SigilError, match="non-negative integer"):
        _parse_receipt(bad)


def test_parse_receipt_string_seq():
    bad = {**MOCK_RECEIPT, "seq": "not_int"}
    with pytest.raises(SigilError, match="non-negative integer"):
        _parse_receipt(bad)


def test_parse_receipt_empty_hash():
    bad = {**MOCK_RECEIPT, "receipt_hash": ""}
    with pytest.raises(SigilError, match="receipt_hash must be a non-empty string"):
        _parse_receipt(bad)


def test_parse_receipt_empty_signature():
    bad = {**MOCK_RECEIPT, "signature": ""}
    with pytest.raises(SigilError, match="signature must be a non-empty string"):
        _parse_receipt(bad)


# --- Fix 5: Malformed receipt from API ---


@respx.mock
def test_attest_malformed_receipt(client: SigilClient):
    """API returns receipt with missing fields → SigilError."""
    respx.post(f"{BASE_URL}/v1/attest").mock(
        return_value=httpx.Response(200, json={"receipt": {"id": "bad", "seq": 1}})
    )
    with pytest.raises(SigilError):
        client.attest("test")


# --- Fix 6: Configurable timeout ---


def test_custom_timeout():
    c = SigilClient(api_key=API_KEY, base_url=BASE_URL, timeout=30.0)
    assert c._client.timeout.connect == 30.0
    c.close()


@pytest.mark.asyncio
async def test_async_custom_timeout():
    c = AsyncSigilClient(api_key=API_KEY, base_url=BASE_URL, timeout=5.0)
    assert c._client.timeout.connect == 5.0
    await c.aclose()


# --- Audit 2, Fix 1: Missing field checks in _parse_receipt ---


def test_parse_receipt_missing_agent_id():
    bad = {k: v for k, v in MOCK_RECEIPT.items() if k != "agent_id"}
    with pytest.raises(SigilError, match="missing required field 'agent_id'"):
        _parse_receipt(bad)


def test_parse_receipt_missing_action_type():
    bad = {k: v for k, v in MOCK_RECEIPT.items() if k != "action_type"}
    with pytest.raises(SigilError, match="missing required field 'action_type'"):
        _parse_receipt(bad)


def test_parse_receipt_missing_timestamp():
    bad = {k: v for k, v in MOCK_RECEIPT.items() if k != "timestamp"}
    with pytest.raises(SigilError, match="missing required field 'timestamp'"):
        _parse_receipt(bad)


# --- Audit 2, Fix 2: verify() validates receipt_id format ---


def test_verify_invalid_receipt_id():
    c = SigilClient(api_key=API_KEY, base_url=BASE_URL)
    with pytest.raises(SigilError, match="Invalid receipt_id"):
        c.verify("../../admin")
    c.close()


def test_verify_non_uuid_receipt_id():
    c = SigilClient(api_key=API_KEY, base_url=BASE_URL)
    with pytest.raises(SigilError, match="Invalid receipt_id"):
        c.verify("not-a-uuid-at-all")
    c.close()


# --- Audit 2, Fix 3: get_chain() validates agent_id format ---


def test_get_chain_invalid_agent_id():
    c = SigilClient(api_key=API_KEY, base_url=BASE_URL)
    with pytest.raises(SigilError, match="Invalid agent_id"):
        c.get_chain("../../etc/passwd")
    c.close()


def test_get_chain_empty_agent_id():
    c = SigilClient(api_key=API_KEY, base_url=BASE_URL)
    with pytest.raises(SigilError, match="Invalid agent_id"):
        c.get_chain("")
    c.close()


# --- Audit 2, Fix 4: _handle_response catches JSON parse failure ---


@respx.mock
def test_handle_response_invalid_json(client: SigilClient):
    """200 with non-JSON body raises SigilError, not JSONDecodeError."""
    respx.post(f"{BASE_URL}/v1/attest").mock(
        return_value=httpx.Response(200, text="<html>Bad Gateway</html>")
    )
    with pytest.raises(SigilError, match="Invalid JSON"):
        client.attest("test")


# --- Audit 2, Fix 6: Async client error tests ---


@respx.mock
@pytest.mark.asyncio
async def test_async_error_401():
    respx.post(f"{BASE_URL}/v1/attest").mock(
        return_value=httpx.Response(401, json={"detail": "Invalid API key"})
    )
    async with AsyncSigilClient(api_key=API_KEY, base_url=BASE_URL) as client:
        with pytest.raises(SigilError) as exc_info:
            await client.attest("test")
        assert exc_info.value.status_code == 401


@respx.mock
@pytest.mark.asyncio
async def test_async_error_500():
    respx.post(f"{BASE_URL}/v1/attest").mock(
        return_value=httpx.Response(500, json={"detail": "Internal server error"})
    )
    async with AsyncSigilClient(api_key=API_KEY, base_url=BASE_URL) as client:
        with pytest.raises(SigilError) as exc_info:
            await client.attest("test")
        assert exc_info.value.status_code == 500


@respx.mock
@pytest.mark.asyncio
async def test_async_attest_malformed_receipt():
    """Async client: API returns receipt with missing fields → SigilError."""
    respx.post(f"{BASE_URL}/v1/attest").mock(
        return_value=httpx.Response(200, json={"receipt": {"id": "bad", "seq": 1}})
    )
    async with AsyncSigilClient(api_key=API_KEY, base_url=BASE_URL) as client:
        with pytest.raises(SigilError):
            await client.attest("test")


@respx.mock
@pytest.mark.asyncio
async def test_async_verify_invalid_receipt_id():
    async with AsyncSigilClient(api_key=API_KEY, base_url=BASE_URL) as client:
        with pytest.raises(SigilError, match="Invalid receipt_id"):
            await client.verify("../../admin")


@respx.mock
@pytest.mark.asyncio
async def test_async_get_chain_invalid_agent_id():
    async with AsyncSigilClient(api_key=API_KEY, base_url=BASE_URL) as client:
        with pytest.raises(SigilError, match="Invalid agent_id"):
            await client.get_chain("../../etc/passwd")


# --- Audit 3, Fix 1: attest() validates action_type format ---


def test_attest_invalid_action_type(client: SigilClient):
    """Special characters in action_type are rejected client-side."""
    with pytest.raises(SigilError, match="Invalid action_type"):
        client.attest("bad!type@here")


def test_attest_action_type_too_long(client: SigilClient):
    """action_type >64 chars is rejected client-side."""
    with pytest.raises(SigilError, match="Invalid action_type"):
        client.attest("a" * 65)


def test_attest_empty_action_type(client: SigilClient):
    """Empty action_type is rejected client-side."""
    with pytest.raises(SigilError, match="Invalid action_type"):
        client.attest("")


@pytest.mark.asyncio
async def test_async_attest_invalid_action_type():
    """Async: special characters in action_type are rejected client-side."""
    async with AsyncSigilClient(api_key=API_KEY, base_url=BASE_URL) as client:
        with pytest.raises(SigilError, match="Invalid action_type"):
            await client.attest("bad!type")


# --- Audit 3, Fix 2: get_chain() validates limit/after_seq bounds ---


def test_get_chain_negative_limit(client: SigilClient):
    with pytest.raises(SigilError, match="Invalid limit"):
        client.get_chain("test-agent", limit=-1)


def test_get_chain_zero_limit(client: SigilClient):
    with pytest.raises(SigilError, match="Invalid limit"):
        client.get_chain("test-agent", limit=0)


def test_get_chain_excessive_limit(client: SigilClient):
    with pytest.raises(SigilError, match="Invalid limit"):
        client.get_chain("test-agent", limit=5000)


def test_get_chain_negative_after_seq(client: SigilClient):
    with pytest.raises(SigilError, match="Invalid after_seq"):
        client.get_chain("test-agent", after_seq=-5)


@pytest.mark.asyncio
async def test_async_get_chain_negative_limit():
    async with AsyncSigilClient(api_key=API_KEY, base_url=BASE_URL) as client:
        with pytest.raises(SigilError, match="Invalid limit"):
            await client.get_chain("test-agent", limit=-1)


@pytest.mark.asyncio
async def test_async_get_chain_excessive_limit():
    async with AsyncSigilClient(api_key=API_KEY, base_url=BASE_URL) as client:
        with pytest.raises(SigilError, match="Invalid limit"):
            await client.get_chain("test-agent", limit=9999)


@pytest.mark.asyncio
async def test_async_get_chain_negative_after_seq():
    async with AsyncSigilClient(api_key=API_KEY, base_url=BASE_URL) as client:
        with pytest.raises(SigilError, match="Invalid after_seq"):
            await client.get_chain("test-agent", after_seq=-1)


# --- Audit 3, Fix 3: verify() response field validation ---


@respx.mock
def test_verify_malformed_response(client: SigilClient):
    """Missing valid/chain_valid in verify response → SigilError."""
    rid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    respx.get(f"{BASE_URL}/v1/verify/{rid}").mock(
        return_value=httpx.Response(200, json={"status": "ok"})
    )
    with pytest.raises(SigilError, match="Malformed verify response"):
        client.verify(rid)


@respx.mock
@pytest.mark.asyncio
async def test_async_verify_malformed_response():
    """Async: missing fields in verify response → SigilError."""
    rid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    respx.get(f"{BASE_URL}/v1/verify/{rid}").mock(
        return_value=httpx.Response(200, json={"valid": True})
    )
    async with AsyncSigilClient(api_key=API_KEY, base_url=BASE_URL) as client:
        with pytest.raises(SigilError, match="Malformed verify response"):
            await client.verify(rid)


# --- Audit 3, Fix 4: get_chain() response field validation ---


@respx.mock
def test_get_chain_malformed_response(client: SigilClient):
    """Missing agent_id/length/receipts in chain response → SigilError."""
    agent = "test-agent"
    respx.get(f"{BASE_URL}/v1/chain/{agent}").mock(
        return_value=httpx.Response(200, json={"status": "ok"})
    )
    with pytest.raises(SigilError, match="Malformed chain response"):
        client.get_chain(agent)


@respx.mock
@pytest.mark.asyncio
async def test_async_get_chain_malformed_response():
    """Async: missing fields in chain response → SigilError."""
    agent = "test-agent"
    respx.get(f"{BASE_URL}/v1/chain/{agent}").mock(
        return_value=httpx.Response(200, json={"agent_id": agent})
    )
    async with AsyncSigilClient(api_key=API_KEY, base_url=BASE_URL) as client:
        with pytest.raises(SigilError, match="Malformed chain response"):
            await client.get_chain(agent)


# --- Audit 3, Fix 5: attest() payload size validation ---


@respx.mock
def test_attest_oversized_payload(client: SigilClient):
    """Payload >10KB is rejected client-side without hitting the server."""
    big_payload = {"data": "x" * 11000}
    with pytest.raises(SigilError, match="exceeds maximum size"):
        client.attest("test_action", big_payload)


@respx.mock
def test_attest_none_payload(client: SigilClient):
    """payload=None is accepted and sent as {} in the request."""
    respx.post(f"{BASE_URL}/v1/attest").mock(
        return_value=httpx.Response(200, json={"receipt": MOCK_RECEIPT})
    )
    receipt = client.attest("file_write", None)
    assert receipt.action_type == "file_write"


@pytest.mark.asyncio
async def test_async_attest_oversized_payload():
    """Async: payload >10KB is rejected client-side."""
    async with AsyncSigilClient(api_key=API_KEY, base_url=BASE_URL) as client:
        with pytest.raises(SigilError, match="exceeds maximum size"):
            await client.attest("test_action", {"data": "x" * 11000})
