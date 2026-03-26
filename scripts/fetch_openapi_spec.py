#!/usr/bin/env python3
"""Fetch and store the gateway OpenAPI specification."""

import json
import sys
from pathlib import Path

import httpx

GATEWAY_URL = "http://10.0.0.35:8000"
OUTPUT = Path(__file__).parent.parent / "docs" / "openapi_spec.json"


def main():
    try:
        resp = httpx.get(f"{GATEWAY_URL}/openapi.json", timeout=10)
        resp.raise_for_status()
    except httpx.ConnectError:
        print(f"ERROR: Cannot reach gateway at {GATEWAY_URL}", file=sys.stderr)
        sys.exit(1)

    spec = resp.json()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(spec, indent=2))
    print(f"Saved OpenAPI spec ({len(spec.get('paths', {}))} endpoints) to {OUTPUT}")


if __name__ == "__main__":
    main()
