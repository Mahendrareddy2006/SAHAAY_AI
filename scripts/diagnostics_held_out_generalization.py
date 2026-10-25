"""
Step 2: Held-Out Multi-Source Generalization Experiment
Evaluates frozen Model V3 Clean and Model V3 Monsoon checkpoints across multiple sources:
1. Held-out V3 Test Set (Clemson Flood, Virenbr11 Plain, Virenbr11 Potholes)
2. External Held-Out Roham1 Cohort (Filtered for zero overlap with Train V3 / Val V3)
   - Roham1 Flood (held-out flood photography)
   - Roham1 Non-Flood (held-out dry / urban scenes)

Reports per-source metrics:
- Precision, Recall, Macro-F1, FPR, FNR, Confusion Matrix, 95% Wilson Confidence Intervals.
Documents the extent and boundaries of source-independent generalization.
"""

import os
import sys
import json
import math
import hashlib
import numpy as np
import pandas as pd
from PIL import Image
import torch
import torch.nn.functional as F
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support, accuracy_score, roc_auc_score

sys.path.insert(0, os.path.abspath("src"))

from sahaay.vision.model import create_flood_classifier
from sahaay.vision.transforms import get_eval_transforms

def compute_md5(filepath):
    hasher = hashlib.md5()
    with open(filepath, 'rb') as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()

def compute_dhash(image, hash_size=8):
    img = image.convert('L').resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)
    pixels = np.array(img, dtype=np.int32)
    diff = pixels[:, 1:] > pixels[:, :-1]
    decimal_val = 0
    for bit in diff.flatten():
        decimal_val = (decimal_val << 1) | int(bit)
    return f"{decimal_val:016x}"

def hamming_distance(h1, h2):
    return bin(int(h1, 16) ^ int(h2, 16)).count('1')

def compute_wilson_ci(p, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    denom = 1 + (z**2) / n
    centre = (p + (z**2) / (2 * n)) / denom
    spread = (z / denom) * math.sqrt((p * (1 - p) / n) + (z**2) / (4 * (n**2)))
    return round(max(0.0, centre - spread), 4), round(min(1.0, centre + spread), 4)

def evaluate_cohort(model, eval_tf, image_paths, labels, device):
    probs = []
    preds = []
    with torch.no_grad():
        for p in image_paths:
            with Image.open(p) as im:
                rgb = im.convert("RGB")
            t = eval_tf(rgb).unsqueeze(0).to(device)
            out = model(t)
            prob = F.softmax(out, dim=1).cpu().numpy()[0]
            probs.append(float(prob[1]))
            preds.append(int(np.argmax(prob)))
            
    y_pred = np.array(preds)
    y_prob = np.array(probs)
    y_true = np.array(labels)
    
    acc = accuracy_score(y_true, y_pred)
    ci_low, ci_high = compute_wilson_ci(acc, len(y_true))
    p, r, f1, _ = precision_recall_fscore_support(y_true, y_pred, average=None, labels=[0, 1], zero_division=0)
    
    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    tn, fp, fn, tp = cm.ravel()
    fpr = float(fp / (fp + tn)) if (fp + tn) > 0 else 0.0
    fnr = float(fn / (fn + tp)) if (fn + tp) > 0 else 0.0
    
    try:
        auc = float(roc_auc_score(y_true, y_prob)) if len(np.unique(y_true)) > 1 else None
    except Exception:
        auc = None

    return {
        "sample_count": len(y_true),
        "accuracy": round(float(acc), 4),
        "accuracy_ci_95": [ci_low, ci_high],
        "macro_f1": round(float(np.mean(f1)), 4),
        "roc_auc": round(auc, 4) if auc is not None else "N/A (single class)",
        "false_positive_rate": round(fpr, 4),
        "false_negative_rate": round(fnr, 4),
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        "per_class": {
            "non_flood": {"precision": round(float(p[0]), 4), "recall": round(float(r[0]), 4), "f1": round(float(f1[0]), 4), "support": int(tn + fp)},
            "flood": {"precision": round(float(p[1]), 4), "recall": round(float(r[1]), 4), "f1": round(float(f1[1]), 4), "support": int(tp + fn)}
        },
        "mean_flood_probability": round(float(np.mean(y_prob)), 4),
        "median_flood_probability": round(float(np.median(y_prob)), 4)
    }

def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    eval_tf = get_eval_transforms(224)

    # 1. Load V3 Train and Val hashes to ensure ZERO overlap with any held-out sample
    train_v3 = pd.read_csv("data/processed/manifest_v3/train_v3.csv")
    val_v3 = pd.read_csv("data/processed/manifest_v3/val_v3.csv")
    test_v3 = pd.read_csv("data/processed/manifest_v3/test_v3.csv")

    forbidden_md5s = set(train_v3['md5']).union(set(val_v3['md5']))
    forbidden_dhashes = set(train_v3['dhash']).union(set(val_v3['dhash']))
    print(f"Loaded {len(forbidden_md5s)} forbidden MD5s from Train V3 and Val V3.")

    # 2. Curate completely unseen held-out cohort from Roham1
    roham1_dir = r"C:\Users\MahendraReddy\.cache\kagglehub\datasets\roham1\flood-classification-dataset\versions\1"
    r_flood_dir = os.path.join(roham1_dir, "Flood")
    r_non_flood_dir = os.path.join(roham1_dir, "Non_Flood")

    np.random.seed(42)
    r_flood_all = sorted(os.listdir(r_flood_dir))
    r_non_flood_all = sorted(os.listdir(r_non_flood_dir))
    np.random.shuffle(r_flood_all)
    np.random.shuffle(r_non_flood_all)

    # Collect 150 strictly non-overlapping flood and 150 non-overlapping non-flood images
    held_out_roham1_flood = []
    for fn in r_flood_all:
        if len(held_out_roham1_flood) >= 150:
            break
        fp = os.path.join(r_flood_dir, fn)
        try:
            m = compute_md5(fp)
            if m in forbidden_md5s:
                continue
            with Image.open(fp) as im:
                dh = compute_dhash(im)
            is_dup = False
            for fdh in forbidden_dhashes:
                if hamming_distance(dh, fdh) <= 2:
                    is_dup = True
                    break
            if not is_dup:
                held_out_roham1_flood.append((fp, 1, "roham1_flood", "held_out_flood_street"))
        except Exception:
            continue

    held_out_roham1_non_flood = []
    for fn in r_non_flood_all:
        if len(held_out_roham1_non_flood) >= 150:
            break
        fp = os.path.join(r_non_flood_dir, fn)
        try:
            m = compute_md5(fp)
            if m in forbidden_md5s:
                continue
            with Image.open(fp) as im:
                dh = compute_dhash(im)
            is_dup = False
            for fdh in forbidden_dhashes:
                if hamming_distance(dh, fdh) <= 2:
                    is_dup = True
                    break
            if not is_dup:
                held_out_roham1_non_flood.append((fp, 0, "roham1_non_flood", "held_out_non_flood_scene"))
        except Exception:
            continue

    print(f"Curated independent Roham1 held-out cohort: {len(held_out_roham1_flood)} floods, {len(held_out_roham1_non_flood)} non-floods.")

    # 3. Load Frozen Models
    models = {}
    for mname, mpath in [
        ("model_v3_clean", "models/vision/v3/model_v3_clean.pt"),
        ("model_v3_monsoon", "models/vision/v3/model_v3_monsoon.pt"),
        ("model_v2_historical", "models/vision/v2/model_v2.pt")
    ]:
        if os.path.exists(mpath):
            m = create_flood_classifier("mobilenet_v3_small", num_classes=2, pretrained=False)
            ckpt = torch.load(mpath, map_location=device)
            sd = ckpt["model_state_dict"] if isinstance(ckpt, dict) and "model_state_dict" in ckpt else ckpt
            m.load_state_dict(sd)
            m.to(device)
            m.eval()
            models[mname] = m

    report = {
        "experiment_title": "Multi-Source Held-Out Generalization Evaluation",
        "evaluation_protocol": "Frozen models evaluated across unseen source partitions",
        "per_source_breakdown": {},
        "overall_held_out_roham1": {}
    }

    # Evaluate per source on Test V3
    print("\n" + "=" * 70)
    print("EVALUATING PER-SOURCE GENERALIZATION ON RESERVED TEST V3")
    print("=" * 70)
    sources = test_v3['source_dataset'].unique()
    for src in sources:
        sub_df = test_v3[test_v3['source_dataset'] == src]
        paths = sub_df['file_path'].tolist()
        lbls = sub_df['label_idx' if 'label_idx' in sub_df.columns else 'label'].tolist()
        
        report["per_source_breakdown"][src] = {
            "source_dataset": src,
            "sample_count": len(paths),
            "ground_truth_label": int(lbls[0]) if len(set(lbls)) == 1 else "mixed",
            "models": {}
        }
        print(f"\n--- Source: {src} (N={len(paths)}) ---")
        for mname, model in models.items():
            res = evaluate_cohort(model, eval_tf, paths, lbls, device)
            report["per_source_breakdown"][src]["models"][mname] = res
            print(f"  {mname:<22}: Acc={res['accuracy']:.4f} (95% CI: {res['accuracy_ci_95'][0]}-{res['accuracy_ci_95'][1]}), FPR={res['false_positive_rate']:.4f}, FNR={res['false_negative_rate']:.4f}")

    # Evaluate on held-out Roham1 cohort (mixed 150 floods + 150 non-floods)
    print("\n" + "=" * 70)
    print("EVALUATING ON INDEPENDENT HELD-OUT ROHAM1 SOURCE (N=300: 150 Flood, 150 Non-Flood)")
    print("=" * 70)
    r_all = held_out_roham1_flood + held_out_roham1_non_flood
    np.random.shuffle(r_all)
    r_paths = [x[0] for x in r_all]
    r_lbls = [x[1] for x in r_all]

    for mname, model in models.items():
        res = evaluate_cohort(model, eval_tf, r_paths, r_lbls, device)
        report["overall_held_out_roham1"][mname] = res
        print(f"  {mname:<22}: Acc={res['accuracy']:.4f} (95% CI: {res['accuracy_ci_95'][0]}-{res['accuracy_ci_95'][1]}), Macro-F1={res['macro_f1']:.4f}, FPR={res['false_positive_rate']:.4f}, FNR={res['false_negative_rate']:.4f}, AUC={res['roc_auc']}")

    # Save report
    out_path = "reports/vision_integrity/held_out_generalization_report.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"\nHeld-out generalization report saved to: {out_path}")

if __name__ == "__main__":
    main()
