"""Dump HN classification then TCs for selected BRFs. Does not publish Zephyr.

Does not hardcode product rules; BRF keys are CLI filters only.
Does not persist Test Cases (avoids wiping mixed Operativa releases).
"""

from __future__ import annotations

import argparse
import json
import sys

from sqlalchemy import select

from app.db import SessionLocal
from app.models.epc import Epc
from app.models.release import Release
from app.services.operativa_engine import generate_operativa_from_matrix
from app.services.operativa_engine.coverage_matrix import build_coverage_matrix


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("brf_keys", nargs="+", help="BRF keys to analyze (filters only)")
    parser.add_argument("--persist", action="store_true", help="Persist TCs for those BRFs only")
    args = parser.parse_args()
    wanted = {key.upper() for key in args.brf_keys}

    db = SessionLocal()
    try:
        epcs = list(db.scalars(select(Epc).where(Epc.brf_key.in_(wanted)).order_by(Epc.id)).all())
        if not epcs:
            print("No EPCs found for:", ", ".join(sorted(wanted)), file=sys.stderr)
            return 1
        by_release: dict[int, list[Epc]] = {}
        for epc in epcs:
            if epc.release_id is None:
                continue
            by_release.setdefault(epc.release_id, []).append(epc)
        report: dict = {"brfs": {}}
        for release_id, group in by_release.items():
            release = db.get(Release, release_id)
            name = release.name if release else f"release-{release_id}"
            matrix = build_coverage_matrix(
                release_id=release_id,
                release_name=name,
                epcs=group,
            )
            generated = generate_operativa_from_matrix(
                release_id=release_id,
                release_name=name,
                epcs=group,
            )
            for brf in sorted({epc.brf_key for epc in group}):
                coverage = [item.model_dump() for item in matrix.hn_coverage if item.brf_key == brf]
                rows = [row.model_dump() for row in matrix.rows if row.brf_key == brf]
                cases = [
                    {
                        "name": case.name,
                        "related_jira": case.related_jira,
                        "use_case": case.use_case_title,
                        "device": case.device,
                        "test_data": case.test_data,
                        "component": case.component or case.related_functionality,
                    }
                    for case in generated.candidates
                    if (case.related_functionality or "").upper() == brf.upper()
                    or (case.component or "").upper() == brf.upper()
                ]
                report["brfs"][brf] = {
                    "release_id": release_id,
                    "release_name": name,
                    "hn_classification": coverage,
                    "behaviors": [
                        {
                            "behavior_title": row["behavior_title"],
                            "hn_keys": row["hn_keys"],
                            "origin": row["origin"],
                            "test_data": row["test_data"],
                        }
                        for row in rows
                    ],
                    "tc_count": len(cases),
                    "test_cases": cases,
                }
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        if args.persist:
            print("No se persistió nada (evita borrar un lote mixto). Revisa el JSON primero.", file=sys.stderr)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
