"""Who may reach the web app: this computer by default, or devices holding the network access token.

Loopback serving accepts only loopback peers that address the server by a loopback name, which stops
other websites from reading the app through a rebound DNS name. Network serving (`serve --host
0.0.0.0`) also admits devices that opened the printed access link once; the link sets a cookie.
The token is saved owner-only in the data folder and survives restarts until `serve --new-token`
replaces it, which signs out every device. Every mode refuses cross-site writes and cross-site API reads.
"""

from __future__ import annotations

import hmac
import logging
import os
import re
import secrets
import socket
from dataclasses import dataclass
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import urlencode

from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse, PlainTextResponse, RedirectResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

LOOPBACK_NAMES = frozenset({"localhost"})
WILDCARD_HOSTS = frozenset({"0.0.0.0", "::"})
COOKIE = "voicestudio_access"
QUERY = "access"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
COOKIE_SECONDS = 400 * 86400  # the longest lifetime browsers allow; `serve --new-token` revokes sooner
TOKEN_FILE = "access-token"  # kept in the data folder, next to llm.json
_TOKEN_OK = re.compile(r"[A-Za-z0-9_-]{43}")  # secrets.token_urlsafe(32)
_TOKEN_IN_PATH = re.compile(rf"(?<=[?&]{QUERY}=)[^&\s]+")


@dataclass(frozen=True)
class AccessPolicy:
    """`token` is None for loopback-only serving; set it to admit network devices that present it."""

    token: str | None = None


def new_token() -> str:
    return secrets.token_urlsafe(32)


def is_loopback_host(host: str) -> bool:
    if host.lower() in LOOPBACK_NAMES:
        return True
    try:
        return ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def stored_token(path: Path, renew: bool = False) -> str:
    """The network access token saved in `path`; a new one replaces a missing, invalid or renewed token."""
    if not renew:
        try:
            token = path.read_text(encoding="ascii").strip()
        except (OSError, UnicodeDecodeError):
            token = ""
        if _TOKEN_OK.fullmatch(token):
            return token
    token = new_token()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.unlink(missing_ok=True)  # O_EXCL below: never reuse a leftover file with looser permissions
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)  # owner-only from the first byte
    with os.fdopen(fd, "w", encoding="ascii") as fh:
        fh.write(token)
    os.replace(tmp, path)
    return token


def policy_for_bind(host: str, token_path: Path) -> AccessPolicy:
    """Loopback binds stay local; any other bind address admits devices holding the saved token."""
    return AccessPolicy() if is_loopback_host(host) else AccessPolicy(token=stored_token(token_path))


def lan_address(bind_host: str) -> str:
    """Best guess at the address other devices use. Connecting a UDP socket sends no packets."""
    if bind_host not in WILDCARD_HOSTS:
        return f"[{bind_host}]" if ":" in bind_host else bind_host
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 80))
            return str(s.getsockname()[0])
    except OSError:
        return "<this-computer's-IP>"


def access_link(bind_host: str, port: int, token: str) -> str:
    return f"http://{lan_address(bind_host)}:{port}/?{urlencode({QUERY: token})}"


def _same_token(candidate: str | None, token: str) -> bool:
    return candidate is not None and hmac.compare_digest(candidate.encode(), token.encode())


def safe_location(path: str, query: list[tuple[str, str]]) -> str:
    """Same-site redirect target with the token removed; never a protocol-relative URL."""
    target = path if path.startswith("/") and not path.startswith("//") else "/"
    rest = [(k, v) for k, v in query if k != QUERY]
    return target + (f"?{urlencode(rest)}" if rest else "")


def _forbidden(conn: HTTPConnection, status: int, message: str) -> Response:
    if conn.url.path.startswith("/api/"):
        return JSONResponse({"detail": message}, status_code=status)
    return PlainTextResponse(message, status_code=status)


def decide(conn: HTTPConnection, policy: AccessPolicy) -> Response | None:
    """None admits the request; otherwise the response that refuses it."""
    method = conn.scope.get("method", "GET")
    unsafe = conn.scope["type"] == "websocket" or method not in SAFE_METHODS
    origin = conn.headers.get("origin")
    scheme = {"ws": "http", "wss": "https"}.get(conn.url.scheme, conn.url.scheme)
    if unsafe and origin and origin != f"{scheme}://{conn.url.netloc}":
        return _forbidden(conn, 403, "Open this page from the Voice Studio app itself.")
    if conn.headers.get("sec-fetch-site") == "cross-site" and (unsafe or conn.url.path.startswith("/api/")):
        return _forbidden(conn, 403, "Cross-site requests are not allowed.")

    peer = conn.client.host if conn.client else ""
    if is_loopback_host(conn.url.hostname or "") and is_loopback_host(peer):
        return None
    if policy.token is None:
        return _forbidden(conn, 403, "Voice Studio only accepts connections from this computer at http://127.0.0.1.")
    if _same_token(conn.cookies.get(COOKIE), policy.token):
        return None
    if method == "GET" and conn.scope["type"] == "http" and _same_token(conn.query_params.get(QUERY), policy.token):
        response = RedirectResponse(safe_location(conn.url.path, conn.query_params.multi_items()), status_code=303)
        response.set_cookie(COOKIE, policy.token, max_age=COOKIE_SECONDS, path="/", httponly=True, samesite="strict")
        return response
    return _forbidden(conn, 401, "Open the access link printed by `voicestudio serve` on this device.")


class LocalAccess:
    """Applies the AccessPolicy stored on `app.state.access` (loopback-only when unset)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return
        conn = HTTPConnection(scope)
        state = scope["app"].state if "app" in scope else None
        refusal = decide(conn, getattr(state, "access", None) or AccessPolicy())
        if refusal is None:
            await self.app(scope, receive, send)
        elif scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
        else:
            await refusal(scope, receive, send)


class RedactAccessToken(logging.Filter):
    """Keeps the access token out of uvicorn's request log lines."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(_TOKEN_IN_PATH.sub("REDACTED", a) if isinstance(a, str) else a for a in record.args)
        return True
