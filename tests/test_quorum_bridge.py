from __future__ import annotations

import copy
import unittest

from src.quorum_bridge import compile_quorum_receipt, digest, verify_quorum_receipt


def portable_hold_receipt():
    required = ["weather", "propulsion", "conjunction", "sequencer"]
    freeze_at = "HIGH"
    now = 110.0
    votes = {
        "weather": {"vote": "NO_GO", "severity": "HIGH", "reason_code": "WINDS", "decided_at": 101.0, "half_life_s": 30.0},
        "propulsion": {"vote": "GO", "severity": "LOW", "reason_code": "NOMINAL", "decided_at": 100.0, "half_life_s": 30.0},
        "conjunction": {"vote": "GO", "severity": "LOW", "reason_code": "CLEAR", "decided_at": 100.0, "half_life_s": 30.0},
        "sequencer": {"vote": "GO", "severity": "LOW", "reason_code": "READY", "decided_at": 100.0, "half_life_s": 30.0},
    }
    normalized = {}
    for subsystem, raw in votes.items():
        fp = digest({"subsystem": subsystem, **raw})
        normalized[subsystem] = {**raw, "vote_fingerprint": fp}
    policy = digest({
        "required": required,
        "freeze_at": freeze_at,
        "freshness": "decided_at<=now<=decided_at+half_life_s",
        "non_monotonic_supersession": "refuse",
        "unknown_subsystem_cast": "refuse",
    })
    body = {
        "state": "HOLD",
        "hold_reason": "HOLD:weather:WINDS:HIGH",
        "required": required,
        "freeze_at": freeze_at,
        "policy_fingerprint": policy,
        "evaluation_time": now,
        "live_votes": normalized,
        "stale_subsystems": [],
        "future_subsystems": [],
        "missing_subsystems": [],
    }
    return {
        "schema": "glaciereq.mission-thread-quorum-portable.v1",
        "state": body["state"],
        "hold_reason": body["hold_reason"],
        "required_subsystems": required,
        "freeze_at": freeze_at,
        "live_votes": normalized,
        "stale_subsystems": [],
        "future_subsystems": [],
        "missing_subsystems": [],
        "evaluation_time": now,
        "policy_fingerprint": policy,
        "receipt_fingerprint": digest(body),
    }


class QuorumBridgeTests(unittest.TestCase):
    def test_verified_hold_becomes_operator_hold_with_source_provenance(self):
        receipt = portable_hold_receipt()
        ok, reason = verify_quorum_receipt(receipt)
        self.assertTrue(ok, reason)
        brief = compile_quorum_receipt(receipt)
        self.assertTrue(brief.hold)
        self.assertEqual(brief.reason_count, 1)
        reason = brief.machine["reasons"][0]
        self.assertEqual(reason["owner"], "weather")
        self.assertEqual(reason["code"], "WINDS")
        self.assertEqual(reason["severity"], "HIGH")
        self.assertIn(receipt["receipt_fingerprint"], reason["detail"])

    def test_state_forgery_refuses_before_compilation(self):
        receipt = portable_hold_receipt()
        receipt["state"] = "GO"
        receipt["hold_reason"] = None
        with self.assertRaisesRegex(ValueError, "UNVERIFIED_QUORUM_RECEIPT:QUORUM_DECISION_MISMATCH"):
            compile_quorum_receipt(receipt)

    def test_vote_forgery_refuses(self):
        receipt = portable_hold_receipt()
        receipt["live_votes"]["weather"]["reason_code"] = "FAKE"
        ok, reason = verify_quorum_receipt(receipt)
        self.assertFalse(ok)
        self.assertEqual(reason, "QUORUM_VOTE_FINGERPRINT_MISMATCH:weather")

    def test_go_compiles_to_no_hold(self):
        receipt = portable_hold_receipt()
        for raw in receipt["live_votes"].values():
            raw["vote"] = "GO"
            raw["severity"] = "LOW"
            raw["reason_code"] = "READY"
        for subsystem, raw in receipt["live_votes"].items():
            raw["vote_fingerprint"] = digest({
                "subsystem": subsystem,
                "vote": raw["vote"],
                "severity": raw["severity"],
                "reason_code": raw["reason_code"],
                "decided_at": raw["decided_at"],
                "half_life_s": raw["half_life_s"],
            })
        receipt["state"] = "GO"
        receipt["hold_reason"] = None
        body = {
            "state": "GO",
            "hold_reason": None,
            "required": receipt["required_subsystems"],
            "freeze_at": receipt["freeze_at"],
            "policy_fingerprint": receipt["policy_fingerprint"],
            "evaluation_time": receipt["evaluation_time"],
            "live_votes": receipt["live_votes"],
            "stale_subsystems": [],
            "future_subsystems": [],
            "missing_subsystems": [],
        }
        receipt["receipt_fingerprint"] = digest(body)
        brief = compile_quorum_receipt(receipt)
        self.assertFalse(brief.hold)
        self.assertEqual(brief.machine["state"], "NO_HOLD")

    def test_stale_vote_becomes_explicit_owner_hold(self):
        receipt = portable_hold_receipt()
        receipt["live_votes"].pop("weather")
        receipt["stale_subsystems"] = ["weather"]
        receipt["missing_subsystems"] = ["weather"]
        receipt["state"] = "INCOMPLETE"
        receipt["hold_reason"] = "STALE:weather"
        body = {
            "state": receipt["state"],
            "hold_reason": receipt["hold_reason"],
            "required": receipt["required_subsystems"],
            "freeze_at": receipt["freeze_at"],
            "policy_fingerprint": receipt["policy_fingerprint"],
            "evaluation_time": receipt["evaluation_time"],
            "live_votes": receipt["live_votes"],
            "stale_subsystems": ["weather"],
            "future_subsystems": [],
            "missing_subsystems": ["weather"],
        }
        receipt["receipt_fingerprint"] = digest(body)
        brief = compile_quorum_receipt(receipt)
        self.assertTrue(brief.hold)
        reason = brief.machine["reasons"][0]
        self.assertEqual(reason["owner"], "weather")
        self.assertEqual(reason["code"], "QUORUM_STALE")
        self.assertEqual(reason["severity"], "HIGH")


if __name__ == "__main__":
    unittest.main()
