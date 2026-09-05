"""Microsoft Graph client for Outlook calendar.

Delegated tokens (Calendars.ReadBasic) use /me/calendarView.
App-only tokens (Calendars.Read) use /users/{MS_GRAPH_MAILBOX}/calendarView.
"""

from __future__ import annotations

import httpx

from app.config import settings
from app.services.graph_auth import (
    calendar_view_path,
    decode_jwt_claims,
    describe_token,
    has_calendar_access,
    is_app_only_token,
)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


async def get_calendar_view(access_token: str, start_iso: str, end_iso: str) -> list[dict]:
    claims = decode_jwt_claims(access_token)
    path = calendar_view_path(claims, getattr(settings, "ms_graph_mailbox", "") or "")
    url = f"{GRAPH_BASE}{path}"
    params = {
        "startDateTime": start_iso,
        "endDateTime": end_iso,
        "$select": "id,subject,start,end,location,webLink",
        "$top": "50",
    }
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Prefer": f'outlook.timezone="{settings.ms_graph_timezone}"',
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(url, params=params, headers=headers)
        if response.status_code == 403:
            hint = _forbidden_hint(claims, path)
            try:
                payload = response.json()
                graph_msg = ((payload.get("error") or {}) if isinstance(payload, dict) else {}).get(
                    "message"
                )
            except ValueError:
                graph_msg = None
            detail = graph_msg or "Access is denied."
            raise httpx.HTTPStatusError(
                f"{detail} {hint} ({describe_token(claims)})",
                request=response.request,
                response=response,
            )
        response.raise_for_status()
        data = response.json()

    return data.get("value") or []


def _forbidden_hint(claims: dict, path: str) -> str:
    if is_app_only_token(claims) and path.startswith("/me"):
        return "Usa MS_GRAPH_MAILBOX y permiso de aplicación Calendars.Read."
    if is_app_only_token(claims) and not has_calendar_access(claims):
        return (
            "El token de app no trae Calendars.Read. En Azure: API permissions → "
            "Application → Calendars.Read → Grant admin consent. ReadBasic no aplica a apps."
        )
    if not is_app_only_token(claims) and not has_calendar_access(claims):
        return (
            "El token de usuario no trae Calendars.ReadBasic. En Graph Explorer: "
            "Modify permissions → Consent → copia un Access token nuevo."
        )
    return "El buzón no permite esta app o falta consentimiento de administrador."
