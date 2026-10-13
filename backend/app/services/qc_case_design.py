"""One QC design call per technical epic.

Crosses the business User Story (CRN) with every Technical Story scenario (COV).
The model decides which scenarios are not QC. Jira text is sent complete.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from app.config import settings
from app.schemas.case_generation import CandidateStep, CoverageUnit, GeneratedCaseCandidate

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).with_name("qc_system_prompt.md")
_CONTEXT_TOKEN_LIMIT = 80_000
_VALIDATION_GAP = "sin cobertura (falla de validación)"
_EXCLUSION_MOTIVOS = {
    "telemetria",
    "tecnico_interno",
    "accion_desarrollo",
    "medicion_tecnica",
    "no_reproducible",
    "otra_epica",
}
_MODEL_SKIP = (
    "mini",
    "nano",
    "audio",
    "realtime",
    "transcribe",
    "tts",
    "image",
    "embed",
    "moderation",
    "search",
    "whisper",
    "dall",
)
_model_cache: tuple[float, list[str]] | None = None
_TIPOS = {"HPP", "HPA", "TTF", "ERG", "E2E"}
_BRECHAS = {"ninguna", "sin_tecnico", "sin_negocio", "implicito"}
_SITUACIONES = {"cruce", "solo_negocio", "solo_tecnico"}
_FORBIDDEN_STEP = re.compile(
    r"implementar|desplegar|configurar la llave|actualizar assets|consumir\s+api|ejecutar servicio|revisar logs",
    re.IGNORECASE,
)
_HEADER = re.compile(
    r"^\s*(Background|Feature|Scenario Outline|Scenario|Escenario esquem[aá]tico|Escenario|Esquema del escenario)\s*:\s*(.*)$",
    re.IGNORECASE,
)
_BUSINESS_PROJECTS = {"TBRFRE", "TBRF", "BRF", "BRFRE"}

_DEVICE_ROWS: dict[str, tuple[str, str, str]] = {
    "WEB": ("WEB", "Mediana", "Cursor / teclado (WEB táctil: táctil)"),
    "WIN/XBOX": ("WIN", "Mediana", "Cursor / teclado"),
    "ADR": ("ADR (móvil)", "Chica", "Táctil"),
    "IOS": ("iOS", "Chica", "Táctil"),
    "TVOS": ("tvOS", "Grande", "Control remoto"),
    "ROKU": ("Roku", "Grande", "Control remoto"),
    "FIRETV": ("FireTV", "Grande", "Control remoto"),
    "KEPLER": ("Kepler", "Grande", "Control remoto"),
    "ADT": ("ADT", "Grande", "Control remoto"),
    "AAF EVOLUTIVO": ("AAF (STV)", "Grande", "Control remoto"),
    "AAF LEGACY": ("AAF (STV)", "Grande", "Control remoto"),
    "COSHIP9085": ("Coship 9085", "Grande", "Control remoto"),
    "STB IPTV": ("AAF (STV)", "Grande", "Control remoto"),
    "IPTV AOSP": ("AAF (STV)", "Grande", "Control remoto"),
}


class LlmQuotaError(RuntimeError):
    """The provider has no credits. The run must stop."""


@dataclass
class DeviceContext:
    dispositivo: str
    grupo: str
    modo: str
    region: str
    metodos: str


@dataclass
class CrnItem:
    crn_id: str
    title: str
    text: str
    story_key: str = ""


@dataclass
class CovItem:
    cov_id: str
    story_key: str
    title: str
    gherkin: str
    inventory_ids: list[str] = field(default_factory=list)


@dataclass
class EpicPacket:
    epic_key: str
    epic_title: str
    has_user_story: bool
    user_story_key: str
    user_story_title: str
    user_story_body: str
    crns: list[CrnItem]
    stories: list[dict[str, Any]]
    covs: list[CovItem]
    user_stories: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class DesignOutcome:
    candidates: list[GeneratedCaseCandidate]
    ledger: list[dict[str, Any]]
    cruce_rows: list[dict[str, Any]]
    warnings: list[str]
    batches: list[dict[str, Any]]
    accounted_ids: set[str]
    summary: str


def account_model_ids() -> list[str]:
    """Model ids enabled on the account. Empty when the listing call fails."""
    global _model_cache
    if _model_cache and time.time() - _model_cache[0] < 3600:
        return list(_model_cache[1])
    if not (settings.openai_api_key or "").strip():
        return []
    url = settings.openai_base_url.rstrip("/") + "/models"
    try:
        with httpx.Client(timeout=20) as client:
            response = client.get(url, headers={"Authorization": f"Bearer {settings.openai_api_key}"})
        if response.status_code != 200:
            return []
        names = [
            str(item.get("id") or "").strip()
            for item in (response.json().get("data") or [])
            if str(item.get("id") or "").strip()
        ]
    except Exception:
        logger.warning("No se pudo listar los modelos de la cuenta", exc_info=True)
        return []
    _model_cache = (time.time(), names)
    return names


def pick_best_chat_model(model_ids: list[str]) -> str | None:
    """Most capable gpt-5 chat model on the account. Skips mini and non-chat variants."""
    ranked: list[tuple[tuple[int, int, int], str]] = []
    for name in model_ids:
        low = name.lower()
        if not low.startswith("gpt-5"):
            continue
        if any(token in low for token in _MODEL_SKIP):
            continue
        if "codex" in low:
            continue
        cleaned = re.sub(r"-\d{4}-\d{2}-\d{2}$", "", low)
        nums = [int(number) for number in re.findall(r"\d+", cleaned) if len(number) < 4]
        major = nums[0] if nums else 0
        minor = nums[1] if len(nums) > 1 else 0
        tier = 3 if "sol" in low else 2 if "terra" in low else 1 if "luna" in low else 0
        pro = 1 if re.search(r"(^|-)pro($|-)", low) else 0
        undated = 0 if re.search(r"\d{4}-\d{2}-\d{2}", low) else 1
        ranked.append(((major, minor, tier, pro, undated), name))
    if not ranked:
        return None
    ranked.sort()
    return ranked[-1][1]


def qc_model() -> str:
    discovered = pick_best_chat_model(account_model_ids())
    if discovered:
        return discovered
    raw = (getattr(settings, "openai_qc_model", None) or "").strip()
    if raw and "mini" not in raw.lower() and "nano" not in raw.lower():
        return raw
    return "gpt-4o"


def qc_temperature() -> float:
    try:
        raw = float(getattr(settings, "openai_qc_temperature", 0.25) or 0.25)
    except (TypeError, ValueError):
        raw = 0.25
    return min(0.3, max(0.2, raw))


def load_system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def device_context(platform: str | None, region: str | None = None) -> DeviceContext:
    key = (platform or "").strip().upper()
    dispositivo, grupo, modo = _DEVICE_ROWS.get(key, (platform or "dispositivo de la Release", "Mediana", "Cursor / teclado"))
    region_label = (region or "").strip() or "México"
    return DeviceContext(
        dispositivo=dispositivo,
        grupo=grupo,
        modo=modo,
        region=region_label,
        metodos=_payment_methods(dispositivo, region_label),
    )


def _payment_methods(dispositivo: str, region: str) -> str:
    mexico = region.strip().lower() in {"méxico", "mexico", "mx"}
    if dispositivo in {"WIN", "XBOX"}:
        return "No transacciona"
    if dispositivo in {"iOS", "tvOS"}:
        return "iTunes, PayPal" if mexico else "No transacciona"
    if dispositivo == "Roku":
        return "RokuPay, PayPal" if mexico else "RokuPay"
    if mexico:
        return "PayPal, MDP Móvil, MDP Fijo, Pincode, TDC"
    return "MDP Móvil, MDP Fijo"


def looks_like_business_story(key: str, issuetype: str = "", summary: str = "") -> bool:
    project = (key or "").split("-")[0].upper()
    if project in _BUSINESS_PROJECTS:
        return True
    kind = (issuetype or "").lower()
    if "user story" in kind or "historia de usuario" in kind:
        return True
    return (summary or "").strip().lower().startswith("user story")


def select_user_story_key(artifact: dict[str, Any], children: list[dict[str, Any]] | None = None) -> str | None:
    """Business ticket linked to the technical epic. Not a Technical Story child."""
    epic_key = str(artifact.get("key") or "").strip().upper()
    explicit = artifact.get("user_story")
    if isinstance(explicit, dict):
        key = str(explicit.get("key") or "").strip().upper()
        if key and key != epic_key and looks_like_business_story(
            key, str(explicit.get("issuetype") or ""), str(explicit.get("summary") or "")
        ):
            return key
    parent = str(artifact.get("parent_key") or "").strip().upper()
    if parent and parent != epic_key and looks_like_business_story(
        parent,
        str(artifact.get("parent_issuetype") or ""),
        str(artifact.get("parent_summary") or ""),
    ):
        return parent
    child_keys = {str(child.get("key") or "").strip().upper() for child in children or [] if isinstance(child, dict)}
    for source in (artifact, *(children or [])):
        if not isinstance(source, dict):
            continue
        for link in source.get("linked_issues") or []:
            if not isinstance(link, dict):
                continue
            key = str(link.get("key") or "").strip().upper()
            if not key or key == epic_key or key in child_keys:
                continue
            if looks_like_business_story(key, str(link.get("issuetype") or ""), str(link.get("summary") or "")):
                return key
    return None


def split_criteria(text: str) -> list[tuple[str, str]]:
    """One CRN per numbered criterion. Sub-bullets stay inside that criterion."""
    raw = (text or "").strip()
    if not raw:
        return []
    parts = re.split(r"(?m)(?=^\s*\d{1,2}[.)]\s+\S)", raw)
    numbered = [part.strip() for part in parts if re.match(r"\s*\d{1,2}[.)]\s+\S", part or "")]
    items = numbered or [raw]
    rows: list[tuple[str, str]] = []
    for item in items:
        title = re.sub(r"^\s*\d{1,2}[.)]\s+", "", item).strip()
        title = title.split("\n", 1)[0].strip() or "Criterio"
        rows.append((title[:80], item))
    return rows


def user_story_header(story: dict[str, Any]) -> str:
    lines: list[str] = []
    for label, key in (
        ("Yo como", "yo_como"),
        ("Quiero", "quiero"),
        ("Para", "para"),
        ("Tipo de usuario", "user_type"),
        ("Criterios de éxito", "success_criteria"),
    ):
        value = str(story.get(key) or "").strip()
        if value:
            lines.append(f"{label}: {value}")
    description = str(story.get("description") or "").strip()
    if description:
        lines.append(description)
    return "\n".join(lines)


def estimate_tokens(text: str) -> int:
    """Approximate input tokens. Conservative for Spanish so a split happens before overflow."""
    return max(1, (len(text) + 2) // 3)


def criteria_text(story: dict[str, Any] | None) -> str:
    if not story:
        return ""
    acceptance = str(story.get("acceptance_criteria") or "").strip()
    if acceptance:
        return acceptance
    description = str(story.get("description") or "")
    match = re.search(r"(?is)criterios de aceptaci[oó]n\s*:?\s*(.+)$", description)
    return match.group(1).strip() if match else ""


def parse_story_text(text: str) -> tuple[str, str, list[tuple[str, str]]]:
    """Preamble, Background and scenarios. Does not strip quotes, backticks or comments."""
    preamble: list[str] = []
    background: list[str] = []
    scenarios: list[tuple[str, list[str]]] = []
    mode = "preamble"
    title = ""
    current: list[str] = []

    def flush() -> None:
        nonlocal current
        if mode == "scenario" and title:
            scenarios.append((title, list(current)))
        elif mode == "background":
            background.extend(current)
        else:
            preamble.extend(current)
        current = []

    for line in (text or "").splitlines():
        match = _HEADER.match(line)
        if not match:
            current.append(line)
            continue
        flush()
        kind = match.group(1).lower()
        if kind == "background":
            mode = "background"
            title = ""
            current = [line]
        elif kind == "feature":
            mode = "preamble"
            title = ""
            current = [line]
        else:
            mode = "scenario"
            title = match.group(2).strip() or "Escenario"
            current = [line]
    flush()
    bodies = [(name, "\n".join(lines).strip()) for name, lines in scenarios]
    return "\n".join(preamble).strip(), "\n".join(background).strip(), bodies


def _norm_title(text: str) -> str:
    cleaned = re.sub(r"\s*\([^)]*\)\s*$", "", text or "")
    return re.sub(r"\s+", " ", cleaned).strip().lower()


def _story_is_technical(child: dict[str, Any]) -> bool:
    blob = f"{child.get('description') or ''}\n{child.get('acceptance_criteria') or ''}"
    if _HEADER.search(blob) and re.search(r"(?im)^\s*(Scenario|Escenario)\b", blob):
        return True
    kind = str(child.get("issuetype") or "").lower()
    summary = str(child.get("summary") or "").lower()
    return "story" in kind or summary.startswith("feature")


def _next_cov_id(used: set[str], seq: list[int]) -> str:
    while True:
        seq[0] += 1
        label = f"COV-{seq[0]:03d}"
        if label not in used:
            used.add(label)
            return label


def build_epic_packet(artifact: dict[str, Any], inventory: list[CoverageUnit]) -> EpicPacket | None:
    if not isinstance(artifact, dict):
        return None
    epic_key = str(artifact.get("key") or "").strip()
    if not epic_key:
        return None
    children = [child for child in (artifact.get("children") or []) if isinstance(child, dict)]
    technical = [child for child in children if _story_is_technical(child)]
    sources = technical or [artifact]
    raw_stories = artifact.get("user_stories")
    if not isinstance(raw_stories, list):
        single = artifact.get("user_story") if isinstance(artifact.get("user_story"), dict) else None
        raw_stories = [single] if single else []
    user_story_blocks: list[dict[str, Any]] = []
    crns: list[CrnItem] = []
    sequence = 1
    for source in raw_stories:
        if not isinstance(source, dict):
            continue
        header = user_story_header(source)
        story_crns: list[CrnItem] = []
        story_key = str(source.get("key") or "")
        for title, body in split_criteria(criteria_text(source)):
            item = CrnItem(crn_id=f"CRN-{sequence:03d}", title=title, text=body, story_key=story_key)
            story_crns.append(item)
            crns.append(item)
            sequence += 1
        if story_crns or header:
            user_story_blocks.append(
                {
                    "key": story_key,
                    "title": str(source.get("summary") or ""),
                    "header": header,
                    "crns": story_crns,
                }
            )
    has_user_story = bool(user_story_blocks)
    first_story = user_story_blocks[0] if user_story_blocks else {}

    used_ids = {unit.coverage_id for unit in inventory if unit.coverage_id}
    seq = [0]
    for label in used_ids:
        match = re.fullmatch(r"COV-(\d+)", label or "")
        if match:
            seq[0] = max(seq[0], int(match.group(1)))
    claimed: set[str] = set()
    stories: list[dict[str, Any]] = []
    covs: list[CovItem] = []
    for source in sources:
        raw = f"{source.get('description') or ''}\n{source.get('acceptance_criteria') or ''}"
        preamble, background, scenarios = parse_story_text(raw)
        story_key = str(source.get("key") or epic_key)
        story_covs: list[CovItem] = []
        for title, gherkin in scenarios:
            hits = _matching_units(story_key, title, inventory, claimed)
            for unit in hits:
                claimed.add(unit.coverage_id)
            if hits:
                cov_id = hits[0].coverage_id
            else:
                cov_id = _next_cov_id(used_ids, seq)
            item = CovItem(
                cov_id=cov_id,
                story_key=story_key,
                title=title,
                gherkin=gherkin,
                inventory_ids=[unit.coverage_id for unit in hits],
            )
            story_covs.append(item)
            covs.append(item)
        stories.append(
            {
                "key": story_key,
                "title": str(source.get("summary") or story_key),
                "preamble": preamble,
                "background": background,
                "covs": story_covs,
            }
        )
    if not covs and not crns and not has_user_story:
        return None
    return EpicPacket(
        epic_key=epic_key,
        epic_title=str(artifact.get("summary") or epic_key),
        has_user_story=has_user_story,
        user_story_key=str(first_story.get("key") or ""),
        user_story_title=str(first_story.get("title") or ""),
        user_story_body=str(first_story.get("header") or ""),
        crns=crns,
        stories=stories,
        covs=covs,
        user_stories=user_story_blocks,
    )


def _matching_units(
    story_key: str,
    title: str,
    inventory: list[CoverageUnit],
    claimed: set[str],
) -> list[CoverageUnit]:
    wanted = _norm_title(title)
    if not wanted:
        return []
    hits: list[CoverageUnit] = []
    for unit in inventory:
        if unit.coverage_id in claimed:
            continue
        unit_story = unit.story_key or unit.jira_key or ""
        if unit_story and unit_story != story_key:
            continue
        scenario = _norm_title(unit.scenario or "")
        if scenario == wanted or scenario.startswith(wanted) or wanted.startswith(scenario):
            hits.append(unit)
    return hits


def render_user_prompt(
    packet: EpicPacket,
    device: DeviceContext,
    *,
    stories: list[dict[str, Any]] | None = None,
    only_crns: list[CrnItem] | None = None,
    note: str = "",
) -> str:
    chosen = stories if stories is not None else packet.stories
    crns = only_crns if only_crns is not None else packet.crns
    lines = [
        f"ÉPICA TÉCNICA: {packet.epic_key} — {packet.epic_title}",
        "",
        "=== USER STORY (qué debe cumplirse) ===",
    ]
    lines.extend(_render_business_stories(packet, crns))
    lines.append("=== TECHNICAL STORIES (cómo se comporta el sistema) ===")
    if not chosen:
        lines.append("Sin Technical Stories.")
    for story in chosen:
        lines.append(f"--- {story['key']} — {story['title']}")
        lines.append(story.get("preamble") or "(sin descripción adicional)")
        if story.get("background"):
            lines.append("")
            lines.append("Contexto (Background, no es un escenario):")
            lines.append(story["background"])
        lines.append("")
        covs = story.get("covs") or []
        if not covs:
            lines.append("Sin escenarios Gherkin. El Background no es un COV.")
        for cov in covs:
            lines.append(f"{cov.cov_id} | {cov.title}")
            lines.append(cov.gherkin)
            lines.append("")
    if note:
        lines.append(note)
        lines.append("")
    lines.append(f"DISPOSITIVO: {device.dispositivo} ({device.grupo}, {device.modo})")
    lines.append(f"REGIÓN: {device.region}")
    lines.append(f"MÉTODOS DE PAGO DISPONIBLES: {device.metodos}")
    lines.append("")
    lines.append("Responde únicamente con el JSON de la sección 6.")
    return "\n".join(lines)


def _render_business_stories(packet: EpicPacket, crns: list[CrnItem]) -> list[str]:
    if not packet.has_user_story:
        return ["Sin User Story"]
    wanted = {item.crn_id for item in crns}
    blocks = packet.user_stories or [
        {
            "key": packet.user_story_key,
            "title": packet.user_story_title,
            "header": packet.user_story_body,
            "crns": packet.crns,
        }
    ]
    lines: list[str] = []
    for story in blocks:
        story_crns = [item for item in (story.get("crns") or []) if item.crn_id in wanted]
        if wanted and set(item.crn_id for item in (story.get("crns") or [])) and not story_crns:
            continue
        lines.append(f"{story.get('key') or ''} — {story.get('title') or ''}".strip(" —"))
        header = str(story.get("header") or "").strip()
        if header:
            lines.append(header)
        lines.append("")
        lines.append("CRITERIOS DE NEGOCIO:")
        if not story_crns:
            lines.append("Sin criterios de aceptación en la User Story.")
        for crn in story_crns:
            lines.append(f"{crn.crn_id} | {crn.title}")
            lines.append(crn.text)
            lines.append("")
    return lines or ["Sin User Story"]


def system_prompt_for(device: DeviceContext) -> str:
    text = load_system_prompt()
    replacements = {
        "{{dispositivo}}": device.dispositivo,
        "{{grupo_pantalla}}": device.grupo,
        "{{modo_interaccion}}": device.modo,
        "{{region}}": device.region,
        "{{metodos_pago}}": device.metodos,
    }
    for token, value in replacements.items():
        text = text.replace(token, value)
    return text


def _as_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def case_errors(caso: Any) -> list[str]:
    if not isinstance(caso, dict):
        return ["un caso no es un objeto"]
    title = str(caso.get("titulo") or "").strip() or "caso sin título"
    errors: list[str] = []
    tipo = str(caso.get("tipo") or "").strip().upper()
    if tipo not in _TIPOS:
        errors.append(f"{title}: tipo inválido")
    brecha = str(caso.get("brecha") or "").strip()
    if brecha not in _BRECHAS:
        errors.append(f"{title}: brecha inválida")
    pre = caso.get("precondiciones")
    if not isinstance(pre, list) or not (2 <= len(pre) <= 5):
        errors.append(f"{title}: debe tener entre 2 y 5 precondiciones")
    steps = caso.get("pasos")
    if not isinstance(steps, list) or not (3 <= len(steps) <= 5):
        errors.append(f"{title}: debe tener entre 3 y 5 pasos")
    else:
        for index, step in enumerate(steps, start=1):
            if not isinstance(step, dict):
                errors.append(f"{title}: el paso {index} no es un objeto")
                continue
            blob = f"{step.get('accion') or ''} {step.get('resultado_esperado') or ''}"
            if _FORBIDDEN_STEP.search(blob):
                errors.append(f"{title}: el paso {index} contiene una acción de Desarrollo o una llamada técnica")
            if not str(step.get("accion") or "").strip() or not str(step.get("resultado_esperado") or "").strip():
                errors.append(f"{title}: el paso {index} no tiene acción y resultado")
    negocio = _as_list(caso.get("cubre_negocio"))
    tecnico = _as_list(caso.get("cubre_tecnico"))
    if brecha == "sin_tecnico" and tecnico:
        errors.append(f"{title}: sin_tecnico no puede fusionarse con un COV")
    if brecha == "sin_negocio" and negocio:
        errors.append(f"{title}: sin_negocio no puede fusionarse con un CRN")
    if brecha == "ninguna" and (not negocio or not tecnico):
        errors.append(f"{title}: brecha ninguna exige al menos un CRN y un COV")
    return errors


def coverage_gaps(payload: dict[str, Any], crn_ids: list[str], cov_ids: list[str]) -> list[str]:
    covered_crn: set[str] = set()
    covered_cov: set[str] = set()
    for caso in payload.get("casos") or []:
        if not isinstance(caso, dict):
            continue
        covered_crn.update(_as_list(caso.get("cubre_negocio")))
        covered_cov.update(_as_list(caso.get("cubre_tecnico")))
    for row in payload.get("excluidos") or []:
        if not isinstance(row, dict):
            continue
        ident = str(row.get("id") or "").strip()
        if ident.startswith("CRN-"):
            covered_crn.add(ident)
        elif ident.startswith("COV-"):
            covered_cov.add(ident)
    missing_crn = [item for item in crn_ids if item not in covered_crn]
    missing_cov = [item for item in cov_ids if item not in covered_cov]
    errors: list[str] = []
    if missing_crn:
        errors.append("Faltan CRN en cubre_negocio o en excluidos: " + ", ".join(missing_crn))
    if missing_cov:
        errors.append("Faltan COV en cubre_tecnico o en excluidos: " + ", ".join(missing_cov))
    return errors


def validate_design(payload: Any, crn_ids: list[str], cov_ids: list[str]) -> list[str]:
    if not isinstance(payload, dict):
        return ["la respuesta no es un JSON objeto"]
    errors: list[str] = []
    for key in ("resumen_funcionalidad", "matriz_cruce", "casos", "excluidos"):
        if key not in payload:
            errors.append(f"falta la clave {key}")
    if not isinstance(payload.get("casos"), list):
        errors.append("casos debe ser una lista")
        return errors
    if not isinstance(payload.get("excluidos"), list):
        errors.append("excluidos debe ser una lista")
    known = set(crn_ids) | set(cov_ids)
    for row in payload.get("excluidos") or []:
        if not isinstance(row, dict):
            errors.append("un excluido no es un objeto")
            continue
        ident = str(row.get("id") or "").strip()
        motivo = str(row.get("motivo") or "").strip()
        if ident not in known:
            errors.append(f"excluido {ident or '(vacío)'} no está en los CRN/COV enviados")
        if motivo not in _EXCLUSION_MOTIVOS:
            errors.append(f"{ident}: motivo de exclusión inválido")
        elif motivo == "otra_epica" and not ident.startswith("CRN-"):
            errors.append(f"{ident}: otra_epica solo aplica a un CRN")
    for caso in payload.get("casos") or []:
        errors.extend(case_errors(caso))
    errors.extend(coverage_gaps(payload, crn_ids, cov_ids))
    return errors


def _parse_json(raw: str) -> Any:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def _is_quota(status: int, text: str) -> bool:
    blob = (text or "").lower()
    if "insufficient_quota" in blob or "no credits" in blob or "exceeded your current quota" in blob:
        return True
    return status == 402


def _is_rate_limit(status: int, text: str) -> bool:
    if _is_quota(status, text):
        return False
    blob = (text or "").lower()
    return status == 429 or "rate limit" in blob or "rate_limit" in blob


def call_qc_llm(system: str, user: str, timeout: float) -> str:
    """One completion. Rate limit: 3 retries with backoff. Quota aborts."""
    url = settings.openai_base_url.rstrip("/") + "/chat/completions"
    body: dict[str, Any] = {
        "model": qc_model(),
        "temperature": qc_temperature(),
        "response_format": {"type": "json_object"},
        "max_completion_tokens": 64000,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    delays = (1.0, 2.0, 4.0)
    rate_attempts = 0
    adjusted = False
    while True:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                url,
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
        if response.status_code == 200:
            message = response.json()["choices"][0]["message"]
            content = message.get("content")
            if isinstance(content, list):
                content = "".join(
                    str(part.get("text") or "") if isinstance(part, dict) else str(part) for part in content
                )
            if not str(content or "").strip():
                raise RuntimeError("LLM respondió sin contenido")
            return str(content)
        text = response.text[:800]
        if response.status_code == 400 and not adjusted:
            low = text.lower()
            dropped = False
            for key in ("temperature", "response_format", "max_completion_tokens"):
                if key in body and key in low:
                    body.pop(key, None)
                    dropped = True
            if dropped:
                adjusted = True
                continue
        if _is_quota(response.status_code, text):
            raise LlmQuotaError(
                "Corrida abortada: la API no tiene créditos (insufficient_quota). "
                "No se entrega un Excel parcial."
            )
        if _is_rate_limit(response.status_code, text) and rate_attempts < 3:
            time.sleep(delays[rate_attempts])
            rate_attempts += 1
            continue
        raise RuntimeError(f"LLM HTTP {response.status_code}: {text[:400]}")


def _exchange(
    system: str,
    user: str,
    crn_ids: list[str],
    cov_ids: list[str],
    timeout: float,
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    feedback = ""
    last: dict[str, Any] | None = None
    meta: dict[str, Any] = {"attempts": 0, "ok": False, "error": None}
    for attempt in range(2):
        meta["attempts"] = attempt + 1
        prompt = user if not feedback else user + "\n\nREVISIÓN: la respuesta anterior no se acepta. Corrige exactamente esto:\n- " + feedback
        try:
            raw = call_qc_llm(system, prompt, timeout)
            parsed = _parse_json(raw)
        except LlmQuotaError:
            raise
        except Exception as exc:
            meta["error"] = str(exc)[:300]
            feedback = meta["error"]
            continue
        if not isinstance(parsed, dict):
            feedback = "la respuesta no es un JSON objeto"
            meta["error"] = feedback
            continue
        last = parsed
        errors = validate_design(parsed, crn_ids, cov_ids)
        if not errors:
            meta["ok"] = True
            meta["error"] = None
            return parsed, meta, []
        feedback = "\n- ".join(errors)
        meta["error"] = feedback[:500]
    if last is None:
        empty = {"resumen_funcionalidad": "", "matriz_cruce": [], "casos": [], "excluidos": []}
        return empty, meta, [meta.get("error") or "sin respuesta válida"]
    kept = [caso for caso in (last.get("casos") or []) if isinstance(caso, dict) and not case_errors(caso)]
    salvaged = {
        "resumen_funcionalidad": last.get("resumen_funcionalidad") or "",
        "matriz_cruce": last.get("matriz_cruce") if isinstance(last.get("matriz_cruce"), list) else [],
        "casos": kept,
        "excluidos": [row for row in (last.get("excluidos") or []) if isinstance(row, dict)],
    }
    return salvaged, meta, coverage_gaps(salvaged, crn_ids, cov_ids) or [meta.get("error") or "respuesta incompleta"]


def _prefer_cases(cases: list[dict[str, Any]], excluidos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    covered: set[str] = set()
    for caso in cases:
        covered.update(_as_list(caso.get("cubre_negocio")))
        covered.update(_as_list(caso.get("cubre_tecnico")))
    return [row for row in excluidos if str(row.get("id") or "") not in covered]


def _design_packet(packet: EpicPacket, device: DeviceContext, timeout: float) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    system = system_prompt_for(device)
    batches: list[dict[str, Any]] = []
    warnings: list[str] = []
    full_prompt = render_user_prompt(packet, device)
    if estimate_tokens(system) + estimate_tokens(full_prompt) <= _CONTEXT_TOKEN_LIMIT:
        payload, meta, notes = _exchange(
            system,
            render_user_prompt(packet, device),
            [item.crn_id for item in packet.crns],
            [item.cov_id for item in packet.covs],
            timeout,
        )
        batches.append(meta)
        warnings.extend(notes)
        return payload, batches, warnings

    cases: list[dict[str, Any]] = []
    excluidos: list[dict[str, Any]] = []
    matriz: list[dict[str, Any]] = []
    resumen = ""
    for story in packet.stories:
        covs = list(story.get("covs") or [])
        if not covs and not packet.crns:
            continue
        payload, meta, notes = _exchange(
            system,
            render_user_prompt(
                packet,
                device,
                stories=[story],
                note=(
                    f"Esta llamada cubre solo la Technical Story {story['key']}. "
                    "La User Story va completa. Cubre los COV de esta historia. "
                    "Un CRN que no corresponda a esta historia se cierra en otra llamada."
                ),
            ),
            [],
            [item.cov_id for item in covs],
            timeout,
        )
        batches.append(meta)
        warnings.extend(f"{story['key']}: {note}" for note in notes)
        resumen = resumen or str(payload.get("resumen_funcionalidad") or "")
        cases.extend(caso for caso in payload.get("casos") or [] if isinstance(caso, dict))
        excluidos.extend(row for row in payload.get("excluidos") or [] if isinstance(row, dict))
        matriz.extend(row for row in payload.get("matriz_cruce") or [] if isinstance(row, dict))
    excluidos = _prefer_cases(cases, excluidos)
    covered_crn = {item for caso in cases for item in _as_list(caso.get("cubre_negocio"))}
    covered_crn.update(str(row.get("id") or "") for row in excluidos)
    missing = [item for item in packet.crns if item.crn_id not in covered_crn]
    if missing:
        payload, meta, notes = _exchange(
            system,
            render_user_prompt(
                packet,
                device,
                only_crns=missing,
                note=(
                    "LLAMADA DE CIERRE. Diseña solo los casos de los CRN listados: "
                    "ninguna llamada anterior los cubrió. No repitas COV ya cubiertos "
                    "salvo que el criterio lo necesite."
                ),
            ),
            [item.crn_id for item in missing],
            [],
            timeout,
        )
        batches.append(meta)
        warnings.extend(notes)
        cases.extend(caso for caso in payload.get("casos") or [] if isinstance(caso, dict))
        excluidos.extend(row for row in payload.get("excluidos") or [] if isinstance(row, dict))
        matriz.extend(row for row in payload.get("matriz_cruce") or [] if isinstance(row, dict))
        excluidos = _prefer_cases(cases, excluidos)
        resumen = resumen or str(payload.get("resumen_funcionalidad") or "")
    return (
        {
            "resumen_funcionalidad": resumen,
            "matriz_cruce": matriz,
            "casos": cases,
            "excluidos": excluidos,
        },
        batches,
        warnings,
    )


def _confidence(value: str) -> str:
    return {"alta": "high", "media": "medium", "baja": "low"}.get((value or "").strip().lower(), "medium")


def cases_from_payload(
    packet: EpicPacket,
    payload: dict[str, Any],
    rn_filename: str,
) -> list[GeneratedCaseCandidate]:
    by_cov = {item.cov_id: item for item in packet.covs}
    out: list[GeneratedCaseCandidate] = []
    for caso in payload.get("casos") or []:
        if not isinstance(caso, dict) or case_errors(caso):
            continue
        negocio = _as_list(caso.get("cubre_negocio"))
        tecnico = _as_list(caso.get("cubre_tecnico"))
        expanded: list[str] = []
        story_keys: list[str] = []
        for cov_id in tecnico:
            if cov_id not in expanded:
                expanded.append(cov_id)
            item = by_cov.get(cov_id)
            if item is None:
                continue
            if item.story_key not in story_keys:
                story_keys.append(item.story_key)
            for extra in item.inventory_ids:
                if extra not in expanded:
                    expanded.append(extra)
        covers = list(dict.fromkeys([*negocio, *expanded]))
        steps = [
            CandidateStep(
                step_number=index,
                action=str(step.get("accion") or "").strip(),
                expected_result=str(step.get("resultado_esperado") or "").strip(),
                covered_unit_ids=list(tecnico or negocio),
            )
            for index, step in enumerate(caso.get("pasos") or [], start=1)
            if isinstance(step, dict)
        ]
        variants = [
            f"{row.get('condicion')} → {row.get('resultado_esperado')}"
            for row in (caso.get("variantes") or [])
            if isinstance(row, dict) and str(row.get("condicion") or "").strip()
        ]
        priority = "BLOCKER" if str(caso.get("prioridad") or "").strip().lower() == "blocker" else "CRITICAL"
        complejidad = str(caso.get("complejidad") or "MEDIA").strip().upper()
        if complejidad not in {"BAJA", "MEDIA", "ALTA"}:
            complejidad = "MEDIA"
        tipo = str(caso.get("tipo") or "").strip().upper()
        brecha = str(caso.get("brecha") or "ninguna").strip()
        reference = caso.get("referencia_tecnica")
        reference_text = None if reference in (None, "", "null") else str(reference).strip() or None
        related = ", ".join(story_keys) or packet.user_story_key or packet.epic_key
        out.append(
            GeneratedCaseCandidate(
                name=str(caso.get("titulo") or "Caso QC")[:250],
                description=str(caso.get("riesgo") or payload.get("resumen_funcionalidad") or "")[:8000],
                precondition="; ".join(str(item).strip() for item in (caso.get("precondiciones") or []) if str(item).strip()),
                steps=steps,
                related_functionality=packet.epic_key,
                related_jira=related[:500],
                related_rn=rn_filename or None,
                evidence=str(caso.get("riesgo") or caso.get("titulo") or ""),
                justification="covers=" + ",".join(covers),
                confidence=_confidence(str(caso.get("confianza") or "")),  # type: ignore[arg-type]
                priority=priority,  # type: ignore[arg-type]
                covers=covers,
                covered_unit_ids=list(covers),
                technical_reference=reference_text,
                variant_table="\n".join(variants) or None,
                generation_origin="qc-design",
                qc_tipo=tipo,
                qc_brecha=brecha,
                qc_complejidad=complejidad,
                applied_rules=[f"tipo:{tipo}", f"brecha:{brecha}"],
                review_required=True,
            )
        )
    return out


def _case_name_for(candidates: list[GeneratedCaseCandidate], ident: str) -> str:
    names = [row.name for row in candidates if ident in (row.covers or [])]
    return "; ".join(dict.fromkeys(names))


def cruce_rows_from(
    packet: EpicPacket,
    payload: dict[str, Any],
    candidates: list[GeneratedCaseCandidate],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(ident: str, situacion: str) -> None:
        if not ident or ident in seen:
            return
        seen.add(ident)
        rows.append(
            {
                "epic": packet.epic_key,
                "id": ident,
                "situacion": situacion if situacion in _SITUACIONES else "cruce",
                "casos": _case_name_for(candidates, ident),
            }
        )

    for item in payload.get("matriz_cruce") or []:
        if not isinstance(item, dict):
            continue
        situacion = str(item.get("situacion") or "").strip()
        crn = item.get("crn")
        if crn:
            add(str(crn), situacion)
        for cov in item.get("cov") or []:
            add(str(cov), situacion)
    for crn in packet.crns:
        situacion = "solo_negocio"
        if any(crn.crn_id in (row.covers or []) and any(item.startswith("COV-") for item in (row.covers or [])) for row in candidates):
            situacion = "cruce"
        elif any(str(row.get("id") or "") == crn.crn_id for row in payload.get("excluidos") or []):
            situacion = "solo_negocio"
        add(crn.crn_id, situacion)
    for cov in packet.covs:
        situacion = "solo_tecnico"
        if any(cov.cov_id in (row.covers or []) and any(item.startswith("CRN-") for item in (row.covers or [])) for row in candidates):
            situacion = "cruce"
        add(cov.cov_id, situacion)
    return rows


def ledger_from(
    packet: EpicPacket,
    payload: dict[str, Any],
    candidates: list[GeneratedCaseCandidate],
    warnings: list[str],
) -> tuple[list[dict[str, Any]], set[str]]:
    excluidos = {
        str(row.get("id") or ""): row
        for row in (payload.get("excluidos") or [])
        if isinstance(row, dict) and row.get("id")
    }
    rows: list[dict[str, Any]] = []
    accounted: set[str] = set()
    if not packet.has_user_story:
        rows.append(
            {
                "story": packet.epic_key,
                "epic": packet.epic_key,
                "scenario": "User Story",
                "estado": "sin_user_story",
                "motivo": "La épica no tiene User Story ligada",
                "case_id": "",
            }
        )
    covered = {ident for row in candidates for ident in (row.covers or [])}
    for cov in packet.covs:
        excluded = excluidos.get(cov.cov_id)
        if excluded and cov.cov_id not in covered:
            accounted.update(cov.inventory_ids or [cov.cov_id])
            rows.append(
                {
                    "story": cov.story_key,
                    "epic": packet.epic_key,
                    "scenario": f"{cov.cov_id} {cov.title}",
                    "estado": str(excluded.get("motivo") or ""),
                    "motivo": str(excluded.get("explicacion") or excluded.get("motivo") or ""),
                    "case_id": "",
                }
            )
            continue
        if cov.cov_id not in covered:
            rows.append(
                {
                    "story": cov.story_key,
                    "epic": packet.epic_key,
                    "scenario": f"{cov.cov_id} {cov.title}",
                    "estado": _VALIDATION_GAP,
                    "motivo": f"{cov.cov_id} no quedó cubierto ni excluido tras el reintento",
                    "case_id": "",
                }
            )
            continue
        accounted.update(cov.inventory_ids or [cov.cov_id])
        rows.append(
            {
                "story": cov.story_key,
                "epic": packet.epic_key,
                "scenario": f"{cov.cov_id} {cov.title}",
                "estado": "caso ejecutable",
                "motivo": "",
                "case_id": _case_name_for(candidates, cov.cov_id),
            }
        )
    for crn in packet.crns:
        excluded = excluidos.get(crn.crn_id)
        if excluded and crn.crn_id not in covered:
            rows.append(
                {
                    "story": crn.story_key or packet.user_story_key or packet.epic_key,
                    "epic": packet.epic_key,
                    "scenario": f"{crn.crn_id} {crn.title}",
                    "estado": str(excluded.get("motivo") or ""),
                    "motivo": str(excluded.get("explicacion") or ""),
                    "case_id": "",
                }
            )
        elif crn.crn_id not in covered:
            rows.append(
                {
                    "story": crn.story_key or packet.user_story_key or packet.epic_key,
                    "epic": packet.epic_key,
                    "scenario": f"{crn.crn_id} {crn.title}",
                    "estado": _VALIDATION_GAP,
                    "motivo": f"{crn.crn_id} no quedó cubierto ni excluido tras el reintento",
                    "case_id": "",
                }
            )
    if warnings and not any(
        str(row.get("estado") or "").startswith("error") or str(row.get("estado") or "") == _VALIDATION_GAP
        for row in rows
    ):
        rows.append(
            {
                "story": packet.epic_key,
                "epic": packet.epic_key,
                "scenario": "Generación QC",
                "estado": "error",
                "motivo": "; ".join(warnings)[:500],
                "case_id": "",
            }
        )
    return rows, accounted


def design_release_cases(
    artifacts: list[dict[str, Any]],
    inventory: list[CoverageUnit],
    release_context: dict[str, Any] | None,
    rn_filename: str,
) -> DesignOutcome | None:
    """Design every epic that has a User Story or Gherkin. None when there is nothing to cross."""
    context = release_context or {}
    device = device_context(str(context.get("platform") or ""), str(context.get("region") or "México"))
    timeout = max(300.0, float(getattr(settings, "llm_scenario_timeout", 45) or 45))
    packets = [packet for artifact in artifacts if (packet := build_epic_packet(artifact, inventory))]
    if not packets:
        return None
    candidates: list[GeneratedCaseCandidate] = []
    ledger: list[dict[str, Any]] = []
    cruce: list[dict[str, Any]] = []
    warnings: list[str] = []
    batches: list[dict[str, Any]] = []
    accounted: set[str] = set()
    for packet in packets:
        if not packet.has_user_story:
            warnings.append(f"{packet.epic_key}: Sin User Story")
        payload, packet_batches, packet_warnings = _design_packet(packet, device, timeout)
        built = cases_from_payload(packet, payload, rn_filename)
        packet_ledger, packet_accounted = ledger_from(packet, payload, built, packet_warnings)
        candidates.extend(built)
        ledger.extend(packet_ledger)
        cruce.extend(cruce_rows_from(packet, payload, built))
        warnings.extend(packet_warnings)
        batches.extend(packet_batches)
        accounted.update(packet_accounted)
        accounted.update(ident for row in built for ident in (row.covers or []))
    summary = (
        f"Diseño QC por épica llamadas={len(batches)} casos={len(candidates)} "
        f"modelo={qc_model()} temperatura={qc_temperature()}"
    )
    return DesignOutcome(
        candidates=candidates,
        ledger=ledger,
        cruce_rows=cruce,
        warnings=list(dict.fromkeys(warnings)),
        batches=batches,
        accounted_ids=accounted,
        summary=summary,
    )


def merge_cruce_rows(
    previous: list[dict[str, Any]] | None,
    incoming: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    prev = [row for row in (previous or []) if isinstance(row, dict)]
    new = [row for row in (incoming or []) if isinstance(row, dict)]
    if not new:
        return prev
    new_epics = {str(row.get("epic") or "").strip() for row in new if str(row.get("epic") or "").strip()}
    kept = [row for row in prev if str(row.get("epic") or "").strip() not in new_epics]
    return kept + new
