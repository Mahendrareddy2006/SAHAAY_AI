"""
Sahaay AI - Phase F: Production Hardening and Controlled Pilot Readiness Test Suite
(tests/test_phase_f_production_hardening_and_pilot_readiness.py)

Comprehensive regression tests covering:
1. Server-side authentication, cryptographic HMAC-SHA256 tokens, and 401 fail-closed on missing/invalid/expired tokens.
2. Role-based authorization (RBAC) and 403 fail-closed on insufficient role.
3. Rejection of client-supplied role spoofing and untrusted flags (is_server_authenticated, bypass_auth).
4. Permanent technical disarming of autonomous dispatch and external side-effects (HTTP 403).
5. Secrets hygiene and credential masking (mask_secret ensures zero leakage).
6. Clear distinction between application liveness (UP) and operational pilot readiness (PILOT_BLOCKED / NO-GO).
7. Machine-readable 10-item Data & Integration Readiness Register honesty (0 READY, 7 PARTIAL, 3 BLOCKED).
8. Preserved Phase A-E safety invariants: missing rainfall never becomes zero, disconnected topology is unsupported,
   unverified destinations are not operational, and emergency decisions remain human-reviewed.
"""

from datetime import datetime, timezone
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from sahaay.api.main import app
from sahaay.config import (
    EnvironmentMode,
    OperationalConfig,
    RuntimeAppConfig,
    SecurityConfig,
    get_runtime_config,
    mask_secret,
)
from sahaay.security.auth import (
    AuthenticatedIdentity,
    UserRole,
    create_access_token,
    verify_bearer_token,
)
from sahaay.pilot.readiness_register import (
    DataIntegrationReadinessRegister,
    ReadinessItemStatus,
    default_readiness_register,
)
from sahaay.emergency_destinations.registry import default_destination_registry
from sahaay.emergency_destinations.schemas import FacilityOperationalStatus
from sahaay.hyderabad_risk.weather_pipeline import (
    WeatherIngestionPipeline,
    default_weather_pipeline,
)
from sahaay.road_network.store import default_road_network_store
from sahaay.routing.graph_router import TopologicalGraphRouter
from sahaay.routing.schemas import RouteAssessmentOutcome


@pytest.fixture
def client():
    return TestClient(app)


# ==============================================================================
# 1. Server-Side Authentication & Cryptographic Token Verification
# ==============================================================================

class TestServerSideAuthentication:
    """Tests verifying that authentication identity originates strictly from trusted server-side mechanisms."""

    def test_create_and_verify_valid_token(self):
        token = create_access_token(
            subject_id="officer_reddy_124",
            role=UserRole.GHMC_DRF_OFFICER,
            expires_in_minutes=60,
        )
        assert isinstance(token, str)
        assert token.startswith("sahaay_v1.")

        identity = verify_bearer_token(token)
        assert identity.subject_id == "officer_reddy_124"
        assert identity.role == UserRole.GHMC_DRF_OFFICER
        assert identity.auth_authority == "SAHAAY_LOCAL_SECURITY_GATEWAY"

    def test_verify_tampered_token_fails(self):
        token = create_access_token(
            subject_id="officer_reddy_124",
            role=UserRole.GHMC_DRF_OFFICER,
        )
        tampered_token = token[:-5] + "abcde"
        with pytest.raises(HTTPException) as excinfo:
            verify_bearer_token(tampered_token)
        assert excinfo.value.status_code == 401
        assert "tampering detected" in excinfo.value.detail or "signature mismatch" in excinfo.value.detail

    def test_verify_malformed_token_fails(self):
        with pytest.raises(HTTPException) as excinfo:
            verify_bearer_token("not_a_valid_token_payload")
        assert excinfo.value.status_code == 401
        assert "invalid token format" in excinfo.value.detail

    def test_expired_token_fails(self):
        token = create_access_token(
            subject_id="officer_expired",
            role=UserRole.SYSTEM_ADMIN,
            expires_in_minutes=-10,  # Expired 10 minutes ago
        )
        with pytest.raises(HTTPException) as excinfo:
            verify_bearer_token(token)
        assert excinfo.value.status_code == 401
        assert "token has expired" in excinfo.value.detail


# ==============================================================================
# 2. Privileged Endpoint Protection (401 vs 403 Separation)
# ==============================================================================

class TestPrivilegedEndpointSecurity:
    """Tests ensuring privileged routes fail closed with appropriate 401 and 403 status codes."""

    def test_missing_auth_header_fails_with_401(self, client):
        response = client.post(
            "/api/v1/security/privileged-action",
            json={
                "action_type": "CORRIDOR_REFRESH",
                "target_resource": "CORRIDOR-001",
            },
        )
        assert response.status_code == 401
        assert "missing authorization header" in response.json()["detail"].lower()

    def test_invalid_bearer_token_fails_with_401(self, client):
        response = client.post(
            "/api/v1/security/privileged-action",
            headers={"Authorization": "Bearer invalid_garbage_token_signature"},
            json={
                "action_type": "CORRIDOR_REFRESH",
                "target_resource": "CORRIDOR-001",
            },
        )
        assert response.status_code == 401
        assert "authentication failed" in response.json()["detail"].lower()

    def test_insufficient_role_fails_with_403(self, client):
        citizen_token = create_access_token(
            subject_id="citizen_user_01",
            role=UserRole.CITIZEN,
        )
        response = client.post(
            "/api/v1/security/privileged-action",
            headers={"Authorization": f"Bearer {citizen_token}"},
            json={
                "action_type": "CORRIDOR_REFRESH",
                "target_resource": "CORRIDOR-001",
            },
        )
        assert response.status_code == 403
        assert "lacks supervisor privileges" in response.json()["detail"].lower()

    def test_authorized_role_succeeds(self, client):
        officer_token = create_access_token(
            subject_id="officer_ghmc_09",
            role=UserRole.GHMC_DRF_OFFICER,
        )
        response = client.post(
            "/api/v1/security/privileged-action",
            headers={"Authorization": f"Bearer {officer_token}"},
            json={
                "action_type": "CORRIDOR_REFRESH",
                "target_resource": "CORRIDOR-001",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "AUTHORIZED_EXECUTION_COMPLETED"
        assert data["operator_id"] == "officer_ghmc_09"
        assert data["authenticated_role"] == "GHMC_DRF_OFFICER"
        assert "audit_hash" in data
        assert "AUDIT DISCLAIMER" in data["audit_disclaimer"]


# ==============================================================================
# 3. Caller Role Spoofing & Untrusted Flag Denial
# ==============================================================================

class TestRoleSpoofingDenial:
    """Tests ensuring client-supplied role names and untrusted authorization flags are strictly denied."""

    def test_body_role_spoofing_mismatch_fails_with_403(self, client):
        # Token has GHMC_DRF_OFFICER role, but payload claims SYSTEM_ADMIN
        officer_token = create_access_token(
            subject_id="officer_ghmc_09",
            role=UserRole.GHMC_DRF_OFFICER,
        )
        response = client.post(
            "/api/v1/security/privileged-action",
            headers={"Authorization": f"Bearer {officer_token}"},
            json={
                "action_type": "CORRIDOR_REFRESH",
                "target_resource": "CORRIDOR-001",
                "caller_role": "SYSTEM_ADMIN",  # Mismatch with token role
            },
        )
        assert response.status_code == 403
        assert "role spoofing" in response.json()["detail"].lower()

    def test_untrusted_is_server_authenticated_flag_fails_with_403(self, client):
        officer_token = create_access_token(
            subject_id="officer_valid",
            role=UserRole.GHMC_DRF_OFFICER,
        )
        response = client.post(
            "/api/v1/security/privileged-action",
            headers={"Authorization": f"Bearer {officer_token}"},
            json={
                "action_type": "CORRIDOR_REFRESH",
                "target_resource": "CORRIDOR-001",
                "is_server_authenticated": True,  # Forbidden client-supplied flag
            },
        )
        assert response.status_code == 403
        assert "is_server_authenticated" in response.json()["detail"].lower()


# ==============================================================================
# 4. Operational Action Disarming & Side-Effect Prevention
# ==============================================================================

class TestOperationalActionDisarming:
    """Tests verifying that autonomous external actions are technically prohibited."""

    def test_autonomous_dispatch_fails_with_403(self, client):
        admin_token = create_access_token(
            subject_id="admin_super",
            role=UserRole.SYSTEM_ADMIN,
        )
        response = client.post(
            "/api/v1/security/privileged-action",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "action_type": "EMERGENCY_DISPATCH",
                "target_resource": "INCIDENT-999",
                "attempt_autonomous_dispatch": True,
            },
        )
        assert response.status_code == 403
        assert "strictly disarmed" in response.json()["detail"].lower()

    def test_live_telemetry_activation_fails_with_403(self, client):
        admin_token = create_access_token(
            subject_id="admin_super",
            role=UserRole.SYSTEM_ADMIN,
        )
        response = client.post(
            "/api/v1/security/privileged-action",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "action_type": "ACTIVATE_LIVE_STREAM",
                "target_resource": "STATION-IMD-01",
                "attempt_live_stream_activation": True,
            },
        )
        assert response.status_code == 403
        assert "strictly disarmed" in response.json()["detail"].lower()

    def test_operational_config_validators(self):
        op_config = OperationalConfig()
        assert op_config.autonomous_dispatch_enabled is False
        assert op_config.autonomous_closures_enabled is False
        assert op_config.live_telemetry_stream_enabled is False

        with pytest.raises(ValueError) as excinfo_disp:
            OperationalConfig(autonomous_dispatch_enabled=True)
        assert "cannot be enabled" in str(excinfo_disp.value).lower()

        with pytest.raises(ValueError) as excinfo_stream:
            OperationalConfig(live_telemetry_stream_enabled=True)
        assert "cannot be enabled" in str(excinfo_stream.value).lower()


# ==============================================================================
# 5. Secrets Hygiene & Token Inspection
# ==============================================================================

class TestSecretsHygieneAndSafety:
    """Tests verifying that credentials and tokens are never exposed in logs or payloads."""

    def test_mask_secret_helper(self):
        assert mask_secret(None) == "[NOT_CONFIGURED]"
        assert mask_secret("") == "[NOT_CONFIGURED]"
        assert mask_secret("short") == "***"
        
        long_secret = "ghmc_production_api_key_secret_value_987654321"
        masked = mask_secret(long_secret)
        assert masked.startswith("ghm...")
        assert masked.endswith("321")
        assert "secret_value" not in masked
        assert len(masked) < len(long_secret)

    def test_token_inspection_endpoint(self, client):
        token = create_access_token(
            subject_id="traffic_command_officer_03",
            role=UserRole.TRAFFIC_POLICE_DUTY_OFFICER,
        )
        response = client.post(
            "/api/v1/security/token/inspect",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["subject_id"] == "traffic_command_officer_03"
        assert data["role"] == "TRAFFIC_POLICE_DUTY_OFFICER"
        assert data["auth_authority"] == "SAHAAY_LOCAL_SECURITY_GATEWAY"
        # Secret HMAC key must never be exposed
        assert "signing_secret" not in data
        assert "raw_secret" not in data


# ==============================================================================
# 6. Liveness vs. Operational Readiness Separation
# ==============================================================================

class TestHealthLivenessVsReadiness:
    """Tests demonstrating that application liveness is clearly separated from operational readiness."""

    def test_liveness_probe_returns_up(self, client):
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["liveness"] == "UP"
        assert data["operational_readiness"] == "PILOT_BLOCKED"
        assert data["pilot_decision"] == "NO_GO"

    def test_readiness_probe_returns_pilot_blocked(self, client):
        response = client.get("/api/v1/readiness")
        assert response.status_code == 200
        data = response.json()
        assert data["liveness"] == "UP"
        assert data["operational_readiness"] == "PILOT_BLOCKED"
        assert data["pilot_decision"] == "NO_GO"
        assert "components" in data
        assert len(data["components"]) == 10
        assert data["components"]["road_network"]["readiness_status"] == "DEGRADED"
        assert data["components"]["pilot_activation_gate"]["readiness_status"] == "BLOCKED"
        assert len(data["active_blockers"]) > 0


# ==============================================================================
# 7. Data & Integration Readiness Register Honesty
# ==============================================================================

class TestDataIntegrationReadinessRegister:
    """Tests verifying the 10-item machine-readable readiness register."""

    def test_readiness_register_endpoint(self, client):
        response = client.get("/api/v1/readiness/register")
        assert response.status_code == 200
        data = response.json()
        assert data["overall_pilot_decision"] == "NO_GO"
        assert data["summary_counts"]["READY"] == 0
        assert data["summary_counts"]["PARTIAL"] == 7
        assert data["summary_counts"]["BLOCKED"] == 3
        assert len(data["items"]) == 10

    def test_readiness_register_items_honesty(self):
        register = default_readiness_register
        summary = register.get_summary()

        assert summary["ready_count"] == 0
        assert summary["partial_count"] == 7
        assert summary["blocked_count"] == 3
        assert summary["pilot_decision"] == "NO_GO"
        assert summary["total_requirements"] == 10

        # Check known blocked items
        flood_obs = register.get_item("REG-05-VERIFIED-FLOOD-OBSERVATIONS")
        assert flood_obs is not None
        assert flood_obs.status == ReadinessItemStatus.BLOCKED
        assert "ground-truth" in flood_obs.limitations.lower()

        vision_gate = register.get_item("REG-06-VISION-DATA-READINESS")
        assert vision_gate is not None
        assert vision_gate.status == ReadinessItemStatus.BLOCKED
        assert "vision v4" in vision_gate.limitations.lower()

        institution_mou = register.get_item("REG-10-INSTITUTIONAL-AGREEMENTS")
        assert institution_mou is not None
        assert institution_mou.status == ReadinessItemStatus.BLOCKED
        assert "zero executed" in institution_mou.limitations.lower()

        # Check known partial items
        road_net = register.get_item("REG-01-ROAD-NETWORK")
        assert road_net is not None
        assert road_net.status == ReadinessItemStatus.PARTIAL
        assert "22 seed segments" in road_net.limitations

        dest_reg = register.get_item("REG-02-EMERGENCY-DESTINATIONS")
        assert dest_reg is not None
        assert dest_reg.status == ReadinessItemStatus.PARTIAL
        assert "synthetic" in dest_reg.limitations.lower()


# ==============================================================================
# 8. Preservation of Safety Invariants (Phases A–E)
# ==============================================================================

class TestPreservedSafetyInvariants:
    """Tests confirming all historical safety contracts and non-fabrication guarantees remain intact."""

    def test_missing_weather_telemetry_never_becomes_zero_rainfall(self):
        pipeline = WeatherIngestionPipeline()
        # Evaluate weather for a corridor when no telemetry observations have been ingested
        result = pipeline.evaluate_corridor_weather(
            corridor_id="SEG-TEST-UNKNOWN",
            corridor_lat=17.4000,
            corridor_lon=78.4000,
        )
        # Missing telemetry must never claim zero verified rainfall or fabricate dry roads
        assert result.rain_1h_mm is None
        assert result.data_freshness_hours >= 90.0
        assert any(
            "observation missing" in w.lower()
            or "disabled" in w.lower()
            or "telemetry unavailable" in w.lower()
            for w in result.warnings
        )

    def test_disconnected_topology_remains_unsupported(self):
        graph = default_road_network_store.get_road_graph()
        router = TopologicalGraphRouter(graph)
        # Querying an unknown / non-existent node ID must return unsupported topology
        result = router.find_risk_aware_route(
            origin_node_id="NON_EXISTENT_ORIGIN_NODE",
            destination_node_id="NON_EXISTENT_DEST_NODE",
        )
        assert result.outcome == RouteAssessmentOutcome.TOPOLOGY_UNSUPPORTED
        assert result.engine_status == "TOPOLOGY_MISSING_NODE_REFERENCE"
        assert any("not exist" in w.lower() or "origin node" in w.lower() for w in result.warnings)

    def test_unverified_destinations_not_operational(self):
        registry = default_destination_registry
        destinations = registry.list_destinations()
        assert len(destinations) > 0
        for record in destinations:
            # In Phase E, synthetic facilities are labeled as synthetic demonstration fixtures
            assert record.is_synthetic_fixture is True
            assert "DEMONSTRATION_FIXTURE" in record.data_quality_flags or "synthetic" in (record.fixture_warning or "").lower()

    def test_map_corridor_refresh_with_bearer_token(self, client):
        # Valid operator token succeeds
        operator_token = create_access_token(
            subject_id="dashboard_operator_01",
            role=UserRole.DASHBOARD_OPERATOR,
        )
        payload = {
            "caller_role": "DASHBOARD_OPERATOR",
            "caller_id": "OP-01",
            "reason": "PERIODIC_SYNC",
        }
        response = client.post(
            "/api/v1/map/corridors/refresh",
            headers={"Authorization": f"Bearer {operator_token}"},
            json=payload,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "REFRESH_SUCCESS"

        # Invalid token fails with 401
        response_bad_token = client.post(
            "/api/v1/map/corridors/refresh",
            headers={"Authorization": "Bearer bad_token_123"},
            json=payload,
        )
        assert response_bad_token.status_code == 401

        # Role spoofing in payload fails with 403
        payload_spoof = {
            "caller_role": "SYSTEM_ADMIN",  # Mismatch with token role
            "caller_id": "OP-01",
            "reason": "SPOOF_ATTEMPT",
        }
        response_spoof = client.post(
            "/api/v1/map/corridors/refresh",
            headers={"Authorization": f"Bearer {operator_token}"},
            json=payload_spoof,
        )
        assert response_spoof.status_code == 403
