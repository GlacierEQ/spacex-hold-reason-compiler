#!/usr/bin/env python3
"""Run producer process → serialized quorum receipt → hold compiler consumer."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.quorum_bridge import compile_quorum_receipt, verify_quorum_receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quorum-repo", required=True)
    args = parser.parse_args()
    producer = Path(args.quorum_repo) / "scripts" / "operate_portable.py"
    if not producer.is_file():
        raise SystemExit(f"portable quorum producer missing: {producer}")

    run = subprocess.run(
        [sys.executable, str(producer)],
        cwd=args.quorum_repo,
        check=False,
        capture_output=True,
        text=True,
    )
    if run.returncode != 0:
        print(json.dumps({"status": "FAIL", "stage": "producer", "stderr": run.stderr, "stdout": run.stdout}))
        return 2
    producer_output = json.loads(run.stdout)
    receipt = producer_output["receipt"]
    verified, reason = verify_quorum_receipt(receipt)
    if not verified:
        print(json.dumps({"status": "FAIL", "stage": "consumer_verify", "reason": reason}, indent=2))
        return 3
    brief = compile_quorum_receipt(receipt)
    output = {
        "status": "PASS" if brief.hold else "FAIL",
        "producer_status": producer_output.get("status"),
        "source_receipt": receipt["receipt_fingerprint"],
        "quorum_state": receipt["state"],
        "hold_state": brief.machine["state"],
        "hold_fingerprint": brief.fingerprint,
        "reasons": brief.machine["reasons"],
        "human": brief.human,
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if brief.hold and brief.machine["reasons"] and receipt["receipt_fingerprint"] in brief.machine["reasons"][0]["detail"] else 4


if __name__ == "__main__":
    raise SystemExit(main())
