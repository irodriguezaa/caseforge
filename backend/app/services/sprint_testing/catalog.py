"""Sprint → Saved Filter and SWF → program catalog. Not frontend, not KPI maps."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SprintDef:
    id: str
    label: str
    filter_id: str | None


@dataclass(frozen=True)
class ProgramDef:
    program_key: str
    display_name: str


@dataclass(frozen=True)
class SwfDef:
    id: str
    label: str
    programs: tuple[ProgramDef, ...]


SPRINTS: tuple[SprintDef, ...] = (
    SprintDef(id="44", label="Sprint 44", filter_id="117698"),
    SprintDef(id="45", label="Sprint 45", filter_id="117703"),
    SprintDef(id="46", label="Sprint 46", filter_id=None),
)

SWFS: tuple[SwfDef, ...] = (
    SwfDef(
        id="hitss",
        label="Hitss",
        programs=(
            ProgramDef("ADTCL", "ADT / FireTV"),
            ProgramDef("WINCL", "WIN / XBOX"),
            ProgramDef("AAFCL", "AAF Stale"),
            ProgramDef("STVCL", "AAF Evolutivo"),
            ProgramDef("WEBCL", "WEB"),
        ),
    ),
    SwfDef(
        id="tata",
        label="Tata",
        programs=(
            ProgramDef("ATSCL", "STB / Launcher"),
            ProgramDef("SCTCL", "STV Tata"),
        ),
    ),
    SwfDef(
        id="nubiral",
        label="Nubiral",
        programs=(ProgramDef("DPLCL", "DPL"),),
    ),
    SwfDef(
        id="neoris",
        label="Neoris",
        programs=(
            ProgramDef("C9085PR", "Coship 9085"),
            ProgramDef("ADRPR", "ADR"),
            ProgramDef("IOSPR", "iOS"),
            ProgramDef("TVOSPR", "tvOS"),
            ProgramDef("ROKUPR", "Roku"),
        ),
    ),
)


def get_sprint(sprint_id: str) -> SprintDef | None:
    wanted = (sprint_id or "").strip()
    for item in SPRINTS:
        if item.id == wanted:
            return item
    return None


def get_swf(swf_id: str) -> SwfDef | None:
    wanted = (swf_id or "").strip().lower()
    for item in SWFS:
        if item.id == wanted:
            return item
    return None


def program_by_key(swf: SwfDef) -> dict[str, ProgramDef]:
    return {program.program_key.upper(): program for program in swf.programs}
