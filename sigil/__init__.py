"""Sigil — Cryptographic audit trails for AI agents."""

from sigil.client import AsyncSigilClient, Chain, Receipt, SigilClient, SigilError, VerifyResult

__version__ = "0.2.0"
__all__ = ["SigilClient", "AsyncSigilClient", "Receipt", "VerifyResult", "Chain", "SigilError"]
