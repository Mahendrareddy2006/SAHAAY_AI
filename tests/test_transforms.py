"""Unit tests for Flood Vision transforms."""
import pytest
import torch
from PIL import Image
from sahaay.vision.transforms import get_train_transforms, get_eval_transforms

def test_train_transforms_output_shape():
    transform = get_train_transforms(image_size=224)
    img = Image.new("RGB", (300, 400), color=(100, 150, 200))
    tensor = transform(img)
    
    assert isinstance(tensor, torch.Tensor)
    assert tensor.shape == (3, 224, 224)
    assert tensor.dtype == torch.float32

def test_eval_transforms_output_shape():
    transform = get_eval_transforms(image_size=224)
    img = Image.new("RGB", (500, 350), color=(255, 0, 0))
    tensor = transform(img)
    
    assert isinstance(tensor, torch.Tensor)
    assert tensor.shape == (3, 224, 224)
    assert tensor.dtype == torch.float32
