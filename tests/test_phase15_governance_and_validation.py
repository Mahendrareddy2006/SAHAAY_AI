"""
Sahaay AI - Phase 15: Vision Data Acquisition & Label Governance Test Suite
(tests/test_phase15_governance_and_validation.py)

Tests:
1. Strict decoupling of visual flood evidence, wet road surface, physical depth, and passability.
2. Rejection of model-inferred water depth and model-inferred road passability.
3. Rejection of contradictory labels (wet non-flooded road labeled as flooded_road).
4. Metadata integrity, timestamp validation, and Hyderabad metropolitan spatial bounding box.
5. De-identification status enforcement and consent reference validation.
6. Source-class balance and Cramér's V confounding audit.
7. Reproducible partitioning grouping correlated sessions and clusters atomically.
8. Independent evaluation set key-lock assertion (is_locked_for_tuning).
9. Exhaustive partition isolation verification (zero cross-split ID, MD5, session, or near-duplicate leaks).
10. Preservation of historical model checkpoints and the NO-GO training gate.
"""

import os
import hashlib
from datetime import datetime, timezone, timedelta
import pytest
import numpy as np
import pandas as pd

from sahaay.data_collection_v4.schemas import (
    AcquisitionRecord,
    AnnotationRecord,
    AnnotationLabel,
    PermissionStatus,
    SourceType,
    CaptureMethod,
    WeatherCondition,
    LightingCondition,
    RoadSurfaceCondition,
    ReviewStatus,
    PrivacyProcessingStatus,
    AdjudicationStatus,
    DepthMeasurementMethod,
    VerifiedPassability,
    ImageQualityStatus,
)
from sahaay.data_collection_v4.governance import (
    HYDERABAD_BOUNDS,
    validate_metadata_integrity,
    validate_annotation_governance,
    audit_source_class_balance,
    partition_dataset_with_session_grouping,
    verify_partition_isolation,
)
from scripts.check_v4_data_readiness import evaluate_readiness


# =====================================================================
# 1. Label Governance & Decoupling Invariants
# =====================================================================

def test_valid_decoupled_annotation():
    """Valid annotation with properly decoupled fields passes validation."""
    record = AnnotationRecord(
        image_id="IMG-HYD-001",
        annotator_id_pseudonymous="ANN-01",
        label=AnnotationLabel.FLOODED_ROAD,
        visible_water_extent="full_carriageway",
        road_obstruction_evidence="slow_traffic",
        visibility_quality="high_clarity",
        lighting_condition=LightingCondition.DAYLIGHT,
        occlusion="none",
        label_confidence=0.95,
        is_wet_non_flooded=False,
        verified_flood_event_id="EVT-2026-07-GHMC-01",
        event_verification_source="GHMC_EMERGENCY_DISPATCH",
        measured_water_depth_mm=175.0,
        depth_measurement_time="2026-07-15T14:30:00Z",
        depth_measurement_method=DepthMeasurementMethod.ULTRASONIC_TELEMETRY,
        verified_road_passability=VerifiedPassability.IMPASSABLE_TWO_WHEELERS,
        image_quality_status=ImageQualityStatus.SUFFICIENT,
    )
    assert record.image_id == "IMG-HYD-001"
    assert record.measured_water_depth_mm == 175.0
    assert record.verified_road_passability == VerifiedPassability.IMPASSABLE_TWO_WHEELERS


def test_rejection_of_depth_without_method():
    """Asserting measured water depth without a valid measurement method must fail."""
    with pytest.raises(ValueError, match="depth_measurement_method is 'unmeasured'"):
        AnnotationRecord(
            image_id="IMG-HYD-002",
            annotator_id_pseudonymous="ANN-01",
            label=AnnotationLabel.FLOODED_ROAD,
            visible_water_extent="curb_to_curb",
            road_obstruction_evidence="none",
            visibility_quality="high_clarity",
            lighting_condition=LightingCondition.DAYLIGHT,
            label_confidence=0.90,
            measured_water_depth_mm=120.0,
            depth_measurement_method=DepthMeasurementMethod.UNMEASURED,  # Violates rule
        )


def test_rejection_of_unverified_road_passability():
    """Asserting road passability without an independent verification source must fail."""
    with pytest.raises(ValueError, match="event_verification_source is unverified"):
        AnnotationRecord(
            image_id="IMG-HYD-003",
            annotator_id_pseudonymous="ANN-01",
            label=AnnotationLabel.FLOODED_ROAD,
            visible_water_extent="full_carriageway",
            road_obstruction_evidence="diverted_traffic",
            visibility_quality="high_clarity",
            lighting_condition=LightingCondition.DAYLIGHT,
            label_confidence=0.90,
            verified_road_passability=VerifiedPassability.IMPASSABLE_ALL_VEHICLES,
            event_verification_source="unverified",  # Violates rule
        )


def test_rejection_of_contradictory_wet_non_flooded_label():
    """A scene flagged as is_wet_non_flooded=True cannot be labeled as FLOODED_ROAD."""
    with pytest.raises(ValueError, match="is_wet_non_flooded=True cannot be labeled as FLOODED_ROAD"):
        AnnotationRecord(
            image_id="IMG-HYD-004",
            annotator_id_pseudonymous="ANN-01",
            label=AnnotationLabel.FLOODED_ROAD,  # Contradicts is_wet_non_flooded
            visible_water_extent="isolated_puddles",
            road_obstruction_evidence="none",
            visibility_quality="high_clarity",
            lighting_condition=LightingCondition.DAYLIGHT,
            label_confidence=0.90,
            is_wet_non_flooded=True,
        )


def test_valid_wet_non_flooded_negative_control():
    """Wet asphalt without inundation must be correctly annotated as negative control."""
    record = AnnotationRecord(
        image_id="IMG-HYD-005",
        annotator_id_pseudonymous="ANN-01",
        label=AnnotationLabel.WET_NO_VISIBLE_INUNDATION,
        visible_water_extent="isolated_puddles",
        road_obstruction_evidence="none",
        visibility_quality="moderate_spray",
        lighting_condition=LightingCondition.TWILIGHT_DUSK,
        label_confidence=0.88,
        is_wet_non_flooded=True,
        depth_measurement_method=DepthMeasurementMethod.UNMEASURED,
        verified_road_passability=VerifiedPassability.PASSABLE_ALL_VEHICLES,
        event_verification_source="FIELD_INSPECTOR_PATROL",
    )
    assert record.is_wet_non_flooded is True
    assert record.label == AnnotationLabel.WET_NO_VISIBLE_INUNDATION


# =====================================================================
# 2. Metadata Integrity & Spatial Bounding Box
# =====================================================================

def test_metadata_hyderabad_bounding_box_validation():
    """Coordinates within Hyderabad metropolitan area pass; outside coordinates are rejected."""
    df_valid = pd.DataFrame([{
        "acquisition_id": "ACQ-VALID-01",
        "location_id": "HYD-LOC-001",
        "capture_timestamp": "2026-07-20T12:00:00Z",
        "source_type": "municipal_cctv",
        "source_owner": "GHMC_ICCC",
        "permission_status": "approved",
        "consent_or_authorization_reference": "MOU-GHMC-2026-01",
        "capture_method": "fixed_cctv",
        "camera_or_device_id_pseudonymous": "cam_01",
        "latitude": 17.3984,  # Inside Hyderabad
        "longitude": 78.4145, # Inside Hyderabad
        "location_precision_m": 5.0,
        "weather_condition": "heavy_rain",
        "lighting_condition": "daylight",
        "road_surface_condition": "inundated_shallow",
        "image_or_clip_reference": "img_01.jpg",
        "retention_expiry": "2029-07-20T00:00:00Z",
        "privacy_processing_status": "blurred_verified"
    }])
    res_valid = validate_metadata_integrity(df_valid)
    assert res_valid["is_valid"] is True
    assert res_valid["valid_records"] == 1

    df_outside = df_valid.copy()
    df_outside.loc[0, "latitude"] = 12.9716  # Bangalore latitude
    df_outside.loc[0, "longitude"] = 77.5946 # Bangalore longitude
    res_outside = validate_metadata_integrity(df_outside)
    assert res_outside["is_valid"] is False
    assert res_outside["excluded_records"] == 1
    assert "coordinates_outside_hyderabad" in res_outside["issues_summary"]


def test_metadata_future_timestamp_rejection():
    """Future timestamps must be intercepted and rejected."""
    future_time = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    df_future = pd.DataFrame([{
        "acquisition_id": "ACQ-FUTURE-01",
        "location_id": "HYD-LOC-001",
        "capture_timestamp": future_time,
        "source_type": "municipal_cctv",
        "source_owner": "GHMC_ICCC",
        "permission_status": "approved",
        "consent_or_authorization_reference": "MOU-GHMC-2026-01",
        "capture_method": "fixed_cctv",
        "camera_or_device_id_pseudonymous": "cam_01",
        "latitude": 17.3984,
        "longitude": 78.4145,
        "location_precision_m": 5.0,
        "weather_condition": "clear",
        "lighting_condition": "daylight",
        "road_surface_condition": "dry",
        "image_or_clip_reference": "img_02.jpg",
        "retention_expiry": "2029-07-20T00:00:00Z",
        "privacy_processing_status": "blurred_verified"
    }])
    res = validate_metadata_integrity(df_future)
    assert res["is_valid"] is False
    assert "future_timestamp" in res["issues_summary"]


# =====================================================================
# 3. Source-Class Balance & Confounding Audit
# =====================================================================

def test_source_class_balance_audit_detects_confounding():
    """Auditing Manifest V4 must flag that Cramer's V is 1.0 and sources are confounded."""
    m4_path = os.path.join("data", "processed", "manifest_v4", "full_manifest_v4.csv")
    if not os.path.exists(m4_path):
        pytest.skip(f"Manifest V4 not found: {m4_path}")

    m4_df = pd.read_csv(m4_path)
    res = audit_source_class_balance(m4_df)

    assert res["is_confounded"] is True
    assert res["cramers_v"] == 1.0000
    assert res["mutual_information_bits"] == 1.0000
    assert res["sources_with_both_classes_count"] == 0
    assert res["gates"]["cramers_v_passed"] is False
    assert res["gates"]["multi_source_cross_representation_passed"] is False


def test_source_class_balance_audit_passes_on_unconfounded_mock():
    """A balanced dataset with 2 sources each contributing both classes passes audit."""
    records = []
    # Source A: 120 flood, 120 non-flood
    for i in range(120):
        records.append({"source_dataset": "source_A", "label": 1})
        records.append({"source_dataset": "source_A", "label": 0})
    # Source B: 120 flood, 120 non-flood
    for i in range(120):
        records.append({"source_dataset": "source_B", "label": 1})
        records.append({"source_dataset": "source_B", "label": 0})

    mock_df = pd.DataFrame(records)
    res = audit_source_class_balance(mock_df)

    assert res["is_confounded"] is False
    assert res["cramers_v"] == 0.0000
    assert res["mutual_information_bits"] == 0.0000
    assert res["sources_with_both_classes_count"] == 2
    assert res["gates"]["cramers_v_passed"] is True
    assert res["gates"]["multi_source_cross_representation_passed"] is True


# =====================================================================
# 4. Reproducible Session-Grouped Partitioning & Isolation
# =====================================================================

def test_partitioning_atomic_session_grouping():
    """
    Asserts that frames sharing capture_session_id or cluster_id are NEVER divided
    across Train, Validation, and Independent Evaluation partitions.
    """
    records = []
    for s_idx in range(1, 11):
        sess_id = f"SESSION_{s_idx:03d}"
        cluster_id = f"CLUSTER_{s_idx:03d}"
        h_base = hashlib.sha256(f"seed_{s_idx}".encode()).hexdigest()[:16]
        for f_idx in range(1, 6):
            img_id = f"FRAME_{s_idx:03d}_{f_idx:03d}"
            records.append({
                "image_id": img_id,
                "capture_session_id": sess_id,
                "cluster_id": cluster_id,
                "md5": hashlib.md5(img_id.encode()).hexdigest(),
                "dhash": h_base,
                "label": 1 if s_idx <= 5 else 0
            })

    df = pd.DataFrame(records)
    tr_df, va_df, ev_df = partition_dataset_with_session_grouping(
        df,
        cluster_col="cluster_id",
        session_col="capture_session_id",
        train_ratio=0.70,
        val_ratio=0.15,
        eval_ratio=0.15,
        random_seed=42
    )

    # 1. Total samples preserved
    assert len(tr_df) + len(va_df) + len(ev_df) == len(df)

    # 2. Independent evaluation set is locked
    assert bool(ev_df["is_locked_for_tuning"].all()) is True

    # 3. Session disjointness
    tr_sessions = set(tr_df["capture_session_id"])
    va_sessions = set(va_df["capture_session_id"])
    ev_sessions = set(ev_df["capture_session_id"])

    assert len(tr_sessions & va_sessions) == 0, "Train and Val share capture sessions!"
    assert len(tr_sessions & ev_sessions) == 0, "Train and Eval share capture sessions!"
    assert len(va_sessions & ev_sessions) == 0, "Val and Eval share capture sessions!"

    # 4. Cluster disjointness
    tr_clusters = set(tr_df["cluster_id"])
    va_clusters = set(va_df["cluster_id"])
    ev_clusters = set(ev_df["cluster_id"])

    assert len(tr_clusters & va_clusters) == 0, "Train and Val share clusters!"
    assert len(tr_clusters & ev_clusters) == 0, "Train and Eval share clusters!"
    assert len(va_clusters & ev_clusters) == 0, "Val and Eval share clusters!"

    # 5. Isolation verification helper
    iso_res = verify_partition_isolation(
        tr_df, va_df, ev_df,
        id_col="image_id",
        md5_col="md5",
        dhash_col="dhash",
        session_col="capture_session_id",
        cluster_col="cluster_id"
    )
    assert iso_res["is_isolated"] is True
    assert iso_res["violations_count"] == 0


def test_verify_partition_isolation_detects_injected_leak():
    """Asserts that verify_partition_isolation intercepts intentional cross-split leaks."""
    tr_df = pd.DataFrame([{"image_id": "img_01", "md5": "hash_A", "capture_session_id": "SES_01", "cluster_id": "c1", "dhash": "0000000000000000"}])
    va_df = pd.DataFrame([{"image_id": "img_02", "md5": "hash_B", "capture_session_id": "SES_02", "cluster_id": "c2", "dhash": "ffffffffffffffff"}])
    # Injected leak: eval shares session SES_01 and MD5 hash_A with train
    ev_df = pd.DataFrame([{"image_id": "img_03", "md5": "hash_A", "capture_session_id": "SES_01", "cluster_id": "c3", "dhash": "aaaaaaaaaaaaaaaa"}])

    iso_res = verify_partition_isolation(tr_df, va_df, ev_df)
    assert iso_res["is_isolated"] is False
    assert iso_res["violations_count"] >= 2
    assert any("exact MD5" in v for v in iso_res["violations"])
    assert any("capture session" in v for v in iso_res["violations"])


# =====================================================================
# 5. Phase 14 Gate & Checkpoint Invariants
# =====================================================================

def test_v4_training_readiness_gate_remains_no_go():
    """Verify that Vision V4 training gate remains in NO-GO status."""
    report = evaluate_readiness(
        register_path="data/collection_v4/acquisition_register.csv",
        manifest_v4_dir="data/processed/manifest_v4",
        shortcut_report_path="reports/vision_integrity/shortcut_diagnosis_v4.json",
        use_synthetic_fixture=False
    )
    assert report["overall_status"] == "NO-GO"
    assert len(report["blocking_reasons"]) >= 3


def test_historical_checkpoints_preserved():
    """All 4 historical checkpoints must exist with non-zero size."""
    checkpoints = [
        os.path.join("models", "vision", "best_model.pt"),
        os.path.join("models", "vision", "v2", "model_v2.pt"),
        os.path.join("models", "vision", "v3", "model_v3_clean.pt"),
        os.path.join("models", "vision", "v3", "model_v3_monsoon.pt"),
    ]
    for ckpt in checkpoints:
        assert os.path.exists(ckpt), f"Checkpoint missing: {ckpt}"
        assert os.path.getsize(ckpt) > 0, f"Checkpoint empty: {ckpt}"
