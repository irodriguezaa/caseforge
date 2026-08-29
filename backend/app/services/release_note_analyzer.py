"""Release Note PDF extraction and structured preparation service.

Strictly deterministic rule-based extraction for Phase 1.
NO intenta reemplazar ni anticipar la lógica del motor QC que se integrará posteriormente
desde el archivo .md (QC Engine). No inventa casos de prueba, estimaciones ni coberturas.
"""

import io
import re
from datetime import date, timedelta
from typing import Any

from pypdf import PdfReader

from app.schemas.release import ReleaseAnalysisBase


def calculate_business_days(start_date: date | None, end_date: date | None) -> int:
    """Calculates business days (Monday through Friday only) between start_date and end_date (inclusive)."""
    if not start_date or not end_date or start_date > end_date:
        return 0
    current = start_date
    business_days = 0
    while current <= end_date:
        if current.weekday() < 5:  # 0=Monday, 4=Friday
            business_days += 1
        current += timedelta(days=1)
    return business_days


# Canonical 17 device options
KNOWN_DEVICES = [
    "WEB",
    "ADR",
    "ADT",
    "FireTv",
    "AAF Evolutivo",
    "AAF Legacy",
    "STB IPTV",
    "STV Tata Samsung",
    "STV Tata Hisense",
    "STV Tata LG",
    "STV Tata ADT",
    "WIN/XBOX",
    "Coship9085",
    "iOS",
    "tvOS",
    "Kepler",
    "IPTV AOSP",
]


class RuleBasedPdfAnalyzer:
    """Deterministic extractor for Release Note PDF documents."""

    def extract_text(self, pdf_bytes: bytes) -> str:
        try:
            reader = PdfReader(io.BytesIO(pdf_bytes))
            pages_text: list[str] = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    pages_text.append(text)
            return "\n".join(pages_text)
        except Exception:
            return ""

    def analyze(self, filename: str, pdf_bytes: bytes) -> ReleaseAnalysisBase:
        text = self.extract_text(pdf_bytes)
        observations: list[str] = []

        # 1. Detect Version
        detected_version = None
        version_match = re.search(
            r"(?:versi[oó]n|ver\.?|v\.?)\s*[:\-]?\s*([0-9]+\.[0-9]+(?:\.[0-9]+)?)",
            text,
            re.IGNORECASE,
        )
        if version_match:
            detected_version = version_match.group(1).strip()
        else:
            # Try to extract version from filename (e.g. RN_CV_7.8.1.pdf)
            fn_version_match = re.search(r"v?([0-9]+\.[0-9]+(?:\.[0-9]+)?)", filename)
            if fn_version_match:
                detected_version = fn_version_match.group(1).strip()

        # 2. Detect Name / Project
        detected_name = None
        name_match = re.search(
            r"(?:nombre|release|proyecto|aplicaci[oó]n)\s*[:\-]\s*([^\n\r]+)",
            text,
            re.IGNORECASE,
        )
        if name_match:
            candidate = name_match.group(1).strip()
            if len(candidate) > 2 and len(candidate) < 100:
                detected_name = candidate

        if not detected_name and "CV" in text.upper():
            # Check for standard Claro Video pattern (e.g. CV - WINDOWS/XBOX)
            cv_match = re.search(r"(CV\s*[-–]\s*[A-Za-z0-9 /_\-]+)", text, re.IGNORECASE)
            if cv_match:
                detected_name = cv_match.group(1).strip()

        if not detected_name:
            # Fallback based on filename without extension
            clean_fn = re.sub(r"\.pdf$", "", filename, flags=re.IGNORECASE)
            detected_name = clean_fn.replace("_", " ").replace("-", " ").strip()

        # 3. Detect Platform / Device
        detected_platform = None
        text_upper = text.upper()
        detected_dev_list: list[str] = []
        for dev in KNOWN_DEVICES:
            dev_upper = dev.upper()
            if dev_upper in text_upper:
                detected_dev_list.append(dev)

        if "WIN" in text_upper or "XBOX" in text_upper:
            detected_platform = "WIN/XBOX"
        elif "IOS" in text_upper:
            detected_platform = "iOS"
        elif "TVOS" in text_upper:
            detected_platform = "tvOS"
        elif "ADR" in text_upper or "ANDROID" in text_upper:
            detected_platform = "ADR"
        elif "WEB" in text_upper:
            detected_platform = "WEB"
        elif detected_dev_list:
            detected_platform = detected_dev_list[0]

        detected_devices_str = " / ".join(detected_dev_list) if detected_dev_list else detected_platform

        # 4. Count Sections / Items deterministically
        features_count = 0
        qa_qc_count = 0
        nco_count = 0

        # Look for bullet points or lists in text
        # Count explicit occurrences in text or section headers
        feature_sections = re.findall(
            r"(?:funcionalidades|features|alcance|nuevos desarrollos)[\s\S]*?(?=(?:incidencias|bugs|nco|control|notas|\Z))",
            text,
            re.IGNORECASE,
        )
        if feature_sections:
            for sec in feature_sections:
                bullets = re.findall(r"(?:^|\n)\s*(?:[\*\-•]|\d+\.)\s*([^\n]+)", sec)
                features_count += len(bullets)

        qa_sections = re.findall(
            r"(?:incidencias qa|incidencias qc|bugs qa|bugs qc|qa/qc)[\s\S]*?(?=(?:nco|funcionalidades|features|notas|\Z))",
            text,
            re.IGNORECASE,
        )
        if qa_sections:
            for sec in qa_sections:
                bullets = re.findall(r"(?:^|\n)\s*(?:[\*\-•]|\d+\.)\s*([^\n]+)", sec)
                qa_qc_count += len(bullets)

        nco_sections = re.findall(
            r"(?:incidencias nco|nco|no conformidades)[\s\S]*?(?=(?:funcionalidades|features|qa|notas|\Z))",
            text,
            re.IGNORECASE,
        )
        if nco_sections:
            for sec in nco_sections:
                bullets = re.findall(r"(?:^|\n)\s*(?:[\*\-•]|\d+\.)\s*([^\n]+)", sec)
                nco_count += len(bullets)

        # 5. Extract Description
        detected_description = None
        desc_match = re.search(
            r"(?:descripci[oó]n|objetivo|resumen)\s*[:\-]\s*([^\n\r]+(?:\n[^\n\r]+)?)",
            text,
            re.IGNORECASE,
        )
        if desc_match:
            detected_description = desc_match.group(1).strip()

        # 6. Build observations
        if not text:
            observations.append("El archivo PDF no contiene texto extraíble (puede ser un documento escaneado o protegido).")
        else:
            if not detected_platform:
                observations.append("No se detectó un dispositivo explícito en el texto del PDF; verifique la selección manual.")
            if not detected_version:
                observations.append("No se detectó el número de versión en el documento; ingréselo manualmente.")
            if features_count > 0:
                observations.append(f"Se detectaron {features_count} elemento(s) en la sección de funcionalidades.")
            if qa_qc_count > 0:
                observations.append(f"Se identificaron {qa_qc_count} incidencia(s) QA/QC reportadas en el Release Note.")
            if nco_count > 0:
                observations.append(f"Se identificaron {nco_count} incidencia(s) NCO reportadas.")

        raw_analysis = {
            "text_length": len(text),
            "pages_analyzed": len(text.split("\n\n")),
            "detected_keywords": detected_dev_list,
            "filename": filename,
        }

        return ReleaseAnalysisBase(
            pdf_filename=filename,
            detected_name=detected_name,
            detected_version=detected_version,
            detected_platform=detected_platform,
            detected_description=detected_description,
            features_count=features_count,
            qa_qc_issues_count=qa_qc_count,
            nco_issues_count=nco_count,
            detected_devices=detected_devices_str,
            proposed_coverage=None,  # Será responsabilidad del QC Engine (.md) futuro
            estimation_text=None,    # Será responsabilidad del QC Engine (.md) futuro
            observations=observations,
            raw_analysis=raw_analysis,
            qc_engine_version="v0.1",
        )
