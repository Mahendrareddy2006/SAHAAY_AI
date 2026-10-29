"""
Sahaay AI - Notification Service
Handles corridor alert dispatch, user subscriptions, deduplication cooldowns, and local demo audit.
"""

from datetime import datetime, timezone, timedelta
import logging
import os
import threading
import uuid
from typing import Any, Dict, List, Optional

from sahaay.notifications.schemas import (
    NotificationDeliveryChannel,
    NotificationRecord,
    NotificationSeverity,
    NotificationType,
    SubscriptionRecord,
    SubscriptionRequest,
)

logger = logging.getLogger(__name__)


class NotificationService:
    """
    In-memory, thread-safe notification manager.
    Enforces deduplication cooldowns, separates forecast warnings from verified hazards,
    targets saved user areas, and implements material-change thresholds.
    """

    def __init__(self, default_cooldown_seconds: float = 1800.0):
        self._lock = threading.Lock()
        self._default_cooldown_seconds = default_cooldown_seconds
        self._notifications: List[NotificationRecord] = []
        self._subscriptions: Dict[str, SubscriptionRecord] = {}
        self._last_emitted_timestamps: Dict[str, datetime] = {}
        self._last_reported_rates: Dict[str, float] = {}

    def get_external_delivery_status(self) -> Dict[str, Any]:
        """Returns operational readiness and credentials status of external notification gateways."""
        webhook_url = os.getenv("SAHAAY_EXTERNAL_NOTIF_WEBHOOK", "").strip()
        sms_url = os.getenv("SAHAAY_SMS_GATEWAY_URL", "").strip()
        configured = bool(webhook_url or sms_url)
        return {
            "is_configured": configured,
            "status": "CONFIGURED" if configured else "NOT_CONFIGURED",
            "provider": "Authorized Civic Push/Webhook Endpoint" if webhook_url else ("SMS Gateway" if sms_url else "External Dispatch Gateway"),
            "delivery_channel": "EXTERNAL_WEBHOOK" if webhook_url else ("EXTERNAL_SMS" if sms_url else "NOT_CONFIGURED"),
            "details": "External gateway credentials not configured in hackathon environment; in-app and local UI dispatch active." if not configured else "External gateway configured.",
        }

    def subscribe(self, request: SubscriptionRequest) -> SubscriptionRecord:
        """Registers a user subscription for a corridor, saved area, or route."""
        with self._lock:
            sub_id = f"SUB-{uuid.uuid4().hex[:8].upper()}"
            record = SubscriptionRecord(
                subscription_id=sub_id,
                user_id=request.user_id,
                corridor_id=request.corridor_id,
                saved_areas=[a.strip() for a in request.saved_areas if a.strip()],
                origin_node_id=request.origin_node_id,
                destination_node_id=request.destination_node_id,
                active_route_segment_ids=list(request.active_route_segment_ids or []),
                minimum_severity=request.minimum_severity,
                created_at_utc=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                is_active=True,
            )
            self._subscriptions[sub_id] = record
            logger.info(f"Registered notification subscription {sub_id} for user {request.user_id} (saved_areas={record.saved_areas})")
            return record

    def find_matching_subscribers(
        self,
        locality: Optional[str] = None,
        corridor_id: Optional[str] = None,
        segment_id: Optional[str] = None,
    ) -> List[SubscriptionRecord]:
        """Finds all active subscribers whose saved areas, corridors, or routes match."""
        matched: List[SubscriptionRecord] = []
        loc_clean = locality.lower().strip() if locality else ""

        with self._lock:
            for sub in self._subscriptions.values():
                if not sub.is_active:
                    continue
                # Check corridor
                if corridor_id and sub.corridor_id and sub.corridor_id == corridor_id:
                    matched.append(sub)
                    continue
                # Check saved area
                if loc_clean and any(loc_clean in area.lower() or area.lower() in loc_clean for area in sub.saved_areas):
                    matched.append(sub)
                    continue
                # Check active route segment
                if segment_id and segment_id in sub.active_route_segment_ids:
                    matched.append(sub)
                    continue
        return matched

    def notify(
        self,
        recipient_or_topic: str,
        severity: NotificationSeverity,
        title: str,
        message: str,
        corridor_id: Optional[str] = None,
        event_type: str = "HAZARD_ALERT",
        notification_type: NotificationType = NotificationType.HAZARD_ALERT,
        evidence_status: str = "OBSERVED_HAZARD",
        cooldown_seconds: Optional[float] = None,
        delivery_channel: NotificationDeliveryChannel = NotificationDeliveryChannel.LOCAL_DEMO_UI,
        recommended_action: Optional[str] = None,
        affected_areas: Optional[List[str]] = None,
        forecast_window_utc: Optional[str] = None,
        recalculation_available: bool = False,
        suggested_alternative_route_id: Optional[str] = None,
        bypass_cooldown: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[NotificationRecord]:
        """
        Dispatches a notification if not suppressed by deduplication cooldown.
        Returns the NotificationRecord if emitted, or None if suppressed.
        """
        cooldown = cooldown_seconds if cooldown_seconds is not None else self._default_cooldown_seconds
        dedup_key = f"{recipient_or_topic}:{corridor_id or 'global'}:{event_type}:{severity.value}"
        now_dt = datetime.now(timezone.utc)

        with self._lock:
            # Check cooldown
            if not bypass_cooldown and dedup_key in self._last_emitted_timestamps:
                last_time = self._last_emitted_timestamps[dedup_key]
                if (now_dt - last_time).total_seconds() < cooldown:
                    logger.debug(f"Suppressed duplicate notification '{dedup_key}' within cooldown window")
                    return None

            meta = dict(metadata or {})
            ext_info = self.get_external_delivery_status()
            meta["external_delivery_status"] = ext_info["status"]
            meta["external_provider"] = ext_info["provider"]

            # If authorized external webhook configured, attempt bounded dispatch
            if ext_info["is_configured"]:
                webhook_url = os.getenv("SAHAAY_EXTERNAL_NOTIF_WEBHOOK", "").strip()
                if webhook_url:
                    try:
                        import urllib.request
                        import json
                        from sahaay.ingestion.image_downloader import is_safe_public_url
                        if is_safe_public_url(webhook_url):
                            payload = json.dumps({
                                "title": title,
                                "message": message,
                                "severity": severity.value,
                                "corridor_id": corridor_id,
                                "event_type": event_type,
                                "notification_type": notification_type.value,
                            }).encode("utf-8")
                            req = urllib.request.Request(webhook_url, data=payload, headers={"Content-Type": "application/json"})
                            with urllib.request.urlopen(req, timeout=3.0) as resp:
                                meta["external_http_status"] = resp.status
                    except Exception as ex:
                        logger.debug(f"External notification dispatch skipped or failed: {ex}")
                        meta["external_dispatch_error"] = str(ex)

            notif_id = f"NOTIF-{uuid.uuid4().hex[:8].upper()}"
            record = NotificationRecord(
                notification_id=notif_id,
                recipient_or_topic=recipient_or_topic,
                severity=severity,
                title=title,
                message=message,
                corridor_id=corridor_id,
                event_type=event_type,
                notification_type=notification_type,
                created_at_utc=now_dt.isoformat().replace("+00:00", "Z"),
                evidence_status=evidence_status,
                deduplication_key=dedup_key,
                delivery_channel=delivery_channel,
                is_delivered=True,
                recommended_action=recommended_action,
                affected_areas=list(affected_areas or []),
                forecast_window_utc=forecast_window_utc,
                recalculation_available=recalculation_available,
                suggested_alternative_route_id=suggested_alternative_route_id,
                delivery_metadata=meta,
            )

            self._notifications.insert(0, record)
            if len(self._notifications) > 200:
                self._notifications = self._notifications[:200]

            self._last_emitted_timestamps[dedup_key] = now_dt
            logger.info(f"Dispatched notification {notif_id}: [{severity.value}] {title} -> {recipient_or_topic}")
            return record

    def dispatch_advance_forecast_warning(
        self,
        locality: str,
        corridor_id: Optional[str],
        forecast_horizon_hours: float,
        rainfall_amount_mm: float,
        risk_level: str = "HIGH",
        forecast_source: str = "IMD/Open-Meteo NWP",
        uncertainty: str = "MODERATE",
        valid_window_utc: Optional[str] = None,
        severity: NotificationSeverity = NotificationSeverity.WATCH,
    ) -> List[NotificationRecord]:
        """
        Scenario A: ADVANCE FORECAST WARNING
        Sends an advance alert targeted to users with saved areas or corridor subscriptions.
        """
        matched = self.find_matching_subscribers(locality=locality, corridor_id=corridor_id)
        emitted: List[NotificationRecord] = []
        recipients = [f"user:{sub.user_id}" for sub in matched] if matched else [f"topic:area:{locality.lower()}"]

        title = f"Advance Rain & Flood Risk Advisory: {locality}"
        message = (
            f"Forecast source ({forecast_source}) predicts {rainfall_amount_mm:.1f}mm rainfall over "
            f"the next {forecast_horizon_hours:.0f}h. Estimated risk: {risk_level} (Uncertainty: {uncertainty})."
        )
        action = "Plan routes early. Avoid low-lying underpasses and parking in basement ramps during the forecast window."

        for recipient in recipients:
            rec = self.notify(
                recipient_or_topic=recipient,
                severity=severity,
                title=title,
                message=message,
                corridor_id=corridor_id,
                event_type="ADVANCE_FORECAST",
                notification_type=NotificationType.ADVANCE_FORECAST_WARNING,
                evidence_status="FORECAST_WARNING",
                recommended_action=action,
                affected_areas=[locality],
                forecast_window_utc=valid_window_utc,
                cooldown_seconds=3600.0,
            )
            if rec:
                emitted.append(rec)
        return emitted

    def dispatch_rain_event_update(
        self,
        locality: str,
        corridor_id: Optional[str],
        current_rate_mm_h: float,
        intensity_state: str = "INTENSIFIED",
        severity: NotificationSeverity = NotificationSeverity.ADVISORY,
    ) -> List[NotificationRecord]:
        """
        Scenario B: RAIN-EVENT UPDATE
        Reassesses risk and notifies relevant users when a material rainfall threshold is crossed.
        Suppresses duplicate alerts for immaterial rate changes.
        """
        rate_key = corridor_id or locality.lower()
        prev_rate = self._last_reported_rates.get(rate_key, 0.0)

        # Thresholds: 10 mm/h (moderate), 25 mm/h (heavy), 50 mm/h (severe)
        def _get_band(r: float) -> int:
            if r <= 0.5: return 0
            if r < 10.0: return 1
            if r < 25.0: return 2
            if r < 50.0: return 3
            return 4

        curr_band = _get_band(current_rate_mm_h)
        prev_band = _get_band(prev_rate)

        # Material check: Band crossed or rate jumped by > 15 mm/h
        is_material = (curr_band != prev_band) or (abs(current_rate_mm_h - prev_rate) >= 15.0)

        # Update tracked rate
        self._last_reported_rates[rate_key] = current_rate_mm_h

        if not is_material and prev_rate > 0.0:
            logger.debug(f"Rain update for {locality} suppressed: Immaterial change ({prev_rate} -> {current_rate_mm_h} mm/h)")
            return []

        matched = self.find_matching_subscribers(locality=locality, corridor_id=corridor_id)
        recipients = [f"user:{sub.user_id}" for sub in matched] if matched else [f"topic:area:{locality.lower()}"]
        emitted: List[NotificationRecord] = []

        title = f"Rainfall Update: {locality} ({intensity_state})"
        message = (
            f"Observed rainfall rate changed to {current_rate_mm_h:.1f} mm/h (previously {prev_rate:.1f} mm/h). "
            f"Local drainage chokepoints may experience sudden water rise."
        )
        action = "Slow down vehicle speed. Use caution near junctions with active storm drain overflows."

        for recipient in recipients:
            rec = self.notify(
                recipient_or_topic=recipient,
                severity=severity,
                title=title,
                message=message,
                corridor_id=corridor_id,
                event_type="RAIN_EVENT_UPDATE",
                notification_type=NotificationType.RAIN_EVENT_UPDATE,
                evidence_status="OBSERVED_HAZARD",
                recommended_action=action,
                affected_areas=[locality],
                cooldown_seconds=1200.0,
                bypass_cooldown=is_material,
            )
            if rec:
                emitted.append(rec)
        return emitted

    def dispatch_local_flood_warning(
        self,
        locality: str,
        corridor_id: Optional[str],
        evidence_summary: str,
        recommended_action: str = "Avoid low-lying underpasses; follow diverted arterial routes.",
        severity: NotificationSeverity = NotificationSeverity.WARNING,
        evidence_status: str = "OBSERVED_HAZARD",
    ) -> List[NotificationRecord]:
        """
        Scenario C: LOCAL FLOOD-RISK WARNING
        Sends a localized warning explaining the affected locality, evidence, and precaution.
        """
        matched = self.find_matching_subscribers(locality=locality, corridor_id=corridor_id)
        recipients = [f"user:{sub.user_id}" for sub in matched] if matched else [f"topic:area:{locality.lower()}"]
        emitted: List[NotificationRecord] = []

        title = f"Local Flood Hazard Warning: {locality}"
        message = f"Hazard detected in {locality}. Evidence: {evidence_summary}"

        for recipient in recipients:
            rec = self.notify(
                recipient_or_topic=recipient,
                severity=severity,
                title=title,
                message=message,
                corridor_id=corridor_id,
                event_type="LOCAL_FLOOD_WARNING",
                notification_type=NotificationType.LOCAL_FLOOD_RISK_WARNING,
                evidence_status=evidence_status,
                recommended_action=recommended_action,
                affected_areas=[locality],
                cooldown_seconds=1800.0,
            )
            if rec:
                emitted.append(rec)
        return emitted

    def dispatch_route_hazard_alert(
        self,
        segment_id: str,
        road_name: str,
        hazard_state: str = "VERIFIED_IMPASSABLE",
        router: Optional[Any] = None,
    ) -> List[NotificationRecord]:
        """
        Scenario D: ROUTE HAZARD ALERT
        Notifies users whose active route intersects a newly blocked/hazardous segment,
        and triggers automatic route recalculation if graph router is provided.
        """
        matched = self.find_matching_subscribers(segment_id=segment_id)
        emitted: List[NotificationRecord] = []

        for sub in matched:
            recalc_available = False
            alt_route_id = None
            action = f"Segment {road_name} has become impassable. Do not attempt crossing."

            if router and sub.origin_node_id and sub.destination_node_id:
                try:
                    alt_route = router.find_risk_aware_route(
                        origin_node_id=sub.origin_node_id,
                        destination_node_id=sub.destination_node_id,
                    )
                    from sahaay.routing.schemas import RouteAssessmentOutcome
                    if alt_route.outcome == RouteAssessmentOutcome.ADVISORY_TRAVERSABLE_WITH_CAUTION:
                        recalc_available = True
                        alt_route_id = alt_route.route_id
                        action = f"Route recalculation succeeded via alternative corridors. Follow updated route {alt_route_id}."
                    else:
                        action = "All topological routes to destination are blocked by floodwaters. Proceed to nearest safe shelter."
                except Exception as ex:
                    logger.debug(f"Route recalculation failed: {ex}")

            rec = self.notify(
                recipient_or_topic=f"user:{sub.user_id}",
                severity=NotificationSeverity.EMERGENCY if hazard_state == "VERIFIED_IMPASSABLE" else NotificationSeverity.WARNING,
                title=f"Active Route Hazard: {road_name}",
                message=f"Your active commute route is affected: {road_name} is currently {hazard_state}.",
                corridor_id=segment_id,
                event_type="ROUTE_HAZARD",
                notification_type=NotificationType.ROUTE_HAZARD_ALERT,
                evidence_status="CONFIRMED_IMPASSABLE" if hazard_state == "VERIFIED_IMPASSABLE" else "OBSERVED_HAZARD",
                recommended_action=action,
                recalculation_available=recalc_available,
                suggested_alternative_route_id=alt_route_id,
                cooldown_seconds=600.0,
            )
            if rec:
                emitted.append(rec)
        return emitted

    def get_history(
        self,
        corridor_id: Optional[str] = None,
        severity: Optional[NotificationSeverity] = None,
        limit: int = 50,
    ) -> List[NotificationRecord]:
        """Returns recent notification history, optionally filtered."""
        with self._lock:
            items = self._notifications
            if corridor_id:
                items = [n for n in items if n.corridor_id == corridor_id or n.corridor_id is None]
            if severity:
                items = [n for n in items if n.severity == severity]
            return items[:limit]

    def clear(self) -> None:
        """Clears all records (used for test isolation)."""
        with self._lock:
            self._notifications.clear()
            self._subscriptions.clear()
            self._last_emitted_timestamps.clear()
            self._last_reported_rates.clear()


# Global singleton instance
default_notification_service = NotificationService()
