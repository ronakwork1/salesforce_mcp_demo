"""Structured audit log. Records what was asked and how much came back, never personal data values."""
import hashlib
import hmac
import json
import logging
import os
import secrets
import sys
import time

_logger = logging.getLogger("sf_mcp.audit")
if not _logger.handlers:
    # stdout is the MCP stdio channel: audit output MUST go to a file or stderr.
    path = os.environ.get("SF_AUDIT_LOG")
    handler = logging.FileHandler(path) if path else logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    _logger.addHandler(handler)
    _logger.setLevel(logging.INFO)
    _logger.propagate = False  # don't let the SDK's root handler print each entry a second time


# Keyed hash: plain SHA-256 of a short value like a surname is trivially brute-forced.
# Set SF_AUDIT_KEY to correlate entries across restarts; otherwise a random per-process key is used.
_KEY = (os.environ.get("SF_AUDIT_KEY") or secrets.token_hex(32)).encode()


def _h(value) -> str:
    return hmac.new(_KEY, str(value).encode(), hashlib.sha256).hexdigest()[:10]


def record(tool: str, params: dict, rows: int | None, ok: bool = True, error: str | None = None) -> None:
    # Param *names* are logged; values are HMAC'd so personal data (names, emails) never lands in logs.
    hashed = {
        k: _h(v) for k, v in params.items() if v is not None
    }
    _logger.info(json.dumps({"ts": time.time(), "tool": tool, "params": hashed, "rows": rows, "ok": ok, "error": error}))
