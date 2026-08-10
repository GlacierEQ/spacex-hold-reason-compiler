"""Hold reason compiler — structured hold briefs from explicit residuals.

This is a deterministic explanation compiler, not a flight/go-no-go controller.
It never clears a hold, commands hardware, or substitutes for an authoritative
mission decision surface.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, Sequence


def digest(obj: object) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


OWNERS: Mapping[str, str] = MappingProxyType(
    {
        "weather": "Pad Meteorology",
        "propulsion": "Propulsion",
        "conjunction": "Flight Dynamics",
        "sequencer": "Launch Conductor",
        "range": "Range Safety",
        "ground": "Ground Systems",
    }
)

PRIORITY: Mapping[str, int] = MappingProxyType(
    {
        "propulsion": 100,
        "range": 95,
        "conjunction": 90,
        "sequencer": 80,
        "weather": 70,
        "ground": 60,
    }
)

SEVERITY_RANK: Mapping[str, int] = MappingProxyType(
    {"LOW": 1, "HIGH": 2, "CRITICAL": 3}
)
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.-]+$")

POLICY_FINGERPRINT = digest(
    {
        "owners": dict(sorted(OWNERS.items())),
        "priority": dict(sorted(PRIORITY.items())),
        "severity_rank": dict(sorted(SEVERITY_RANK.items())),
        "unknown_subsystem_owner_prefix": "UNASSIGNED:",
        "unknown_subsystem_priority": 0,
    }
)


@dataclass(frozen=True)
class HoldResidual:
    subsystem: str
    code: str
    detail: str
    severity: str = "HIGH"


@dataclass(frozen=True)
class HoldBrief:
    headline: str
    machine_codes: tuple[str, ...]
    owners: tuple[str, ...]
    narrative: str
    primary: str | None
    machine: dict[str, Any]
    policy_fingerprint: str
    fingerprint: str


class HoldReasonCompiler:
    @staticmethod
    def _validate(residual: HoldResidual) -> None:
        if not residual.subsystem.strip() or not _TOKEN_RE.match(residual.subsystem):
            raise ValueError("subsystem must be a non-empty machine-safe token")
        if not residual.code.strip() or not _TOKEN_RE.match(residual.code):
            raise ValueError("code must be a non-empty machine-safe token")
        if not residual.detail.strip():
            raise ValueError("detail must be non-empty")
        if residual.severity not in SEVERITY_RANK:
            raise ValueError(f"unknown severity: {residual.severity}")

    @staticmethod
    def _dedupe(residuals: Sequence[HoldResidual]) -> list[HoldResidual]:
        """Keep highest severity per subsystem/code and preserve tied details.

        Equal-severity duplicates are merged deterministically instead of making
        the result depend on caller input order.
        """
        grouped: dict[tuple[str, str], list[HoldResidual]] = {}
        for residual in residuals:
            HoldReasonCompiler._validate(residual)
            grouped.setdefault((residual.subsystem, residual.code), []).append(residual)

        unique: list[HoldResidual] = []
        for (subsystem, code), group in grouped.items():
            highest = max(SEVERITY_RANK[item.severity] for item in group)
            winners = [item for item in group if SEVERITY_RANK[item.severity] == highest]
            severity = winners[0].severity
            details = sorted({item.detail.strip() for item in winners})
            unique.append(HoldResidual(subsystem, code, " | ".join(details), severity))
        return unique

    def compile(self, residuals: Sequence[HoldResidual]) -> HoldBrief:
        if not residuals:
            machine = {
                "state": "NO_HOLD",
                "residuals": [],
                "policy_fingerprint": POLICY_FINGERPRINT,
            }
            return HoldBrief(
                "NO_HOLD",
                (),
                (),
                "No active hold residuals were supplied.",
                None,
                machine,
                POLICY_FINGERPRINT,
                digest(machine),
            )

        unique = self._dedupe(residuals)
        unique.sort(
            key=lambda residual: (
                -SEVERITY_RANK[residual.severity],
                -PRIORITY.get(residual.subsystem, 0),
                residual.subsystem,
                residual.code,
                residual.detail,
            )
        )

        codes = tuple(f"{residual.subsystem}:{residual.code}" for residual in unique)
        owners = tuple(
            sorted(
                {
                    OWNERS.get(residual.subsystem, f"UNASSIGNED:{residual.subsystem}")
                    for residual in unique
                }
            )
        )
        primary = codes[0]
        headline = f"HOLD({len(unique)}): " + ", ".join(codes)
        narrative = "; ".join(
            f"{residual.subsystem} [{residual.code}/{residual.severity}] {residual.detail}"
            for residual in unique
        )
        machine = {
            "state": "HOLD",
            "primary": primary,
            "codes": list(codes),
            "owners": list(owners),
            "residuals": [
                {
                    "subsystem": residual.subsystem,
                    "code": residual.code,
                    "severity": residual.severity,
                    "detail": residual.detail,
                }
                for residual in unique
            ],
            "policy_fingerprint": POLICY_FINGERPRINT,
        }
        return HoldBrief(
            headline,
            codes,
            owners,
            narrative,
            primary,
            machine,
            POLICY_FINGERPRINT,
            digest(machine),
        )
