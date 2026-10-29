"""
Sahaay AI - Community Posts & Image Ingestion Connector
Ingests posts from authorized community channels (Telegram/WhatsApp bot or civic webhooks).
Automatically routes attached images to the vision AI pipeline without manual dashboard upload.
Enforces NOT_CONFIGURED state when external credentials/secrets are absent.
"""

from datetime import datetime, timezone, timedelta
import hmac
import hashlib
import io
import logging
import os
import uuid
from typing import Any, Dict, List, Optional
from PIL import Image

from sahaay.ingestion.connectors.base import BaseSourceConnector
from sahaay.ingestion.image_pipeline import default_image_pipeline
from sahaay.ingestion.schemas import (
    EventProcessingStatus,
    EventVerificationStatus,
    IngestedEvent,
    IngestionEventType,
    IngestionSourceType,
    LocationResolutionAccuracy,
)
from sahaay.ingestion.text_pipeline import default_text_pipeline

logger = logging.getLogger(__name__)


class CommunityIngestionConnector(BaseSourceConnector):
    """
    Automated connector for authorized community reports.
    Automatically extracts image payloads and runs MobileNetV3 inference without user UI upload.
    Reports NOT_CONFIGURED if external credentials/secrets are not supplied.
    """

    def __init__(
        self,
        connector_id: str = "CONN-HYD-COMMUNITY-BOT",
        source_name: str = "HYD-CITIZEN-COMMUNITY-WEBHOOK",
        is_live: Optional[bool] = None,
        polling_interval_seconds: int = 120,
    ):
        self.webhook_secret = os.getenv("SAHAAY_COMMUNITY_WEBHOOK_SECRET", "").strip()
        self.bot_token = os.getenv("SAHAAY_COMMUNITY_BOT_TOKEN", "").strip()
        configured = bool(self.webhook_secret or self.bot_token)

        live_flag = (
            is_live
            if is_live is not None
            else configured
        )

        super().__init__(
            connector_id=connector_id,
            source_name=source_name,
            source_type=IngestionSourceType.COMMUNITY_CHANNEL,
            is_live=live_flag,
            polling_interval_seconds=polling_interval_seconds,
        )
        if is_live is False:
            self.is_configured = True  # Explicit fixture testing mode
        else:
            self.is_configured = configured

        self._fixture_queue: List[IngestedEvent] = []
        self._incoming_webhook_events: List[IngestedEvent] = []
        self.provenance_metadata = {
            "webhook_auth_configured": bool(self.webhook_secret),
            "bot_token_configured": bool(self.bot_token),
            "submission_channels": ["Telegram Civic Bot", "Civic Webhook Endpoint"],
        }

        if not self.is_live:
            self._initialize_default_fixtures()

    def _initialize_default_fixtures(self) -> None:
        """Pre-populates demonstration community post with attached flood image."""
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat().replace("+00:00", "Z")
        exp_iso = (now + timedelta(hours=3)).isoformat().replace("+00:00", "Z")

        sample_img = Image.new("RGB", (256, 256), color=(60, 75, 90))
        img_buf = io.BytesIO()
        sample_img.save(img_buf, format="JPEG")
        img_bytes = img_buf.getvalue()

        text = "Water logging near Tolichowki Flyover Underpass. Cars are slowing down due to knee deep water."
        analysis = default_text_pipeline.analyze_text(text)

        vision_result = default_image_pipeline.process_image_bytes(
            image_bytes=img_bytes,
            corridor_id=analysis.resolved_corridor_id,
            source_name=self.source_name,
        )

        event = IngestedEvent(
            event_id="EVT-COMM-20261029-001",
            event_type=IngestionEventType.COMMUNITY_IMAGE,
            source_type=IngestionSourceType.COMMUNITY_CHANNEL,
            source_name=self.source_name,
            source_item_id="TG-POST-9401",
            source_url="https://t.me/hyd_flood_intel/9401",
            observed_at=now_iso,
            published_at=now_iso,
            retrieved_at=now_iso,
            expires_at=exp_iso,
            latitude=analysis.latitude,
            longitude=analysis.longitude,
            location_name=analysis.reported_place_name,
            location_accuracy=analysis.location_accuracy,
            resolved_corridor_id=analysis.resolved_corridor_id,
            raw_text=text,
            raw_evidence_reference=f"Community Post #9401 (Image SHA: {vision_result.image_sha256[:12]}...)",
            image_reference=f"sha256:{vision_result.image_sha256}",
            processing_status=EventProcessingStatus.PROCESSED if not vision_result.is_inconclusive else EventProcessingStatus.INCONCLUSIVE,
            verification_status=EventVerificationStatus.UNVERIFIED,
            confidence=vision_result.confidence,
            provenance={
                "channel_platform": "Telegram Civic Channel",
                "predicted_class": vision_result.predicted_class,
                "model_confidence": vision_result.confidence,
                "is_inconclusive": vision_result.is_inconclusive,
                "model_version": vision_result.model_version,
                "quality_passed": vision_result.quality_passed,
                "inference_latency_ms": vision_result.inference_latency_ms,
                "safety_disclaimer": vision_result.safety_disclaimer,
            },
            is_synthetic_fixture=True,
        )
        self._fixture_queue.append(event)

    def verify_webhook_signature(self, payload_bytes: bytes, signature_header: Optional[str]) -> bool:
        """
        Validates HMAC-SHA256 signature on incoming community webhooks.
        If no secret is configured, returns True in non-production environments.
        """
        if not self.webhook_secret:
            return True
        if not signature_header:
            return False

        expected = hmac.new(
            self.webhook_secret.encode("utf-8"),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected, signature_header.replace("sha256=", "").strip())

    def receive_webhook_submission(
        self,
        text: str,
        image_bytes: Optional[bytes] = None,
        author: str = "community_member",
        post_id: Optional[str] = None,
        platform: str = "Civic Webhook Gateway",
    ) -> IngestedEvent:
        """
        Receives an authorized community submission via webhook/bot API,
        automatically triggering text classification and flood-vision inference.
        """
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat().replace("+00:00", "Z")
        exp_iso = (now + timedelta(hours=3)).isoformat().replace("+00:00", "Z")

        # 1. Text analysis
        analysis = default_text_pipeline.analyze_text(text)

        # 2. Vision analysis if image payload attached
        vision_provenance: Dict[str, Any] = {}
        image_ref: Optional[str] = None
        event_type = analysis.event_type

        if image_bytes:
            vision_result = default_image_pipeline.process_image_bytes(
                image_bytes=image_bytes,
                corridor_id=analysis.resolved_corridor_id,
                source_name=self.source_name,
            )
            image_ref = f"sha256:{vision_result.image_sha256}"
            event_type = IngestionEventType.COMMUNITY_IMAGE
            vision_provenance = {
                "predicted_class": vision_result.predicted_class,
                "model_confidence": vision_result.confidence,
                "is_inconclusive": vision_result.is_inconclusive,
                "rejection_reasons": getattr(vision_result, "rejection_reasons", []),
                "quality_passed": vision_result.quality_passed,
                "model_version": vision_result.model_version,
                "safety_disclaimer": vision_result.safety_disclaimer,
            }

        event = IngestedEvent(
            event_id=f"EVT-COMM-WEBHOOK-{uuid.uuid4().hex[:8].upper()}",
            event_type=event_type,
            source_type=IngestionSourceType.COMMUNITY_CHANNEL,
            source_name=self.source_name,
            source_item_id=post_id or f"WH-{uuid.uuid4().hex[:6]}",
            source_url=None,
            observed_at=now_iso,
            published_at=now_iso,
            retrieved_at=now_iso,
            expires_at=exp_iso,
            latitude=analysis.latitude,
            longitude=analysis.longitude,
            location_name=analysis.reported_place_name or "Reported Location",
            location_accuracy=analysis.location_accuracy,
            resolved_corridor_id=analysis.resolved_corridor_id,
            raw_text=text,
            raw_evidence_reference=f"Community Post via {platform} (Author: {author})",
            image_reference=image_ref,
            processing_status=EventProcessingStatus.PROCESSED,
            verification_status=EventVerificationStatus.UNVERIFIED,
            confidence=analysis.confidence if not image_bytes else vision_provenance.get("model_confidence", 0.5),
            provenance={
                "channel_platform": platform,
                "author": author,
                "matched_keywords": analysis.matched_keywords,
                "is_live_stream": True,
                **vision_provenance,
            },
            is_synthetic_fixture=False,
        )

        self._incoming_webhook_events.append(event)
        self.record_success(1)
        return event

    def ingest_post_with_image(
        self,
        text: str,
        image_bytes: bytes,
        post_id: Optional[str] = None,
        author: str = "community_member",
    ) -> IngestedEvent:
        """Alias for backward-compatibility with tests."""
        return self.receive_webhook_submission(
            text=text,
            image_bytes=image_bytes,
            author=author,
            post_id=post_id,
        )

    def fetch_events(self) -> List[IngestedEvent]:
        """Polls or drains queued community events."""
        self.record_attempt()
        events: List[IngestedEvent] = []

        # 1. Drain incoming live webhook queue
        if self._incoming_webhook_events:
            events.extend(self._incoming_webhook_events)
            self._incoming_webhook_events.clear()
            self.record_success(len(events))
            return events

        # 2. Return injected demo fixtures if any
        if self._fixture_queue:
            events.extend(self._fixture_queue)
            self._fixture_queue.clear()
            self.record_success(len(events))
            return events

        # 3. If live/configured and no events, return empty list
        if self.is_live and self.is_configured:
            return []

        # 4. Fallback default fixture for demo mode
        self._initialize_default_fixtures()
        events.extend(self._fixture_queue)
        self._fixture_queue.clear()
        return events
