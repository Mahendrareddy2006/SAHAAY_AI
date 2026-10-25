"""
Sahaay AI - Flood Vision Training Pipeline
Trains transfer learning baselines with early stopping, validation tracking, and checkpointing.
"""

import os
import time
import json
import random
from typing import Dict, Any, Optional
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from sklearn.metrics import precision_recall_fscore_support, accuracy_score

from sahaay.vision.dataset import FloodDataset
from sahaay.vision.transforms import get_train_transforms, get_eval_transforms
from sahaay.vision.model import create_flood_classifier, count_parameters
from sahaay.config import LABEL_MAP, VisionModelConfig

def set_seed(seed: int = 42):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False

def train_epoch(
    model: nn.Module,
    dataloader: DataLoader,
    criterion: nn.Module,
    optimizer: torch.optim.Optimizer,
    device: torch.device
) -> float:
    model.train()
    running_loss = 0.0
    
    for images, labels, _ in dataloader:
        images = images.to(device)
        labels = labels.to(device)
        
        optimizer.zero_grad()
        outputs = model(images)
        loss = criterion(outputs, labels)
        loss.backward()
        optimizer.step()
        
        running_loss += loss.item() * images.size(0)
        
    return running_loss / len(dataloader.dataset)

def evaluate(
    model: nn.Module,
    dataloader: DataLoader,
    criterion: nn.Module,
    device: torch.device
) -> Dict[str, Any]:
    model.eval()
    running_loss = 0.0
    all_preds = []
    all_targets = []
    
    with torch.no_grad():
        for images, labels, _ in dataloader:
            images = images.to(device)
            labels = labels.to(device)
            
            outputs = model(images)
            loss = criterion(outputs, labels)
            
            running_loss += loss.item() * images.size(0)
            preds = torch.argmax(outputs, dim=1).cpu().numpy()
            
            all_preds.extend(preds)
            all_targets.extend(labels.cpu().numpy())
            
    val_loss = running_loss / len(dataloader.dataset)
    acc = accuracy_score(all_targets, all_preds)
    p, r, f1, _ = precision_recall_fscore_support(all_targets, all_preds, average=None, labels=[0, 1])
    macro_f1 = float(np.mean(f1))
    
    return {
        "loss": float(val_loss),
        "accuracy": float(acc),
        "macro_f1": float(macro_f1),
        "precision_not_flooded": float(p[0]),
        "recall_not_flooded": float(r[0]),
        "f1_not_flooded": float(f1[0]),
        "precision_flooded": float(p[1]),
        "recall_flooded": float(r[1]),
        "f1_flooded": float(f1[1]),
        "targets": all_targets,
        "predictions": all_preds
    }

def train_flood_model(
    train_csv: str,
    val_csv: str,
    output_dir: str,
    config: Optional[VisionModelConfig] = None
) -> Dict[str, Any]:
    if config is None:
        config = VisionModelConfig()
        
    set_seed(config.random_seed)
    os.makedirs(output_dir, exist_ok=True)
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using compute device: {device} ({torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'})")
    
    train_dataset = FloodDataset(train_csv, transform=get_train_transforms(config.image_size))
    val_dataset = FloodDataset(val_csv, transform=get_eval_transforms(config.image_size))
    
    train_loader = DataLoader(
        train_dataset,
        batch_size=config.batch_size,
        shuffle=True,
        num_workers=0,
        pin_memory=(device.type == "cuda")
    )
    val_loader = DataLoader(
        val_dataset,
        batch_size=config.batch_size,
        shuffle=False,
        num_workers=0,
        pin_memory=(device.type == "cuda")
    )
    
    print(f"Initializing {config.model_name} (pretrained on ImageNet)...")
    model = create_flood_classifier(
        model_name=config.model_name,
        num_classes=config.num_classes,
        pretrained=True
    ).to(device)
    
    total_params, trainable_params = count_parameters(model)
    print(f"Total parameters: {total_params:,} | Trainable: {trainable_params:,}")
    
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=config.learning_rate,
        weight_decay=config.weight_decay
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=config.epochs)
    
    best_val_macro_f1 = -1.0
    best_epoch = -1
    best_metrics = {}
    history = []
    
    checkpoint_path = os.path.join(output_dir, "best_model.pt")
    
    print(f"\n--- Commencing Training: {config.epochs} Epochs ---")
    start_time = time.time()
    
    for epoch in range(1, config.epochs + 1):
        epoch_start = time.time()
        train_loss = train_epoch(model, train_loader, criterion, optimizer, device)
        val_metrics = evaluate(model, val_loader, criterion, device)
        scheduler.step()
        
        elapsed = time.time() - epoch_start
        val_macro_f1 = val_metrics["macro_f1"]
        
        epoch_info = {
            "epoch": epoch,
            "train_loss": float(train_loss),
            "val_loss": val_metrics["loss"],
            "val_accuracy": val_metrics["accuracy"],
            "val_macro_f1": val_macro_f1,
            "val_f1_flooded": val_metrics["f1_flooded"],
            "val_f1_not_flooded": val_metrics["f1_not_flooded"],
            "epoch_time_seconds": round(elapsed, 2)
        }
        history.append(epoch_info)
        
        print(
            f"Epoch [{epoch:02d}/{config.epochs:02d}] "
            f"Train Loss: {train_loss:.4f} | "
            f"Val Loss: {val_metrics['loss']:.4f} | "
            f"Val Acc: {val_metrics['accuracy']:.4f} | "
            f"Val Macro-F1: {val_macro_f1:.4f} "
            f"({elapsed:.1f}s)"
        )
        
        # Save best checkpoint on validation Macro-F1
        if val_macro_f1 > best_val_macro_f1:
            best_val_macro_f1 = val_macro_f1
            best_epoch = epoch
            best_metrics = val_metrics
            
            torch.save({
                "epoch": epoch,
                "model_name": config.model_name,
                "model_version": config.model_version,
                "model_state_dict": model.state_dict(),
                "optimizer_state_dict": optimizer.state_dict(),
                "val_macro_f1": val_macro_f1,
                "val_metrics": {k: v for k, v in val_metrics.items() if k not in ["targets", "predictions"]},
                "label_map": LABEL_MAP,
                "config": config.dict()
            }, checkpoint_path)
            print(f"  -> Best model saved to: {checkpoint_path} (Val Macro-F1: {val_macro_f1:.4f})")
            
    total_training_time = time.time() - start_time
    print(f"\nTraining completed in {total_training_time:.2f} seconds.")
    print(f"Best Checkpoint: Epoch {best_epoch} with Val Macro-F1: {best_val_macro_f1:.4f}")
    
    metadata = {
        "model_name": config.model_name,
        "model_version": config.model_version,
        "best_epoch": best_epoch,
        "best_val_macro_f1": best_val_macro_f1,
        "best_val_metrics": {k: v for k, v in best_metrics.items() if k not in ["targets", "predictions"]},
        "total_training_time_seconds": round(total_training_time, 2),
        "history": history,
        "total_parameters": total_params,
        "checkpoint_file": checkpoint_path
    }
    
    meta_path = os.path.join(output_dir, "model_metadata.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
        
    return metadata
