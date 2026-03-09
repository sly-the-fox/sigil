"""Sigil Python SDK — thin sync + async client for the Sigil REST API."""

from __future__ import annotations

import re as _re_mod
import uuid as _uuid_mod
from dataclasses import dataclass, field
from typing import Any

import httpx

_AGENT_ID_RE = _re_mod.compile(r"^[a-zA-Z0-9_\-\.]{1,128}$")

_MAX_ERROR_BODY = 200


class SigilError(Exception):
    """Base exception for Sigil API errors."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class Receipt:
    id: str
    seq: int
    agent_id: str
    action_type: str
    receipt_hash: str
    signature: str
    timestamp: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VerifyResult:
    valid: bool
    chain_valid: bool
    receipt_id: str


@dataclass(frozen=True)
class Chain:
    agent_id: str
    length: int
    receipts: list[Receipt]


def _handle_response(resp: httpx.Response) -> dict:
    """Raise SigilError on non-2xx responses, otherwise return JSON."""
    if resp.status_code >= 400:
        detail = ""
        try:
            detail = resp.json().get("detail", "")
        except Exception:
            detail = resp.text[:_MAX_ERROR_BODY]
        raise SigilError(f"API error {resp.status_code}: {detail}", resp.status_code)
    try:
        return resp.json()
    except Exception as exc:
        raise SigilError("Invalid JSON in API response") from exc


def _build_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


def _parse_receipt(r: dict) -> Receipt:
    try:
        _uuid_mod.UUID(r["id"])
    except (ValueError, KeyError) as exc:
        raise SigilError(f"Malformed receipt: invalid or missing id: {r.get('id')}") from exc
    seq = r.get("seq")
    if not isinstance(seq, int) or seq < 0:
        raise SigilError(f"Malformed receipt: seq must be a non-negative integer, got {seq!r}")
    for field_name in ("receipt_hash", "signature"):
        val = r.get(field_name)
        if not isinstance(val, str) or not val:
            raise SigilError(f"Malformed receipt: {field_name} must be a non-empty string")
    for field_name in ("agent_id", "action_type", "timestamp"):
        if field_name not in r:
            raise SigilError(f"Malformed receipt: missing required field '{field_name}'")
    return Receipt(
        id=r["id"],
        seq=r["seq"],
        agent_id=r["agent_id"],
        action_type=r["action_type"],
        receipt_hash=r["receipt_hash"],
        signature=r["signature"],
        timestamp=r["timestamp"],
        payload=r.get("payload", {}),
    )


class SigilClient:
    """Synchronous Sigil API client."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.sigil-notary.dev",
        timeout: float = 10.0,
    ):
        self._client = httpx.Client(
            base_url=base_url, headers=_build_headers(api_key), timeout=timeout
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def attest(self, action_type: str, payload: dict[str, Any] | None = None) -> Receipt:
        resp = self._client.post(
            "/v1/attest", json={"action_type": action_type, "payload": payload or {}}
        )
        data = _handle_response(resp)
        return _parse_receipt(data["receipt"])

    def verify(self, receipt_id: str) -> VerifyResult:
        try:
            _uuid_mod.UUID(receipt_id)
        except (ValueError, AttributeError) as exc:
            raise SigilError(
                f"Invalid receipt_id: must be a valid UUID, got {receipt_id!r}"
            ) from exc
        resp = self._client.get(f"/v1/verify/{receipt_id}")
        data = _handle_response(resp)
        return VerifyResult(
            valid=data["valid"], chain_valid=data["chain_valid"], receipt_id=receipt_id
        )

    def get_chain(self, agent_id: str, limit: int = 100, after_seq: int = 0) -> Chain:
        if not _AGENT_ID_RE.match(agent_id):
            raise SigilError(
                f"Invalid agent_id: must match {_AGENT_ID_RE.pattern}, got {agent_id!r}"
            )
        resp = self._client.get(
            f"/v1/chain/{agent_id}", params={"limit": limit, "after_seq": after_seq}
        )
        data = _handle_response(resp)
        receipts = [_parse_receipt(r) for r in data["receipts"]]
        return Chain(agent_id=data["agent_id"], length=data["length"], receipts=receipts)


class AsyncSigilClient:
    """Asynchronous Sigil API client."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.sigil-notary.dev",
        timeout: float = 10.0,
    ):
        self._client = httpx.AsyncClient(
            base_url=base_url, headers=_build_headers(api_key), timeout=timeout
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.aclose()

    async def attest(self, action_type: str, payload: dict[str, Any] | None = None) -> Receipt:
        resp = await self._client.post(
            "/v1/attest", json={"action_type": action_type, "payload": payload or {}}
        )
        data = _handle_response(resp)
        return _parse_receipt(data["receipt"])

    async def verify(self, receipt_id: str) -> VerifyResult:
        try:
            _uuid_mod.UUID(receipt_id)
        except (ValueError, AttributeError) as exc:
            raise SigilError(
                f"Invalid receipt_id: must be a valid UUID, got {receipt_id!r}"
            ) from exc
        resp = await self._client.get(f"/v1/verify/{receipt_id}")
        data = _handle_response(resp)
        return VerifyResult(
            valid=data["valid"], chain_valid=data["chain_valid"], receipt_id=receipt_id
        )

    async def get_chain(self, agent_id: str, limit: int = 100, after_seq: int = 0) -> Chain:
        if not _AGENT_ID_RE.match(agent_id):
            raise SigilError(
                f"Invalid agent_id: must match {_AGENT_ID_RE.pattern}, got {agent_id!r}"
            )
        resp = await self._client.get(
            f"/v1/chain/{agent_id}", params={"limit": limit, "after_seq": after_seq}
        )
        data = _handle_response(resp)
        receipts = [_parse_receipt(r) for r in data["receipts"]]
        return Chain(agent_id=data["agent_id"], length=data["length"], receipts=receipts)
