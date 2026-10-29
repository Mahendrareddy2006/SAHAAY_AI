"""
Sahaay AI - Security & API Hardening Verification Suite
(tests/test_security_and_api_hardening.py)

Validates Workstream C, E, and G hardening implementations:
1. Server-side Bearer authentication & verification (no client-side trust)
2. Role enforcement on privileged endpoints & prevention of client role spoofing
3. Token expiration, tampering rejection, and zero-downtime key rotation
4. In-memory sliding-window rate limiting & abuse prevention (HTTP 429)
5. Sensitive data & PII redaction in structured logging
6. Road matching configurable bounds, distant coordinate rejection, and invalid coordinate resilience
7. Image upload abuse prevention (MIME types, empty bytes, corrupt files)
8. Root dashboard redirection
"""

import io
import logging
import math
import os
import time
from PIL import Image
import pytest
from fastapi.testclient import TestClient

from sahaay.api.main import app
from sahaay.security.auth import (
    UserRole,
    create_access_token,
    verify_bearer_token,
    INTERNAL_DEV_AUTH_SECRET,
)
from sahaay.security.rate_limiter import SlidingWindowRateLimiter, default_rate_limiter
from sahaay.security.logging_filter import RedactingLoggingFilter
from sahaay.road_network.store import default_road_network_store
from sahaay.emergency_destinations.service import default_destination_routing_service


@pytest.fixture
def client():
    # Disable rate limiter by default for unrelated tests, then enable specifically in rate limit tests
    default_rate_limiter.set_enabled(False)
    yield TestClient(app)
    default_rate_limiter.set_enabled(True)
    default_rate_limiter.reset()


# ---------------------------------------------------------------------------
# 1. Server-Side Authentication & Role Enforcement Tests
# ---------------------------------------------------------------------------

def test_privileged_action_requires_authentication(client):
    """Accessing /security/privileged-action without token must return 401 Unauthorized."""
    payload = {
        "action_type": "EMERGENCY_CORRIDOR_SURVEILLANCE_OVERRIDE",
        "target_resource": "HYD-LOC-001",
    }
    res = client.post("/api/v1/security/privileged-action", json=payload)
    assert res.status_code == 401
    assert "missing authorization header" in res.json()["detail"].lower()


def test_privileged_action_invalid_token_format(client):
    """Malformed token strings must fail closed with 401 Unauthorized."""
    res = client.post(
        "/api/v1/security/privileged-action",
        json={"action_type": "TEST_ACTION", "target_resource": "RES-1"},
        headers={"Authorization": "Bearer malformed_token_string_without_dots"}
    )
    assert res.status_code == 401
    assert "invalid token format" in res.json()["detail"].lower()


def test_privileged_action_tampered_signature(client):
    """Tampered token signatures must be rejected immediately with 401 Unauthorized."""
    token = create_access_token("USER-01", UserRole.SYSTEM_ADMIN)
    parts = token.split(".")
    tampered_token = f"{parts[0]}.{parts[1]}.tampered_signature_abc123"

    res = client.post(
        "/api/v1/security/privileged-action",
        json={"action_type": "TEST_ACTION", "target_resource": "RES-1"},
        headers={"Authorization": f"Bearer {tampered_token}"}
    )
    assert res.status_code == 401
    assert "cryptographic signature mismatch" in res.json()["detail"].lower()


def test_privileged_action_expired_token(client):
    """Expired tokens must fail closed with 401 Unauthorized."""
    # Issue a token that expired 5 minutes ago
    expired_token = create_access_token("USER-01", UserRole.SYSTEM_ADMIN, expires_in_minutes=-5)

    res = client.post(
        "/api/v1/security/privileged-action",
        json={"action_type": "TEST_ACTION", "target_resource": "RES-1"},
        headers={"Authorization": f"Bearer {expired_token}"}
    )
    assert res.status_code == 401
    assert "expired" in res.json()["detail"].lower()


def test_privileged_action_role_spoofing_prevention(client):
    """Client cannot supply a privileged role in body that disagrees with their server token."""
    # Token has CITIZEN role
    citizen_token = create_access_token("CITIZEN-01", UserRole.CITIZEN)

    # Client tries to claim GHMC_DRF_OFFICER in request body
    res = client.post(
        "/api/v1/security/privileged-action",
        json={
            "action_type": "TEST_ACTION",
            "target_resource": "RES-1",
            "caller_role": "GHMC_DRF_OFFICER"
        },
        headers={"Authorization": f"Bearer {citizen_token}"}
    )
    # Role checker stops CITIZEN from supervisor action (403)
    assert res.status_code == 403


def test_privileged_action_insufficient_role(client):
    """Even if client-supplied role matches token, non-supervisor roles are rejected with 403."""
    observer_token = create_access_token("OBS-01", UserRole.OBSERVER)
    res = client.post(
        "/api/v1/security/privileged-action",
        json={
            "action_type": "TEST_ACTION",
            "target_resource": "RES-1",
            "caller_role": "OBSERVER"
        },
        headers={"Authorization": f"Bearer {observer_token}"}
    )
    assert res.status_code == 403
    assert "lacks supervisor privileges" in res.json()["detail"].lower()


def test_privileged_action_disarmed_operational_triggers(client):
    """Autonomous emergency dispatch and live stream activation remain strictly barred."""
    admin_token = create_access_token("ADMIN-01", UserRole.SYSTEM_ADMIN)

    # 1. Autonomous dispatch attempt
    res_dispatch = client.post(
        "/api/v1/security/privileged-action",
        json={
            "action_type": "DISPATCH_CREW",
            "target_resource": "ZONE-WEST",
            "attempt_autonomous_dispatch": True
        },
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert res_dispatch.status_code == 403
    assert "strictly disarmed" in res_dispatch.json()["detail"].lower()

    # 2. Autonomous live feed activation attempt
    res_feed = client.post(
        "/api/v1/security/privileged-action",
        json={
            "action_type": "ACTIVATE_LIVE_FEED",
            "target_resource": "IMD-FEED",
            "attempt_live_stream_activation": True
        },
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert res_feed.status_code == 403
    assert "strictly disarmed" in res_feed.json()["detail"].lower()


def test_authorized_supervisor_action_succeeds(client):
    """Authorized supervisor role with clean parameters succeeds and produces an audit hash."""
    drf_token = create_access_token("OFFICER-42", UserRole.GHMC_DRF_OFFICER)
    res = client.post(
        "/api/v1/security/privileged-action",
        json={
            "action_type": "CORRIDOR_VERIFICATION_AUDIT",
            "target_resource": "HYD-LOC-001",
            "caller_role": "GHMC_DRF_OFFICER"
        },
        headers={"Authorization": f"Bearer {drf_token}"}
    )
    assert res.status_code == 200
    out = res.json()
    assert out["status"] == "AUTHORIZED_EXECUTION_COMPLETED"
    assert out["operator_id"] == "OFFICER-42"
    assert out["authenticated_role"] == "GHMC_DRF_OFFICER"
    assert len(out["audit_hash"]) == 64


# ---------------------------------------------------------------------------
# 2. Key Rotation Readiness Test
# ---------------------------------------------------------------------------

def test_key_rotation_standby_verification():
    """Tokens signed with a previous key must still be accepted when previous key is configured."""
    old_secret = "sahaay_previous_auth_key_2025_rotation_test"
    new_secret = "sahaay_current_new_auth_key_2026_active"

    # Temporarily set env var for previous key
    os.environ["SAHAAY_PREVIOUS_SECRET_KEY"] = old_secret

    try:
        # Issue token signed with old_secret
        import hmac
        import hashlib
        import json
        import base64
        from datetime import datetime, timezone, timedelta

        now = datetime.now(timezone.utc)
        exp = now + timedelta(minutes=30)
        payload = {
            "sub": "ROTATED-USER",
            "role": "GHMC_DRF_OFFICER",
            "iat": now.isoformat().replace("+00:00", "Z"),
            "exp": exp.isoformat().replace("+00:00", "Z"),
            "jti": "rot123",
            "inst": True,
            "iss": "SAHAAY_LOCAL_SECURITY_GATEWAY",
        }
        payload_b64 = base64.urlsafe_b64encode(json.dumps(payload, sort_keys=True).encode()).decode().rstrip("=")
        sig = hmac.new(old_secret.encode(), payload_b64.encode(), hashlib.sha256).digest()
        sig_b64 = base64.urlsafe_b64encode(sig).decode().rstrip("=")
        token_old_key = f"sahaay_v1.{payload_b64}.{sig_b64}"

        # verify_bearer_token must verify against standby key
        identity = verify_bearer_token(token_old_key)
        assert identity.subject_id == "ROTATED-USER"
        assert identity.role == UserRole.GHMC_DRF_OFFICER
    finally:
        os.environ.pop("SAHAAY_PREVIOUS_SECRET_KEY", None)


# ---------------------------------------------------------------------------
# 3. In-Memory Sliding-Window Rate Limiter Tests
# ---------------------------------------------------------------------------

def test_rate_limiter_sliding_window_enforcement():
    """Rate limiter must enforce request ceilings and report retry after."""
    limiter = SlidingWindowRateLimiter(default_limit_per_minute=3)
    key = "test_client_ip_1"

    # Requests 1, 2, 3 allowed
    assert limiter.check_rate_limit(key, limit_per_minute=3)[0] is True
    assert limiter.check_rate_limit(key, limit_per_minute=3)[0] is True
    assert limiter.check_rate_limit(key, limit_per_minute=3)[0] is True

    # 4th request must be rejected with retry_after > 0
    allowed, remaining, retry_after = limiter.check_rate_limit(key, limit_per_minute=3)
    assert allowed is False
    assert remaining == 0
    assert retry_after > 0.0

    # Separate client IP has independent quota
    assert limiter.check_rate_limit("test_client_ip_2", limit_per_minute=3)[0] is True


# ---------------------------------------------------------------------------
# 4. Redacting Logging Filter Tests
# ---------------------------------------------------------------------------

def test_redacting_logging_filter_sanitization():
    """Redacting filter must mask tokens, passwords, phone numbers, and emails."""
    sanitizer = RedactingLoggingFilter()

    # 1. Bearer token
    raw_token_msg = "Received request with header Authorization: Bearer sahaay_v1.payload123.sig456"
    redacted_token = sanitizer.redact(raw_token_msg)
    assert "sahaay_v1.payload123.sig456" not in redacted_token
    assert "[REDACTED_TOKEN]" in redacted_token

    # 2. Secret / API key
    raw_key_msg = "Calling provider with api_key=ghmc_super_secret_key_123456"
    redacted_key = sanitizer.redact(raw_key_msg)
    assert "ghmc_super_secret_key_123456" not in redacted_key
    assert "[REDACTED_API_KEY]" in redacted_key

    # 3. PII Phone number and Email
    raw_pii = "Citizen reporter phone: 9876543210 and email: citizen@hyderabad.gov.in"
    redacted_pii = sanitizer.redact(raw_pii)
    assert "9876543210" not in redacted_pii
    assert "citizen@hyderabad.gov.in" not in redacted_pii
    assert "[REDACTED_PHONE_NUMBER]" in redacted_pii
    assert "[REDACTED_EMAIL]" in redacted_pii


# ---------------------------------------------------------------------------
# 5. Road Matching & Coordinate Boundary Tests
# ---------------------------------------------------------------------------

def test_road_matching_nearby_point():
    """Point adjacent to Tolichowki Flyover Underpass must match HYD-LOC-001."""
    # Tolichowki coords: [78.4112, 17.4023]
    match = default_road_network_store.find_nearest_segment_to_coords(
        lat=17.4024,
        lon=78.4113,
        max_distance_meters=200.0
    )
    assert match is not None
    assert match.segment_id == "HYD-LOC-001"


def test_road_matching_distant_point_returns_none():
    """Point outside monitored corridors (> max distance) must return None, not a distant road."""
    # Delhi coordinate ~28.61, 77.20 (hundreds of km away from Hyderabad)
    match = default_road_network_store.find_nearest_segment_to_coords(
        lat=28.6139,
        lon=77.2090,
        max_distance_meters=3000.0
    )
    assert match is None


def test_road_matching_invalid_coordinates_resilience():
    """Invalid latitude, longitude, NaN, and Inf must return None without raising unhandled errors."""
    # Out of latitude bounds
    assert default_road_network_store.find_nearest_segment_to_coords(lat=999.0, lon=78.45) is None
    assert default_road_network_store.find_nearest_segment_to_coords(lat=-95.0, lon=78.45) is None

    # Out of longitude bounds
    assert default_road_network_store.find_nearest_segment_to_coords(lat=17.40, lon=250.0) is None

    # NaN and Inf
    assert default_road_network_store.find_nearest_segment_to_coords(lat=float("nan"), lon=78.45) is None
    assert default_road_network_store.find_nearest_segment_to_coords(lat=17.40, lon=float("inf")) is None

    # None
    assert default_road_network_store.find_nearest_segment_to_coords(lat=None, lon=None) is None


def test_graph_node_matching_boundary_and_resilience():
    """Destination routing node matcher must reject distant points and invalid coordinates."""
    # Distant point (e.g. Mumbai ~19.07, 72.87)
    node = default_destination_routing_service._find_nearest_graph_node(
        lat=19.0760,
        lon=72.8777,
        max_distance_meters=5000.0
    )
    assert node is None

    # Invalid coordinates
    assert default_destination_routing_service._find_nearest_graph_node(999.0, 78.45) is None
    assert default_destination_routing_service._find_nearest_graph_node(float("nan"), 78.45) is None
    assert default_destination_routing_service._find_nearest_graph_node(None, None) is None


def test_road_matching_ambiguity_detection():
    """When ambiguity_threshold exceeds distance delta between closest two segments, is_ambiguous must be True."""
    seg, dist, is_ambiguous = default_road_network_store.find_nearest_segment_to_coords(
        lat=17.4024,
        lon=78.4113,
        ambiguity_threshold_meters=100000.0,
        return_metadata=True,
    )
    assert seg is not None
    assert is_ambiguous is True


def test_vision_predict_ambiguous_coordinate_rejects_evidence(client, monkeypatch):
    """Ambiguous coordinate match must not register evidence on road network and must log warning."""
    im = Image.new("RGB", (128, 128), color=(20, 80, 140))
    buf = io.BytesIO()
    im.save(buf, format="JPEG")
    buf.seek(0)

    fake_seg = default_road_network_store.get_segment("HYD-LOC-001")
    monkeypatch.setattr(
        default_road_network_store,
        "find_nearest_segment_to_coords",
        lambda lat, lon, return_metadata=False: (fake_seg, 25.0, True) if return_metadata else fake_seg
    )

    files = {"file": ("test.jpg", buf, "image/jpeg")}
    data = {"latitude": "17.4024", "longitude": "78.4113"}
    resp = client.post("/api/v1/vision/predict", files=files, data=data)
    assert resp.status_code == 200
    res = resp.json()
    assert res["corridor_id"] is None
    assert res["evidence_registered"] is False
    assert any("LOCATION_AMBIGUOUS" in w for w in res["warnings"])



# ---------------------------------------------------------------------------
# 6. Image Upload Security & Malformed File Rejection Tests
# ---------------------------------------------------------------------------

def test_image_upload_empty_file_rejected(client):
    """Uploading an empty 0-byte file must return HTTP 400."""
    res = client.post(
        "/api/v1/vision/predict",
        files={"file": ("empty.jpg", b"", "image/jpeg")}
    )
    assert res.status_code == 400
    assert "empty" in res.json()["detail"].lower()


def test_image_upload_unsupported_media_type_rejected(client):
    """Uploading shell script or non-image MIME type must return HTTP 415."""
    res = client.post(
        "/api/v1/vision/predict",
        files={"file": ("exploit.sh", b"#!/bin/sh\necho hack", "application/x-sh")}
    )
    assert res.status_code == 415
    assert "unsupported file mime type" in res.json()["detail"].lower()


def test_image_upload_corrupt_bytes_rejected(client):
    """Uploading corrupted image payload with image/jpeg header must fail decode (HTTP 422)."""
    corrupt_bytes = b"NOT_A_VALID_JPEG_HEADER_RANDOM_GARBAGE_BYTES_12345"
    res = client.post(
        "/api/v1/vision/predict",
        files={"file": ("corrupt.jpg", corrupt_bytes, "image/jpeg")}
    )
    assert res.status_code == 422
    assert "corrupt or malformed image" in res.json()["detail"].lower()


def test_root_redirects_to_dashboard(client):
    """GET / must redirect to /dashboard."""
    res = client.get("/", follow_redirects=False)
    assert res.status_code in (302, 307)
    assert res.headers["location"] == "/dashboard"
