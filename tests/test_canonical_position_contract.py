from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path: str):
    return json.loads((ROOT / path).read_text())


CANONICAL = load("machine/canonical-position.json")
CAPABILITIES = load("machine/capabilities.json")
TARGET = load("machine/target-contract.json")


class CanonicalPositionContractTests(unittest.TestCase):
    def test_repository_owns_explanation_not_mission_authority(self):
        self.assertEqual(CANONICAL["role"], "CANONICAL_SPECIALIST")
        self.assertEqual(CANONICAL["owns"], "deterministic_structured_hold_explanation")
        self.assertIn("flight safety/go-no-go decision authority", CANONICAL["does_not_own"])
        self.assertIn("hold clearance or hardware actuation", CANONICAL["does_not_own"])

    def test_mission_thread_sibling_is_not_integrated(self):
        edge = CANONICAL["relationships"][0]
        self.assertEqual(edge["repository"], "GlacierEQ/spacex-mission-thread-quorum")
        self.assertFalse(edge["integration_exercised"])

    def test_capabilities_are_repository_native(self):
        capabilities = set(CAPABILITIES["capabilities"])
        self.assertNotIn("hyper-scaling", capabilities)
        self.assertIn("deterministic_hold_residual_deduplication", capabilities)
        self.assertIn("hold_policy_fingerprint", capabilities)
        self.assertIn("complete_hold_brief_receipt", capabilities)

    def test_target_waits_for_exact_head_proof(self):
        self.assertEqual(TARGET["current"]["state"], "PROMOTED")
        self.assertTrue(TARGET["current"]["canonical_position_pending_exact_head_proof"])
        self.assertEqual(TARGET["promotion"]["next_gate"], "CANONICAL_POSITION_RESOLVED")

    def test_truth_boundary_excludes_clearance_and_actuation(self):
        boundary = CAPABILITIES["truth_boundary"]
        self.assertIn("does not authenticate residuals", boundary)
        self.assertIn("clear holds", boundary)
        self.assertIn("actuate hardware", boundary)


if __name__ == "__main__":
    unittest.main()
