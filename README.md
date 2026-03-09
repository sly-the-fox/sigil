# Sigil Notary

[![PyPI version](https://img.shields.io/pypi/v/sigil-notary)](https://pypi.org/project/sigil-notary/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)

**Tamper-evident audit trails for AI agents.**

Sigil gives AI agents cryptographically signed, hash-chained audit trails via the [Model Context Protocol](https://modelcontextprotocol.io). Every action gets a verifiable receipt with an Ed25519 signature and SHA-256 chain link.

## Install

```bash
pip install sigil-notary
```

## MCP Server Usage

Sigil ships as an MCP server that any MCP-compatible AI agent can use natively.

### Claude Code

Add to your `.claude/settings.json` or project MCP config:

```json
{
  "mcpServers": {
    "sigil": {
      "command": "uvx",
      "args": ["sigil-notary"],
      "env": {
        "SIGIL_API_KEY": "sg_your_key_here",
        "SIGIL_API_URL": "https://api.sigil-notary.dev"
      }
    }
  }
}
```

### Available MCP Tools

| Tool | Description |
|------|-------------|
| `attest_action` | Record an action and get a signed, hash-chained receipt |
| `verify_receipt` | Verify a receipt's signature and chain integrity |
| `get_chain` | Retrieve the full audit trail for the current agent |

## Python SDK

For programmatic access, use the Python client directly:

```python
from sigil import SigilClient

client = SigilClient(api_key="sg_your_key_here")

# Record an action
receipt = client.attest(
    action_type="file_write",
    payload={"path": "/app/config.yaml", "summary": "Updated DB connection string"}
)
print(f"Receipt #{receipt.seq}: {receipt.receipt_hash[:16]}...")

# Verify a receipt
result = client.verify(receipt.id)
print(f"Valid: {result.valid}, Chain intact: {result.chain_valid}")

# Get the audit trail
chain = client.get_chain(agent_id="my-agent")
for r in chain.receipts:
    print(f"  #{r.seq} {r.action_type} — {r.timestamp}")
```

### Async Client

```python
from sigil.client import AsyncSigilClient

async with AsyncSigilClient(api_key="sg_your_key_here") as client:
    receipt = await client.attest("api_request", {"endpoint": "/users"})
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SIGIL_API_KEY` | Yes | — | API key for authentication |
| `SIGIL_API_URL` | No | `http://localhost:8100` | Notary API base URL |
| `SIGIL_AGENT_ID` | No | from key | Agent identity for chain queries |

## Development

```bash
git clone https://github.com/sly-the-fox/sigil.git
cd sigil
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check .
```

## Links

- **Documentation:** https://sigil-notary.dev/docs
- **Hosted Service:** https://sigil-notary.dev
- **Issues:** https://github.com/sly-the-fox/sigil/issues
- **Changelog:** [CHANGELOG.md](CHANGELOG.md)

## License

[MIT](LICENSE)
