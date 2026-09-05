"""CaseForge → Zephyr publication mapping. Dry-run only. Never writes to Jira/Zephyr.

Publication is a later operation on already-persisted Test Cases. It must not rebuild
coverage, expand devices, or merge behaviors.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.models.test_case import TestCase, TestCasePriority, TestCaseStatus, TestCaseType

# Contract already implemented in CaseForge: FLAT Zephyr Excel (one row per step).
# There is no Zephyr Scale / Jira Test API client in this repo.
ZEPHYR_MODEL = "FLAT_EXCEL"
ZEPHYR_SHEET = "Zephyr Export"

ZEPHYR_REQUIRED = (
    "Test Case ID",
    "Component",
    "Test Case Name",
    "Step",
    "Test Step",
    "Expected Result",
    "Priority",
    "Test Type",
    "Status",
)

ZEPHYR_OPTIONAL = (
    "Description",
    "User Type",
)

# Native Zephyr/Jira fields with no CaseForge source. Must stay empty until QC supplies them.
ZEPHYR_UNSOURCED = (
    "Project Key",
    "Folder / Cycle",
    "Issue Key",
    "Assignee / Owner",
    "Labels",
    "Attachments",
    "Estimated Time",
    "Jira Component ID",
)

PRIORITY_MAP = {
    TestCasePriority.CRITICAL.value: "CRITICAL",
    TestCasePriority.BLOCKER.value: "BLOCKER",
}
TEST_TYPE_MAP = {member.value: member.value for member in TestCaseType}
STATUS_MAP = {
    TestCaseStatus.UNEXECUTED.value: "UNEXECUTED",
    TestCaseStatus.PASS.value: "PASS",
    TestCaseStatus.FAIL.value: "FAIL",
    TestCaseStatus.BLOCKED.value: "BLOCKED",
    TestCaseStatus.N_A.value: "N_A",
}


class MappingRow(BaseModel):
    caseforge_field: str
    destination_field: str
    transform: str
    required: bool
    source: str
    risk: str


class DryRunCase(BaseModel):
    test_case_id: str
    brf: str
    name: str
    status: Literal["publicable", "requiere_mapping", "error"]
    reasons: list[str] = Field(default_factory=list)
    zephyr_step_rows: int = 0


class DryRunResponse(BaseModel):
    status: Literal["DRY_RUN"] = "DRY_RUN"
    wrote_jira: bool = False
    wrote_zephyr: bool = False
    model: str = ZEPHYR_MODEL
    evaluated: int = 0
    publicable: int = 0
    require_mapping: int = 0
    without_destination: int = 0
    errors: int = 0
    mapping: list[MappingRow] = Field(default_factory=list)
    unsourced_zephyr_fields: list[str] = Field(default_factory=list)
    cases: list[DryRunCase] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


def publication_mapping() -> list[MappingRow]:
    """Static map. Publication copies persisted TC fields; it does not reason coverage."""
    return [
        MappingRow(
            caseforge_field="test_case_id (QC-nnn)",
            destination_field="Test Case ID",
            transform="Copia literal. Identidad de publicación; no regenerar.",
            required=True,
            source="TestCase.test_case_id persistido",
            risk="Sin ID no hay fila Zephyr. No inventar claves Jira.",
        ),
        MappingRow(
            caseforge_field="BRF (component / technical_epic)",
            destination_field="Component",
            transform="Copia BRF (p. ej. BRF-17442). No sustituir por familia funcional.",
            required=True,
            source="TestCase.component",
            risk="Zephyr Component nativo de Jira no tiene ID; se publica el texto BRF.",
        ),
        MappingRow(
            caseforge_field="Test Case Name (incluye · Device o · Email)",
            destination_field="Test Case Name",
            transform="Copia el nombre completo. No recortar el sufijo de dispositivo.",
            required=True,
            source="TestCase.test_case_name",
            risk="El export Excel actual recorta ' · Device'; la publicación no debe usarlo.",
        ),
        MappingRow(
            caseforge_field="Description + trazabilidad",
            destination_field="Description",
            transform=(
                "Description persistida + bloque de trazabilidad solo con valores existentes: "
                "BRF, HN/CA, EPCs, Behavior, Ecosystem, Device, Canal / Punto de interacción, MDP, Test Data, Reasoning."
            ),
            required=False,
            source="description + test_data + justification + technical_story + group_id",
            risk="Zephyr FLAT no tiene columnas propias para Device/HN/EPC/MDP; sin este bloque se pierden.",
        ),
        MappingRow(
            caseforge_field="User / relevant_users",
            destination_field="User Type",
            transform="Copia si la matriz declaró usuario. Si está vacío, publicar vacío. No inventar.",
            required=False,
            source="TestCase.user_type",
            risk="La mayoría de TCs oficiales no tienen split de usuario.",
        ),
        MappingRow(
            caseforge_field="Test Steps (step_number, test_step)",
            destination_field="Step + Test Step",
            transform="1 TC × N steps = N filas FLAT. Mismo Test Case ID. No fusionar TCs ni steps.",
            required=True,
            source="TestStep.step_number + TestStep.test_step",
            risk="Step vacío bloquea publicación. No reescribir el texto del lote.",
        ),
        MappingRow(
            caseforge_field="Expected Result por step",
            destination_field="Expected Result",
            transform="Pareo posicional 1:1 con Test Step. No embeber todos los expected en una celda.",
            required=True,
            source="TestStep.expected_result",
            risk="El layout EMBEDDED (una celda) no se usa para publicar este lote.",
        ),
        MappingRow(
            caseforge_field="Priority",
            destination_field="Priority",
            transform="CRITICAL→CRITICAL, BLOCKER→BLOCKER. Sin alias inventados (High/Medium).",
            required=True,
            source="TestCase.priority",
            risk="Zephyr Scale UI puede mostrar otras etiquetas; no convertir sin catálogo acordado.",
        ),
        MappingRow(
            caseforge_field="Test Type",
            destination_field="Test Type",
            transform="FUNCTIONAL→FUNCTIONAL. Copia el enum persistido.",
            required=True,
            source="TestCase.test_type",
            risk="No reclasificar a SMOKE/REGRESSION en la publicación.",
        ),
        MappingRow(
            caseforge_field="Status",
            destination_field="Status",
            transform="UNEXECUTED→UNEXECUTED. No marcar PASS/FAIL al publicar.",
            required=True,
            source="TestCase.status",
            risk="Publicar no ejecuta el caso.",
        ),
        MappingRow(
            caseforge_field="Device",
            destination_field="Description (trazabilidad) — sin columna Zephyr",
            transform="Incluir 'Device: {valor}' en Description si hay valor. Email: no fingir dispositivo.",
            required=False,
            source="TestCase.device",
            risk="Sin columna nativa. Perder el device fusionaría comportamientos de la matriz.",
        ),
        MappingRow(
            caseforge_field="Ecosystem",
            destination_field="Description (trazabilidad) — sin columna Zephyr",
            transform="Incluir 'Ecosystem: {valor}' solo si existe.",
            required=False,
            source="TestCase.ecosystem",
            risk="Sin columna nativa.",
        ),
        MappingRow(
            caseforge_field="Canal / Punto de interacción",
            destination_field="Description (trazabilidad) — sin columna Zephyr",
            transform="Copiar interaction_point ya persistido en description/test_data. No añadir puntos de interacción.",
            required=False,
            source="description / test_data",
            risk="Sin columna nativa.",
        ),
        MappingRow(
            caseforge_field="HN/CA",
            destination_field="Description (trazabilidad) — sin columna Zephyr",
            transform="Copiar HN listadas en test_data/description. No reconsultar Confluence.",
            required=False,
            source="test_data / description",
            risk="No hay campo HN en el modelo TestCase; vive en texto persistido.",
        ),
        MappingRow(
            caseforge_field="EPCs",
            destination_field="Description (trazabilidad) + Technical Story local",
            transform="Copiar technical_story (EPCs). No crear un issue Jira por EPC.",
            required=False,
            source="TestCase.technical_story",
            risk="Varios EPC en un TC son trazabilidad, no multiplicador.",
        ),
        MappingRow(
            caseforge_field="Grupo/Behavior (group_id)",
            destination_field="Description (trazabilidad) — sin columna Zephyr",
            transform="Copiar group_id/behavior. Publicación 1 TC persistido = 1 TC Zephyr.",
            required=False,
            source="TestCase.group_id",
            risk="Fusionar por behavior_key rompería la dimensión dispositivo.",
        ),
        MappingRow(
            caseforge_field="MDP",
            destination_field="Description (trazabilidad) — sin columna Zephyr",
            transform="Copiar MDP solo si el TC lo trae. No inventar catálogo de pago.",
            required=False,
            source="test_data / description",
            risk="Sin columna nativa.",
        ),
        MappingRow(
            caseforge_field="Test Data",
            destination_field="Description (concatenado) — sin columna Zephyr FLAT",
            transform="Anexar Test Data a Description. No crear custom field sin acuerdo.",
            required=False,
            source="TestCase.test_data",
            risk="El import FLAT ignora Datos de Prueba como columna propia.",
        ),
        MappingRow(
            caseforge_field="Reasoning / justification",
            destination_field="Description (trazabilidad) — sin columna Zephyr",
            transform="Anexar justification tal cual. No resumir con LLM.",
            required=False,
            source="TestCase.justification",
            risk="Sin columna nativa.",
        ),
        MappingRow(
            caseforge_field="Evidence/Notes",
            destination_field="sin destino Zephyr FLAT",
            transform="No mapear a Test Step. Conservar en CaseForge. Opcional: adjunto posterior.",
            required=False,
            source="TestCase.evidence",
            risk="Extractos largos no caben en Step. No recortar cobertura para publicar.",
        ),
        MappingRow(
            caseforge_field="hn_source / duplicate_status / confidence / complexity / estimation",
            destination_field="sin destino",
            transform="No publicar. Permanecen en CaseForge.",
            required=False,
            source="TestCase metadata",
            risk="Ninguno para cobertura. No inventar Labels a partir de estos campos.",
        ),
    ]


def pack_traceability_description(
    *,
    description: str | None,
    test_data: str | None,
    reasoning: str | None,
    brf: str | None,
    hn: str | None,
    epcs: str | None,
    behavior: str | None,
    ecosystem: str | None,
    device: str | None,
    interaction_point: str | None,
    mdp: str | None,
) -> str:
    """Only copies existing values. Empty fields are omitted, never invented."""
    lines: list[str] = []
    if description:
        lines.append(description.strip())
    block: list[str] = []
    for label, value in (
        ("BRF", brf),
        ("HN/CA", hn),
        ("EPCs", epcs),
        ("Behavior", behavior),
        ("Ecosystem", ecosystem),
        ("Device", device),
        ("Canal / Punto de interacción", interaction_point),
        ("MDP", mdp),
    ):
        text = (value or "").strip()
        if text and text != "—":
            block.append(f"{label}: {text}")
    if test_data and test_data.strip():
        block.append("Test Data:")
        block.append(test_data.strip())
    if reasoning and reasoning.strip():
        block.append("Reasoning:")
        block.append(reasoning.strip())
    if block:
        lines.append("— Trazabilidad CaseForge —")
        lines.extend(block)
    return "\n".join(lines).strip()


def dry_run_persisted_cases(cases: list[TestCase]) -> DryRunResponse:
    mapping = publication_mapping()
    results: list[DryRunCase] = []
    publicable = 0
    require_mapping = 0
    errors = 0
    without_destination = 0

    for case in cases:
        reasons: list[str] = []
        status: Literal["publicable", "requiere_mapping", "error"] = "publicable"
        steps = sorted(case.steps, key=lambda item: item.step_number)
        name = case.test_case_name or ""
        if not (case.test_case_id or "").strip():
            reasons.append("Falta Test Case ID.")
            status = "error"
        if not (case.component or "").strip():
            reasons.append("Falta Component/BRF.")
            status = "error"
        if not name.strip():
            reasons.append("Falta Test Case Name.")
            status = "error"
        if not steps:
            reasons.append("Sin steps persistidos.")
            status = "error"
        for step in steps:
            if not (step.test_step or "").strip() or not (step.expected_result or "").strip():
                reasons.append(f"Step {step.step_number} sin Test Step o Expected Result.")
                status = "error"
        priority = _enum(case.priority)
        if priority not in PRIORITY_MAP:
            reasons.append(f"Priority '{priority}' no mapeable sin inventar valor.")
            status = "error"
        test_type = _enum(case.test_type)
        if test_type not in TEST_TYPE_MAP:
            reasons.append(f"Test Type '{test_type}' no mapeable.")
            status = "error"
        case_status = _enum(case.status)
        if case_status not in STATUS_MAP:
            reasons.append(f"Status '{case_status}' no mapeable.")
            status = "error"

        needs_pack = bool(
            case.device
            or case.ecosystem
            or case.test_data
            or case.justification
            or case.technical_story
            or case.group_id
            or not (case.user_type or "").strip()
        )
        if status != "error":
            if needs_pack:
                status = "requiere_mapping"
                reasons.append(
                    "Device/Ecosystem/HN/EPC/MDP/Test Data/Reasoning no tienen columna Zephyr; "
                    "van en Description sin inventar valores."
                )
            if not (case.user_type or "").strip():
                reasons.append("User Type vacío en fuente; se publica vacío.")

        if status == "error":
            errors += 1
        elif status == "requiere_mapping":
            require_mapping += 1
            publicable += 1
        else:
            publicable += 1

        results.append(
            DryRunCase(
                test_case_id=case.test_case_id,
                brf=case.component,
                name=name,
                status=status,
                reasons=reasons,
                zephyr_step_rows=len(steps),
            )
        )

    # Fields without a native Zephyr column are not "TCs sin destino".
    without_destination = 0

    return DryRunResponse(
        evaluated=len(cases),
        publicable=publicable if errors == 0 else publicable,
        require_mapping=require_mapping,
        without_destination=without_destination,
        errors=errors,
        mapping=mapping,
        unsourced_zephyr_fields=list(ZEPHYR_UNSOURCED),
        cases=results,
        notes=[
            "Modelo de publicación disponible: Excel FLAT 'Zephyr Export' (1 fila = 1 step).",
            "No existe cliente API Zephyr/Jira Test en el repo; este dry-run no escribe nada.",
            "1 Test Case persistido = 1 Test Case Zephyr. No fusionar por BRF/HN/behavior.",
            "No recortar el dispositivo del nombre.",
            "User Type vacío no se rellena.",
            "Evidence/Notes y metadatos de motor no tienen columna destino.",
        ],
    )


def preview_zephyr_rows(case: TestCase) -> list[dict[str, str]]:
    """In-memory FLAT rows. Not written to Jira/Zephyr/files unless a caller persists locally."""
    steps = sorted(case.steps, key=lambda item: item.step_number)
    hn = _line_value(case.test_data, "HN:")
    interaction_point = (
        _line_value(case.test_data, "Canal / Punto de interacción:")
        or _line_value(case.test_data, "Superficies:")
        or _line_value(case.test_data, "Superficies/puntos de entrada:")
    )
    canal = _line_value(case.test_data, "Canal:")
    if not interaction_point and canal == "Email":
        interaction_point = "Email"
    mdp = _line_value(case.test_data, "MDP:")
    description = pack_traceability_description(
        description=case.description,
        test_data=case.test_data,
        reasoning=case.justification,
        brf=case.component,
        hn=hn,
        epcs=case.technical_story,
        behavior=case.group_id,
        ecosystem=case.ecosystem,
        device=case.device,
        interaction_point=interaction_point,
        mdp=mdp if mdp and "no declarado" not in mdp.lower() else (mdp or None),
    )
    rows = []
    for step in steps:
        rows.append(
            {
                "Test Case ID": case.test_case_id,
                "Component": case.component,
                "Test Case Name": case.test_case_name,
                "Description": description,
                "User Type": case.user_type or "",
                "Step": str(step.step_number),
                "Test Step": step.test_step,
                "Expected Result": step.expected_result,
                "Priority": PRIORITY_MAP[_enum(case.priority)],
                "Test Type": TEST_TYPE_MAP[_enum(case.test_type)],
                "Status": STATUS_MAP[_enum(case.status)],
            }
        )
    return rows


def _enum(value: object) -> str:
    return value.value if hasattr(value, "value") else str(value or "")


def _line_value(blob: str | None, prefix: str) -> str | None:
    if not blob:
        return None
    for line in blob.splitlines():
        if line.startswith(prefix):
            text = line.split(":", 1)[1].strip()
            return text or None
    return None
