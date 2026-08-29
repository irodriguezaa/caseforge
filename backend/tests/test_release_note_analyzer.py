"""Tests for Release Note PDF analyzer, business days calculation, and release endpoints."""

from datetime import date
from io import BytesIO

from pypdf import PdfWriter

from app.services.release_note_analyzer import (
    RuleBasedPdfAnalyzer,
    calculate_business_days,
)


def _generate_test_pdf(text: str) -> bytes:
    """Helper to generate a minimal valid in-memory PDF containing text for testing."""
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    # We can write minimal metadata or text annotations to the page
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_calculate_business_days() -> None:
    # Monday to Friday: 5 days
    assert calculate_business_days(date(2026, 8, 24), date(2026, 8, 28)) == 5
    # Friday to Monday: 2 days (Fri, Mon)
    assert calculate_business_days(date(2026, 8, 28), date(2026, 8, 31)) == 2
    # Weekend only (Saturday to Sunday): 0 days
    assert calculate_business_days(date(2026, 8, 29), date(2026, 8, 30)) == 0
    # Same day (Wednesday): 1 day
    assert calculate_business_days(date(2026, 8, 26), date(2026, 8, 26)) == 1
    # Invalid range (start after end): 0 days
    assert calculate_business_days(date(2026, 8, 28), date(2026, 8, 24)) == 0
    # None input: 0 days
    assert calculate_business_days(None, date(2026, 8, 28)) == 0


def test_rule_based_pdf_analyzer_handles_empty_or_minimal_pdf() -> None:
    pdf_bytes = _generate_test_pdf("Test")
    analyzer = RuleBasedPdfAnalyzer()
    res = analyzer.analyze("RN_CV_7.8.1.pdf", pdf_bytes)

    assert res.pdf_filename == "RN_CV_7.8.1.pdf"
    assert res.detected_version == "7.8.1"
    assert res.qc_engine_version == "v0.1"


def test_analyze_rn_endpoint_validates_pdf(client) -> None:
    # Invalid extension rejected
    response = client.post(
        "/api/v1/releases/analyze-rn",
        files={"file": ("test.txt", b"plain text", "text/plain")},
    )
    assert response.status_code == 400
    assert "Solo se aceptan archivos PDF" in response.json()["detail"]

    # Valid PDF processed
    pdf_bytes = _generate_test_pdf("CV - WINDOWS/XBOX Version 7.8.1")
    response = client.post(
        "/api/v1/releases/analyze-rn",
        files={"file": ("CV_RN_7.8.1.pdf", pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["analysis"]["pdf_filename"] == "CV_RN_7.8.1.pdf"
    assert data["analysis"]["qc_engine_version"] == "v0.1"


def test_create_release_with_qc_setup_and_analysis(client) -> None:
    payload = {
        "name": "CV - WINDOWS/XBOX",
        "version": "7.8.1",
        "platform": "WIN/XBOX",
        "cluster": "Todos",
        "start_date": "2026-09-01",
        "end_date": "2026-09-04",
        "qc_resources": 2,
        "validation_type": "Smoke",
        "jira_issue_filter": "project = CV AND fixVersion = 7.8.1",
        "analysis_data": {
            "pdf_filename": "CV_RN_7.8.1.pdf",
            "detected_name": "CV - WINDOWS/XBOX",
            "detected_version": "7.8.1",
            "detected_platform": "WIN/XBOX",
            "features_count": 5,
            "qa_qc_issues_count": 2,
            "nco_issues_count": 1,
            "qc_engine_version": "v0.1",
        },
    }
    response = client.post("/api/v1/releases", json=payload)
    assert response.status_code == 201
    created = response.json()
    assert created["name"] == "CV - WINDOWS/XBOX"
    assert created["start_date"] == "2026-09-01"
    assert created["end_date"] == "2026-09-04"
    assert created["qc_resources"] == 2
    assert created["execution_days"] == 4  # Sep 1 to Sep 4 (Tue-Fri = 4 business days)
    assert created["validation_type"] == "Smoke"
    assert created["jira_issue_filter"] == "project = CV AND fixVersion = 7.8.1"

    # Verify analysis is retrieved
    analysis_resp = client.get(f"/api/v1/releases/{created['id']}/analysis")
    assert analysis_resp.status_code == 200
    analysis = analysis_resp.json()
    assert analysis["pdf_filename"] == "CV_RN_7.8.1.pdf"
    assert analysis["features_count"] == 5
    assert analysis["qc_engine_version"] == "v0.1"

    # Verify generate-cases stub
    gen_resp = client.post(f"/api/v1/releases/{created['id']}/generate-cases")
    assert gen_resp.status_code == 200
    assert gen_resp.json()["status"] == "READY"
    assert gen_resp.json()["has_analysis"] is True
