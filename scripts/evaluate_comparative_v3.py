"""
Phase 3: Controlled Model Comparisons on Reserved V3 Test Set
Evaluates:
1. Historical Model V2 (trained on V2 split)
2. Dimensional Shortcut Baseline (Width/Height/File-size only)
3. Model V3 Clean (trained on balanced V3 split)
4. Model V3 Monsoon (trained with degradation augmentations)

Reports:
- Accuracy, Precision, Recall, Macro-F1
- Confusion Matrix, False Positive Rate (FPR), False Negative Rate (FNR)
- 95% Confidence Intervals for Accuracy
- Per-source breakdown (virenbr11_plain, virenbr11_pothole, clemson_flood)
- Per-condition breakdown (plain dry road, puddle hard negative, flooded street)
"""

import os
import sys
import json
import math
import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from PIL import Image
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support, accuracy_score, roc_auc_score

sys.path.insert(0, os.path.abspath("src"))

from sahaay.vision.model import create_flood_classifier
from sahaay.vision.transforms import get_eval_transforms

def compute_confidence_interval(p, n, z=1.96):
    """Wilson score interval for binomial proportion."""
    if n == 0:
        return (0.0, 0.0)
    denom = 1 + (z**2) / n
    centre = (p + (z**2) / (2 * n)) / denom
    spread = (z / denom) * math.sqrt((p * (1 - p) / n) + (z**2) / (4 * (n**2)))
    low = max(0.0, centre - spread)
    high = min(1.0, centre + spread)
    return round(low, 4), round(high, 4)

def evaluate_pytorch_checkpoint(checkpoint_path, test_df, device):
    model = create_flood_classifier("mobilenet_v3_small", num_classes=2, pretrained=False)
    checkpoint = torch.load(checkpoint_path, map_location=device)
    if isinstance(checkpoint, dict) and "model_state_dict" in checkpoint:
        state_dict = checkpoint["model_state_dict"]
    else:
        state_dict = checkpoint
    model.load_state_dict(state_dict)
    model.to(device)
    model.eval()

    eval_tf = get_eval_transforms(224)
    probs = []
    preds = []
    label_col = 'label_idx' if 'label_idx' in test_df.columns else 'label'
    targets = test_df[label_col].values

    with torch.no_grad():
        for _, row in test_df.iterrows():
            img_path = row['file_path']
            with Image.open(img_path) as im:
                img_rgb = im.convert("RGB")
            tensor = eval_tf(img_rgb).unsqueeze(0).to(device)
            logits = model(tensor)
            prob = F.softmax(logits, dim=1).cpu().numpy()[0]
            probs.append(float(prob[1]))
            preds.append(int(np.argmax(prob)))

    return np.array(preds), np.array(probs), targets

def compute_metrics(y_true, y_pred, y_prob):
    acc = accuracy_score(y_true, y_pred)
    p, r, f1, _ = precision_recall_fscore_support(y_true, y_pred, average=None, labels=[0, 1], zero_division=0)
    macro_f1 = np.mean(f1)
    
    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    tn, fp, fn, tp = cm.ravel()
    fpr = float(fp / (fp + tn)) if (fp + tn) > 0 else 0.0
    fnr = float(fn / (fn + tp)) if (fn + tp) > 0 else 0.0
    
    ci_low, ci_high = compute_confidence_interval(acc, len(y_true))
    try:
        auc = roc_auc_score(y_true, y_prob)
    except Exception:
        auc = 0.5

    return {
        "accuracy": round(float(acc), 4),
        "accuracy_ci_95": [ci_low, ci_high],
        "macro_f1": round(float(macro_f1), 4),
        "roc_auc": round(float(auc), 4),
        "false_positive_rate": round(fpr, 4),
        "false_negative_rate": round(fnr, 4),
        "confusion_matrix": {
            "tn": int(tn),
            "fp": int(fp),
            "fn": int(fn),
            "tp": int(tp)
        },
        "per_class": {
            "non_flood": {
                "precision": round(float(p[0]), 4),
                "recall": round(float(r[0]), 4),
                "f1": round(float(f1[0]), 4),
                "support": int(tn + fp)
            },
            "flood": {
                "precision": round(float(p[1]), 4),
                "recall": round(float(r[1]), 4),
                "f1": round(float(f1[1]), 4),
                "support": int(tp + fn)
            }
        }
    }

def evaluate_subcohort(df, y_pred, y_prob, group_col):
    cohort_results = {}
    label_col = 'label_idx' if 'label_idx' in df.columns else 'label'
    for group_name, group_indices in df.groupby(group_col).groups.items():
        sub_true = df.loc[group_indices, label_col].values
        sub_pred = y_pred[group_indices]
        sub_prob = y_prob[group_indices]
        
        acc = accuracy_score(sub_true, sub_pred)
        cohort_results[str(group_name)] = {
            "sample_count": len(sub_true),
            "accuracy": round(float(acc), 4),
            "ground_truth_counts": pd.Series(sub_true).value_counts().to_dict(),
            "predicted_positive_count": int(np.sum(sub_pred == 1)),
            "mean_flood_probability": round(float(np.mean(sub_prob)), 4)
        }
    return cohort_results

def main():
    test_csv = "data/processed/manifest_v3/test_v3.csv"
    test_df = pd.read_csv(test_csv)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Evaluating models on reserved Test V3 ({len(test_df)} images) using {device}...")

    results = {
        "evaluation_target": "test_v3.csv (Unseen Reserved Split)",
        "test_sample_size": len(test_df),
        "models": {}
    }

    # 1. Historical Model V2
    v2_path = "models/vision/v2/model_v2.pt"
    if os.path.exists(v2_path):
        print("\nEvaluating Model V2 (Historical Checkpoint)...")
        v2_preds, v2_probs, y_true = evaluate_pytorch_checkpoint(v2_path, test_df, device)
        v2_metrics = compute_metrics(y_true, v2_preds, v2_probs)
        v2_metrics["per_condition"] = evaluate_subcohort(test_df, v2_preds, v2_probs, "subcondition")
        v2_metrics["per_source"] = evaluate_subcohort(test_df, v2_preds, v2_probs, "source_dataset")
        results["models"]["model_v2_historical"] = v2_metrics

    # 2. Dimensional Shortcut Baseline
    shortcut_path = "reports/vision_integrity/shortcut_diagnosis_v3.json"
    if os.path.exists(shortcut_path):
        with open(shortcut_path, "r") as f:
            sc_data = json.load(f)
        results["models"]["dimension_metadata_baseline"] = sc_data["all_metadata_features"]

    # 3. Model V3 Clean
    v3_clean_path = "models/vision/v3/model_v3_clean.pt"
    if os.path.exists(v3_clean_path):
        print("\nEvaluating Model V3 Clean...")
        clean_preds, clean_probs, y_true = evaluate_pytorch_checkpoint(v3_clean_path, test_df, device)
        clean_metrics = compute_metrics(y_true, clean_preds, clean_probs)
        clean_metrics["per_condition"] = evaluate_subcohort(test_df, clean_preds, clean_probs, "subcondition")
        clean_metrics["per_source"] = evaluate_subcohort(test_df, clean_preds, clean_probs, "source_dataset")
        results["models"]["model_v3_clean"] = clean_metrics

    # 4. Model V3 Monsoon-Augmented
    v3_monsoon_path = "models/vision/v3/model_v3_monsoon.pt"
    if os.path.exists(v3_monsoon_path):
        print("\nEvaluating Model V3 Monsoon...")
        monsoon_preds, monsoon_probs, y_true = evaluate_pytorch_checkpoint(v3_monsoon_path, test_df, device)
        monsoon_metrics = compute_metrics(y_true, monsoon_preds, monsoon_probs)
        monsoon_metrics["per_condition"] = evaluate_subcohort(test_df, monsoon_preds, monsoon_probs, "subcondition")
        monsoon_metrics["per_source"] = evaluate_subcohort(test_df, monsoon_preds, monsoon_probs, "source_dataset")
        results["models"]["model_v3_monsoon"] = monsoon_metrics

    out_path = "models/vision/v3/comparative_evaluation_v3.json"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print(f"\nComparative evaluation saved to: {out_path}")
    print("\n" + "=" * 80)
    print("COMPARATIVE EVALUATION SUMMARY (RESERVED TEST V3)")
    print("=" * 80)
    for mname, mdata in results["models"].items():
        if "accuracy" in mdata:
            ci = mdata.get('accuracy_ci_95', ['N/A', 'N/A'])
            print(f"{mname:<28} | Acc: {mdata['accuracy']:.4f} (95% CI: {ci[0]}-{ci[1]}) | Macro-F1: {mdata['macro_f1']:.4f} | FPR: {mdata.get('false_positive_rate', 'N/A')}")
            if "per_condition" in mdata:
                pothole_sub = mdata["per_condition"].get("wet_road_pothole_hard_negative", {})
                print(f"   -> Hard Negative (Wet Potholes/Puddles) Accuracy: {pothole_sub.get('accuracy', 'N/A')} (Mean Flood Prob: {pothole_sub.get('mean_flood_probability', 'N/A')})")

if __name__ == "__main__":
    main()
