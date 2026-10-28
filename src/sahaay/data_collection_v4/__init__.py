"""
Sahaay AI - Data Collection V4 Package
Provides provenance, privacy, ingestion, and validation pipelines for Hyderabad field data.
"""

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

from sahaay.data_collection_v4.operations import (
    LockedEvaluationSetViolationError,
    ProvenanceCategory,
    StreamApprovalStatus,
    EvaluationSplitMetadata,
    validate_stream_permissions,
    validate_acquisition_record_eligibility,
    categorize_provenance,
    EvaluationSetProtectionGuard,
    generate_phase16_readiness_audit,
)

__all__ = [
    "AcquisitionRecord",
    "PermissionStatus",
    "SourceType",
    "CaptureMethod",
    "WeatherCondition",
    "LightingCondition",
    "RoadSurfaceCondition",
    "ReviewStatus",
    "PrivacyProcessingStatus",
    "AnnotationLabel",
    "AnnotationRecord",
    "AdjudicationStatus",
    "DepthMeasurementMethod",
    "VerifiedPassability",
    "ImageQualityStatus",
    "HYDERABAD_BOUNDS",
    "validate_metadata_integrity",
    "validate_annotation_governance",
    "audit_source_class_balance",
    "partition_dataset_with_session_grouping",
    "verify_partition_isolation",
    "LockedEvaluationSetViolationError",
    "ProvenanceCategory",
    "StreamApprovalStatus",
    "EvaluationSplitMetadata",
    "validate_stream_permissions",
    "validate_acquisition_record_eligibility",
    "categorize_provenance",
    "EvaluationSetProtectionGuard",
    "generate_phase16_readiness_audit",
]


