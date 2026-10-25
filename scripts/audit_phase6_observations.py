#!/usr/bin/env python3
"""
Sahaay AI — Phase 6 Ground-Truth Observation Audit Script

Usage:
    python scripts/audit_phase6_observations.py --input-csv data/phase6/observation_template.csv --dry-run
"""

import os
import sys
import json
import argparse
import logging
from datetime import datetime, timezone

# Add repository root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from sahaay.observations.ingestion import ObservationIngestionPipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("audit_phase6_observations")


def audit_observations(input_csv: str, dry_run: bool = True, output_report: str = None) -> dict:
    logger.info(f"Auditing observation dataset: {input_csv} (dry_run={dry_run})")
    
    pipeline = ObservationIngestionPipeline()
    results = pipeline.ingest_csv(input_csv, dry_run=dry_run)
    
    report = {
        "audit_timestamp": datetime.now(timezone.utc).isoformat(),
        "input_dataset": input_csv,
        "dry_run": dry_run,
        "total_records_evaluated": results.get("total_records", 0),
        "valid_records_passed": results.get("valid_records", 0),
        "rejected_records": results.get("rejected_records", 0),
        "duplicate_records_flagged": results.get("duplicate_records", 0),
        "synthetic_records_quarantined": results.get("synthetic_quarantined", 0),
        "status": "AUDIT_COMPLETE",
        "real_world_field_data_acquired": 0,  # Explicitly tracking real field data acquired
        "errors": results.get("errors", []),
    }
    
    if output_report:
        os.makedirs(os.path.dirname(os.path.abspath(output_report)), exist_ok=True)
        with open(output_report, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        logger.info(f"Audit report saved to: {output_report}")
        
    logger.info(
        f"Audit Summary: {report['valid_records_passed']}/{report['total_records_evaluated']} valid, "
        f"{report['rejected_records']} rejected, {report['duplicate_records_flagged']} duplicates, "
        f"{report['synthetic_records_quarantined']} quarantined."
    )
    return report


def main():
    parser = argparse.ArgumentParser(description="Audit Phase 6 Ground-Truth Field Observations")
    parser.add_argument("--input-csv", type=str, default="data/phase6/observation_template.csv", help="Path to observation CSV")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Validate without mutating database")
    parser.add_argument("--output-report", type=str, default="reports/phase6/observation_audit_report.json", help="Path to output JSON report")
    
    args = parser.parse_args()
    audit_observations(args.input_csv, dry_run=args.dry_run, output_report=args.output_report)


if __name__ == "__main__":
    main()
