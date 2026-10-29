"""
Sahaay AI - Hyderabad News Ingestion Connector
Ingests civic news articles, traffic alerts, and published RSS feeds.
Discovers embedded images, runs automated flood-vision analysis,
and extracts localities and event categories using the text pipeline.
"""

from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
import logging
import os
import re
from typing import Any, Dict, List, Optional, Set
import urllib.request
import uuid
import xml.etree.ElementTree as ET

from sahaay.ingestion.connectors.base import BaseSourceConnector
from sahaay.ingestion.image_downloader import (
    extract_image_urls_from_article_html,
    fetch_remote_image,
    fetch_safe_article_html,
)
from sahaay.ingestion.image_pipeline import default_image_pipeline
from sahaay.ingestion.schemas import (
    EventProcessingStatus,
    EventVerificationStatus,
    IngestedEvent,
    IngestionEventType,
    IngestionSourceType,
)
from sahaay.ingestion.text_pipeline import default_text_pipeline

logger = logging.getLogger(__name__)

# Default permitted RSS sources for Hyderabad civic and weather news
DEFAULT_RSS_FEEDS = [
    {
        "name": "THE-HINDU-HYDERABAD-FEED",
        "url": "https://www.thehindu.com/news/cities/Hyderabad/feeder/default.rss",
        "publisher": "The Hindu",
    },
    {
        "name": "TELANGANA-TODAY-HYDERABAD-FEED",
        "url": "https://telanganatoday.com/feed",
        "publisher": "Telangana Today",
    },
    {
        "name": "GOOGLE-NEWS-HYDERABAD-RAIN-FEED",
        "url": "https://news.google.com/rss/search?q=Hyderabad+rain+OR+flood+OR+waterlogging+OR+traffic&hl=en-IN&gl=IN&ceid=IN:en",
        "publisher": "Google News Aggregation",
    },
]

MEDIA_NS = "{http://search.yahoo.com/mrss/}"


class NewsIngestionConnector(BaseSourceConnector):
    """
    Automated connector for Hyderabad civic news and RSS outlets.
    Extracts road disruption events, discovers article images, and triggers
    vision AI inference without manual operator intervention.
    """

    def __init__(
        self,
        connector_id: str = "CONN-HYD-NEWS-RSS",
        source_name: str = "HYD-CIVIC-NEWS-MONITOR",
        is_live: Optional[bool] = None,
        polling_interval_seconds: int = 600,
    ):
        live_flag = (
            is_live
            if is_live is not None
            else os.getenv("SAHAAY_LIVE_NEWS_ENABLED", "true").lower() in ("true", "1")
        )
        super().__init__(
            connector_id=connector_id,
            source_name=source_name,
            source_type=IngestionSourceType.NEWS_FEED,
            is_live=live_flag,
            polling_interval_seconds=polling_interval_seconds,
        )
        self.feed_registry = list(DEFAULT_RSS_FEEDS)
        # Allow extra feeds from environment
        extra_urls = os.getenv("SAHAAY_NEWS_RSS_URLS", "").strip()
        if extra_urls:
            for i, u in enumerate(extra_urls.split(",")):
                u = u.strip()
                if u:
                    self.feed_registry.append({
                        "name": f"CUSTOM-FEED-{i+1}",
                        "url": u,
                        "publisher": "Custom Configured Feed",
                    })

        self._fixture_queue: List[IngestedEvent] = []
        self._seen_article_ids: Set[str] = set()

        if not self.is_live:
            self._initialize_default_fixtures()

    def _initialize_default_fixtures(self) -> None:
        """Pre-populates demonstration news items."""
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat().replace("+00:00", "Z")
        exp_iso = (now + timedelta(hours=4)).isoformat().replace("+00:00", "Z")

        # Article 1: Malakpet RUB closure
        text_1 = "Hyderabad Traffic Police Alert: Severe waterlogging reported under Malakpet Railway Underbridge (RUB); traffic diverted towards Chaderghat."
        analysis_1 = default_text_pipeline.analyze_text(text_1)

        event1 = IngestedEvent(
            event_id="EVT-NEWS-20261029-001",
            event_type=analysis_1.event_type,
            source_type=IngestionSourceType.NEWS_FEED,
            source_name=self.source_name,
            source_item_id="ARTICLE-TT-89211",
            source_url="https://telanganatoday.com/hyderabad-rains-malakpet-underbridge-waterlogged",
            observed_at=now_iso,
            published_at=now_iso,
            retrieved_at=now_iso,
            expires_at=exp_iso,
            latitude=analysis_1.latitude,
            longitude=analysis_1.longitude,
            location_name=analysis_1.reported_place_name,
            location_accuracy=analysis_1.location_accuracy,
            resolved_corridor_id=analysis_1.resolved_corridor_id,
            raw_text=text_1,
            raw_evidence_reference="Telangana Today Civic Desk #89211",
            processing_status=EventProcessingStatus.PROCESSED,
            verification_status=EventVerificationStatus.UNVERIFIED,
            confidence=analysis_1.confidence,
            provenance={
                "publisher": "Telangana Today",
                "matched_keywords": analysis_1.matched_keywords,
                "is_out_of_scope": analysis_1.is_out_of_scope,
                "summary": analysis_1.summary,
            },
            is_synthetic_fixture=True,
        )
        self._fixture_queue.append(event1)

    def inject_article(self, headline: str, body: str, item_id: Optional[str] = None) -> IngestedEvent:
        """Allows injecting an article dynamically for testing or scenario playback."""
        full_text = f"{headline}. {body}"
        analysis = default_text_pipeline.analyze_text(full_text)
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat().replace("+00:00", "Z")
        exp_iso = (now + timedelta(hours=4)).isoformat().replace("+00:00", "Z")

        event = IngestedEvent(
            event_id=f"EVT-NEWS-{uuid.uuid4().hex[:8].upper()}",
            event_type=analysis.event_type,
            source_type=IngestionSourceType.NEWS_FEED,
            source_name=self.source_name,
            source_item_id=item_id or f"ITEM-{uuid.uuid4().hex[:6]}",
            source_url=f"https://telanganatoday.com/article-{uuid.uuid4().hex[:4]}",
            observed_at=now_iso,
            published_at=now_iso,
            retrieved_at=now_iso,
            expires_at=exp_iso,
            latitude=analysis.latitude,
            longitude=analysis.longitude,
            location_name=analysis.reported_place_name,
            location_accuracy=analysis.location_accuracy,
            resolved_corridor_id=analysis.resolved_corridor_id,
            raw_text=full_text,
            raw_evidence_reference=f"News Item: {headline[:40]}...",
            processing_status=EventProcessingStatus.PROCESSED,
            verification_status=EventVerificationStatus.UNVERIFIED,
            confidence=analysis.confidence,
            provenance={
                "headline": headline,
                "matched_keywords": analysis.matched_keywords,
                "is_out_of_scope": analysis.is_out_of_scope,
                "summary": analysis.summary,
            },
            is_synthetic_fixture=True,
        )
        self._fixture_queue.append(event)
        return event

    def _parse_pub_date(self, pub_date_str: Optional[str]) -> str:
        """Safely parses RFC 822/2822 or ISO 8601 publication timestamps to ISO UTC."""
        if not pub_date_str:
            return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        try:
            dt = parsedate_to_datetime(pub_date_str)
            if not dt.tzinfo:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        except Exception:
            return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _fetch_live_rss_feeds(self) -> List[IngestedEvent]:
        """
        Polls registered RSS feeds, parses article items, discovers attached images,
        runs automated vision and text inference, and produces normalized events.
        """
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat().replace("+00:00", "Z")
        exp_iso = (now + timedelta(hours=6)).isoformat().replace("+00:00", "Z")
        discovered_events: List[IngestedEvent] = []

        for feed in self.feed_registry:
            feed_name = feed["name"]
            feed_url = feed["url"]
            publisher = feed.get("publisher", "Unknown Publisher")

            try:
                req = urllib.request.Request(
                    feed_url,
                    headers={"User-Agent": "SahaayAI-Hyderabad-Flood-Intel/1.0 (+https://github.com/Mahendrareddy2006/SAHAAY_AI)"},
                )
                with urllib.request.urlopen(req, timeout=5.0) as resp:
                    xml_content = resp.read()

                root = ET.fromstring(xml_content)
                items = root.findall(".//item")

                for item in items[:15]:  # Process top 15 items per feed
                    title_elem = item.find("title")
                    title = (title_elem.text if title_elem is not None and title_elem.text else "")
                    link_elem = item.find("link")
                    link = (link_elem.text if link_elem is not None and link_elem.text else "")
                    desc_elem = item.find("description")
                    desc = (desc_elem.text if desc_elem is not None and desc_elem.text else "")
                    pub_elem = item.find("pubDate")
                    pub_date_str = (pub_elem.text if pub_elem is not None else None)
                    guid_elem = item.find("guid")
                    guid = (guid_elem.text if guid_elem is not None and guid_elem.text else link)

                    item_id = guid or link or f"{feed_name}-{hash(title)}"
                    if item_id in self._seen_article_ids:
                        continue
                    self._seen_article_ids.add(item_id)

                    # Strip HTML tags from description
                    clean_desc = re.sub(r"<[^>]+>", " ", desc).strip()
                    full_text = f"{title}. {clean_desc}".strip()

                    # Analyze text with existing NLP pipeline
                    analysis = default_text_pipeline.analyze_text(full_text)

                    # Skip entirely irrelevant articles that have no locality or flood/weather keywords
                    if analysis.event_type == IngestionEventType.IRRELEVANT_OR_UNSUPPORTED and analysis.is_out_of_scope:
                        continue

                    # Discover candidate images:
                    # 1. Media RSS: <media:content url="...">
                    media_elem = item.find(f"{MEDIA_NS}content")
                    # 2. Enclosure: <enclosure url="..." type="image/...">
                    enc_elem = item.find("enclosure")
                    # 3. HTML img tag in description
                    desc_img_matches = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', desc)

                    candidate_image_url: Optional[str] = None
                    if media_elem is not None and media_elem.get("url"):
                        candidate_image_url = media_elem.get("url")
                    elif enc_elem is not None and "image" in (enc_elem.get("type") or ""):
                        candidate_image_url = enc_elem.get("url")
                    elif desc_img_matches:
                        candidate_image_url = desc_img_matches[0]

                    # 4. If no image in RSS item and article matches flood/traffic keywords or corridor, inspect article HTML
                    if not candidate_image_url and link and (
                        analysis.event_type != IngestionEventType.IRRELEVANT_OR_UNSUPPORTED
                        or analysis.resolved_corridor_id is not None
                    ):
                        try:
                            art_html = fetch_safe_article_html(link, max_bytes=256 * 1024, timeout_seconds=4.0)
                            if art_html:
                                art_imgs = extract_image_urls_from_article_html(art_html, link)
                                if art_imgs:
                                    candidate_image_url = art_imgs[0]
                        except Exception as ex:
                            logger.debug(f"Article HTML image discovery failed for {link}: {ex}")

                    # If candidate image found, safely fetch and run vision inference
                    vision_provenance: Dict[str, Any] = {}
                    image_ref: Optional[str] = None
                    event_type = analysis.event_type

                    if candidate_image_url:
                        img_bytes = fetch_remote_image(candidate_image_url)
                        if img_bytes:
                            vision_res = default_image_pipeline.process_image_bytes(
                                image_bytes=img_bytes,
                                corridor_id=analysis.resolved_corridor_id,
                                source_name=feed_name,
                            )
                            image_ref = f"sha256:{vision_res.image_sha256}"
                            vision_provenance = {
                                "discovered_image_url": candidate_image_url,
                                "vision_predicted_class": vision_res.predicted_class,
                                "vision_confidence": vision_res.confidence,
                                "is_inconclusive": vision_res.is_inconclusive,
                                "rejection_reasons": getattr(vision_res, "rejection_reasons", []),
                                "quality_passed": getattr(vision_res, "quality_passed", True),
                                "inference_latency_ms": getattr(vision_res, "inference_latency_ms", 0.0),
                                "model_version": getattr(vision_res, "model_version", "v3.0.0-monsoon-robust"),
                                "safety_disclaimer": "Article imagery is provisional visual evidence. Model prediction does NOT confirm ground truth inundation without responder inspection.",
                            }
                            # If vision detected flood and text was general, promote event type
                            if vision_res.predicted_class == "flooded" and not vision_res.is_inconclusive and getattr(vision_res, "quality_passed", True):
                                event_type = IngestionEventType.REPORTED_FLOODING

                    pub_iso = self._parse_pub_date(pub_date_str)

                    event = IngestedEvent(
                        event_id=f"EVT-NEWS-LIVE-{uuid.uuid4().hex[:8].upper()}",
                        event_type=event_type,
                        source_type=IngestionSourceType.NEWS_FEED,
                        source_name=feed_name,
                        source_item_id=item_id,
                        source_url=link,
                        observed_at=pub_iso,
                        published_at=pub_iso,
                        retrieved_at=now_iso,
                        expires_at=exp_iso,
                        latitude=analysis.latitude,
                        longitude=analysis.longitude,
                        location_name=analysis.reported_place_name or "Hyderabad Region",
                        location_accuracy=analysis.location_accuracy,
                        resolved_corridor_id=analysis.resolved_corridor_id,
                        raw_text=full_text[:400],
                        raw_evidence_reference=f"RSS Article: {title[:50]} ({publisher})",
                        image_reference=image_ref,
                        processing_status=EventProcessingStatus.PROCESSED,
                        verification_status=EventVerificationStatus.UNVERIFIED,
                        confidence=analysis.confidence,
                        provenance={
                            "publisher": publisher,
                            "matched_keywords": analysis.matched_keywords,
                            "is_out_of_scope": analysis.is_out_of_scope,
                            "summary": analysis.summary,
                            "feed_url": feed_url,
                            "is_live_stream": True,
                            **vision_provenance,
                        },
                        is_synthetic_fixture=False,
                    )
                    discovered_events.append(event)
            except Exception as e:
                logger.warning(f"Failed to poll RSS feed '{feed_name}': {e}")

        self.provenance_metadata = {
            "feeds_count": len(self.feed_registry),
            "registered_feeds": [f["name"] for f in self.feed_registry],
            "total_articles_seen": len(self._seen_article_ids),
        }
        return discovered_events

    def fetch_events(self) -> List[IngestedEvent]:
        """
        Polls news articles from registered sources.
        """
        self.record_attempt()
        events: List[IngestedEvent] = []

        # 1. Return any explicitly injected fixtures first (e.g. for deterministic demo)
        if self._fixture_queue:
            events.extend(self._fixture_queue)
            self._fixture_queue.clear()
            self.record_success(len(events))
            return events

        # 2. Poll live RSS feeds if enabled
        if self.is_live:
            try:
                live_items = self._fetch_live_rss_feeds()
                if live_items:
                    events.extend(live_items)
                    self.record_success(len(events))
                    return events
            except Exception as e:
                logger.warning(f"Live news poll failed: {e}. Degrading connector state.")
                self.record_failure(str(e))

        # 3. Fallback: if no live events or disabled, return default demonstration fixture
        self._initialize_default_fixtures()
        events.extend(self._fixture_queue)
        self._fixture_queue.clear()
        return events
