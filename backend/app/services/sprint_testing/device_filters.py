"""Per-sprint device QA/QC Jira filters from env. Read at request time.

SPRINT45_DEVICE_FILTERS=ADTCL=99868,117752;WEBCL=117767,117790
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceFilterPair:
    qa_filter_id: str | None = None
    qc_filter_id: str | None = None

    def filter_ids(self) -> tuple[str, ...]:
        return tuple(fid for fid in (self.qa_filter_id, self.qc_filter_id) if fid)


def sprint_device_filters(sprint_id: str) -> dict[str, DeviceFilterPair]:
    wanted = (sprint_id or "").strip()
    if not wanted:
        return {}
    raw = os.getenv(f"SPRINT{wanted}_DEVICE_FILTERS", "")
    mapping: dict[str, DeviceFilterPair] = {}
    for chunk in raw.split(";"):
        item = chunk.strip()
        if not item or "=" not in item:
            continue
        device, filters = item.split("=", 1)
        program_key = device.strip().upper()
        slots = [part.strip() for part in filters.split(",")]
        qa = slots[0] if slots and slots[0] else None
        qc = slots[1] if len(slots) > 1 and slots[1] else None
        if not program_key or (qa is None and qc is None):
            continue
        mapping[program_key] = DeviceFilterPair(qa_filter_id=qa, qc_filter_id=qc)
    return mapping
