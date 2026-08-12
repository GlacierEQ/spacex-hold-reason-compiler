"""Mission-thread quorum → HoldReasonCompiler bridge.

The bridge verifies the serialized producer receipt independently, then converts
non-GO evidence into ordinary HoldResidual objects. The core hold compiler remains
the single owner of dedupe, priority, and rendering behavior.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Mapping

try:
    from .hold_compiler import HoldBrief, HoldReasonCompiler, HoldResidual
except ImportError:
    from hold_compiler import HoldBrief, HoldReasonCompiler, HoldResidual

SCHEMA = "glaciereq.mission-thread-quorum-portable.v1"
SEVERITY_RANK = {"LOW": 1, "HIGH": 2, "CRITICAL": 3}
VALID_VOTES = {"GO", "NO_GO", "ABSTAIN"}


def digest(obj: object) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def verify_quorum_receipt(receipt: Mapping[str, Any]) -> tuple[bool, str | None]:
    if receipt.get("schema") != SCHEMA:
        return False, "QUORUM_SCHEMA_MISMATCH"
    required = receipt.get("required_subsystems")
    live_votes = receipt.get("live_votes")
    stale = receipt.get("stale_subsystems")
    future = receipt.get("future_subsystems")
    missing = receipt.get("missing_subsystems")
    now = receipt.get("evaluation_time")
    freeze_at = receipt.get("freeze_at")
    if not isinstance(required, list) or not required or not all(isinstance(x, str) and x for x in required):
        return False, "QUORUM_REQUIRED_INVALID"
    if len(required) != len(set(required)):
        return False, "QUORUM_REQUIRED_DUPLICATE"
    if freeze_at not in SEVERITY_RANK or receipt.get("state") not in {"GO", "HOLD", "NO_GO", "INCOMPLETE"}:
        return False, "QUORUM_ENUM_INVALID"
    if not isinstance(now, (int, float)) or not math.isfinite(float(now)):
        return False, "QUORUM_TIME_INVALID"
    if not isinstance(live_votes, Mapping) or not all(isinstance(x, list) for x in (stale, future, missing)):
        return False, "QUORUM_SHAPE_INVALID"
    required_set = set(required)
    if set(missing) != required_set - set(live_votes):
        return False, "QUORUM_MISSING_SET_MISMATCH"
    if not set(stale) <= set(missing) or not set(future) <= set(missing) or set(stale) & set(future):
        return False, "QUORUM_FRESHNESS_SET_MISMATCH"

    normalized: dict[str, dict[str, Any]] = {}
    for subsystem in required:
        if subsystem not in live_votes:
            continue
        raw = live_votes[subsystem]
        if not isinstance(raw, Mapping):
            return False, f"QUORUM_VOTE_INVALID:{subsystem}"
        vote = raw.get("vote")
        severity = raw.get("severity")
        reason_code = raw.get("reason_code")
        decided_at = raw.get("decided_at")
        half_life = raw.get("half_life_s")
        if vote not in VALID_VOTES or severity not in SEVERITY_RANK or not isinstance(reason_code, str) or not reason_code:
            return False, f"QUORUM_VOTE_INVALID:{subsystem}"
        if not isinstance(decided_at, (int, float)) or not isinstance(half_life, (int, float)) or not math.isfinite(float(decided_at)) or not math.isfinite(float(half_life)) or half_life <= 0:
            return False, f"QUORUM_VOTE_INVALID:{subsystem}"
        if not (decided_at <= now <= decided_at + half_life):
            return False, f"QUORUM_VOTE_NOT_LIVE:{subsystem}"
        fingerprint = digest({
            "subsystem": subsystem,
            "vote": vote,
            "severity": severity,
            "reason_code": reason_code,
            "decided_at": decided_at,
            "half_life_s": half_life,
        })
        if raw.get("vote_fingerprint") != fingerprint:
            return False, f"QUORUM_VOTE_FINGERPRINT_MISMATCH:{subsystem}"
        normalized[subsystem] = {
            "vote": vote,
            "severity": severity,
            "reason_code": reason_code,
            "decided_at": decided_at,
            "half_life_s": half_life,
            "vote_fingerprint": fingerprint,
        }

    policy_fp = digest({
        "required": required,
        "freeze_at": freeze_at,
        "freshness": "decided_at<=now<=decided_at+half_life_s",
        "non_monotonic_supersession": "refuse",
        "unknown_subsystem_cast": "refuse",
    })
    if receipt.get("policy_fingerprint") != policy_fp:
        return False, "QUORUM_POLICY_FINGERPRINT_MISMATCH"

    if missing:
        parts = []
        if stale:
            parts.append(f"STALE:{','.join(stale)}")
        if future:
            parts.append(f"FUTURE:{','.join(future)}")
        never_seen = [s for s in missing if s not in stale and s not in future]
        if never_seen:
            parts.append(f"MISSING:{','.join(never_seen)}")
        state, reason = "INCOMPLETE", ";".join(parts) or "INCOMPLETE_QUORUM"
    else:
        freeze_hits = []
        for subsystem in required:
            raw = normalized[subsystem]
            if raw["vote"] == "NO_GO" and SEVERITY_RANK[raw["severity"]] >= SEVERITY_RANK[freeze_at]:
                freeze_hits.append(f"{subsystem}:{raw['reason_code']}:{raw['severity']}")
        if freeze_hits:
            state, reason = "HOLD", f"HOLD:{';'.join(freeze_hits)}"
        elif any(normalized[s]["vote"] == "NO_GO" for s in required):
            state, reason = "NO_GO", "NO_GO_STACK"
        elif any(normalized[s]["vote"] == "ABSTAIN" for s in required):
            state, reason = "INCOMPLETE", "ABSTAIN_PRESENT"
        else:
            state, reason = "GO", None
    if receipt.get("state") != state or receipt.get("hold_reason") != reason:
        return False, "QUORUM_DECISION_MISMATCH"

    body = {
        "state": state,
        "hold_reason": reason,
        "required": required,
        "freeze_at": freeze_at,
        "policy_fingerprint": policy_fp,
        "evaluation_time": now,
        "live_votes": normalized,
        "stale_subsystems": list(stale),
        "future_subsystems": list(future),
        "missing_subsystems": list(missing),
    }
    if receipt.get("receipt_fingerprint") != digest(body):
        return False, "QUORUM_RECEIPT_FINGERPRINT_MISMATCH"
    return True, None


def _residual(subsystem: str, code: str, severity: str, detail: str) -> HoldResidual:
    """Use named fields so producer/consumer evolution cannot silently reorder meaning."""
    return HoldResidual(
        subsystem=subsystem,
        code=code,
        detail=detail,
        severity=severity,
    )


def residuals_from_quorum(receipt: Mapping[str, Any]) -> list[HoldResidual]:
    ok, reason = verify_quorum_receipt(receipt)
    if not ok:
        raise ValueError(f"UNVERIFIED_QUORUM_RECEIPT:{reason}")
    source = str(receipt["receipt_fingerprint"])
    now = receipt["evaluation_time"]
    out: list[HoldResidual] = []

    for subsystem in receipt["stale_subsystems"]:
        out.append(_residual(subsystem, "QUORUM_STALE", "HIGH", f"mission-thread vote stale at t={now}; source_receipt={source}"))
    for subsystem in receipt["future_subsystems"]:
        out.append(_residual(subsystem, "QUORUM_FUTURE", "HIGH", f"mission-thread vote is future-dated at t={now}; source_receipt={source}"))
    never_seen = [s for s in receipt["missing_subsystems"] if s not in receipt["stale_subsystems"] and s not in receipt["future_subsystems"]]
    for subsystem in never_seen:
        out.append(_residual(subsystem, "QUORUM_MISSING", "HIGH", f"mission-thread vote missing at t={now}; source_receipt={source}"))

    for subsystem, raw in receipt["live_votes"].items():
        if raw["vote"] == "NO_GO":
            out.append(_residual(subsystem, raw["reason_code"], raw["severity"], f"mission-thread NO_GO at t={now}; source_receipt={source}"))
        elif raw["vote"] == "ABSTAIN":
            out.append(_residual(subsystem, "QUORUM_ABSTAIN", "HIGH", f"mission-thread abstention at t={now}; source_receipt={source}"))
    return out


def compile_quorum_receipt(receipt: Mapping[str, Any], compiler: HoldReasonCompiler | None = None) -> HoldBrief:
    engine = compiler or HoldReasonCompiler()
    return engine.compile(residuals_from_quorum(receipt))
