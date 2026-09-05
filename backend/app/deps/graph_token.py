"""Resolve a Microsoft Graph delegated access token.

TODO(MSAL): CaseForge has no user OAuth2 today. Replace this dependency with the
MSAL login that obtains a delegated token (scope Calendars.ReadBasic) and pass it here.
Until then, accept Authorization: Bearer or MS_GRAPH_ACCESS_TOKEN for local smoke tests.
"""

from fastapi import Header, HTTPException, status

from app.services.graph_auth import normalize_access_token
from app.config import settings


def get_graph_access_token(authorization: str | None = Header(default=None)) -> str:
    if authorization:
        token = normalize_access_token(authorization)
        if token:
            return token
    token = normalize_access_token(settings.ms_graph_access_token)
    if token:
        return token
    raise HTTPException(
        status.HTTP_501_NOT_IMPLEMENTED,
        detail=(
            "Calendario QC: Microsoft Graph no está conectado. "
            "TODO: integrar MSAL (Calendars.ReadBasic). Mientras tanto define "
            "MS_GRAPH_ACCESS_TOKEN o envía Authorization: Bearer."
        ),
    )
