"""
Sahaay AI - Flood Vision Evaluation Module
Evaluates checkpoint on held-out test set, measures latency, computes confusion matrix and error analysis.
"""

import os
import time
import json
from typing import Dict, Any, List
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support, accuracy_score

from sahaay.vision.dataset import FloodDataset
from sahaay.vision.transforms import get_eval_transforms
from sahaay.vision.model import create_flood_classifier
from sahaay.config import LABEL_MAP

def evaluate_checkpoint(
    checkpoint_path: str,
    test_csv: str,
    device_name: str = "auto",
    batch_size: int = 32
) -> Dict[str, Any]:
    if not os.path.exists(checkpoint_path):
        raise FileNotFoundError(f"Checkpoint not found at: {checkpoint_path}")
    if not os.path.exists(test_csv):
        raise FileNotFoundError(f"Test CSV not found at: {test_csv}")
        
    if device_name == "auto":
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    else:
        device = torch.device(device_name)
        
    print(f"Loading checkpoint: {checkpoint_path}")
    checkpoint = torch.load(checkpoint_path, map_location=device)
    
    model_name = checkpoint.get("model_name", "mobilenet_v3_small")
    model_version = checkpoint.get("model_version", "1.0.0")
    
    model = create_flood_classifier(model_name=model_name, num_classes=2, pretrained=False)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.to(device)
    model.eval()
    
    test_dataset = FloodDataset(test_csv, transform=get_eval_transforms(224))
    test_loader = DataLoader(test_dataset, batch_size=batch_size, shuffle=False, num_workers=0)
    
    print(f"Evaluating {len(test_dataset)} held-out test images on {device}...")
    
    all_targets = []
    all_preds = []
    all_probs = []
    all_paths = []
    
    t0 = time.time()
    with torch.no_grad():
        for images, labels, paths in test_loader:
            images = images.to(device)
            outputs = model(images)
            probs = torch.softmax(outputs, dim=1).cpu().numpy()
            preds = np.argmax(probs, axis=1)
            
            all_targets.extend(labels.numpy())
            all_preds.extend(preds)
            all_probs.extend(probs)
            all_paths.extend(paths)
            
    total_eval_time = time.time() - t0
    avg_latency_ms = (total_eval_time / len(test_dataset)) * 1000.0
    
    # Calculate performance metrics
    acc = accuracy_score(all_targets, all_preds)
    p, r, f1, support = precision_recall_fscore_support(all_targets, all_preds, average=None, labels=[0, 1])
    cm = confusion_matrix(all_targets, all_preds, labels=[0, 1])
    # cm: [[TN, FP], [FN, TP]]
    tn, fp, fn, tp = int(cm[0, 0]), int(cm[0, 1]), int(cm[1, 0]), int(cm[1, 1])
    
    # Identify errors
    false_positives = []
    false_negatives = []
    
    for i in range(len(all_targets)):
        target = all_targets[i]
        pred = all_preds[i]
        path = all_paths[i]
        prob = all_probs[i].tolist()
        
        if target == 0 and pred == 1:
            false_positives.append({
                "path": path,
                "confidence_flooded": float(prob[1]),
                "true_label": "not_flooded",
                "predicted_label": "flooded"
            })
        elif target == 1 and pred == 0:
            false_negatives.append({
                "path": path,
                "confidence_not_flooded": float(prob[0]),
                "true_label": "flooded",
                "predicted_label": "not_flooded"
            })
            
    # File size
    file_size_bytes = os.path.getsize(checkpoint_path)
    file_size_mb = round(file_size_bytes / (1024 * 1024), 2)
    
    report = {
        "model_name": model_name,
        "model_version": model_version,
        "checkpoint_path": checkpoint_path,
        "evaluation_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "test_dataset_size": len(test_dataset),
        "class_support": {
            "not_flooded": int(support[0]),
            "flooded": int(support[1])
        },
        "accuracy": float(acc),
        "macro_f1": float(np.mean(f1)),
        "metrics_by_class": {
            "not_flooded": {
                "precision": float(p[0]),
                "recall": float(r[0]),
                "f1_score": float(f1[0]),
                "support": int(support[0])
            },
            "flooded": {
                "precision": float(p[1]),
                "recall": float(r[1]),
                "f1_score": float(f1[1]),
                "support": int(support[1])
            }
        },
        "confusion_matrix": {
            "true_negatives": tn,
            "false_positives": fp,
            "false_negatives": fn,
            "true_positives": tp,
            "matrix_layout": "[[TN, FP], [FN, TP]]",
            "raw": [[tn, fp], [fn, tp]]
        },
        "error_analysis": {
            "total_errors": fp + fn,
            "false_positives_count": len(false_positives),
            "false_negatives_count": len(false_negatives),
            "false_positives": false_positives[:10],
            "false_negatives": false_negatives[:10]
        },
        "inference_benchmark": {
            "device": str(device),
            "total_inference_time_seconds": round(total_eval_time, 3),
            "average_latency_ms_per_image": round(avg_latency_ms, 2),
            "checkpoint_size_mb": file_size_mb
        }
    }
    
    return report
