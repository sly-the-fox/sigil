# Contributing to Sigil Notary

Thank you for your interest in contributing.

## Getting Started

```bash
git clone https://github.com/sly-the-fox/sigil.git
cd sigil
pip install -e ".[dev]"
```

## Development

```bash
# Run tests
pytest -v

# Lint
ruff check .

# Format
ruff format .
```

## Pull Requests

1. Fork the repo and create a branch from `main`
2. Add tests for new functionality
3. Ensure `pytest` and `ruff check` pass
4. Submit a PR with a clear description

## Issues

Use the issue templates for bug reports and feature requests. For questions, start a discussion.

## Code Style

- We use `ruff` for linting and formatting
- Target Python 3.12+
- Keep functions focused and well-named
- Add docstrings to public APIs
