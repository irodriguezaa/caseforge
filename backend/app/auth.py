"""In-memory users from QC_USERS and HMAC-signed session cookies. No database."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from enum import StrEnum

COOKIE_NAME = "qc_session"
SESSION_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
VALID_ROLES = frozenset({"jefe", "lider", "tester", "consulta"})


class Role(StrEnum):
    JEFE = "jefe"
    LIDER = "lider"
    TESTER = "tester"
    CONSULTA = "consulta"


@dataclass(frozen=True)
class AuthUser:
    email: str
    role: Role


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def session_secret() -> str:
    return os.getenv("QC_SESSION_SECRET", "")


def cookie_secure() -> bool:
    return os.getenv("QC_COOKIE_SECURE", "").lower() in {"1", "true", "yes"}


def parse_users(raw: str | None = None) -> dict[str, tuple[Role, str]]:
    """Map lowercase email -> (role, password). Format: email:role:password,..."""
    blob = raw if raw is not None else os.getenv("QC_USERS", "")
    users: dict[str, tuple[Role, str]] = {}
    for chunk in blob.split(","):
        entry = chunk.strip()
        if not entry:
            continue
        parts = entry.split(":", 2)
        if len(parts) != 3:
            continue
        email, role_name, password = parts[0].strip().lower(), parts[1].strip().lower(), parts[2]
        if not email or not password or role_name not in VALID_ROLES:
            continue
        users[email] = (Role(role_name), password)
    return users


def authenticate(email: str, password: str) -> AuthUser | None:
    users = parse_users()
    record = users.get(email.strip().lower())
    if record is None:
        return None
    role, expected = record
    if not hmac.compare_digest(expected, password):
        return None
    return AuthUser(email=email.strip().lower(), role=role)


def sign_session(user: AuthUser) -> str:
    secret = session_secret()
    if not secret:
        raise RuntimeError("QC_SESSION_SECRET is not set.")
    payload = json.dumps(
        {"e": user.email, "r": user.role.value, "exp": int(time.time()) + SESSION_MAX_AGE_SECONDS},
        separators=(",", ":"),
    ).encode("utf-8")
    body = _b64encode(payload)
    digest = hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{digest}"


def read_session(token: str | None) -> AuthUser | None:
    if not token or "." not in token:
        return None
    secret = session_secret()
    if not secret:
        return None
    body, _, digest = token.partition(".")
    expected = hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, digest):
        return None
    try:
        payload = json.loads(_b64decode(body))
        if int(payload["exp"]) < time.time():
            return None
        role = payload["r"]
        if role not in VALID_ROLES:
            return None
        return AuthUser(email=str(payload["e"]).lower(), role=Role(role))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
