"""
Sahaay AI - Flood Vision Model Architecture
Supports transfer learning baselines: MobileNetV3-Small (primary) and ResNet-18 (alternative).
"""

from typing import Tuple
import torch
import torch.nn as nn
from torchvision import models

def create_flood_classifier(
    model_name: str = "mobilenet_v3_small",
    num_classes: int = 2,
    pretrained: bool = True
) -> nn.Module:
    """
    Constructs a pretrained convolutional neural network adapted for binary flood classification.
    
    Args:
        model_name: 'mobilenet_v3_small' or 'resnet18'
        num_classes: Number of target classes (default 2: not_flooded, flooded)
        pretrained: If True, initializes with official torchvision ImageNet weights
    """
    model_name_clean = model_name.lower().strip()
    
    if model_name_clean == "mobilenet_v3_small":
        weights = models.MobileNet_V3_Small_Weights.DEFAULT if pretrained else None
        model = models.mobilenet_v3_small(weights=weights)
        in_features = model.classifier[3].in_features
        model.classifier[3] = nn.Linear(in_features, num_classes)
        model.arch_name = "mobilenet_v3_small"
        
    elif model_name_clean == "resnet18":
        weights = models.ResNet18_Weights.DEFAULT if pretrained else None
        model = models.resnet18(weights=weights)
        in_features = model.fc.in_features
        model.fc = nn.Linear(in_features, num_classes)
        model.arch_name = "resnet18"
        
    else:
        raise ValueError(f"Unsupported model architecture: {model_name}. Use 'mobilenet_v3_small' or 'resnet18'.")
        
    return model

def count_parameters(model: nn.Module) -> Tuple[int, int]:
    """
    Returns (total_params, trainable_params) of the model.
    """
    total = sum(p.numel() for p in model.parameters())
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    return total, trainable
