"""Unit tests for FloodDataset."""
import os
import pytest
import torch
from sahaay.vision.dataset import FloodDataset
from sahaay.vision.transforms import get_eval_transforms

def test_dataset_loading():
    manifest = os.path.join("data", "processed", "test.csv")
    if not os.path.exists(manifest):
        pytest.skip("Test manifest does not exist yet")
        
    dataset = FloodDataset(manifest, transform=get_eval_transforms(224))
    assert len(dataset) == 450
    
    img, label, path = dataset[0]
    assert isinstance(img, torch.Tensor)
    assert img.shape == (3, 224, 224)
    assert label in [0, 1]
    assert os.path.exists(path)
