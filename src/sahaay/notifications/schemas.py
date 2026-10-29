"""
Sahaay AI - Notification Schemas
Data contracts for risk notifications, alert severity, delivery channels, and corridor subscriptions.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class NotificationSeverity(str, Enum):
    INFO = "INFO"
    ADVISORY = "ADVISORY"
    WATCH = "WATCH"
    WARNING = "WARNING"
    EMERGENCY = "EMERGENCY"


class NotificationType(str, Enum):
    """Specific operational alert scenarios defined in Sahaay notification policy."""
    ADVANCE_FORECAST_WARNING = "ADVANCE_FORECAST_WARNING"
    RAIN_EVENT_UPDATE = "RAIN_EVENT_UPDATE"
    LOCAL_FLOOD_RISK_WARNING = "LOCAL_FLOOD_RISK_WARNING"
    ROUTE_HAZARD_ALERT = "ROUTE_HAZARD_ALERT"
    HAZARD_ALERT = "HAZARD_ALERT"
    FEED_DEGRADATION = "FEED_DEGRADATION"


class NotificationDeliveryChannel(str, Enum):
    LOCAL_DEMO_UI = "LOCAL_DEMO_UI"
    LOG_ONLY = "LOG_ONLY"
    MOCK_SMS_GATEWAY = "MOCK_SMS_GATEWAY"
    MOCK_PUSH_SERVICE = "MOCK_PUSH_SERVICE"
    EXTERNAL_WEBHOOK = "EXTERNAL_WEBHOOK"
    EXTERNAL_PUSH = "EXTERNAL_PUSH"
    EXTERNAL_SMS = "EXTERNAL_SMS"


class NotificationRecord(BaseModel):
    """
    Standardized notification record emitted for risk-state transitions.
    """
    notification_id: str
    recipient_or_topic: str = Field(..., description="e.g. corridor:HYD-LOC-001 or user:USR-123 or public:all")
    severity: NotificationSeverity
    title: str
    message: str
    corridor_id: Optional[str] = None
    event_type: str = Field(..., description="e.g. WEATHER_SURGE, VERIFIED_FLOOD, FEED_DEGRADATION")
    notification_type: NotificationType = Field(default=NotificationType.HAZARD_ALERT)
    created_at_utc: str
    evidence_status: str = Field(..., description="FORECAST_WARNING vs OBSERVED_HAZARD vs DEGRADED_TELEMETRY")
    deduplication_key: str
    delivery_channel: NotificationDeliveryChannel = NotificationDeliveryChannel.LOCAL_DEMO_UI
    is_delivered: bool = True
    recommended_action: Optional[str] = Field(None, description="Precaution or suggested navigation guidance")
    affected_areas: List[str] = Field(default_factory=list, description="Targeted localities e.g. ['Begumpet', 'Khairatabad']")
    forecast_window_utc: Optional[str] = Field(None, description="Valid time window for advance forecast alerts")
    recalculation_available: bool = Field(False, description="True if alternate safe route was computed")
    suggested_alternative_route_id: Optional[str] = Field(None, description="Alternative route assessment ID if re-routed")
    delivery_metadata: Dict[str, Any] = Field(default_factory=dict)


class SubscriptionRequest(BaseModel):
    """
    Request to subscribe to corridor, saved-area, or route alerts.
    """
    user_id: str = Field(default="demo-user", min_length=2)
    corridor_id: Optional[str] = Field(None, description="Corridor to monitor (e.g. HYD-LOC-001)")
    saved_areas: List[str] = Field(default_factory=list, description="Saved localities e.g. ['Begumpet', 'Tolichowki']")
    origin_node_id: Optional[str] = Field(None, description="Optional route origin")
    destination_node_id: Optional[str] = Field(None, description="Optional route destination")
    active_route_segment_ids: List[str] = Field(default_factory=list, description="Segment IDs on active commute/route")
    minimum_severity: NotificationSeverity = NotificationSeverity.ADVISORY


class SubscriptionRecord(BaseModel):
    """
    Active subscription record.
    """
    subscription_id: str
    user_id: str
    corridor_id: Optional[str] = None
    saved_areas: List[str] = Field(default_factory=list)
    origin_node_id: Optional[str] = None
    destination_node_id: Optional[str] = None
    active_route_segment_ids: List[str] = Field(default_factory=list)
    minimum_severity: NotificationSeverity
    created_at_utc: str
    is_active: bool = True
