"""
Sahaay AI - Flood Vision Production Inference Service
Encapsulates model loading, validation, preprocessing, and prediction generation.
"""

import os
import io
import time
import uuid
from typing import Dict, Any, Union, Optional, Tuple, List
from PIL import Image
import numpy as np
import torch

from sahaay.vision.model import create_flood_classifier
from sahaay.vision.transforms import get_eval_transforms
from sahaay.vision.policy import map_vision_probabilities_to_decision
from sahaay.config import (
    DEFAULT_CHECKPOINT_PATH,
    DEFAULT_MODEL_NAME,
    DEFAULT_MODEL_VERSION,
    LABEL_MAP
)

class FloodVisionInference:
    """
    Thread-safe, production-ready inference service for Flood Vision AI.
    Features:
    - Automatic loading of best available checkpoint (V3 Monsoon > V3 Clean > V2 > V1)
    - Image Quality Gate checking blur variance, extreme darkness, washed out whiteout, and resolution
    - Rejection of out-of-distribution or degraded imagery with explicit 'inconclusive' verdict
    - Advisory policy safeguards preventing autonomous road action on unvalidated predictions
    """
    def __init__(
        self,
        checkpoint_path: Optional[str] = None,
        device_name: str = "auto",
        confidence_threshold: float = 0.65
    ):
        if checkpoint_path is None:
            v3_monsoon = os.path.join("models", "vision", "v3", "model_v3_monsoon.pt")
            v3_clean = os.path.join("models", "vision", "v3", "model_v3_clean.pt")
            v2_path = os.path.join("models", "vision", "v2", "model_v2.pt")
            if os.path.exists(v3_monsoon):
                self.checkpoint_path = v3_monsoon
            elif os.path.exists(v3_clean):
                self.checkpoint_path = v3_clean
            elif os.path.exists(v2_path):
                self.checkpoint_path = v2_path
            else:
                self.checkpoint_path = str(DEFAULT_CHECKPOINT_PATH)
        else:
            self.checkpoint_path = checkpoint_path

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
        if isinstance(checkpoint, dict) and "model_state_dict" in checkpoint:
            self.model_name = checkpoint.get("model_name", DEFAULT_MODEL_NAME)
            self.model_version = checkpoint.get("model_version", DEFAULT_MODEL_VERSION)
            state_dict = checkpoint["model_state_dict"]
        else:
            self.model_name = DEFAULT_MODEL_NAME
            self.model_version = "3.0.0-monsoon"
            state_dict = checkpoint
            
        self.model = create_flood_classifier(
            model_name=self.model_name,
            num_classes=2,
            pretrained=False
        )
        self.model.load_state_dict(state_dict)
        self.model.to(self.device)
        self.model.eval()
        print(f"Loaded {self.model_name} (v{self.model_version}) checkpoint from {self.checkpoint_path} on {self.device}")

    def evaluate_image_quality(self, image: Image.Image) -> Tuple[bool, List[str], Dict[str, Any]]:
        """
        Automated Image Quality Gate.
        Evaluates discrete Laplacian variance (blur), luminance distribution, dynamic range,
        and spatial dimensions to intercept degraded, out-of-distribution, or obscured images.
        """
        w, h = image.size
        gray = np.array(image.convert("L"), dtype=np.float32)
        
        # 1. Blur estimation via 3x3 discrete Laplacian operator
        if w >= 3 and h >= 3:
            lap = (
                gray[2:, 1:-1] + gray[:-2, 1:-1] +
                gray[1:-1, 2:] + gray[1:-1, :-2] -
                4.0 * gray[1:-1, 1:-1]
            )
            blur_variance = float(np.var(lap))
        else:
            blur_variance = 0.0

        mean_lum = float(np.mean(gray))
        std_lum = float(np.std(gray))

        metrics = {
            "blur_variance": round(blur_variance, 2),
            "mean_luminance": round(mean_lum, 2),
            "luminance_std": round(std_lum, 2),
            "dimensions": [w, h]
        }

        reasons = []
        # Insufficient resolution
        if w < 64 or h < 64:
            reasons.append(f"Image resolution ({w}x{h}) is below minimal discernment threshold (64x64).")
        # Pitch darkness or obscured camera
        if mean_lum < 10.0:
            reasons.append(f"Image is underexposed or near-pitch black (mean luminance: {mean_lum:.1f} < 10.0).")
        # Blown out overexposure / pure whiteout
        if mean_lum > 248.0 and std_lum < 8.0:
            reasons.append(f"Image is overexposed or washed out (mean luminance: {mean_lum:.1f} > 248.0).")
        # Severe lens blur / water spray obstruction on non-uniform scene
        if blur_variance < 15.0 and std_lum > 12.0:
            reasons.append(f"Image has severe motion smearing or lens condensation blur (blur variance: {blur_variance:.1f} < 15.0).")

        is_inconclusive = len(reasons) > 0
        return is_inconclusive, reasons, metrics
        
    def validate_and_decode_image(self, image_input: Union[bytes, io.BytesIO, Image.Image]) -> Image.Image:
        """
        Validates image payload integrity, checks against corruptions, and ensures RGB format.
        """
        if isinstance(image_input, Image.Image):
            return image_input.copy().convert("RGB")
            
        if isinstance(image_input, (bytes, bytearray)):
            if len(image_input) == 0:
                raise ValueError("Image byte payload is empty.")
            if len(image_input) > 15 * 1024 * 1024:
                raise ValueError("Image file exceeds maximum allowable size (15 MB).")
            try:
                Image.open(io.BytesIO(image_input)).verify()
                image = Image.open(io.BytesIO(image_input))
            except Exception as e:
                raise ValueError(f"Corrupt or malformed image: {e}")
        elif isinstance(image_input, io.BytesIO):
            try:
                Image.open(image_input).verify()
                image_input.seek(0)
                image = Image.open(image_input)
            except Exception as e:
                raise ValueError(f"Corrupt or malformed image: {e}")
        else:
            raise TypeError(f"Unsupported image input type: {type(image_input)}")
            
        return image.convert("RGB")
        
    def predict(
        self,
        image_input: Union[bytes, io.BytesIO, Image.Image],
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        report_id: Optional[str] = None,
        check_quality: bool = True
    ) -> Dict[str, Any]:
        """
        Generates calibrated flood prediction from image with automated quality gating.
        """
        t0 = time.time()
        prediction_id = f"vis_{uuid.uuid4().hex[:12]}"
        
        # 1. Validation and decoding
        image_rgb = self.validate_and_decode_image(image_input)
        
        # 2. Image Quality Gate Check
        is_inconclusive = False
        quality_reasons = []
        metrics = {}
        if check_quality:
            is_inconclusive, quality_reasons, metrics = self.evaluate_image_quality(image_rgb)

        if is_inconclusive:
            latency_ms = round((time.time() - t0) * 1000.0, 2)
            warnings = [
                "IMAGE QUALITY GATE TRIGGERED: Image is too degraded for reliable flood inference.",
                "Inconclusive imagery must NOT trigger autonomous road closure or emergency action.",
                "Manual field verification recommended."
            ]
            return {
                "prediction_id": prediction_id,
                "predicted_class": "inconclusive",
                "confidence": 0.0,
                "class_scores": {
                    "not_flooded": 0.5,
                    "flooded": 0.5
                },
                "is_ambiguous": True,
                "is_inconclusive": True,
                "inconclusive_reasons": quality_reasons,
                "quality_metrics": metrics,
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

        # 3. Preprocessing
        tensor = self.transform(image_rgb).unsqueeze(0).to(self.device)
        
        # 4. Model forward pass
        with torch.no_grad():
            logits = self.model(tensor)
            probs = torch.softmax(logits, dim=1).squeeze(0).cpu().numpy()
            
        latency_ms = round((time.time() - t0) * 1000.0, 2)
        
        score_not_flooded = float(probs[0])
        score_flooded = float(probs[1])
        
        predicted_class, confidence, is_ambiguous, is_inconclusive_prob, prob_reasons = (
            map_vision_probabilities_to_decision(score_flooded)
        )
        is_inconclusive = is_inconclusive or is_inconclusive_prob
        inconclusive_reasons = (quality_reasons or []) + prob_reasons
        
        warnings = [
            "Experimental prototype: Visual evidence only. Does not constitute official emergency advice.",
            "A negative prediction does not guarantee road passability or absence of flood hazard.",
            "Advisory only: Do not generate emergency actions from unvalidated imagery."
        ]
        if is_inconclusive:
            warnings.append(
                f"Model evaluation is inconclusive (flood probability {score_flooded:.2f}). "
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
            "is_inconclusive": is_inconclusive,
            "inconclusive_reasons": inconclusive_reasons if is_inconclusive else None,
            "quality_metrics": metrics,
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

