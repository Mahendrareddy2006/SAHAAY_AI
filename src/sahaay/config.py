"""
Sahaay AI - Configuration Settings
"""
import os
from pathlib import Path
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
MODELS_DIR = BASE_DIR / "models"
DOCS_DIR = BASE_DIR / "docs"

CLASS_NAMES = ["not_flooded", "flooded"]
LABEL_MAP = {0: "not_flooded", 1: "flooded"}
REV_LABEL_MAP = {"not_flooded": 0, "flooded": 1}

DEFAULT_MODEL_NAME = "mobilenet_v3_small"
DEFAULT_MODEL_VERSION = "1.0.0"
DEFAULT_CHECKPOINT_PATH = MODELS_DIR / "vision" / "best_model.pt"

class VisionModelConfig(BaseModel):
    model_name: str = DEFAULT_MODEL_NAME
    model_version: str = DEFAULT_MODEL_VERSION
    num_classes: int = 2
    image_size: int = 224
    batch_size: int = 32
    learning_rate: float = 3e-4
    weight_decay: float = 1e-4
    epochs: int = 5
    random_seed: int = 42
    checkpoint_dir: str = str(MODELS_DIR / "vision")
    confidence_threshold: float = 0.65


# ==============================================================================
# Phase F: Production Hardening, Environment Separation & Secrets Hygiene
# ==============================================================================

from enum import Enum
from typing import Optional
from pydantic import Field, field_validator


class EnvironmentMode(str, Enum):
    """Execution environment classification."""
    DEVELOPMENT = "DEVELOPMENT"
    TESTING = "TESTING"
    STAGING = "STAGING"
    PRODUCTION = "PRODUCTION"


def mask_secret(secret_value: Optional[str]) -> str:
    """
    Safely masks sensitive credentials, tokens, and API keys for audit logs and error messages.
    Never prints or logs raw credentials.
    """
    if not secret_value:
        return "[NOT_CONFIGURED]"
    val = str(secret_value).strip()
    if len(val) <= 6:
        return "***"
    return f"{val[:3]}...{val[-3:]}"


class SecurityConfig(BaseModel):
    """
    Server-side security configuration.
    Credentials must originate from trusted environment variables, never hardcoded.
    """
    secret_key: Optional[str] = Field(
        default_factory=lambda: os.getenv("SAHAAY_AUTH_SECRET_KEY")
    )
    token_issuer: str = "sahaay.ai.security"
    token_expiry_minutes: int = 60
    allow_anonymous_read: bool = True
    enforce_strict_auth: bool = False

    def masked_summary(self) -> dict:
        return {
            "secret_key_configured": bool(self.secret_key),
            "secret_key_masked": mask_secret(self.secret_key),
            "token_issuer": self.token_issuer,
            "token_expiry_minutes": self.token_expiry_minutes,
            "allow_anonymous_read": self.allow_anonymous_read,
            "enforce_strict_auth": self.enforce_strict_auth,
        }


class OperationalConfig(BaseModel):
    """
    Operational safety switches and runtime boundaries.
    Autonomous external dispatch and road closures are strictly barred from activation.
    """
    environment: EnvironmentMode = Field(
        default_factory=lambda: EnvironmentMode(os.getenv("SAHAAY_ENV", "TESTING").upper())
    )
    autonomous_dispatch_enabled: bool = False
    autonomous_closures_enabled: bool = False
    live_telemetry_stream_enabled: bool = False
    require_human_authorization_for_emergency_resolution: bool = True

    @field_validator("autonomous_dispatch_enabled", "autonomous_closures_enabled", "live_telemetry_stream_enabled")
    @classmethod
    def validate_dangerous_settings(cls, v: bool, info) -> bool:
        if v is True:
            raise ValueError(
                f"Operational safety invariant violation: '{info.field_name}' CANNOT be enabled. "
                "Autonomous public actions and live telemetry activation are strictly disarmed."
            )
        return False


class RuntimeAppConfig(BaseModel):
    """Unified application settings container."""
    vision: VisionModelConfig = Field(default_factory=VisionModelConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    operational: OperationalConfig = Field(default_factory=OperationalConfig)


# Global default configuration instance
app_config = RuntimeAppConfig()

def get_runtime_config() -> RuntimeAppConfig:
    """Returns singleton runtime application configuration."""
    global app_config
    return app_config

