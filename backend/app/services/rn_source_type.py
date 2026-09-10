"""Maps RN bucket + Jira issuetype to the App Test Case Type column.

Does not change test_type (FUNCTIONAL/SMOKE/…). Manual and imported cases stay unset.
"""

from __future__ import annotations

from app.schemas.case_generation import GeneratedCaseCandidate

SOURCE_FUNCTIONALITY = "functionality"
SOURCE_NCO = "nco"
SOURCE_TRI = "tri"
SOURCE_QA_BUG = "qa_bug"
SOURCE_QC_BUG = "qc_bug"
SOURCE_QA_QC = "qa_qc"

_VALID = {
    SOURCE_FUNCTIONALITY,
    SOURCE_NCO,
    SOURCE_TRI,
    SOURCE_QA_BUG,
    SOURCE_QC_BUG,
    SOURCE_QA_QC,
}


def source_type_from_issuetype(issuetype: str | None) -> str | None:
    name = (issuetype or "").strip().lower()
    if name == "qa bug":
        return SOURCE_QA_BUG
    if name == "qc bug":
        return SOURCE_QC_BUG
    return None


def source_type_for_rn_bucket(bucket: str, issuetype: str | None = None) -> str:
    if bucket == "nco":
        return SOURCE_NCO
    if bucket == "tri":
        return SOURCE_TRI
    if bucket == "qa_qc":
        return source_type_from_issuetype(issuetype) or SOURCE_QA_QC
    return SOURCE_FUNCTIONALITY


def bucket_from_generation_origin(origin: str | None) -> str | None:
    text = (origin or "").lower()
    if "nco" in text:
        return "nco"
    if "tri" in text and "qa" not in text:
        return "tri"
    if "qa-qc" in text or "qa_qc" in text:
        return "qa_qc"
    if text:
        return "functionality"
    return None


def stamp_source_types(
    candidates: list[GeneratedCaseCandidate],
    issuetypes: dict[str, str] | None = None,
    *,
    fetch_issuetypes=None,
) -> None:
    """Sets candidate.source_type in place. One bulk Jira lookup only for QA/QC keys."""
    qa_keys: list[str] = []
    for candidate in candidates:
        bucket = bucket_from_generation_origin(candidate.generation_origin)
        if candidate.source_type in _VALID and bucket != "qa_qc":
            continue
        if bucket == "qa_qc":
            key = (candidate.related_jira or "").strip().upper()
            if key:
                qa_keys.append(key)
            continue
        if bucket:
            candidate.source_type = source_type_for_rn_bucket(bucket)
        elif not candidate.source_type:
            candidate.source_type = SOURCE_FUNCTIONALITY

    types = dict(issuetypes or {})
    missing = [key for key in dict.fromkeys(qa_keys) if key not in types]
    if missing and fetch_issuetypes is not None:
        types.update(fetch_issuetypes(missing) or {})
    elif missing:
        from app.services.jira_generation import fetch_issuetypes_for_keys

        types.update(fetch_issuetypes_for_keys(missing))

    for candidate in candidates:
        bucket = bucket_from_generation_origin(candidate.generation_origin)
        if bucket != "qa_qc":
            continue
        key = (candidate.related_jira or "").strip().upper()
        candidate.source_type = source_type_for_rn_bucket("qa_qc", types.get(key))
