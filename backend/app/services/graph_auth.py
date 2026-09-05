"""Normalize Graph tokens and choose /me vs /users/{mailbox} from JWT claims.

Does not verify the JWT signature; claims are only used to pick the Graph path
and to explain 403s. Never log the raw token.
"""

from __future__ import annotations

import base64
import json

from fastapi import HTTPException, status

from app.config import settings

GRAPH_SCOPE = "https://graph.microsoft.com/.default"


def normalize_access_token(raw: str | None) -> str:
    token = (raw or "").strip().strip('"').strip("'")
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    return token


def decode_jwt_claims(token: str) -> dict:
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1]
    padding = "=" * (-len(payload) % 4)
    try:
        data = json.loads(base64.urlsafe_b64decode(payload + padding))
    except (ValueError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def token_scopes(claims: dict) -> list[str]:
    scp = claims.get("scp") or ""
    if isinstance(scp, str) and scp.strip():
        return scp.split()
    roles = claims.get("roles") or []
    if isinstance(roles, list):
        return [str(role) for role in roles]
    return []


def is_app_only_token(claims: dict) -> bool:
    if claims.get("idtyp") == "app":
        return True
    roles = claims.get("roles") or []
    scp = claims.get("scp")
    return bool(roles) and not scp


def has_calendar_access(claims: dict) -> bool:
    blob = " ".join(token_scopes(claims)).lower()
    return "calendars.read" in blob


def calendar_view_path(claims: dict, mailbox: str | None) -> str:
    """Relative Graph path for calendarView."""
    if is_app_only_token(claims):
        box = (mailbox or "").strip()
        if not box:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=(
                    "El token de Graph es de aplicación (client credentials), no de usuario. "
                    "/me/calendarView no funciona con ese token. Define MS_GRAPH_MAILBOX "
                    "con el UPN del buzón de QC (ej. usuario@dominio.com) y concede permiso "
                    "de aplicación Calendars.Read (Calendars.ReadBasic es solo delegado)."
                ),
            )
        return f"/users/{box}/calendarView"
    return "/me/calendarView"


def describe_token(claims: dict) -> str:
    kind = "aplicación" if is_app_only_token(claims) else "usuario (delegado)"
    scopes = ", ".join(token_scopes(claims)) or "(ninguno en el JWT)"
    aud = claims.get("aud")
    return f"tipo={kind}; aud={aud}; scopes={scopes}"


async def acquire_client_credentials_token(client: object) -> str | None:
    """Return an app token when Azure app credentials are configured. None otherwise."""
    tenant = settings.ms_tenant_id.strip()
    client_id = settings.ms_client_id.strip()
    secret = settings.ms_client_secret.strip()
    if not (tenant and client_id and secret):
        return None
    url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    response = await client.post(
        url,
        data={
            "client_id": client_id,
            "client_secret": secret,
            "grant_type": "client_credentials",
            "scope": GRAPH_SCOPE,
        },
        timeout=20.0,
    )
    response.raise_for_status()
    data = response.json()
    return normalize_access_token(data.get("access_token") or "")
