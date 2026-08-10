from __future__ import annotations

import unittest

from src.hold_compiler import HoldReasonCompiler, HoldResidual


class HoldLeveledTests(unittest.TestCase):
    def test_compile(self):
        brief = HoldReasonCompiler().compile(
            [
                HoldResidual("weather", "WINDS", "gusts above limit"),
                HoldResidual("conjunction", "TCA", "object in window"),
            ]
        )
        self.assertIn("WINDS", brief.headline)
        self.assertEqual(len(brief.machine_codes), 2)
        self.assertTrue(any("Meteorology" in owner or "Dynamics" in owner for owner in brief.owners))
        self.assertIsNotNone(brief.primary)
        self.assertEqual(brief.fingerprint, __import__("src.hold_compiler", fromlist=["digest"]).digest(brief.machine))

    def test_empty(self):
        brief = HoldReasonCompiler().compile([])
        self.assertEqual(brief.headline, "NO_HOLD")
        self.assertEqual(brief.machine["state"], "NO_HOLD")
        self.assertEqual(brief.machine["policy_fingerprint"], brief.policy_fingerprint)

    def test_dedupe_keeps_higher_severity(self):
        brief = HoldReasonCompiler().compile(
            [
                HoldResidual("weather", "WINDS", "mild", "LOW"),
                HoldResidual("weather", "WINDS", "severe", "CRITICAL"),
            ]
        )
        self.assertEqual(len(brief.machine_codes), 1)
        self.assertEqual(brief.machine["residuals"][0]["severity"], "CRITICAL")
        self.assertEqual(brief.machine["residuals"][0]["detail"], "severe")

    def test_equal_severity_duplicate_is_order_independent_and_preserves_details(self):
        first_input = [
            HoldResidual("weather", "WINDS", "gusts", "HIGH"),
            HoldResidual("weather", "WINDS", "crosswind", "HIGH"),
        ]
        second_input = list(reversed(first_input))
        first = HoldReasonCompiler().compile(first_input)
        second = HoldReasonCompiler().compile(second_input)
        self.assertEqual(first.fingerprint, second.fingerprint)
        self.assertEqual(first.machine, second.machine)
        self.assertEqual(first.machine["residuals"][0]["detail"], "crosswind | gusts")

    def test_priority_orders_propulsion_first_at_same_severity(self):
        brief = HoldReasonCompiler().compile(
            [
                HoldResidual("weather", "WINDS", "x", "HIGH"),
                HoldResidual("propulsion", "CHAMBER", "y", "HIGH"),
            ]
        )
        self.assertTrue(brief.primary and brief.primary.startswith("propulsion:"))

    def test_severity_precedes_subsystem_priority(self):
        brief = HoldReasonCompiler().compile(
            [
                HoldResidual("propulsion", "CHAMBER", "x", "LOW"),
                HoldResidual("weather", "LIGHTNING", "y", "CRITICAL"),
            ]
        )
        self.assertTrue(brief.primary and brief.primary.startswith("weather:"))

    def test_unknown_subsystem_is_not_dropped(self):
        brief = HoldReasonCompiler().compile(
            [HoldResidual("novel", "X1", "unclassified residual", "HIGH")]
        )
        self.assertEqual(brief.machine_codes, ("novel:X1",))
        self.assertEqual(brief.owners, ("UNASSIGNED:novel",))

    def test_invalid_residuals_refuse(self):
        invalid = [
            HoldResidual("", "X", "detail", "HIGH"),
            HoldResidual("weather", "", "detail", "HIGH"),
            HoldResidual("weather", "BAD:CODE", "detail", "HIGH"),
            HoldResidual("weather", "X", "", "HIGH"),
            HoldResidual("weather", "X", "detail", "UNKNOWN"),
        ]
        for residual in invalid:
            with self.subTest(residual=residual):
                with self.assertRaises(ValueError):
                    HoldReasonCompiler().compile([residual])

    def test_fingerprint_stable(self):
        residuals = [HoldResidual("weather", "WINDS", "x")]
        first = HoldReasonCompiler().compile(residuals)
        second = HoldReasonCompiler().compile(residuals)
        self.assertEqual(first.fingerprint, second.fingerprint)
        self.assertEqual(first.policy_fingerprint, second.policy_fingerprint)


if __name__ == "__main__":
    unittest.main()
