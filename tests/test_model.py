"""Unit tests for model architecture instantiation and forward pass."""
import pytest
import torch
from sahaay.vision.model import create_flood_classifier, count_parameters

def test_mobilenet_v3_small_instantiation():
    model = create_flood_classifier("mobilenet_v3_small", num_classes=2, pretrained=False)
    x = torch.randn(2, 3, 224, 224)
    out = model(x)
    assert out.shape == (2, 2)
    
    total, trainable = count_parameters(model)
    assert total > 1_000_000
    assert total == trainable

def test_resnet18_instantiation():
    model = create_flood_classifier("resnet18", num_classes=2, pretrained=False)
    x = torch.randn(2, 3, 224, 224)
    out = model(x)
    assert out.shape == (2, 2)
