"""Corre v2-B para una o varias Technical Epics sin tocar la base de datos.

Uso (desde la raíz, con Docker):
    docker compose run --rm --no-deps -v "$PWD/exports:/out" backend \\
        python -m app.services.qc_v2b.cli WEBCL-1586 --device WEB --out /out
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from app.services.qc_v2.cli import _jsonable, build_workbook
from app.services.qc_v2b.engine import run_epics


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="QcPulse v2-B: paquete QC sin tocar la base de datos")
    parser.add_argument("epics", nargs="+", help="Technical Epics, ej. WEBCL-1586")
    parser.add_argument("--device", required=True, help="Dispositivo de la Release, ej. WEB, ADT, ADR")
    parser.add_argument("--region", default=None)
    parser.add_argument("--out", default="/out")
    parser.add_argument("--label", default=None)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    label = args.label or f"v2b_{args.device}_{datetime.now():%Y%m%d_%H%M}"
    runs = []
    for key in [k.strip().upper() for k in args.epics]:
        current = run_epics([key], args.device, args.region)
        runs.extend(current)
        (out / f"qcv2b_{label}.json").write_text(
            json.dumps([_jsonable(r) for r in runs], ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        build_workbook(runs).save(out / f"qcv2b_{label}.xlsx")
        for run in current:
            print(run.summary(), flush=True)
            for warning in run.bundle.warnings:
                print(f"   aviso: {warning}", flush=True)
            tipos = {}
            for candidate in run.candidates:
                tipo = next((r.split("=", 1)[1] for r in candidate.applied_rules if r.startswith("qc-v2:tipo=")), "?")
                tipos[tipo] = tipos.get(tipo, 0) + 1
            print(f"   paquete={len(run.candidates)} tipos={tipos}", flush=True)
        if any((r.error or "").startswith("corrida detenida") for r in current):
            print("Corrida detenida (OpenAI sin créditos). Lo generado hasta aquí quedó guardado.")
            break
    print(f"Listo: {out / f'qcv2b_{label}.xlsx'}")
    return 1 if any(r.error for r in runs) else 0


if __name__ == "__main__":
    sys.exit(main())
