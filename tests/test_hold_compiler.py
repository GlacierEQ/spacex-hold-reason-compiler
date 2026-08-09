from __future__ import annotations
import unittest
from src.hold_compiler import HoldReasonCompiler, HoldResidual

class HoldTests(unittest.TestCase):
    def test_compile(self):
        b = HoldReasonCompiler().compile([
            HoldResidual("weather", "WINDS", "gusts above limit"),
            HoldResidual("conjunction", "TCA", "object in window"),
        ])
        self.assertIn("WINDS", b.headline)
        self.assertEqual(len(b.machine_codes), 2)
        self.assertTrue(any("Meteorology" in o for o in b.owners))

if __name__ == "__main__":
    unittest.main()
