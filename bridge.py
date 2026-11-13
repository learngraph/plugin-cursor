#!/usr/bin/env python3
"""stdio MCP bridge to the LearnGraph public door.

Cursor talks JSON-RPC on stdin/stdout. This process forwards each message to the
public HTTP door and writes the JSON-RPC responses back as single lines. It asks
the learngraph CLI for an access token and does not refresh the Keycloak grant
itself.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

DEFAULT_URL = "https://app.learngraph.org/service-mcp/v1/public/mcp"
WORKER_PATH = "/service-mcp/v1/mcp"
REFRESH_SKEW_S = 30


def mcp_url() -> str:
    raw = os.environ.get("LEARNGRAPH_MCP_URL", "").strip() or DEFAULT_URL
    parsed = urlparse(raw)
    path = parsed.path.rstrip("/") or "/"
    if path == WORKER_PATH:
        raise SystemExit("LEARNGRAPH_MCP_URL must be the public MCP door, not /service-mcp/v1/mcp.")
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SystemExit("LEARNGRAPH_MCP_URL must be an http(s) URL.")
    return raw


def use_production_login() -> bool:
    return os.environ.get("LEARNGRAPH_MCP_URL", "").strip() == ""


def token_command() -> list[str]:
    if use_production_login():
        return ["learngraph", "--environment", "prod", "auth", "token"]
    return ["learngraph", "auth", "token"]


def login_hint() -> str:
    if use_production_login():
        return "Run: learngraph --environment prod auth login"
    return "Run: learngraph auth login"


class TokenCache:
    def __init__(self) -> None:
        self.token = ""
        self.exp = 0.0

    def bearer(self) -> str:
        if self.token and self.exp - time.time() > REFRESH_SKEW_S:
            return self.token
        self.token = fetch_token()
        self.exp = jwt_exp(self.token)
        return self.token


def fetch_token() -> str:
    try:
        completed = subprocess.run(token_command(), check=False, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise SystemExit(f"learngraph is not installed. {login_hint()}") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise SystemExit(detail or f"Not logged in. {login_hint()}")
    token = completed.stdout.strip()
    if not token or any(ch.isspace() for ch in token):
        raise SystemExit("learngraph auth token did not print a single access token.")
    return token


def jwt_exp(token: str) -> float:
    try:
        payload = token.split(".")[1]
        padding = "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload + padding))
        exp = float(data.get("exp") or 0)
    except (IndexError, ValueError, json.JSONDecodeError, TypeError):
        exp = 0
    if exp <= 0:
        return time.time() + 60
    return exp


def post_message(url: str, message: dict, token: str, protocol_version: str) -> tuple[int, str, str]:
    body = json.dumps(message, separators=(",", ":")).encode()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if protocol_version:
        headers["Mcp-Protocol-Version"] = protocol_version
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read().decode()
            return response.status, response.headers.get("Content-Type", ""), raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode(errors="replace")
        return exc.code, exc.headers.get("Content-Type", ""), raw


def response_messages(content_type: str, raw: str) -> list[dict]:
    if not raw.strip():
        return []
    if "text/event-stream" in content_type:
        messages: list[dict] = []
        data_lines: list[str] = []

        def flush() -> None:
            if not data_lines:
                return
            text = "\n".join(data_lines)
            data_lines.clear()
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                return
            if isinstance(parsed, dict) and parsed.get("jsonrpc"):
                messages.append(parsed)

        for line in raw.splitlines():
            if line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
            elif line == "":
                flush()
        flush()
        return messages
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if isinstance(parsed, dict) and parsed.get("jsonrpc"):
        return [parsed]
    return []


def protocol_from(message: dict) -> str:
    if message.get("id") is None:
        return ""
    result = message.get("result")
    if not isinstance(result, dict):
        return ""
    version = result.get("protocolVersion")
    return version if isinstance(version, str) else ""


def main() -> None:
    url = mcp_url()
    cache = TokenCache()
    protocol_version = ""
    for line in sys.stdin:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            message = json.loads(stripped)
        except json.JSONDecodeError:
            print("ignored non-JSON stdin", file=sys.stderr)
            continue
        if not isinstance(message, dict):
            continue
        status, content_type, raw = post_message(url, message, cache.bearer(), protocol_version)
        if status >= 400:
            request_id = message.get("id")
            if request_id is not None:
                err = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32000, "message": raw.strip() or f"HTTP {status}"},
                }
                sys.stdout.write(json.dumps(err) + "\n")
                sys.stdout.flush()
            else:
                print(raw.strip() or f"HTTP {status}", file=sys.stderr)
            continue
        for outgoing in response_messages(content_type, raw):
            found = protocol_from(outgoing)
            if found:
                protocol_version = found
            sys.stdout.write(json.dumps(outgoing, separators=(",", ":")) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        try:
            sys.stdout.close()
        except Exception:
            pass
        raise SystemExit(0)
