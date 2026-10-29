"""
Sahaay AI - Phase F: Security, Authentication & Role-Based Authorization
(src/sahaay/security/auth.py)

Implements trusted server-side identity verification, role-based access control,
prohibition of client-side role spoofing, and fail-closed operational boundaries.
"""

from datetime import datetime, timezone, timedelta
from enum import Enum
import hashlib
import hmac
import json
import logging
import base64
from typing import Any, Callable, Dict, List, Optional, Set
from fastapi import Header, HTTPException, status
from pydantic import BaseModel, Field

from sahaay.config import get_runtime_config, mask_secret

logger = logging.getLogger(__name__)

# Fallback internal secret for deterministic test verification when env var is unset
INTERNAL_DEV_AUTH_SECRET = "sahaay_dev_secret_auth_key_do_not_use_in_prod_2026"


class UserRole(str, Enum):
    """
    Validated institutional and operational user roles.
    Authority is granted solely by trusted server-side identity assertion.
    """
    SYSTEM_ADMIN = "SYSTEM_ADMIN"
    GHMC_DRF_OFFICER = "GHMC_DRF_OFFICER"
    TRAFFIC_POLICE_DUTY_OFFICER = "TRAFFIC_POLICE_DUTY_OFFICER"
    FIELD_SAFETY_LEAD = "FIELD_SAFETY_LEAD"
    MUNICIPAL_DISPATCHER = "MUNICIPAL_DISPATCHER"
    DASHBOARD_OPERATOR = "DASHBOARD_OPERATOR"
    OBSERVER = "OBSERVER"
    CITIZEN = "CITIZEN"


# Sets of privileged roles for specific operational scopes
RESPONDER_ROLES: Set[UserRole] = {
    UserRole.SYSTEM_ADMIN,
    UserRole.GHMC_DRF_OFFICER,
    UserRole.TRAFFIC_POLICE_DUTY_OFFICER,
    UserRole.FIELD_SAFETY_LEAD,
    UserRole.MUNICIPAL_DISPATCHER,
    UserRole.DASHBOARD_OPERATOR,
}

SUPERVISOR_ROLES: Set[UserRole] = {
    UserRole.SYSTEM_ADMIN,
    UserRole.GHMC_DRF_OFFICER,
    UserRole.TRAFFIC_POLICE_DUTY_OFFICER,
    UserRole.FIELD_SAFETY_LEAD,
}

ADMIN_ROLES: Set[UserRole] = {
    UserRole.SYSTEM_ADMIN,
}


class AuthenticatedIdentity(BaseModel):
    """
    Verified server-side security context.
    Established exclusively via trusted token verification; never client-asserted.
    """
    subject_id: str = Field(..., description="Unique immutable identity identifier")
    role: UserRole = Field(..., description="Server-validated authorized role")
    issued_at_utc: str = Field(..., description="ISO-8601 UTC timestamp of token issuance")
    token_id: str = Field(..., description="Unique nonce token identifier")
    is_institutional_credential: bool = Field(False, description="True only if backed by official institutional IdP")
    auth_authority: str = Field("SAHAAY_LOCAL_SECURITY_GATEWAY", description="Issuing security authority")


import os

def _get_signing_key() -> bytes:
    """Retrieves server signing secret safely without exposing in logs."""
    cfg = get_runtime_config()
    secret = cfg.security.secret_key or INTERNAL_DEV_AUTH_SECRET
    return secret.encode("utf-8")


def _get_verification_keys() -> List[bytes]:
    """
    Returns candidate signing keys for token verification, supporting zero-downtime key rotation.
    Checks primary active signing key first, followed by previous/standby keys.
    """
    keys = [_get_signing_key()]
    prev_secret = os.getenv("SAHAAY_PREVIOUS_SECRET_KEY")
    if prev_secret and prev_secret.strip():
        keys.append(prev_secret.strip().encode("utf-8"))
    return keys


def create_access_token(
    subject_id: str,
    role: UserRole,
    expires_in_minutes: int = 60,
    is_institutional: bool = False,
    auth_authority: str = "SAHAAY_LOCAL_SECURITY_GATEWAY",
) -> str:
    """
    Generates a cryptographically signed server-side Bearer token.
    Format: sahaay_v1.<payload_b64>.<hmac_sha256_b64>
    """
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=expires_in_minutes)
    token_id = hashlib.sha256(f"{subject_id}:{role.value}:{now.isoformat()}".encode()).hexdigest()[:16]

    payload = {
        "sub": subject_id,
        "role": role.value,
        "iat": now.isoformat().replace("+00:00", "Z"),
        "exp": exp.isoformat().replace("+00:00", "Z"),
        "jti": token_id,
        "inst": is_institutional,
        "iss": auth_authority,
    }

    payload_json = json.dumps(payload, sort_keys=True)
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode("utf-8")).decode("utf-8").rstrip("=")

    signature = hmac.new(_get_signing_key(), payload_b64.encode("utf-8"), hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(signature).decode("utf-8").rstrip("=")

    return f"sahaay_v1.{payload_b64}.{sig_b64}"


def verify_bearer_token(raw_token: str) -> AuthenticatedIdentity:
    """
    Validates a cryptographic Bearer token and returns the trusted AuthenticatedIdentity.
    Raises HTTPException(401) on any failure (tampering, expiration, or malformation).
    Supports key rotation by checking standby keys if the primary signature fails.
    """
    if not raw_token or not isinstance(raw_token, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed: empty or non-string token provided.",
        )

    parts = raw_token.strip().split(".")
    if len(parts) != 3 or parts[0] != "sahaay_v1":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed: invalid token format or unsupported token version.",
        )

    _, payload_b64, sig_b64 = parts

    # Verify HMAC signature against active primary key and standby rotated keys
    signature_valid = False
    for candidate_key in _get_verification_keys():
        expected_sig = hmac.new(candidate_key, payload_b64.encode("utf-8"), hashlib.sha256).digest()
        expected_sig_b64 = base64.urlsafe_b64encode(expected_sig).decode("utf-8").rstrip("=")
        if hmac.compare_digest(sig_b64, expected_sig_b64):
            signature_valid = True
            break

    if not signature_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed: cryptographic signature mismatch or token tampering detected.",
        )

    # Decode and parse payload
    try:
        # Re-add padding
        padded_b64 = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload_bytes = base64.urlsafe_b64decode(padded_b64)
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: token payload corrupted: {str(e)}",
        )

    # Validate expiration
    exp_iso = payload.get("exp")
    if exp_iso:
        try:
            exp_dt = datetime.fromisoformat(exp_iso.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) > exp_dt:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication failed: authentication token has expired.",
                )
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication failed: invalid expiration timestamp format in token.",
            )

    try:
        role_enum = UserRole(payload["role"])
    except (KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed: unrecognized or missing role claim in token.",
        )

    return AuthenticatedIdentity(
        subject_id=payload["sub"],
        role=role_enum,
        issued_at_utc=payload["iat"],
        token_id=payload.get("jti", "UNKNOWN"),
        is_institutional_credential=bool(payload.get("inst", False)),
        auth_authority=payload.get("iss", "SAHAAY_LOCAL_SECURITY_GATEWAY"),
    )


def get_current_authenticated_identity(
    authorization: Optional[str] = Header(None, description="Bearer token header")
) -> AuthenticatedIdentity:
    """
    FastAPI dependency extracting and verifying server-side Bearer authentication.
    Fails closed with HTTP 401 Unauthorized if header is missing or invalid.
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required: missing Authorization header with Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    parts = authorization.strip().split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed Authorization header: must use 'Bearer <token>' schema.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return verify_bearer_token(parts[1])


def require_role(allowed_roles: Set[UserRole]) -> Callable:
    """
    Factory creating a FastAPI dependency enforcing role-based authorization.
    Fails closed with HTTP 403 Forbidden if user lacks required role.
    """
    def _role_checker(
        identity: AuthenticatedIdentity = get_current_authenticated_identity
    ) -> AuthenticatedIdentity:
        if identity.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Forbidden: role '{identity.role.value}' lacks required permissions for this operation. "
                    f"Required one of: {[r.value for r in allowed_roles]}."
                ),
            )
        return identity
    return _role_checker


def validate_no_client_role_spoofing(
    identity: AuthenticatedIdentity,
    client_supplied_role: Optional[str],
) -> None:
    """
    Prohibits client-supplied request body or header parameters from overriding
    or spoofing server-verified identity.
    Fails closed with HTTP 403 Forbidden.
    """
    if client_supplied_role:
        client_clean = str(client_supplied_role).strip().upper()
        if client_clean != identity.role.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Security violation: client-supplied role '{client_supplied_role}' does not match "
                    f"authenticated server token role '{identity.role.value}'. Role spoofing is strictly rejected."
                ),
            )


def fail_closed_operational_action(action_name: str) -> None:
    """
    Guarantees that dangerous operational side-effects (dispatching responders,
    closing roads, activating live streams) cannot be triggered autonomously.
    Fails closed with HTTP 403 Forbidden.
    """
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=(
            f"SECURITY GATE: Operational action '{action_name}' is strictly disarmed. "
            "Autonomous physical actions, external alerts, and live provider activations "
            "are prohibited pending formal institutional approval and deployment authorization."
        ),
    )
