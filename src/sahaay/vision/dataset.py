"""
Sahaay AI - Flood Dataset Loader
Provides PyTorch Dataset implementations reading from validated CSV manifests.
"""

import os
from typing import Optional, Callable, Tuple
import pandas as pd
from PIL import Image
import torch
from torch.utils.data import Dataset

class FloodDataset(Dataset):
    """
    Standard PyTorch dataset for binary flood classification.
    Reads image paths and labels from a structured CSV manifest.
    """
    def __init__(self, csv_file: str, transform: Optional[Callable] = None):
        self.csv_file = csv_file
        self.transform = transform
        
        if not os.path.exists(csv_file):
            raise FileNotFoundError(f"Manifest not found at: {csv_file}")
            
        self.df = pd.read_csv(csv_file)
        if "file_path" not in self.df.columns or "label_idx" not in self.df.columns:
            raise ValueError(f"CSV manifest must contain 'file_path' and 'label_idx' columns: {csv_file}")
            
    def __len__(self) -> int:
        return len(self.df)
        
    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, int, str]:
        row = self.df.iloc[idx]
        img_path = row["file_path"]
        label = int(row["label_idx"])
        
        try:
            with Image.open(img_path) as im:
                image = im.convert("RGB")
        except Exception as e:
            raise IOError(f"Failed to read image at {img_path}: {e}")
            
        if self.transform is not None:
            image = self.transform(image)
            
        return image, label, img_path
