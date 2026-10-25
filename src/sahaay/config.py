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
