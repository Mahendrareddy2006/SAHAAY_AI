"""
Sahaay AI Security Package - Phase F
"""

from .auth import (
    UserRole,
    RESPONDER_ROLES,
    SUPERVISOR_ROLES,
    ADMIN_ROLES,
    AuthenticatedIdentity,
    create_access_token,
    verify_bearer_token,
    get_current_authenticated_identity,
    require_role,
    validate_no_client_role_spoofing,
    fail_closed_operational_action,
)

__all__ = [
    "UserRole",
    "RESPONDER_ROLES",
    "SUPERVISOR_ROLES",
    "ADMIN_ROLES",
    "AuthenticatedIdentity",
    "create_access_token",
    "verify_bearer_token",
    "get_current_authenticated_identity",
    "require_role",
    "validate_no_client_role_spoofing",
    "fail_closed_operational_action",
]
