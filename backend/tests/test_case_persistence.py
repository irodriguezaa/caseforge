from app.models.release import Release
from app.schemas.case_generation import CandidateStep, GeneratedCaseCandidate
from app.services.case_persistence import persist_candidates


def test_persist_clips_merged_jira_keys_that_exceed_columns(db_session) -> None:
    """ADT 10.1.2 consolidates the same Gherkin across many epics; pipe-joined keys
    overflow technical_epic (250) / technical_story (500) and 500 on Postgres."""
    release = Release(name="ADT 10.1.2", version="10.1.2", platform="ADT")
    db_session.add(release)
    db_session.flush()
    epic = " | ".join(f"ADTCL-{i}" for i in range(100, 140))
    story = " | ".join(f"ADTCL-{i}" for i in range(200, 280))
    assert len(epic) > 250
    assert len(story) > 500
    candidate = GeneratedCaseCandidate(
        name="No se logra obtener una llave",
        description="Consolidado",
        steps=[CandidateStep(step_number=1, action="Abrir", expected_result="Se observa el error")],
        related_functionality=epic,
        related_jira=story,
        evidence="gherkin",
        justification="fill",
        covers=["COV-001"],
    )
    created = persist_candidates(db_session, release.id, "ADT", [candidate])
    db_session.commit()
    row = created[0]
    assert len(row.technical_epic or "") == 250
    assert len(row.technical_story or "") == 500
    assert (row.technical_epic or "").startswith("ADTCL-100")
