# Changelog

All notable changes to this project will be documented in this file.

## [0.2.1] - 2026-03-09

### Fixed
- `mcp` is now a base dependency — `uvx sigil-notary` and `pip install sigil-notary` both work out of the box without needing `pip install sigil-notary[mcp]`
- Added Smithery registry config (`smithery.yaml`) and MCP server card

## [0.2.0] - 2026-03-08

### Added
- Python SDK (`sigil.client`) with sync and async clients
- Input validation for UUIDs and agent IDs

### Changed
- Package renamed from `sigil` to `sigil-notary` for PyPI clarity

## [0.1.0] - 2026-02-23

### Added
- Initial MCP server with `attest_action`, `verify_receipt`, `get_chain` tools
- Ed25519-signed, SHA-256 hash-chained audit trails
- API key authentication
- Structured error handling with recovery hints
