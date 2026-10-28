"""
Sahaay AI - Phase 15: Community Verification Offline Runner
(scripts/validate_phase15_community_verification.py)

Executes offline community verification audit and writes machine-readable results
to reports/phase15/phase15_community_verification_results.json
"""

import os
import sys
import json

from sahaay.reports.verification import run_phase15_community_verification_audit


def main():
    print("=" * 80)
    print("SAHAAY AI — PHASE 15: COMMUNITY VERIFICATION AUDIT")
    print("=" * 80)

    out_path = os.path.join("reports", "phase15", "phase15_community_verification_results.json")
    print(f"\nExecuting community verification offline governance audit...")

    results = run_phase15_community_verification_audit(output_path=out_path)

    print(f"Results written to: {out_path}")
    print(f"\nOverall Audit Status: {results['overall_status']}")
    print("\n[Gate Results]")
    for gate_name, gate_info in results["gates"].items():
        st = gate_info.get("status", "UNKNOWN")
        print(f"  * {gate_name:<42}: {st}")

    print("\n[Safety Invariants Verified]")
    for inv in results["safety_invariants_verified"]:
        print(f"  + {inv}")

    print("=" * 80)


if __name__ == "__main__":
    main()
