"""
Sahaay AI - External Baseline Evaluation Diagnostic (Phase A)
Evaluates the historical checkpoint against external ground-level flood images from Clemson FloodIMG,
verifying zero MD5 overlap with the training data and recording confidence distributions.
"""

import os
import json
import hashlib
import numpy as np
from PIL import Image
import torch

from sahaay.vision.inference import FloodVisionInference

def compute_md5(file_path: str) -> str:
    hasher = hashlib.md5()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()

def main():
    checkpoint_path = os.path.join("models", "vision", "best_model.pt")
    clemson_dir = r"C:\Users\MahendraReddy\.cache\kagglehub\datasets\hhrclemson\flooding-image-dataset\versions\5\Flood Images"
    out_dir = os.path.join("reports", "vision_integrity")
    os.makedirs(out_dir, exist_ok=True)
    
    # 1. Load historical training MD5s to guarantee zero overlap
    train_csv = os.path.join("data", "processed", "train.csv")
    import pandas as pd
    train_df = pd.read_csv(train_csv)
    train_md5s = set()
    for fp in train_df["file_path"]:
        train_md5s.add(compute_md5(fp))
        
    print(f"Loaded {len(train_md5s)} unique training MD5 hashes.")
    
    # 2. Select 200 random external images from Clemson
    all_clemson_files = sorted(os.listdir(clemson_dir))
    np.random.seed(42)
    selected_files = np.random.choice(all_clemson_files, size=200, replace=False)
    
    # 3. Check for any overlap
    overlapping = []
    clean_sample = []
    for fn in selected_files:
        fp = os.path.join(clemson_dir, fn)
        h = compute_md5(fp)
        if h in train_md5s:
            overlapping.append((fn, h))
        else:
            clean_sample.append((fn, fp, h))
            
    print(f"Selected 200 Clemson images. Overlapping with training set: {len(overlapping)}")
    
    # 4. Evaluate using historical checkpoint
    device_name = "cuda" if torch.cuda.is_available() else "cpu"
    service = FloodVisionInference(checkpoint_path=checkpoint_path, device_name=device_name)
    
    results = []
    confidences = []
    correct_count = 0
    
    for fn, fp, h in clean_sample:
        try:
            with Image.open(fp) as im:
                res = service.predict(im)
            pred_cls = res["predicted_class"]
            conf = res["confidence"]
            is_correct = (pred_cls == "flooded")
            if is_correct:
                correct_count += 1
            confidences.append(conf)
            results.append({
                "filename": fn,
                "md5": h,
                "true_label": "flooded",
                "predicted_label": pred_cls,
                "confidence": conf,
                "is_correct": is_correct
            })
        except Exception as e:
            print(f"Error evaluating {fn}: {e}")
            
    accuracy = correct_count / len(clean_sample) if clean_sample else 0.0
    mean_conf = float(np.mean(confidences))
    std_conf = float(np.std(confidences))
    
    report = {
        "evaluation_date": "2026-10-25",
        "dataset_name": "Clemson FloodIMG (External Ground-Level)",
        "source_path": clemson_dir,
        "total_evaluated": len(clean_sample),
        "overlapping_with_training": len(overlapping),
        "accuracy_on_external_positives": accuracy,
        "mean_confidence": mean_conf,
        "std_confidence": std_conf,
        "confidence_percentiles": {
            "p25": float(np.percentile(confidences, 25)),
            "p50_median": float(np.percentile(confidences, 50)),
            "p75": float(np.percentile(confidences, 75)),
            "p95": float(np.percentile(confidences, 95))
        },
        "sample_predictions": results[:10]
    }
    
    out_file = os.path.join(out_dir, "external_clemson_evaluation.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
        
    print(f"\nExternal Clemson Evaluation Complete!")
    print(f"Accuracy on 200 external flood positives: {accuracy*100:.2f}%")
    print(f"Mean confidence: {mean_conf:.4f} (std: {std_conf:.4f})")
    print(f"Report saved to: {out_file}")

if __name__ == "__main__":
    main()
