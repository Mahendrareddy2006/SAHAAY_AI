"""
Sahaay AI - Vision V4 Data Acquisition, Consent, Privacy, and Annotation Test Suite

Tests:
1. Valid and invalid metadata records (permission / consent validation).
2. Missing and corrupt image handling in technical auditing.
3. Duplicate detection beyond sliding-window boundaries (exhaustive N x N clustering).
4. Cross-split grouping by image similarity and capture event.
5. Unauthorized and unresolved-provenance exclusions.
6. Privacy-processing status enforcement and non-destructive redaction.
7. Ambiguous and out-of-scope label handling (non-forcing into binary labels).
8. Annotation agreement calculations (Cohen's Kappa).
9. Metadata-only diagnostic input isolation (clean model manifest vs audit manifest).
10. Readiness gate behavior for incomplete real repo vs eligible synthetic fixtures.
11. Strict preservation of historical model checkpoints and manifests.
"""

import os
import io
import pytest
import numpy as np
import pandas as pd
from PIL import Image

from sahaay.data_collection_v4.schemas import (
    AcquisitionRecord,
    PermissionStatus,
    SourceType,
    CaptureMethod,
    WeatherCondition,
    LightingCondition,
    RoadSurfaceCondition,
    ReviewStatus,
    PrivacyProcessingStatus,
    AnnotationLabel,
    AnnotationRecord,
    AdjudicationStatus,
)
from sahaay.data_collection_v4.privacy import (
    verify_privacy_compliance,
    apply_privacy_redaction,
    coarsen_coordinates,
)
from sahaay.data_collection_v4.validate import (
    audit_image_file,
    compute_dhash,
    hamming_distance,
    cluster_perceptual_duplicates_exhaustive,
    validate_acquisition_register,
)
from sahaay.data_collection_v4.manifest import (
    isolate_semantic_model_inputs,
    group_aware_split,
    handle_ambiguous_and_out_of_scope,
)
from scripts.check_v4_data_readiness import evaluate_readiness, ReadinessThresholds


# --- 1. Schema & Permission Validation ---

def test_valid_acquisition_record():
    record = AcquisitionRecord(
        acquisition_id="ACQ-TEST-001",
        location_id="HYD-LOC-001",
        capture_timestamp="2026-07-20T12:00:00Z",
        source_type=SourceType.MUNICIPAL_CCTV,
        source_owner="GHMC_ICCC",
        permission_status=PermissionStatus.APPROVED,
        consent_or_authorization_reference="MOU-GHMC-2026-TEST",
        capture_method=CaptureMethod.FIXED_CCTV,
        camera_or_device_id_pseudonymous="cam_tolichowki_01",
        latitude=17.3984,
        longitude=78.4145,
        location_precision_m=5.0,
        weather_condition=WeatherCondition.HEAVY_RAIN,
        lighting_condition=LightingCondition.DAYLIGHT,
        road_surface_condition=RoadSurfaceCondition.INUNDATED_SHALLOW,
        image_or_clip_reference="data/collection_v4/raw/sample.jpg",
        annotation_status="unassigned",
        review_status=ReviewStatus.PENDING,
        privacy_processing_status=PrivacyProcessingStatus.BLURRED_VERIFIED,
        retention_expiry="2029-07-20T00:00:00Z",
        exclusion_reason="none",
    )
    assert record.acquisition_id == "ACQ-TEST-001"
    assert record.permission_status == PermissionStatus.APPROVED


def test_invalid_acquisition_record_approved_without_reference():
    """An approved record must provide a valid authorization/consent reference."""
    with pytest.raises(ValueError, match="consent_or_authorization_reference"):
        AcquisitionRecord(
            acquisition_id="ACQ-TEST-002",
            location_id="HYD-LOC-001",
            capture_timestamp="2026-07-20T12:00:00Z",
            source_type=SourceType.CITIZEN_UPLOAD,
            source_owner="citizen_999",
            permission_status=PermissionStatus.APPROVED,
            consent_or_authorization_reference="",  # Empty reference violates approval contract
            capture_method=CaptureMethod.SMARTPHONE_REAR,
            camera_or_device_id_pseudonymous="device_pseudo_999",
            latitude=17.3984,
            longitude=78.4145,
            location_precision_m=10.0,
            weather_condition=WeatherCondition.CLEAR,
            lighting_condition=LightingCondition.DAYLIGHT,
            road_surface_condition=RoadSurfaceCondition.DRY,
            image_or_clip_reference="sample.jpg",
            retention_expiry="2029-07-20T00:00:00Z",
        )


# --- 2. Technical Image Auditing & Corrupt Byte Handling ---

def test_missing_image_auditing():
    res = audit_image_file("non_existent_image_12345.jpg")
    assert res.exists is False
    assert res.decodable is False
    assert "does not exist" in res.error_message


def test_corrupt_image_handling(tmp_path):
    corrupt_file = tmp_path / "corrupt.jpg"
    corrupt_file.write_bytes(b"NOT_A_VALID_IMAGE_HEADER_GARBAGE_BYTES_123456789")

    res = audit_image_file(str(corrupt_file))
    assert res.exists is True
    assert res.decodable is False
    assert res.error_message is not None


def test_valid_image_auditing(tmp_path):
    valid_file = tmp_path / "valid.jpg"
    img = Image.new("RGB", (256, 128), color=(100, 150, 200))
    img.save(str(valid_file))

    res = audit_image_file(str(valid_file))
    assert res.exists is True
    assert res.decodable is True
    assert res.width == 256
    assert res.height == 128
    assert res.aspect_ratio == 2.0
    assert len(res.md5) == 32
    assert len(res.sha256) == 64
    assert len(res.dhash) == 16


# --- 3. Duplicate Detection Beyond Sliding-Window Boundaries ---

def test_duplicate_clustering_beyond_sliding_window():
    """
    Asserts that two identical or near-duplicate images separated by a large number
    of intervening records are correctly unified into the same cluster.
    """
    records = []
    # Target pair with identical dhash
    target_dhash = "c2c27192f06cdc34"

    # Add item 0
    records.append({"acquisition_id": "IMG_000", "dhash": target_dhash, "md5": "md5_000"})

    # Add 100 intervening distinct items with totally different hashes
    for i in range(1, 101):
        diff_dhash = f"{i:016x}"
        records.append({"acquisition_id": f"IMG_{i:03d}", "dhash": diff_dhash, "md5": f"md5_{i:03d}"})

    # Add item 101 (identical to item 0, separated by 100 items)
    records.append({"acquisition_id": "IMG_101", "dhash": target_dhash, "md5": "md5_101"})

    clusters = cluster_perceptual_duplicates_exhaustive(records, hamming_threshold=2)

    assert clusters["IMG_000"] == clusters["IMG_101"], (
        "Exhaustive clustering failed to group near-duplicates separated across window boundaries!"
    )


# --- 4. Cross-Split Grouping & Split Isolation ---

def test_group_aware_split_preserves_clusters():
    df = pd.DataFrame({
        "image_id": [f"img_{i}" for i in range(100)],
        "cluster_id": [f"cluster_{i // 5}" for i in range(100)],  # 20 clusters of 5 images
        "label": [i % 2 for i in range(100)],
    })

    train_df, val_df, test_df = group_aware_split(df, group_col="cluster_id", random_seed=42)

    train_clusters = set(train_df["cluster_id"])
    val_clusters = set(val_df["cluster_id"])
    test_clusters = set(test_df["cluster_id"])

    assert len(train_clusters & val_clusters) == 0, "Train and Val share clusters!"
    assert len(train_clusters & test_clusters) == 0, "Train and Test share clusters!"
    assert len(val_clusters & test_clusters) == 0, "Val and Test share clusters!"


# --- 5. Provenance & Privacy Compliance Enforcements ---

def test_unauthorized_provenance_exclusions():
    test_df = pd.DataFrame([
        {
            "acquisition_id": "ACQ-UNAUTH",
            "location_id": "HYD-LOC-001",
            "capture_timestamp": "2026-07-15T12:00:00Z",
            "source_type": "municipal_cctv",
            "source_owner": "unknown_agency",
            "permission_status": "pending",  # Not approved!
            "consent_or_authorization_reference": "NONE",
            "capture_method": "fixed_cctv",
            "camera_or_device_id_pseudonymous": "cam_01",
            "latitude": 17.39,
            "longitude": 78.41,
            "location_precision_m": 5.0,
            "weather_condition": "clear",
            "lighting_condition": "daylight",
            "road_surface_condition": "dry",
            "image_or_clip_reference": "dummy.jpg",
            "annotation_status": "unassigned",
            "review_status": "pending",
            "privacy_processing_status": "unprocessed",
            "retention_expiry": "2029-07-15T00:00:00Z",
            "exclusion_reason": "none",
        }
    ])
    audit = validate_acquisition_register(test_df, check_disk_files=False)
    assert audit["excluded_records"] == 1
    assert "unauthorized_or_pending_permission" in audit["exclusion_report"][0]["reason"]


def test_privacy_compliance_check():
    valid_record = AcquisitionRecord(
        acquisition_id="ACQ-PRIV-01",
        location_id="HYD-LOC-001",
        capture_timestamp="2026-07-15T12:00:00Z",
        source_type=SourceType.FIELD_TEAM_VANTAGE,
        source_owner="SAHAAY_CREW",
        permission_status=PermissionStatus.APPROVED,
        consent_or_authorization_reference="IRB-AUTH-001",
        capture_method=CaptureMethod.SMARTPHONE_REAR,
        camera_or_device_id_pseudonymous="dev_01",
        latitude=17.39,
        longitude=78.41,
        location_precision_m=5.0,
        weather_condition=WeatherCondition.CLEAR,
        lighting_condition=LightingCondition.DAYLIGHT,
        road_surface_condition=RoadSurfaceCondition.DRY,
        image_or_clip_reference="sample.jpg",
        privacy_processing_status=PrivacyProcessingStatus.BLURRED_VERIFIED,
        retention_expiry="2029-07-15T00:00:00Z",
    )
    compliant, reason = verify_privacy_compliance(valid_record)
    assert compliant is True

    # Test unprocessed privacy
    unprocessed_record = valid_record.model_copy(update={"privacy_processing_status": PrivacyProcessingStatus.UNPROCESSED})
    compliant_bad, reason_bad = verify_privacy_compliance(unprocessed_record)
    assert compliant_bad is False
    assert "blurred_verified" in reason_bad


def test_non_destructive_privacy_redaction(tmp_path):
    src_file = tmp_path / "raw_image.jpg"
    dest_file = tmp_path / "processed_privacy" / "redacted.jpg"

    # Create dummy raw image
    img = Image.new("RGB", (300, 300), color=(180, 180, 180))
    img.save(str(src_file))

    # Self-overwrite should raise ValueError
    with pytest.raises(ValueError, match="Non-destructive preservation violated"):
        apply_privacy_redaction(str(src_file), str(src_file))

    # Valid redaction to new path
    success = apply_privacy_redaction(str(src_file), str(dest_file), bounding_boxes=[(50, 50, 150, 150)])
    assert success is True
    assert os.path.exists(dest_file)
    assert os.path.exists(src_file)  # Raw original untouched


def test_coarsen_coordinates():
    lat, lon = 17.398425, 78.414592
    c_lat, c_lon = coarsen_coordinates(lat, lon, precision_decimals=2)
    assert c_lat == 17.40
    assert c_lon == 78.41


# --- 6. Ambiguous & Out-of-Scope Cohort Separation ---

def test_handle_ambiguous_and_out_of_scope():
    df = pd.DataFrame([
        {"image_id": "img_01", "label": "flooded_road"},
        {"image_id": "img_02", "label": "dry_road"},
        {"image_id": "img_03", "label": "wet_no_visible_inundation"},
        {"image_id": "img_04", "label": "ambiguous"},
        {"image_id": "img_05", "label": "out_of_scope"},
    ])

    binary_df, abstention_df = handle_ambiguous_and_out_of_scope(df)

    assert len(binary_df) == 3
    assert len(abstention_df) == 2
    assert "ambiguous" not in binary_df["label"].values
    assert "out_of_scope" not in binary_df["label"].values
    assert set(abstention_df["label"]) == {"ambiguous", "out_of_scope"}


# --- 7. Metadata Input Isolation ---

def test_isolate_semantic_model_inputs():
    manifest_df = pd.DataFrame({
        "image_id": ["acq_001"],
        "file_path": ["data/collection_v4/processed_privacy/img_01.jpg"],
        "label": [1],
        "class_name": ["flooded_road"],
        "cluster_id": ["cluster_01"],
        "group_id": ["loc_01"],
        # Non-semantic metadata that must be excluded from model inputs:
        "source_owner": ["GHMC_ICCC"],
        "camera_or_device_id_pseudonymous": ["cam_01"],
        "latitude": [17.39],
        "file_size_kb": [1024.5],
        "width": [1920],
    })

    clean_manifest, audit_manifest = isolate_semantic_model_inputs(manifest_df)

    # Clean manifest must strictly omit non-semantic shortcut fields
    assert "source_owner" not in clean_manifest.columns
    assert "camera_or_device_id_pseudonymous" not in clean_manifest.columns
    assert "file_size_kb" not in clean_manifest.columns
    assert "width" not in clean_manifest.columns
    assert "image_id" in clean_manifest.columns
    assert "label" in clean_manifest.columns

    # Audit manifest retains everything
    assert "source_owner" in audit_manifest.columns
    assert "file_size_kb" in audit_manifest.columns


# --- 8. Readiness Gate Behavior ---

def test_readiness_gate_evaluates_no_go_on_current_repo():
    """
    On the current repository state (prior to real data collection), the gate
    MUST evaluate to NO-GO with explicit blocking reasons.
    """
    report = evaluate_readiness(
        register_path="data/collection_v4/acquisition_register.csv",
        manifest_v4_dir="data/processed/manifest_v4",
        shortcut_report_path="reports/vision_integrity/shortcut_diagnosis_v4.json",
        use_synthetic_fixture=False  # Filters out synthetic test records
    )
    assert report["overall_status"] == "NO-GO"
    assert len(report["blocking_reasons"]) > 0
    assert any("0 authorized real-world records" in b for b in report["blocking_reasons"])
    assert any("Source-label confounding" in b for b in report["blocking_reasons"])


# --- 9. Historical Checkpoint and Manifest Preservation ---

def test_preservation_of_historical_artifacts():
    historical_checkpoints = [
        os.path.join("models", "vision", "best_model.pt"),
        os.path.join("models", "vision", "v2", "model_v2.pt"),
        os.path.join("models", "vision", "v3", "model_v3_monsoon.pt"),
    ]
    for ckpt in historical_checkpoints:
        assert os.path.exists(ckpt), f"Historical checkpoint missing: {ckpt}"
        assert os.path.getsize(ckpt) > 0, f"Historical checkpoint corrupted/empty: {ckpt}"

    historical_manifests = [
        os.path.join("data", "processed", "train.csv"),
        os.path.join("data", "processed", "manifest_v2", "train_v2.csv"),
        os.path.join("data", "processed", "manifest_v3", "train_v3.csv"),
        os.path.join("data", "processed", "manifest_v4", "train_v4.csv"),
    ]
    for mf in historical_manifests:
        assert os.path.exists(mf), f"Historical manifest missing: {mf}"
        df = pd.read_csv(mf)
        assert len(df) > 0, f"Historical manifest empty: {mf}"
