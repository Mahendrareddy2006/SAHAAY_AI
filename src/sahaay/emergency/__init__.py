"""
Sahaay AI - Phase 20: Emergency Mode Module
Exports emergency-mode state machines, human authorization checks,
readiness auditor, and workflow engine.
"""

from sahaay.emergency.schemas import (
    EmergencyState,
    EmergencyPriority,
    AuthorizedReviewerRole,
    EmergencyResolutionRecord,
    EmergencyAssessmentInput,
    EmergencyModeAssessment,
    FORBIDDEN_SAFETY_PHRASES,
    MANDATORY_EMERGENCY_MODE_DISCLAIMER,
)
from sahaay.emergency.readiness import (
    audit_emergency_mode_readiness,
    EmergencyReadinessRecord,
    EmergencyModeReadinessReport,
)
from sahaay.emergency.workflow import (
    EmergencyWorkflowEngine,
    VALID_STATE_TRANSITIONS,
)

__all__ = [
    # Schemas
    "EmergencyState",
    "EmergencyPriority",
    "AuthorizedReviewerRole",
    "EmergencyResolutionRecord",
    "EmergencyAssessmentInput",
    "EmergencyModeAssessment",
    "FORBIDDEN_SAFETY_PHRASES",
    "MANDATORY_EMERGENCY_MODE_DISCLAIMER",
    # Readiness
    "audit_emergency_mode_readiness",
    "EmergencyReadinessRecord",
    "EmergencyModeReadinessReport",
    # Workflow
    "EmergencyWorkflowEngine",
    "VALID_STATE_TRANSITIONS",
]
