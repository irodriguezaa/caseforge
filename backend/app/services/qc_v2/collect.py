"""Recolección de Jira para la v2 (sin IA).

- Technical Stories de la épica: descripción completa sin limpiar; cada Scenario / Scenario Outline
  es un COV. El Background y lo que va antes del primer escenario es contexto, no COV.
- User Stories: Technical Epic → parent (Technical Brief) → … → Product Brief → Product Epic(s)
  cuyo título coincide con el Technical Brief → User Stories. Cada criterio numerado de
  customfield_19114 es un CRN.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Callable

from app.services.jira_generation import adf_to_text

F_AC = "customfield_19114"
F_YO_COMO = "customfield_19120"
F_QUIERO = "customfield_19121"
F_PARA = "customfield_19122"
F_TIPO_USUARIO = "customfield_19125"
F_EXITO = "customfield_19094"

FIELDS = [
    "summary",
    "issuetype",
    "description",
    "parent",
    "status",
    F_AC,
    F_YO_COMO,
    F_QUIERO,
    F_PARA,
    F_TIPO_USUARIO,
    F_EXITO,
]

TITLE_MATCH_THRESHOLD = 0.8


# ---------------------------------------------------------------- data


@dataclass
class Item:
    id: str
    title: str
    text: str
    source_key: str


@dataclass
class TechStory:
    key: str
    summary: str
    context: str
    scenarios: list[Item] = field(default_factory=list)


@dataclass
class UserStory:
    key: str
    summary: str
    yo_como: str = ""
    quiero: str = ""
    para: str = ""
    tipo_usuario: str = ""
    exito: str = ""
    criteria: list[Item] = field(default_factory=list)


@dataclass
class EpicBundle:
    key: str
    summary: str
    technical_stories: list[TechStory] = field(default_factory=list)
    user_stories: list[UserStory] = field(default_factory=list)
    technical_brief_key: str | None = None
    product_brief_key: str | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def covs(self) -> list[Item]:
        return [item for story in self.technical_stories for item in story.scenarios]

    @property
    def crns(self) -> list[Item]:
        return [item for story in self.user_stories for item in story.criteria]

    def item(self, item_id: str) -> Item | None:
        for item in self.covs + self.crns:
            if item.id == item_id:
                return item
        return None


# ---------------------------------------------------------------- text helpers


def field_text(value: Any) -> str:
    """Texto de un campo de Jira: ADF, string, opción o lista de opciones."""
    if value is None:
        return ""
    if isinstance(value, list) and all(isinstance(v, dict) and "value" in v for v in value):
        return ", ".join(str(v.get("value") or "").strip() for v in value if v.get("value"))
    if isinstance(value, dict) and "value" in value and "type" not in value:
        return str(value.get("value") or "").strip()
    return adf_to_text(value)


_SCENARIO_LINE = re.compile(
    r"^[ \t]*(Scenario Outline|Scenario|Esquema del escenario|Escenario)\s*:[ \t]*(.*)$",
    re.IGNORECASE | re.MULTILINE,
)


def split_gherkin(description: str) -> tuple[str, list[tuple[str, str]]]:
    """Devuelve (contexto, [(titulo, bloque)]). El contexto incluye Feature y Background."""
    text = description or ""
    matches = list(_SCENARIO_LINE.finditer(text))
    if not matches:
        return text.strip(), []
    context = text[: matches[0].start()].strip()
    blocks: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[match.start() : end].rstrip()
        block = re.sub(r"\n\s*```\s*$", "", block).rstrip()
        title = match.group(2).strip() or f"Escenario {index + 1}"
        blocks.append((title, block))
    return context, blocks


_TOP_NUMBERED = re.compile(r"^(?:\d+[.)]|#)\s+")


def _criteria_from_adf(doc: dict[str, Any]) -> list[str]:
    for node in doc.get("content") or []:
        if isinstance(node, dict) and node.get("type") == "orderedList":
            items = [adf_to_text(child) for child in node.get("content") or []]
            items = [item.strip() for item in items if item and item.strip()]
            if items:
                return items
    return []


def split_criteria(value: Any) -> list[str]:
    """Separa los criterios de aceptación numerados de primer nivel (con sus subincisos)."""
    if isinstance(value, dict):
        found = _criteria_from_adf(value)
        if found:
            return found
        value = adf_to_text(value)
    text = (value or "").strip() if isinstance(value, str) else field_text(value)
    if not text:
        return []
    criteria: list[list[str]] = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            if criteria:
                criteria[-1].append("")
            continue
        top_level = not raw_line[:1].isspace() and bool(_TOP_NUMBERED.match(line))
        if top_level:
            criteria.append([_TOP_NUMBERED.sub("", line, count=1).strip()])
        elif criteria:
            criteria[-1].append(line)
        else:
            criteria.append([line.strip()])
    joined = ["\n".join(lines).strip() for lines in criteria]
    joined = [item for item in joined if item]
    numbered = sum(1 for line in text.splitlines() if _TOP_NUMBERED.match(line))
    if numbered == 0:
        return [text]
    return joined


_PREFIX = re.compile(r"^\s*([^:]{1,40}):\s+")
_PARENS = re.compile(r"\([^)]*\)")


def normalize_title(title: str) -> str:
    text = unicodedata.normalize("NFKD", title or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    text = _PARENS.sub(" ", text)
    while True:
        match = _PREFIX.match(text)
        if not match or len(match.group(1).split()) > 4:
            break
        text = text[match.end() :]
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def title_similarity(a: str, b: str) -> float:
    left, right = normalize_title(a), normalize_title(b)
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    if (left in right or right in left) and min(len(left), len(right)) >= 20:
        return 0.95
    return difflib.SequenceMatcher(None, left, right).ratio()


# ---------------------------------------------------------------- Jira access


class JiraReader:
    """Envoltura mínima sobre el cliente httpx de QcPulse (inyectable en tests)."""

    def __init__(self, client: Any):
        self.client = client

    def get(self, key: str) -> dict[str, Any] | None:
        response = self.client.get(f"/rest/api/3/issue/{key}", params={"fields": ",".join(FIELDS)})
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    def children(self, key: str) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        token: str | None = None
        while True:
            body: dict[str, Any] = {
                "jql": f'parent = "{key}" ORDER BY key ASC',
                "maxResults": 100,
                "fields": FIELDS,
            }
            if token:
                body["nextPageToken"] = token
            response = self.client.post("/rest/api/3/search/jql", json=body)
            response.raise_for_status()
            payload = response.json()
            issues.extend(payload.get("issues") or [])
            token = payload.get("nextPageToken") or None
            if not token:
                return issues


def _fields(issue: dict[str, Any]) -> dict[str, Any]:
    return issue.get("fields") or {}


def _type(issue: dict[str, Any]) -> str:
    return ((_fields(issue).get("issuetype") or {}).get("name") or "").strip()


def _parent_key(issue: dict[str, Any]) -> str | None:
    return (_fields(issue).get("parent") or {}).get("key")


def _tech_story(issue: dict[str, Any], counter: Callable[[], str]) -> TechStory:
    fields = _fields(issue)
    key = issue.get("key") or ""
    summary = fields.get("summary") or ""
    description = adf_to_text(fields.get("description"))
    context, blocks = split_gherkin(description)
    scenarios = [Item(counter(), title, block, key) for title, block in blocks]
    if not scenarios and description.strip():
        scenarios = [Item(counter(), summary, description.strip(), key)]
    return TechStory(key=key, summary=summary, context=context, scenarios=scenarios)


def _user_story(issue: dict[str, Any], counter: Callable[[], str]) -> UserStory:
    fields = _fields(issue)
    key = issue.get("key") or ""
    criteria = split_criteria(fields.get(F_AC))
    return UserStory(
        key=key,
        summary=fields.get("summary") or "",
        yo_como=field_text(fields.get(F_YO_COMO)),
        quiero=field_text(fields.get(F_QUIERO)),
        para=field_text(fields.get(F_PARA)),
        tipo_usuario=field_text(fields.get(F_TIPO_USUARIO)),
        exito=field_text(fields.get(F_EXITO)),
        criteria=[Item(counter(), text.splitlines()[0][:160], text, key) for text in criteria],
    )


def _counter(prefix: str) -> Callable[[], str]:
    state = {"n": 0}

    def next_id() -> str:
        state["n"] += 1
        return f"{prefix}-{state['n']:03d}"

    return next_id


def _find_product_brief(reader: JiraReader, start_key: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Sube desde el padre de la épica. Devuelve (technical_brief, product_brief)."""
    technical_brief = reader.get(start_key)
    current = technical_brief
    for _ in range(3):
        if current is None:
            return technical_brief, None
        if "product brief" in _type(current).lower():
            return technical_brief, current
        parent = _parent_key(current)
        if not parent:
            return technical_brief, None
        current = reader.get(parent)
    return technical_brief, None


def collect_user_stories(reader: JiraReader, epic: dict[str, Any], bundle: EpicBundle) -> None:
    parent = _parent_key(epic)
    if not parent:
        bundle.warnings.append("Sin User Story: la épica no tiene Technical Brief padre")
        return
    technical_brief, product_brief = _find_product_brief(reader, parent)
    if technical_brief is None:
        bundle.warnings.append(f"Sin User Story: no se pudo leer {parent}")
        return
    bundle.technical_brief_key = technical_brief.get("key")
    if product_brief is None:
        bundle.warnings.append("Sin User Story: no se encontró el Product Brief")
        return
    bundle.product_brief_key = product_brief.get("key")
    brief_title = _fields(technical_brief).get("summary") or ""
    product_epics = [
        child for child in reader.children(product_brief.get("key") or "")
        if "product epic" in _type(child).lower()
    ]
    scored = [
        (title_similarity(brief_title, _fields(pe).get("summary") or ""), pe) for pe in product_epics
    ]
    matched = [pe for score, pe in scored if score >= TITLE_MATCH_THRESHOLD]
    if not matched and len(product_epics) == 1:
        matched = product_epics
        bundle.warnings.append(
            "User Story emparejada por ser la única Product Epic del Product Brief "
            f"({product_epics[0].get('key')})"
        )
    if not matched:
        options = ", ".join(f"{pe.get('key')} ({score:.2f})" for score, pe in scored) or "ninguna"
        bundle.warnings.append(f"User Story sin emparejar: {brief_title!r} vs {options}")
        return
    counter = _counter("CRN")
    for product_epic in matched:
        for child in reader.children(product_epic.get("key") or ""):
            if "user story" not in _type(child).lower():
                continue
            story = _user_story(child, counter)
            if story.criteria:
                bundle.user_stories.append(story)
            else:
                bundle.warnings.append(f"{story.key}: User Story sin criterios de aceptación")
    if not bundle.user_stories:
        bundle.warnings.append("Sin User Story: las User Stories emparejadas no tienen criterios")


def collect_epic(reader: JiraReader, epic_key: str) -> EpicBundle:
    epic = reader.get(epic_key)
    if epic is None:
        bundle = EpicBundle(key=epic_key, summary="")
        bundle.warnings.append("La épica no existe o no es accesible en Jira")
        return bundle
    bundle = EpicBundle(key=epic.get("key") or epic_key, summary=_fields(epic).get("summary") or "")
    counter = _counter("COV")
    for child in reader.children(bundle.key):
        story = _tech_story(child, counter)
        if story.scenarios:
            bundle.technical_stories.append(story)
    if not bundle.technical_stories:
        bundle.warnings.append("La épica no tiene Technical Stories con contenido")
    try:
        collect_user_stories(reader, epic, bundle)
    except Exception as exc:  # Jira caído en la rama de negocio: se sigue solo con TS
        bundle.warnings.append(f"Sin User Story: error leyendo la rama de negocio ({exc})")
    return bundle
