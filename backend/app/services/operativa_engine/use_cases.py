"""HN → behavior → use case / scenario. Identified before device expansion.

A use case is an independent functional scenario, not a cartesian of every
listed attribute. Interaction points, MDP catalogues, EPCs and ofertas are not
use cases by themselves.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.schemas.coverage_matrix import CoverageMatrixRow

_VOD_RE = re.compile(
    r"suscripci[oó]n\s+desde\s+(?:vod|v\.?o\.?d\.?|video\s*on\s*demand|contenido(?:\s+vod)?)",
    re.IGNORECASE,
)
_LIVE_RE = re.compile(
    r"suscripci[oó]n\s+desde\s+(?:live|en\s+vivo|player\s+live|tv\s+en\s+vivo)",
    re.IGNORECASE,
)
_NEGATIVE_TITLE_RE = re.compile(
    r"\bno\s+(?:se\s+)?(?:debe\s+)?(?:ser\s+)?(?:mostrad|mostrar|publicar|liberar|"
    r"habilitar|implementar|encontrar|incluir|permitir)\b|"
    r"\bbaja del canal\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class FunctionalUseCase:
    key: str
    title: str | None
    user: str | None
    access_path: str | None
    polarity: str | None
    reason: str


def extract_use_cases(row: CoverageMatrixRow) -> list[FunctionalUseCase]:
    """Scenarios required by the behavior. Empty evidence → one default use case."""
    blob = "\n".join(
        part
        for part in (row.evidence, row.test_data, row.behavior_title, row.reasoning)
        if part
    )
    users = [item.strip() for item in row.relevant_users if item and item.strip()]
    scenarios: list[FunctionalUseCase] = []

    independent_users = _independent_user_scenarios(users, row.behavior_title or "")
    access_paths = _independent_access_paths(blob)

    if independent_users:
        scenarios.extend(independent_users)
    if access_paths:
        scenarios.extend(access_paths)

    if not scenarios:
        user = users[0] if len(users) == 1 else None
        return [
            FunctionalUseCase(
                key="default",
                title=None,
                user=user,
                access_path=None,
                polarity=None,
                reason=(
                    "Un escenario por comportamiento: la HN no declara casos de uso "
                    "independientes. Canal / Punto de interacción y MDP no multiplican TCs."
                ),
            )
        ]
    return scenarios


def _independent_user_scenarios(users: list[str], title: str) -> list[FunctionalUseCase]:
    """Split only when the matrix distinguished user types with different access.

    A globally negative behavior (baja / no publicar) is one scenario for every user.
    """
    if len(users) < 2:
        return []
    if _NEGATIVE_TITLE_RE.search(title or ""):
        return []
    lowered = {item.casefold() for item in users}
    has_sub = any("suscrit" in item and "no suscrit" not in item for item in lowered)
    has_unsub = any("no suscrit" in item for item in lowered)
    if not (has_sub and has_unsub):
        return []
    rows: list[FunctionalUseCase] = []
    for user in users:
        unsub = "no suscrit" in user.casefold()
        if unsub:
            polarity = "negative"
            reason = (
                "Caso de uso independiente: usuario no suscrito con expectativa de "
                "restricción/ausencia de acceso."
            )
        else:
            polarity = "positive"
            reason = (
                "Caso de uso independiente: usuario suscrito con expectativa de acceso."
            )
        rows.append(
            FunctionalUseCase(
                key="user-" + re.sub(r"[^a-z0-9]+", "-", user.lower()).strip("-")[:40],
                title=f"Usuario {user}",
                user=user,
                access_path=None,
                polarity=polarity,
                reason=reason,
            )
        )
    return rows


def _independent_access_paths(blob: str) -> list[FunctionalUseCase]:
    vod = bool(_VOD_RE.search(blob or ""))
    live = bool(_LIVE_RE.search(blob or ""))
    if not (vod and live):
        return []
    return [
        FunctionalUseCase(
            key="access-vod",
            title="Suscripción desde VOD",
            user=None,
            access_path="VOD",
            polarity="positive",
            reason="La HN declara suscripción desde VOD como escenario de acceso independiente.",
        ),
        FunctionalUseCase(
            key="access-live",
            title="Suscripción desde Live",
            user=None,
            access_path="Live",
            polarity="positive",
            reason="La HN declara suscripción desde Live como escenario de acceso independiente.",
        ),
    ]
