"""
Sahaay AI - Flood Vision Production Inference Service
Encapsulates model loading, validation, preprocessing, and prediction generation.
"""

import os
import io
import time
import uuid
from typing import Dict, Any, Union, Optional
from PIL import Image
import torch

from sahaay.vision.model import create_flood_classifier
from sahaay.vision.transforms import get_eval_transforms
from sahaay.config import (
    DEFAULT_CHECKPOINT_PATH,
    DEFAULT_MODEL_NAME,
    DEFAULT_MODEL_VERSION,
    LABEL_MAP
)

class FloodVisionInference:
    """
    Thread-safe, production-ready inference service for Flood Vision AI.
    Loads model checkpoint once and manages compute lifecycle.
    """
    def __init__(
        self,
        checkpoint_path: Optional[str] = None,
        device_name: str = "auto",
        confidence_threshold: float = 0.65
    ):
        self.checkpoint_path = checkpoint_path or str(DEFAULT_CHECKPOINT_PATH)
        self.confidence_threshold = confidence_threshold
        
        if device_name == "auto":
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(device_name)
            
        self.transform = get_eval_transforms(224)
        self._load_model()
        
    def _load_model(self):
        if not os.path.exists(self.checkpoint_path):
            raise FileNotFoundError(
                f"Model checkpoint not found at: {self.checkpoint_path}. "
                "Ensure baseline model training has been executed."
            )
            
        checkpoint = torch.load(self.checkpoint_path, map_location=self.device)
        self.model_name = checkpoint.get("model_name", DEFAULT_MODEL_NAME)
        self.model_version = checkpoint.get("model_version", DEFAULT_MODEL_VERSION)
        
        self.model = create_flood_classifier(
            model_name=self.model_name,
            num_classes=2,
            pretrained=False
        )
        self.model.load_state_dict(checkpoint["model_state_dict"])
        self.model.to(self.device)
        self.model.eval()
        print(f"Loaded {self.model_name} (v{self.model_version}) checkpoint on {self.device}")
        
    def validate_and_decode_image(self, image_input: Union[bytes, io.BytesIO, Image.Image]) -> Image.Image:
        """
        Validates image payload integrity, checks against corruptions, and ensures RGB format.
        """
        if isinstance(image_input, Image.Image):
            image = image_input
        elif isinstance(image_input, (bytes, bytearray)):
            if len(image_input) == 0:
                raise ValueError("Image byte payload is empty.")
            if len(image_input) > 15 * 1024 * 1024:
                raise ValueError("Image file exceeds maximum allowable size (15 MB).")
            try:
                image = Image.open(io.BytesIO(image_input))
            except Exception as e:
                raise ValueError(f"Failed to decode image from bytes: {e}")
        elif isinstance(image_input, io.BytesIO):
            try:
                image = Image.open(image_input)
            except Exception as e:
                raise ValueError(f"Failed to decode image from stream: {e}")
        else:
            raise TypeError(f"Unsupported image input type: {type(image_input)}")
            
        try:
            image.verify()
        except Exception as e:
            raise ValueError(f"Corrupt or malformed image: {e}")
            
        # Re-open after verify() because verify() invalidates the image pointer
        if isinstance(image_input, (bytes, bytearray)):
            image = Image.open(io.BytesIO(image_input))
        elif isinstance(image_input, io.BytesIO):
            image_input.seek(0)
            image = Image.open(image_input)
            
        return image.convert("RGB")
        
    def predict(
        self,
        image_input: Union[bytes, io.BytesIO, Image.Image],
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        report_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generates calibrated flood prediction from image.
        """
        t0 = time.time()
        prediction_id = f"vis_{uuid.uuid4().hex[:12]}"
        
        # 1. Validation and decoding
        image_rgb = self.validate_and_decode_image(image_input)
        
        # 2. Preprocessing
        tensor = self.transform(image_rgb).unsqueeze(0).to(self.device)
        
        # 3. Model forward pass
        with torch.no_grad():
            logits = self.model(tensor)
            probs = torch.softmax(logits, dim=1).squeeze(0).cpu().numpy()
            
        latency_ms = round((time.time() - t0) * 1000.0, 2)
        
        score_not_flooded = float(probs[0])
        score_flooded = float(probs[1])
        
        pred_idx = int(torch.argmax(logits, dim=1).item())
        predicted_class = LABEL_MAP[pred_idx]
        confidence = float(probs[pred_idx])
        
        is_ambiguous = confidence < self.confidence_threshold
        
        warnings = [
            "Experimental prototype: Visual evidence only. Does not constitute official emergency advice.",
            "A negative prediction does not guarantee road passability or absence of flood hazard."
        ]
        if is_ambiguous:
            warnings.append(
                f"Prediction confidence ({confidence:.2f}) is below threshold ({self.confidence_threshold:.2f}). "
                "Manual field verification recommended."
            )
            
        return {
            "prediction_id": prediction_id,
            "predicted_class": predicted_class,
            "confidence": round(confidence, 4),
            "class_scores": {
                "not_flooded": round(score_not_flooded, 4),
                "flooded": round(score_flooded, 4)
            },
            "is_ambiguous": is_ambiguous,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "device": str(self.device),
            "inference_latency_ms": latency_ms,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "report_id": report_id,
            "location": {
                "latitude": latitude,
                "longitude": longitude
            } if latitude is not None and longitude is not None else None,
            "warnings": warnings
        }
