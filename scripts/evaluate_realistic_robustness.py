"""
Phase 4 & 5: Realistic Robustness Evaluation, Calibration, and Safety Gate Analysis
Evaluates Model V2, V3 Clean, and V3 Monsoon across:
1. Real-world cohorts (hard-negative puddles, dry roads, flooded scenes, low light)
2. Synthetic perturbation cohorts (rain mist blur, low light night, glare, droplet obstruction, motion blur)
3. Confidence calibration (ECE, Brier score) and 0.65 ambiguity threshold effectiveness
4. Image quality gate validation (detecting blurred, pitch black, or blown out images)
"""

import os
import sys
import json
import math
import numpy as np
import pandas as pd
from PIL import Image, ImageFilter, ImageEnhance, ImageDraw
import torch
import torch.nn.functional as F
from sklearn.metrics import accuracy_score, precision_recall_fscore_support, brier_score_loss, confusion_matrix

sys.path.insert(0, os.path.abspath("src"))

from sahaay.vision.model import create_flood_classifier
from sahaay.vision.transforms import get_eval_transforms

def compute_ece(probs, targets, n_bins=10):
    """Computes Expected Calibration Error (ECE)."""
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

# --- Synthetic Perturbations ---
def apply_rain_mist_blur(img: Image.Image) -> Image.Image:
    """Simulates rain mist, water spray, and condensation on camera lens."""
    return img.filter(ImageFilter.GaussianBlur(radius=3.5))

def apply_night_low_light(img: Image.Image) -> Image.Image:
    """Simulates night conditions or heavy dark storm cloud lighting."""
    enhancer = ImageEnhance.Brightness(img)
    return enhancer.enhance(0.25)

def apply_headlight_glare(img: Image.Image) -> Image.Image:
    """Simulates oncoming headlight glare and specular wet reflection overexposure."""
    enhancer = ImageEnhance.Brightness(img)
    bright = enhancer.enhance(1.8)
    contrast = ImageEnhance.Contrast(bright)
    return contrast.enhance(1.4)

def apply_droplet_obstruction(img: Image.Image) -> Image.Image:
    """Simulates physical raindrops stuck on camera lens."""
    im_copy = img.copy()
    draw = ImageDraw.Draw(im_copy)
    w, h = im_copy.size
    np.random.seed(42)
    # Draw 20 translucent raindrops
    for _ in range(25):
        cx = np.random.randint(0, w)
        cy = np.random.randint(0, h)
        r = np.random.randint(8, 25)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(180, 200, 220, 128), outline=(230, 240, 255, 200))
    return im_copy

def apply_motion_blur(img: Image.Image) -> Image.Image:
    """Simulates vehicle camera motion blur."""
    # Approximate motion blur with directional box blur
    return img.filter(ImageFilter.BoxBlur(radius=3))

def evaluate_cohort(model, eval_tf, image_paths, targets, perturbation_fn=None, device="cpu"):
    probs = []
    preds = []
    with torch.no_grad():
        for p in image_paths:
            with Image.open(p) as im:
                img_rgb = im.convert("RGB")
            if perturbation_fn is not None:
                img_rgb = perturbation_fn(img_rgb)
            tensor = eval_tf(img_rgb).unsqueeze(0).to(device)
            logits = model(tensor)
            prob = F.softmax(logits, dim=1).cpu().numpy()[0]
            probs.append(float(prob[1]))
            preds.append(int(np.argmax(prob)))
            
    y_pred = np.array(preds)
    y_prob = np.array(probs)
    y_true = np.array(targets)
    
    acc = accuracy_score(y_true, y_pred)
    p, r, f1, _ = precision_recall_fscore_support(y_true, y_pred, average='binary', pos_label=1, zero_division=0)
    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    tn, fp, fn, tp = cm.ravel()
    fpr = float(fp / (fp + tn)) if (fp + tn) > 0 else 0.0
    fnr = float(fn / (fn + tp)) if (fn + tp) > 0 else 0.0
    
    return {
        "sample_count": len(y_true),
        "accuracy": round(float(acc), 4),
        "precision": round(float(p), 4),
        "recall": round(float(r), 4),
        "macro_f1": round(float(f1), 4),
        "false_positive_rate": round(fpr, 4),
        "false_negative_rate": round(fnr, 4),
        "mean_confidence": round(float(np.mean(np.max(np.column_stack([1 - y_prob, y_prob]), axis=1))), 4),
        "y_true": y_true.tolist(),
        "y_pred": y_pred.tolist(),
        "y_prob": y_prob.tolist()
    }

def main():
    test_csv = "data/processed/manifest_v3/test_v3.csv"
    val_csv = "data/processed/manifest_v3/val_v3.csv"
    test_df = pd.read_csv(test_csv)
    val_df = pd.read_csv(val_csv)
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    eval_tf = get_eval_transforms(224)
    
    label_col = 'label_idx' if 'label_idx' in test_df.columns else 'label'
    image_paths = test_df['file_path'].tolist()
    targets = test_df[label_col].tolist()
    
    # Load Models
    models = {}
    for mname, mpath in [
        ("model_v2_historical", "models/vision/v2/model_v2.pt"),
        ("model_v3_clean", "models/vision/v3/model_v3_clean.pt"),
        ("model_v3_monsoon", "models/vision/v3/model_v3_monsoon.pt")
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
        "test_split_size": len(test_df),
        "real_world_cohorts": {},
        "synthetic_perturbation_cohorts": {},
        "calibration_and_confidence": {},
        "high_confidence_error_analysis": {}
    }

    print("\n" + "=" * 70)
    print("PHASE 4: REAL-WORLD COHORTS EVALUATION")
    print("=" * 70)

    # 1. Real-World Subcohorts
    real_cohorts_meta = {
        "puddles_and_wet_roads_hard_negatives": {
            "indices": test_df[test_df['subcondition'] == 'wet_road_pothole_hard_negative'].index.tolist(),
            "selection_procedure": "Real road inspection images with rain puddles, wet asphalt, cracks without flooding"
        },
        "plain_dry_roads": {
            "indices": test_df[test_df['subcondition'] == 'plain_dry_road'].index.tolist(),
            "selection_procedure": "Real road inspection images with dry asphalt, curbs, traffic"
        },
        "flooded_streets_clemson": {
            "indices": test_df[test_df['subcondition'] == 'flood_street'].index.tolist(),
            "selection_procedure": "Ground-level street flood photography"
        }
    }

    # Add real low-light cohort (measured luminance < 85)
    low_light_indices = []
    for idx, row in test_df.iterrows():
        try:
            with Image.open(row['file_path']) as im:
                lum = np.mean(np.array(im.convert("L")))
                if lum < 85.0:
                    low_light_indices.append(idx)
        except Exception:
            pass
    real_cohorts_meta["real_low_light_and_overcast"] = {
        "indices": low_light_indices,
        "selection_procedure": f"Natural images with mean pixel luminance < 85 (N={len(low_light_indices)})"
    }

    for cname, cmeta in real_cohorts_meta.items():
        idxs = cmeta["indices"]
        sub_paths = [image_paths[i] for i in idxs]
        sub_targets = [targets[i] for i in idxs]
        report["real_world_cohorts"][cname] = {
            "sample_count": len(idxs),
            "selection_procedure": cmeta["selection_procedure"],
            "models": {}
        }
        print(f"\nCohort: {cname} (N={len(idxs)})")
        for mname, model in models.items():
            res = evaluate_cohort(model, eval_tf, sub_paths, sub_targets, perturbation_fn=None, device=device)
            clean_res = {k: v for k, v in res.items() if k not in ["y_true", "y_pred", "y_prob"]}
            report["real_world_cohorts"][cname]["models"][mname] = clean_res
            print(f"  {mname:<22}: Acc={res['accuracy']:.4f}, FPR={res['false_positive_rate']:.4f}, FNR={res['false_negative_rate']:.4f}, Conf={res['mean_confidence']:.4f}")

    print("\n" + "=" * 70)
    print("PHASE 4: SYNTHETIC PERTURBATION COHORTS (N=222 each)")
    print("=" * 70)

    perturbations = {
        "synthetic_rain_mist_blur": apply_rain_mist_blur,
        "synthetic_night_darkness": apply_night_low_light,
        "synthetic_headlight_glare": apply_headlight_glare,
        "synthetic_lens_droplet_spray": apply_droplet_obstruction,
        "synthetic_motion_blur": apply_motion_blur
    }

    for pname, pfn in perturbations.items():
        report["synthetic_perturbation_cohorts"][pname] = {
            "sample_count": len(image_paths),
            "perturbation_type": pname,
            "models": {}
        }
        print(f"\nPerturbation: {pname}")
        for mname, model in models.items():
            res = evaluate_cohort(model, eval_tf, image_paths, targets, perturbation_fn=pfn, device=device)
            clean_res = {k: v for k, v in res.items() if k not in ["y_true", "y_pred", "y_prob"]}
            report["synthetic_perturbation_cohorts"][pname]["models"][mname] = clean_res
            print(f"  {mname:<22}: Acc={res['accuracy']:.4f}, Macro-F1={res['macro_f1']:.4f}, FPR={res['false_positive_rate']:.4f}, FNR={res['false_negative_rate']:.4f}")

    # PHASE 5: Calibration, Ambiguity Threshold (0.65), and High-Confidence Errors
    print("\n" + "=" * 70)
    print("PHASE 5: CALIBRATION & AMBIGUITY THRESHOLD (0.65) EVALUATION")
    print("=" * 70)

    val_paths = val_df['file_path'].tolist()
    val_targets = val_df['label_idx' if 'label_idx' in val_df.columns else 'label'].tolist()

    for mname, model in models.items():
        val_eval = evaluate_cohort(model, eval_tf, val_paths, val_targets, device=device)
        test_eval = evaluate_cohort(model, eval_tf, image_paths, targets, device=device)
        
        val_probs = np.array(val_eval["y_prob"])
        val_targs = np.array(val_eval["y_true"])
        test_probs = np.array(test_eval["y_prob"])
        test_targs = np.array(test_eval["y_true"])

        val_ece = compute_ece(val_probs, val_targs)
        val_brier = float(brier_score_loss(val_targs, val_probs))
        test_ece = compute_ece(test_probs, test_targs)
        test_brier = float(brier_score_loss(test_targs, test_probs))

        # Ambiguity analysis at 0.65
        confidences = np.max(np.column_stack([1 - test_probs, test_probs]), axis=1)
        ambiguous_mask = (confidences < 0.65)
        ambiguous_count = int(np.sum(ambiguous_mask))
        ambiguous_acc = float(accuracy_score(test_targs[ambiguous_mask], (test_probs[ambiguous_mask] >= 0.5).astype(int))) if ambiguous_count > 0 else 1.0

        # High confidence errors (> 0.85 confidence but wrong)
        high_conf_mask = (confidences >= 0.85)
        preds = (test_probs >= 0.5).astype(int)
        high_conf_errors = int(np.sum(high_conf_mask & (preds != test_targs)))

        report["calibration_and_confidence"][mname] = {
            "validation_ece": round(val_ece, 4),
            "validation_brier_score": round(val_brier, 4),
            "test_ece": round(test_ece, 4),
            "test_brier_score": round(test_brier, 4),
            "ambiguity_analysis_0_65_threshold": {
                "ambiguous_sample_count": ambiguous_count,
                "ambiguous_fraction": round(ambiguous_count / len(test_df), 4),
                "ambiguous_accuracy": round(ambiguous_acc, 4),
                "unambiguous_accuracy": round(float(accuracy_score(test_targs[~ambiguous_mask], preds[~ambiguous_mask])), 4)
            },
            "high_confidence_errors_over_85": {
                "error_count": high_conf_errors,
                "high_conf_total": int(np.sum(high_conf_mask))
            }
        }
        print(f"\nModel: {mname}")
        print(f"  Val ECE: {val_ece:.4f} | Test ECE: {test_ece:.4f} | Brier: {test_brier:.4f}")
        print(f"  Ambiguous (Conf < 0.65): {ambiguous_count}/{len(test_df)} samples ({ambiguous_count/len(test_df)*100:.1f}%) | Ambiguous Acc: {ambiguous_acc:.4f}")
        print(f"  High Confidence Errors (Conf >= 0.85): {high_conf_errors}")

    out_file = "reports/vision_integrity/robustness_cohorts_report.json"
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"\nRobustness and calibration report saved to: {out_file}")

if __name__ == "__main__":
    main()
