"""Hold reason compiler — structured hold briefs from residuals."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Sequence


def digest(obj: object) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


OWNERS = {
    "weather": "Pad Meteorology",
    "propulsion": "Propulsion",
    "conjunction": "Flight Dynamics",
    "sequencer": "Launch Conductor",
}


@dataclass(frozen=True)
class HoldResidual:
    subsystem: str
    code: str
    detail: str


@dataclass(frozen=True)
class HoldBrief:
    headline: str
    machine_codes: tuple[str, ...]
    owners: tuple[str, ...]
    narrative: str
    fingerprint: str


class HoldReasonCompiler:
    def compile(self, residuals: Sequence[HoldResidual]) -> HoldBrief:
        if not residuals:
            body = {"empty": True}
            return HoldBrief(
                "NO_HOLD",
                (),
                (),
                "No active hold residuals.",
                digest(body),
            )
        codes = tuple(f"{r.subsystem}:{r.code}" for r in residuals)
        owners = tuple(sorted({OWNERS.get(r.subsystem, r.subsystem) for r in residuals}))
        headline = f"HOLD({len(residuals)}): " + ", ".join(codes)
        narrative = "; ".join(f"{r.subsystem} [{r.code}] {r.detail}" for r in residuals)
        body = {"codes": list(codes), "owners": list(owners), "narrative": narrative}
        return HoldBrief(headline, codes, owners, narrative, digest(body))
