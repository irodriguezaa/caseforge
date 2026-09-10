from app.schemas.case_generation import CandidateStep, GeneratedCaseCandidate
from app.services.jira_generation import fetch_issuetypes_for_keys
from app.services.rn_source_type import stamp_source_types


def _candidate(**kwargs) -> GeneratedCaseCandidate:
    payload = {
        "name": "Validar X",
        "description": "d",
        "steps": [CandidateStep(step_number=1, action="a", expected_result="e")],
        "related_jira": "WEBCL-1",
        "related_rn": "rn.pdf",
        "evidence": "e",
        "justification": "j",
        "possible_duplicate_of": None,
        "confidence": "medium",
        "review_required": True,
    }
    payload.update(kwargs)
    return GeneratedCaseCandidate.model_validate(payload)


def test_stamp_splits_qa_qc_without_network() -> None:
    qa = _candidate(related_jira="WEBCL-3849", generation_origin="revalidation-qa-qc")
    qc = _candidate(related_jira="WEBCL-3900", generation_origin="incremental-qa-qc")
    nco = _candidate(related_jira="NCO-9", generation_origin="revalidation-nco", source_type="nco")
    stamp_source_types(
        [qa, qc, nco],
        fetch_issuetypes=lambda keys: {key: ("QC Bug" if key.endswith("3900") else "QA Bug") for key in keys},
    )
    assert qa.source_type == "qa_bug"
    assert qc.source_type == "qc_bug"
    assert nco.source_type == "nco"


def test_stamp_defaults_nuevo_to_functionality() -> None:
    row = _candidate(related_jira="WEBCL-3721", generation_origin=None)
    stamp_source_types([row], fetch_issuetypes=lambda _keys: (_ for _ in ()).throw(AssertionError("no jira")))
    assert row.source_type == "functionality"


def test_fetch_issuetypes_posts_search_jql(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _FakeResponse:
        status_code = 200

        def json(self) -> dict:
            return {
                "issues": [
                    {"key": "WEBCL-3900", "fields": {"issuetype": {"name": "QC Bug"}}},
                ],
                "nextPageToken": None,
            }

    class _FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def post(self, path: str, json: dict) -> _FakeResponse:
            captured["path"] = path
            captured["json"] = json
            return _FakeResponse()

    monkeypatch.setattr("app.services.jira_generation._client", lambda timeout=None: _FakeClient())
    found = fetch_issuetypes_for_keys(["WEBCL-3900", "WEBCL-3900"])
    assert found == {"WEBCL-3900": "QC Bug"}
    assert captured["path"] == "/rest/api/3/search/jql"
    assert "issuetype" in captured["json"]["fields"]
    assert "WEBCL-3900" in captured["json"]["jql"]
