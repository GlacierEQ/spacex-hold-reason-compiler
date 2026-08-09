
from __future__ import annotations
import unittest
from src.hold_compiler import HoldReasonCompiler, HoldResidual

class HoldLeveledTests(unittest.TestCase):
    def test_compile(self):
        b = HoldReasonCompiler().compile([
            HoldResidual("weather", "WINDS", "gusts above limit"),
            HoldResidual("conjunction", "TCA", "object in window"),
        ])
        self.assertIn("WINDS", b.headline)
        self.assertEqual(len(b.machine_codes), 2)
        self.assertTrue(any("Meteorology" in o or "Dynamics" in o for o in b.owners))
        self.assertIsNotNone(b.primary)

    def test_empty(self):
        b = HoldReasonCompiler().compile([])
        self.assertEqual(b.headline, "NO_HOLD")
        self.assertEqual(b.machine["state"], "NO_HOLD")

    def test_dedupe_keeps_higher_severity(self):
        b = HoldReasonCompiler().compile([
            HoldResidual("weather", "WINDS", "mild", "LOW"),
            HoldResidual("weather", "WINDS", "severe", "CRITICAL"),
        ])
        self.assertEqual(len(b.machine_codes), 1)
        self.assertEqual(b.machine["residuals"][0]["severity"], "CRITICAL")

    def test_priority_orders_propulsion_first(self):
        b = HoldReasonCompiler().compile([
            HoldResidual("weather", "WINDS", "x", "HIGH"),
            HoldResidual("propulsion", "CHAMBER", "y", "HIGH"),
        ])
        self.assertTrue(b.primary and b.primary.startswith("propulsion:"))

    def test_fingerprint_stable(self):
        rs = [HoldResidual("weather", "WINDS", "x")]
        a = HoldReasonCompiler().compile(rs)
        b = HoldReasonCompiler().compile(rs)
        self.assertEqual(a.fingerprint, b.fingerprint)

if __name__ == "__main__":
    unittest.main()
