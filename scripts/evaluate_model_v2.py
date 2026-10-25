"""
Sahaay AI - Model V2 Test Evaluation with Bootstrap CIs (Phase C)
Evaluates clean checkpoint models/vision/v2/model_v2.pt on untouched test_v2.csv,
computes 95% bootstrap confidence intervals, and compares with dimension-only shortcuts.
"""

import os
import sys
import json
import time
import numpy as np
import pandas as pd
import torch
from sklearn.metrics import accuracy_score, precision_recall_fscore_support, confusion_matrix
from torch.utils.data import DataLoader

sys.path.insert(0, os.path.abspath("src"))

from sahaay.vision.dataset import FloodDataset
from sahaay.vision.transforms import get_eval_transforms
from sahaay.vision.model import create_flood_classifier

def bootstrap_confidence_intervals(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    n_bootstraps: int = 1000,
    confidence_level: float = 0.95,
    seed: int = 42
):
    rng = np.random.RandomState(seed)
    n = len(y_true)
    boot_acc = []
    boot_f1 = []
    
    for _ in range(n_bootstraps):
        indices = rng.choice(n, size=n, replace=True)
        sample_true = y_true[indices]
        sample_pred = y_pred[indices]
        
        acc = accuracy_score(sample_true, sample_pred)
        _, _, f1, _ = precision_recall_fscore_support(sample_true, sample_pred, average="macro", zero_division=0)
        boot_acc.append(acc)
        boot_f1.append(f1)
        
    alpha = (1.0 - confidence_level) / 2.0
    acc_lower = float(np.percentile(boot_acc, alpha * 100))
    acc_upper = float(np.percentile(boot_acc, (1.0 - alpha) * 100))
    f1_lower = float(np.percentile(boot_f1, alpha * 100))
    f1_upper = float(np.percentile(boot_f1, (1.0 - alpha) * 100))
    
    return {
        "n_bootstraps": n_bootstraps,
        "confidence_level": confidence_level,
        "accuracy_ci_95": [acc_lower, acc_upper],
        "macro_f1_ci_95": [f1_lower, f1_upper]
    }

def main():
    checkpoint_path = os.path.join("models", "vision", "v2", "model_v2.pt")
    test_csv = os.path.join("data", "processed", "manifest_v2", "test_v2.csv")
    out_json = os.path.join("models", "vision", "v2", "test_evaluation_results_v2.json")
    
    print("=" * 60)
    print("SAHAAY AI — MODEL V2 EVALUATION (CLEAN SPLIT)")
    print(f"Checkpoint: {checkpoint_path}")
    print(f"Test Set:   {test_csv}")
    print("=" * 60)
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Loading checkpoint on {device}...")
    checkpoint = torch.load(checkpoint_path, map_location=device)
    
    model = create_flood_classifier(model_name="mobilenet_v3_small", num_classes=2, pretrained=False)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.to(device)
    model.eval()
    
    test_dataset = FloodDataset(test_csv, transform=get_eval_transforms(224))
    test_loader = DataLoader(test_dataset, batch_size=32, shuffle=False, num_workers=0)
    
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
            
    eval_time = time.time() - t0
    y_true = np.array(all_targets)
    y_pred = np.array(all_preds)
    probs_arr = np.array(all_probs)
    
    # Metrics
    acc = float(accuracy_score(y_true, y_pred))
    p, r, f1, support = precision_recall_fscore_support(y_true, y_pred, average=None, labels=[0, 1])
    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    tn, fp, fn, tp = int(cm[0, 0]), int(cm[0, 1]), int(cm[1, 0]), int(cm[1, 1])
    
    # Confidence distribution
    pred_confidences = [float(probs_arr[i, y_pred[i]]) for i in range(len(y_pred))]
    
    # Bootstrap CIs
    ci_results = bootstrap_confidence_intervals(y_true, y_pred, n_bootstraps=1000)
    
    # Error cases
    false_positives = []
    false_negatives = []
    for i in range(len(y_true)):
        if y_true[i] == 0 and y_pred[i] == 1:
            false_positives.append({"path": all_paths[i], "confidence": float(probs_arr[i, 1])})
        elif y_true[i] == 1 and y_pred[i] == 0:
            false_negatives.append({"path": all_paths[i], "confidence": float(probs_arr[i, 0])})
            
    # Load shortcut baseline results for direct comparison
    shortcut_diag_path = os.path.join("reports", "vision_integrity", "shortcut_diagnosis.json")
    shortcut_info = {}
    if os.path.exists(shortcut_diag_path):
        with open(shortcut_diag_path) as f:
            shortcut_info = json.load(f)
            
    report = {
        "model_name": "mobilenet_v3_small_v2",
        "model_version": "2.0.0-clean-split",
        "evaluation_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "test_manifest": test_csv,
        "test_size": len(y_true),
        "accuracy": acc,
        "macro_f1": float(np.mean(f1)),
        "class_metrics": {
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
            "tn": tn, "fp": fp, "fn": fn, "tp": tp,
            "raw": [[tn, fp], [fn, tp]]
        },
        "bootstrap_confidence_intervals": ci_results,
        "confidence_distribution": {
            "mean": float(np.mean(pred_confidences)),
            "std": float(np.std(pred_confidences)),
            "median": float(np.median(pred_confidences)),
            "min": float(np.min(pred_confidences)),
            "p25": float(np.percentile(pred_confidences, 25)),
            "p75": float(np.percentile(pred_confidences, 75))
        },
        "error_analysis": {
            "total_errors": fp + fn,
            "false_positives_count": len(false_positives),
            "false_negatives_count": len(false_negatives),
            "false_positives_sample": false_positives[:5],
            "false_negatives_sample": false_negatives[:5]
        },
        "comparison_with_shortcuts": {
            "dimension_only_decision_stump_accuracy": 1.0,
            "dimension_shortcut_summary": "The raw roham1 dataset possesses 100% resolution disparity between classes (all not_flooded are 224x224, flooded are >800px). Even with zero duplicate leakage in Manifest V2, a dimensional shortcut remains in the underlying dataset source.",
            "operational_recommendation": "External ground-level validation (e.g. Clemson, local Hyderabad images) is mandatory before deploying this classifier."
        }
    }
    
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
        
    print(f"\nEvaluation Complete!")
    print(f"Test Accuracy: {acc:.4f} (95% CI: [{ci_results['accuracy_ci_95'][0]:.4f}, {ci_results['accuracy_ci_95'][1]:.4f}])")
    print(f"Macro-F1:      {float(np.mean(f1)):.4f} (95% CI: [{ci_results['macro_f1_ci_95'][0]:.4f}, {ci_results['macro_f1_ci_95'][1]:.4f}])")
    print(f"Confusion Matrix: TN={tn}, FP={fp}, FN={fn}, TP={tp}")
    print(f"Mean Confidence: {np.mean(pred_confidences):.4f}")
    print(f"Report saved to: {out_json}")

if __name__ == "__main__":
    main()
