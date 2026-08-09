
"""Hold reason compiler — structured hold briefs from residuals.

Leveled (L1): priority ranking, de-dupe, machine JSON export, severity weight.

Independent reference only — no flight operations claim.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Sequence


def digest(obj: object) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


OWNERS = {
    "weather": "Pad Meteorology",
    "propulsion": "Propulsion",
    "conjunction": "Flight Dynamics",
    "sequencer": "Launch Conductor",
    "range": "Range Safety",
    "ground": "Ground Systems",
}

PRIORITY = {
    "propulsion": 100,
    "range": 95,
    "conjunction": 90,
    "sequencer": 80,
    "weather": 70,
    "ground": 60,
}


@dataclass(frozen=True)
class HoldResidual:
    subsystem: str
    code: str
    detail: str
    severity: str = "HIGH"  # LOW|HIGH|CRITICAL


@dataclass(frozen=True)
class HoldBrief:
    headline: str
    machine_codes: tuple[str, ...]
    owners: tuple[str, ...]
    narrative: str
    primary: str | None
    machine: dict[str, Any]
    fingerprint: str


class HoldReasonCompiler:
    def compile(self, residuals: Sequence[HoldResidual]) -> HoldBrief:
        if not residuals:
            body = {"empty": True, "codes": []}
            return HoldBrief(
                "NO_HOLD",
                (),
                (),
                "No active hold residuals.",
                None,
                {"state": "NO_HOLD", "residuals": []},
                digest(body),
            )

        # de-dupe by subsystem:code keeping highest severity
        sev_rank = {"LOW": 1, "HIGH": 2, "CRITICAL": 3}
        best: dict[tuple[str, str], HoldResidual] = {}
        for r in residuals:
            key = (r.subsystem, r.code)
            prev = best.get(key)
            if prev is None or sev_rank.get(r.severity, 0) >= sev_rank.get(prev.severity, 0):
                best[key] = r
        uniq = list(best.values())
        uniq.sort(
            key=lambda r: (
                -sev_rank.get(r.severity, 0),
                -PRIORITY.get(r.subsystem, 0),
                r.subsystem,
                r.code,
            )
        )

        codes = tuple(f"{r.subsystem}:{r.code}" for r in uniq)
        owners = tuple(sorted({OWNERS.get(r.subsystem, r.subsystem) for r in uniq}))
        primary = codes[0]
        headline = f"HOLD({len(uniq)}): " + ", ".join(codes)
        narrative = "; ".join(
            f"{r.subsystem} [{r.code}/{r.severity}] {r.detail}" for r in uniq
        )
        machine = {
            "state": "HOLD",
            "primary": primary,
            "codes": list(codes),
            "owners": list(owners),
            "residuals": [
                {
                    "subsystem": r.subsystem,
                    "code": r.code,
                    "severity": r.severity,
                    "detail": r.detail,
                }
                for r in uniq
            ],
        }
        body = {"codes": list(codes), "owners": list(owners), "narrative": narrative, "primary": primary}
        return HoldBrief(headline, codes, owners, narrative, primary, machine, digest(body))
