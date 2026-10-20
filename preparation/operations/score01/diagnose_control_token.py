#!/usr/bin/env python3
"""Non-mutating diagnostic for the live dashboard control token path."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from urllib.error import HTTPError
from urllib.request import Request, urlopen


base = Path(__file__).resolve().parent
file_token = (base / "state" / "control-token").read_text(encoding="ascii").strip()
page = (base / "public" / "index.html").read_text(encoding="utf-8")
match = re.search(r'<meta name="summit-control-token" content="([^"]*)">', page)
page_token = match.group(1) if match else ""


def fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12] if value else "EMPTY"


request = Request(
    "http://127.0.0.1:8766/api/control",
    data=json.dumps({"action": "diagnostic-only"}).encode("utf-8"),
    headers={
        "Content-Type": "application/json",
        "Origin": "http://127.0.0.1:8766",
        "X-Summit-Control-Token": page_token,
    },
    method="POST",
)
try:
    urlopen(request, timeout=5)
except HTTPError as error:
    response_status = error.code
else:
    response_status = 200

print(
    {
        "file_token": fingerprint(file_token),
        "page_token": fingerprint(page_token),
        "tokens_match": file_token == page_token,
        "non_mutating_probe_status": response_status,
    }
)
