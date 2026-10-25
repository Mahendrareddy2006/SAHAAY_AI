"""
Field Observation Session Management & Safety Lifecycle for Sahaay AI Phase 7.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, List, Optional, Tuple
import hashlib
import logging
from pydantic import BaseModel, Field, model_validator

from sahaay.observations.schemas import GroundTruthObservation
from sahaay.observations.ingestion import ObservationIngestionPipeline

logger = logging.getLogger("sahaay.pilot.session")


class FieldSessionState(str, Enum):
    INITIALIZED = "INITIALIZED"
    ACTIVE_COLLECTING = "ACTIVE_COLLECTING"
    SAFETY_ABORTED = "SAFETY_ABORTED"
    CLOSED_COMPLETE = "CLOSED_COMPLETE"


class PreCollectionSafetyCheck(BaseModel):
    """Safety checklist completed on site by the Field Lead prior to starting observations."""
    vantage_point_clear_of_traffic: bool = Field(...)
    zero_entry_into_floodwater_confirmed: bool = Field(...)
    lightning_detected_within_10km: bool = Field(False)
    wind_gusts_exceed_35kmh: bool = Field(False)
    ppe_gear_verified_for_all: bool = Field(...)
    first_aid_and_whistles_verified: bool = Field(...)
    emergency_contacts_saved_on_phones: bool = Field(...)
    daylight_window_confirmed: bool = Field(...)
    field_lead_id: str = Field(..., min_length=3)
    safety_officer_id: str = Field(..., min_length=3)
    data_recorder_id: str = Field(..., min_length=3)

    @model_validator(mode="after")
    def validate_safety_conditions(self) -> "PreCollectionSafetyCheck":
        if not self.vantage_point_clear_of_traffic:
            raise ValueError("Safety violation: Observation vantage point is not clear of traffic.")
        if not self.zero_entry_into_floodwater_confirmed:
            raise ValueError("Safety violation: Cardinal Rule 1 violated - Zero entry into floodwater must be confirmed.")
        if self.lightning_detected_within_10km:
            raise ValueError("Safety violation: Lightning detected within 10km. Field collection prohibited.")
        if self.wind_gusts_exceed_35kmh:
            raise ValueError("Safety violation: Wind gusts exceed 35km/h. Hazard threshold breached.")
        if not self.ppe_gear_verified_for_all:
            raise ValueError("Safety violation: High-visibility PPE gear not verified for all team members.")
        if not self.daylight_window_confirmed:
            raise ValueError("Safety violation: Operations outside approved daylight window (08:00-17:30 IST).")
        return self


class PostCollectionSafetyReview(BaseModel):
    """Post-deployment review completed upon return to base camp."""
    safety_incidents_occurred: bool = Field(False)
    incident_details: Optional[str] = None
    abort_triggered: bool = Field(False)
    abort_reason: Optional[str] = None
    completed_at_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    field_lead_signoff_id: str = Field(..., min_length=3)


class FieldSession(BaseModel):
    """Auditable container for a human-supervised field observation shift."""
    session_id: str = Field(..., pattern=r"^SES-[0-9]{8}-[0-9]{4}$")
    corridor_id: str = Field(..., min_length=3)
    vantage_location_name: str = Field(..., min_length=5)
    scheduled_start_utc: datetime = Field(...)
    scheduled_end_utc: datetime = Field(...)
    actual_start_utc: Optional[datetime] = None
    actual_end_utc: Optional[datetime] = None
    session_state: FieldSessionState = Field(FieldSessionState.INITIALIZED)
    pre_safety_check: Optional[PreCollectionSafetyCheck] = None
    post_safety_review: Optional[PostCollectionSafetyReview] = None
    observation_ids: List[str] = Field(default_factory=list)
    is_synthetic_or_simulated: bool = Field(False)


class FieldSessionManager:
    """Manages creation, activation, observation logging, and closure of field sessions."""

    def __init__(self, ingestion_pipeline: Optional[ObservationIngestionPipeline] = None):
        self._sessions: Dict[str, FieldSession] = {}
        self.ingestion_pipeline = ingestion_pipeline or ObservationIngestionPipeline()

    def create_session(
        self,
        session_id: str,
        corridor_id: str,
        vantage_location_name: str,
        scheduled_start_utc: datetime,
        scheduled_end_utc: datetime,
        is_synthetic: bool = False,
    ) -> FieldSession:
        """Initializes a new scheduled field session."""
        session = FieldSession(
            session_id=session_id,
            corridor_id=corridor_id,
            vantage_location_name=vantage_location_name,
            scheduled_start_utc=scheduled_start_utc,
            scheduled_end_utc=scheduled_end_utc,
            session_state=FieldSessionState.INITIALIZED,
            is_synthetic_or_simulated=is_synthetic,
        )
        self._sessions[session_id] = session
        logger.info(f"Initialized field session {session_id} for corridor {corridor_id}")
        return session

    def start_session(
        self,
        session_id: str,
        pre_check_dict: Dict[str, Any],
        pilot_authorized: bool = False,
    ) -> Tuple[bool, Optional[FieldSession], str]:
        """
        Activates a field session.
        
        Requires:
        1. PilotActivationGate evaluates to PILOT_AUTHORIZED (unless synthetic dry run).
        2. PreCollectionSafetyCheck passes all safety validations.
        """
        session = self._sessions.get(session_id)
        if not session:
            return False, None, f"Session {session_id} not found."

        if session.session_state != FieldSessionState.INITIALIZED:
            return False, session, f"Session {session_id} is already in state {session.session_state}."

        # Pilot authorization gate check
        if not pilot_authorized and not session.is_synthetic_or_simulated:
            return False, session, "Pilot activation gate is BLOCKED. Live field session cannot be started without PILOT_AUTHORIZED status."

        try:
            pre_check = PreCollectionSafetyCheck(**pre_check_dict)
        except Exception as e:
            return False, session, f"Pre-collection safety check FAILED: {str(e)}"

        session.pre_safety_check = pre_check
        session.actual_start_utc = datetime.now(timezone.utc)
        session.session_state = FieldSessionState.ACTIVE_COLLECTING
        logger.info(f"Field session {session_id} ACTIVATED by Lead {pre_check.field_lead_id}.")
        return True, session, "Session successfully activated."

    def log_observation(
        self,
        session_id: str,
        obs_dict: Dict[str, Any],
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Validates and records an observation within an active field session."""
        session = self._sessions.get(session_id)
        if not session:
            return {"success": False, "error": f"Session {session_id} not found."}

        if session.session_state != FieldSessionState.ACTIVE_COLLECTING:
            return {"success": False, "error": f"Cannot log observation: Session is {session.session_state}."}

        # Validate through ingestion pipeline
        res = self.ingestion_pipeline.ingest_record(obs_dict, dry_run=dry_run)
        if res["success"]:
            obs_id = res["observation_id"]
            if obs_id not in session.observation_ids and not dry_run:
                session.observation_ids.append(obs_id)

        return res

    def abort_session(
        self,
        session_id: str,
        abort_reason: str,
        field_lead_id: str,
    ) -> Tuple[bool, Optional[FieldSession], str]:
        """Immediately aborts an active session upon weather hazard or safety breach."""
        session = self._sessions.get(session_id)
        if not session:
            return False, None, f"Session {session_id} not found."

        session.session_state = FieldSessionState.SAFETY_ABORTED
        session.actual_end_utc = datetime.now(timezone.utc)
        session.post_safety_review = PostCollectionSafetyReview(
            safety_incidents_occurred=True,
            incident_details=f"SAFETY ABORT TRIGGERED: {abort_reason}",
            abort_triggered=True,
            abort_reason=abort_reason,
            field_lead_signoff_id=field_lead_id,
        )
        logger.warning(f"Session {session_id} SAFETY ABORTED by {field_lead_id}: {abort_reason}")
        return True, session, f"Session safely aborted: {abort_reason}"

    def close_session(
        self,
        session_id: str,
        post_review_dict: Dict[str, Any],
    ) -> Tuple[bool, Optional[FieldSession], str]:
        """Formally closes an active session after demobilization to base camp."""
        session = self._sessions.get(session_id)
        if not session:
            return False, None, f"Session {session_id} not found."

        if session.session_state != FieldSessionState.ACTIVE_COLLECTING:
            return False, session, f"Cannot close session in state {session.session_state}."

        post_review = PostCollectionSafetyReview(**post_review_dict)
        session.post_safety_review = post_review
        session.actual_end_utc = datetime.now(timezone.utc)
        session.session_state = FieldSessionState.CLOSED_COMPLETE
        logger.info(f"Session {session_id} CLOSED by Lead {post_review.field_lead_signoff_id}. Total observations: {len(session.observation_ids)}")
        return True, session, "Session successfully closed."
