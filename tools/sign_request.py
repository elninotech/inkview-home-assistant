#!/usr/bin/env python3
"""Sign an auth/token request against a running InkView HA integration.

Usage:
  python tools/sign_request.py \\
      --base-url https://your-ha-host:8123 \\
      --instance-id <hex from config entry> \\
      --secret <64 hex chars>

Prints the bearer JWT (and expiry) on success. Pipe it into curl:

  TOKEN=$(python tools/sign_request.py ... | tail -1)
  curl -H "Authorization: Bearer $TOKEN" \\
       https://your-ha-host:8123/api/inkview/v1/states/sensor.solar

TLS notes:
  Self-signed dev certs must be trusted properly — add the cert/CA to your
  system trust store (e.g. `security add-trusted-cert` on macOS, the
  `ca-certificates` package on Linux) or point Python at it via the
  SSL_CERT_FILE env var. We intentionally do NOT expose an --insecure flag:
  disabling verification turns the bearer flow into a free MITM oracle for
  anyone on the network path.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import secrets
import sys
import time
import urllib.error
import urllib.request


def sign(secret: bytes, body: bytes, ts: str, nonce: str) -> str:
    msg = body + b"|" + ts.encode("ascii") + b"|" + nonce.encode("ascii")
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--base-url", required=True, help="e.g. https://your-ha-host:8123")
    ap.add_argument("--instance-id", required=True, help="hex string from the config entry")
    ap.add_argument("--secret", required=True, help="64 hex chars")
    args = ap.parse_args()

    try:
        secret = bytes.fromhex(args.secret.strip().lower())
    except ValueError:
        print("secret must be 64 hex chars", file=sys.stderr)
        return 2
    if len(secret) != 32:
        print("secret must decode to 32 bytes", file=sys.stderr)
        return 2

    ts = str(int(time.time()))
    nonce = secrets.token_urlsafe(12)
    signed_payload = args.instance_id.encode("ascii")
    sig = sign(secret, signed_payload, ts, nonce)

    payload = {
        "instance_id": args.instance_id,
        "ts": ts,
        "nonce": nonce,
        "sig": sig,
    }
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{args.base_url.rstrip('/')}/api/inkview/v1/auth/token",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode(errors='replace')}", file=sys.stderr)
        return 1
    except Exception as e:  # noqa: BLE001
        print(f"request failed: {e}", file=sys.stderr)
        return 1

    print(json.dumps(data, indent=2), file=sys.stderr)
    print(data.get("access_token", ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
