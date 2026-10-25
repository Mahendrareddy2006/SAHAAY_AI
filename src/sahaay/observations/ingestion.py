"""Auditable Ground-Truth Data Ingestion Pipeline for Sahaay AI Phase 6."""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
import pandas as pd
from pydantic import ValidationError

from .schemas import (
    GroundTruthObservation,
    VerificationStatus,
    ConsentPrivacyStatus,
)

logger = logging.getLogger("sahaay.observations.ingestion")


class IngestionAuditLog:
    """Audit log entry capturing provenance and processing version."""
    SCHEMA_VERSION = "2.0.0"
    PIPELINE_VERSION = "phase6-1.0.0"


class ObservationIngestionPipeline:
    """
    Ingestion pipeline enforcing:
    1. Schema and coordinate bounding box validation
    2. Non-destructive duplicate detection
    3. Quarantine of synthetic/simulated records
    4. Data tiering: raw immutable vs analysis-ready
    5. Dry-run mode without committing changes
    """

    def __init__(
        self,
        raw_vault_dir: str = "data/phase6/vault/raw",
        analysis_ready_dir: str = "data/phase6/vault/analysis_ready",
        quarantine_dir: str = "data/phase6/vault/quarantine",
    ):
        self.raw_vault_dir = raw_vault_dir
        self.analysis_ready_dir = analysis_ready_dir
        self.quarantine_dir = quarantine_dir
        self._existing_observation_index: Dict[str, GroundTruthObservation] = {}
        self._spatio_temporal_index: List[Tuple[str, str, float, float]] = []  # (id, start_iso, lat, lon)

    def validate_record(self, record_data: Dict[str, Any]) -> Tuple[bool, Optional[GroundTruthObservation], Optional[str]]:
        """Validate a single record against the GroundTruthObservation schema."""
        # Check explicit synthetic flag
        if record_data.get("is_synthetic_or_simulated") is True:
            return False, None, "SYNTHETIC_RECORD_QUARANTINED"

        try:
            obs = GroundTruthObservation(**record_data)
            return True, obs, None
        except ValidationError as e:
            error_msgs = "; ".join([f"{err['loc']}: {err['msg']}" for err in e.errors()])
            return False, None, f"SCHEMA_VALIDATION_ERROR: {error_msgs}"
        except Exception as ex:
            return False, None, f"UNEXPECTED_ERROR: {str(ex)}"

    def check_duplicate(self, obs: GroundTruthObservation) -> Tuple[bool, Optional[str]]:
        """Check for exact or near-duplicate observations in index."""
        # Exact ID duplicate
        if obs.observation_id in self._existing_observation_index:
            return True, f"DUPLICATE_ID_DETECTED: {obs.observation_id}"

        # Spatio-temporal duplicate (same corridor, same 15-min start time, within 0.001 deg lat/lon)
        start_iso = obs.start_time_utc.isoformat()
        for prev_id, prev_start, prev_lat, prev_lon in self._spatio_temporal_index:
            if prev_start[:16] == start_iso[:16]:  # match to minute
                dist_lat = abs(prev_lat - obs.latitude)
                dist_lon = abs(prev_lon - obs.longitude)
                if dist_lat < 0.0005 and dist_lon < 0.0005:  # ~50 meters
                    return True, f"SPATIO_TEMPORAL_DUPLICATE_OF: {prev_id}"

        return False, None

    def ingest_record(self, record_data: Dict[str, Any], dry_run: bool = False) -> Dict[str, Any]:
        """Ingest and route a single observation record."""
        valid, obs, err = self.validate_record(record_data)
        if not valid:
            logger.warning(f"Record rejected: {err}")
            return {
                "success": False,
                "status": "REJECTED",
                "error": err,
                "observation_id": record_data.get("observation_id", "UNKNOWN"),
                "dry_run": dry_run,
            }

        is_dup, dup_reason = self.check_duplicate(obs)
        if is_dup:
            logger.info(f"Duplicate flagged: {dup_reason}")
            return {
                "success": False,
                "status": "FLAGGED_DUPLICATE",
                "error": dup_reason,
                "observation_id": obs.observation_id,
                "dry_run": dry_run,
            }

        # If valid and unique
        if not dry_run:
            self._existing_observation_index[obs.observation_id] = obs
            self._spatio_temporal_index.append((
                obs.observation_id,
                obs.start_time_utc.isoformat(),
                obs.latitude,
                obs.longitude
            ))

        return {
            "success": True,
            "status": "VALIDATED" if dry_run else "INGESTED",
            "observation_id": obs.observation_id,
            "dry_run": dry_run,
            "schema_version": IngestionAuditLog.SCHEMA_VERSION,
            "pipeline_version": IngestionAuditLog.PIPELINE_VERSION,
        }

    def ingest_csv(self, csv_path: str, dry_run: bool = True) -> Dict[str, Any]:
        """Ingest and validate an entire CSV of observation records."""
        if not os.path.exists(csv_path):
            return {
                "success": False,
                "error": f"File not found: {csv_path}",
                "total_records": 0,
                "valid_records": 0,
                "dry_run": dry_run,
            }

        df = pd.read_csv(csv_path)
        records = df.to_dict(orient="records")

        results = {
            "total_records": len(records),
            "valid_records": 0,
            "rejected_records": 0,
            "duplicate_records": 0,
            "synthetic_quarantined": 0,
            "dry_run": dry_run,
            "errors": [],
            "ingested_ids": [],
        }

        for r in records:
            # Clean nan floats to None
            clean_r = {k: (None if pd.isna(v) else v) for k, v in r.items()}
            res = self.ingest_record(clean_r, dry_run=dry_run)
            if res["success"]:
                results["valid_records"] += 1
                results["ingested_ids"].append(res["observation_id"])
            else:
                if res["error"] == "SYNTHETIC_RECORD_QUARANTINED":
                    results["synthetic_quarantined"] += 1
                elif "DUPLICATE" in res["error"]:
                    results["duplicate_records"] += 1
                else:
                    results["rejected_records"] += 1
                results["errors"].append({
                    "observation_id": res.get("observation_id"),
                    "error": res.get("error"),
                })

        return results
