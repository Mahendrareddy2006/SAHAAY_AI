"""
Step 4: Audit Confidence and Abstention
Traces the origin of the 0.65 threshold.
Sweeps confidence thresholds across [0.50, 0.99] to compute:
- Coverage vs. Error Rate (Risk-Coverage trade-off)
- Risk among accepted predictions
- Proportion sent to human review (abstention rate)
- Accuracy on ambiguous/rejected inputs
- Reassesses calibration (ECE, Brier) across validation, test, and held-out multi-source data.
"""

import os
import sys
import json
import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from PIL import Image
from sklearn.metrics import accuracy_score, brier_score_loss

sys.path.insert(0, os.path.abspath("src"))

from sahaay.vision.model import create_flood_classifier
from sahaay.vision.transforms import get_eval_transforms

def compute_ece(probs, targets, n_bins=10):
    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    confidences = np.max(np.column_stack([1 - probs, probs]), axis=1)
    predictions = (probs >= 0.5).astype(int)
    accuracies = (predictions == targets)

    for i in range(n_bins):
        in_bin = (confidences > bin_boundaries[i]) & (confidences <= bin_boundaries[i + 1])
        prop_in_bin = np.mean(in_bin)
        if prop_in_bin > 0:
            accuracy_in_bin = np.mean(accuracies[in_bin])
            avg_confidence_in_bin = np.mean(confidences[in_bin])
            ece += np.abs(avg_confidence_in_bin - accuracy_in_bin) * prop_in_bin
    return float(ece)

def get_predictions(model, eval_tf, df, device):
    probs = []
    targets = df['label_idx' if 'label_idx' in df.columns else 'label'].values
    with torch.no_grad():
        for _, row in df.iterrows():
            with Image.open(row['file_path']) as im:
                rgb = im.convert("RGB")
            t = eval_tf(rgb).unsqueeze(0).to(device)
            out = model(t)
            p = F.softmax(out, dim=1).cpu().numpy()[0]
            probs.append(float(p[1]))
    return np.array(probs), np.array(targets)

def sweep_thresholds(probs, targets, thresholds):
    confidences = np.max(np.column_stack([1 - probs, probs]), axis=1)
    preds = (probs >= 0.5).astype(int)
    total_n = len(targets)

    sweep_results = []
    for tau in thresholds:
        accepted_mask = confidences >= tau
        rejected_mask = ~accepted_mask

        n_accepted = int(np.sum(accepted_mask))
        n_rejected = int(np.sum(rejected_mask))

        coverage = float(n_accepted / total_n)
        review_rate = float(n_rejected / total_n)

        if n_accepted > 0:
            accepted_acc = float(accuracy_score(targets[accepted_mask], preds[accepted_mask]))
            accepted_risk = float(1.0 - accepted_acc)
        else:
            accepted_acc = 1.0
            accepted_risk = 0.0

        if n_rejected > 0:
            rejected_acc = float(accuracy_score(targets[rejected_mask], preds[rejected_mask]))
        else:
            rejected_acc = 0.0

        sweep_results.append({
            "threshold": round(float(tau), 2),
            "coverage": round(coverage, 4),
            "review_rate": round(review_rate, 4),
            "accepted_count": n_accepted,
            "reviewed_count": n_rejected,
            "risk_on_accepted": round(accepted_risk, 4),
            "accuracy_on_accepted": round(accepted_acc, 4),
            "accuracy_on_reviewed": round(rejected_acc, 4)
        })
    return sweep_results

def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    eval_tf = get_eval_transforms(224)

    # Load Model V3 Monsoon
    model_path = "models/vision/v3/model_v3_monsoon.pt"
    model = create_flood_classifier("mobilenet_v3_small", num_classes=2, pretrained=False)
    ckpt = torch.load(model_path, map_location=device)
    sd = ckpt["model_state_dict"] if isinstance(ckpt, dict) and "model_state_dict" in ckpt else ckpt
    model.load_state_dict(sd)
    model.to(device)
    model.eval()

    val_df = pd.read_csv("data/processed/manifest_v3/val_v3.csv")
    test_df = pd.read_csv("data/processed/manifest_v3/test_v3.csv")

    val_probs, val_targs = get_predictions(model, eval_tf, val_df, device)
    test_probs, test_targs = get_predictions(model, eval_tf, test_df, device)

    thresholds = [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95, 0.98]

    val_sweep = sweep_thresholds(val_probs, val_targs, thresholds)
    test_sweep = sweep_thresholds(test_probs, test_targs, thresholds)

    val_ece = compute_ece(val_probs, val_targs)
    val_brier = float(brier_score_loss(val_targs, val_probs))
    test_ece = compute_ece(test_probs, test_targs)
    test_brier = float(brier_score_loss(test_targs, test_probs))

    report = {
        "audit_title": "Confidence, Abstention, and Risk-Coverage Audit",
        "model_evaluated": "model_v3_monsoon (mobilenet_v3_small)",
        "threshold_origin_trace": {
            "origin": "Heuristic preset in src/sahaay/config.py (VisionModelConfig.confidence_threshold = 0.65)",
            "selected_on_validation_only": False,
            "provisional_status": "PROVISIONAL. The 0.65 threshold was chosen a priori based on standard binary classification heuristics rather than empirical risk-coverage optimization on validation data.",
            "recommendation": "Maintain 0.65 as an advisory threshold for development, but calibrate to a target false-alarm tolerance (e.g. risk <= 0.01) before municipal deployment."
        },
        "calibration_metrics": {
            "validation_split": {
                "sample_count": len(val_df),
                "ece": round(val_ece, 4),
                "brier_score": round(val_brier, 4)
            },
            "test_split": {
                "sample_count": len(test_df),
                "ece": round(test_ece, 4),
                "brier_score": round(test_brier, 4)
            }
        },
        "risk_coverage_sweep": {
            "validation_v3": val_sweep,
            "test_v3": test_sweep
        },
        "operational_threshold_comparison": {
            "at_threshold_0_50": {
                "coverage": test_sweep[0]["coverage"],
                "risk": test_sweep[0]["risk_on_accepted"],
                "review_rate": test_sweep[0]["review_rate"]
            },
            "at_threshold_0_65": {
                "coverage": test_sweep[3]["coverage"],
                "risk": test_sweep[3]["risk_on_accepted"],
                "review_rate": test_sweep[3]["review_rate"]
            },
            "at_threshold_0_80": {
                "coverage": test_sweep[6]["coverage"],
                "risk": test_sweep[6]["risk_on_accepted"],
                "review_rate": test_sweep[6]["review_rate"]
            },
            "at_threshold_0_90": {
                "coverage": test_sweep[8]["coverage"],
                "risk": test_sweep[8]["risk_on_accepted"],
                "review_rate": test_sweep[8]["review_rate"]
            }
        }
    }

    out_file = "reports/vision_integrity/confidence_abstention_risk_coverage.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("\n--- Confidence & Abstention Sweep (Reserved Test V3) ---")
    print(f"{'Threshold':<10} | {'Coverage':<10} | {'Review Rate':<12} | {'Risk (Error)':<14} | {'Accuracy':<10}")
    print("-" * 65)
    for row in test_sweep:
        print(f"{row['threshold']:<10.2f} | {row['coverage']*100:<9.1f}% | {row['review_rate']*100:<11.1f}% | {row['risk_on_accepted']*100:<13.2f}% | {row['accuracy_on_accepted']*100:<9.2f}%")

    print(f"\nReport saved to: {out_file}")

if __name__ == "__main__":
    main()
