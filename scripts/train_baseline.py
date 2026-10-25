"""
Sahaay AI - Train Flood Vision Baseline Script
Runs reproducible baseline training using the stratified manifests.
"""

import os
import sys

# Ensure src is in sys.path
sys.path.insert(0, os.path.abspath("src"))

from sahaay.config import VisionModelConfig
from sahaay.vision.train import train_flood_model

def main():
    train_csv = os.path.join("data", "processed", "train.csv")
    val_csv = os.path.join("data", "processed", "val.csv")
    output_dir = os.path.join("models", "vision")
    
    config = VisionModelConfig(
        model_name="mobilenet_v3_small",
        model_version="1.0.0",
        epochs=5,
        batch_size=32,
        learning_rate=3e-4,
        random_seed=42
    )
    
    print("=" * 60)
    print("SAHAAY AI — FLOOD VISION BASELINE TRAINING")
    print(f"Architecture: {config.model_name}")
    print(f"Epochs:       {config.epochs}")
    print(f"Batch Size:   {config.batch_size}")
    print(f"Random Seed:  {config.random_seed}")
    print("=" * 60)
    
    metadata = train_flood_model(
        train_csv=train_csv,
        val_csv=val_csv,
        output_dir=output_dir,
        config=config
    )
    
    print("\nBaseline training process completed successfully.")

if __name__ == "__main__":
    main()
