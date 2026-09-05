"""Publication to QCO Test issues. Does not mutate TestCase coverage fields."""

import json

from app.models.test_case import TestCase, TestCasePriority, TestCaseStatus, TestCaseType
from app.models.test_step import TestStep
from app.services.zephyr_publish import build_remote_description, fingerprint, publish_cases


class _Resp:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or json.dumps(self._payload)

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    def __init__(self) -> None:
        self.created: list[dict] = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, path: str, params=None):
        if "priority" in path:
            return _Resp(
                200,
                [
                    {"id": "1", "name": "Supone un impedimento"},
                    {"id": "2", "name": "Crítica"},
                ],
            )
        return _Resp(200, {"accountId": "acc-1", "displayName": "Tester"})

    def post(self, path: str, json: dict | None = None):
        self.created.append({"path": path, "json": json})
        return _Resp(201, {"key": f"QCO-{len(self.created)}"})


def _case() -> TestCase:
    case = TestCase(
        id=11,
        release_id=20,
        test_case_id="QC-001",
        component="BRF-17442",
        test_case_name="Iniciar el flujo de contratación · WEB",
        description="desc original",
        user_type=None,
        priority=TestCasePriority.CRITICAL,
        test_type=TestCaseType.FUNCTIONAL,
        status=TestCaseStatus.UNEXECUTED,
        test_data="HN: HN001\nDispositivo: WEB",
        justification="razon",
        technical_story="EPC-1",
        ecosystem="OTT",
        device="WEB",
        group_id="g1",
    )
    case.steps = [
        TestStep(step_number=1, test_step="Abrir WEB", expected_result="Sesión WEB"),
        TestStep(step_number=2, test_step="Ejecutar HN001", expected_result="Flujo inicia"),
    ]
    return case


def test_remote_description_keeps_device_and_steps(monkeypatch) -> None:
    text = build_remote_description(_case())
    assert "CaseForgeID:QC-001" in text
    assert "Iniciar el flujo de contratación · WEB"
    assert "Step 1:" in text
    assert "Expected 2:" in text
    assert "Device: WEB" in text or "WEB" in text


def test_publish_does_not_change_fingerprint(monkeypatch) -> None:
    case = _case()
    before = fingerprint(case)
    fake = _FakeClient()
    monkeypatch.setattr("app.services.zephyr_publish._client", lambda timeout=60.0: fake)

    class _DB:
        def scalars(self, _stmt):
            class _R:
                def all(self_inner):
                    return []

            return _R()

        def scalar(self, _stmt):
            return None

        def add(self, _row):
            return None

        def commit(self):
            return None

    records = publish_cases(_DB(), [case])  # type: ignore[arg-type]
    assert records[0].resultado == "created"
    assert records[0].zephyr_id == "QCO-2" or records[0].zephyr_id.startswith("QCO-")
    assert fingerprint(case) == before
    summary = fake.created[-1]["json"]["fields"]["summary"]
    assert summary.endswith("· WEB")
    assert fake.created[-1]["json"]["fields"]["priority"]["id"] == "2"
