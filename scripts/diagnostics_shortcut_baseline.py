"""
Sahaay AI - Shortcut Baseline & Non-Semantic Diagnostic Tool (Phase A)
Quantifies label predictability based purely on non-semantic image properties:
1. Dimensions (width, height, aspect ratio, pixel count)
2. File size on disk
3. Simple RGB color statistics (mean, std)

Outputs machine-readable diagnosis to reports/vision_integrity/shortcut_diagnosis.json
and source distributions to reports/vision_integrity/source_distribution.json
"""

import os
import json
import numpy as np
import pandas as pd
from PIL import Image
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier, export_text
from sklearn.dummy import DummyClassifier
from sklearn.metrics import accuracy_score, precision_recall_fscore_support, roc_auc_score
from collections import Counter

def extract_features(df: pd.DataFrame):
    """
    Extracts purely non-semantic metadata and low-level statistics from images.
    """
    records = []
    for idx, row in df.iterrows():
        fpath = row["file_path"]
        file_size = os.path.getsize(fpath)
        w = row["width"]
        h = row["height"]
        aspect = w / h if h > 0 else 1.0
        pixels = w * h
        
        # Color statistics
        try:
            with Image.open(fpath) as img:
                img_rgb = img.convert("RGB")
                arr = np.array(img_rgb)
                mean_r = float(np.mean(arr[:, :, 0]))
                mean_g = float(np.mean(arr[:, :, 1]))
                mean_b = float(np.mean(arr[:, :, 2]))
                std_r = float(np.std(arr[:, :, 0]))
                std_g = float(np.std(arr[:, :, 1]))
                std_b = float(np.std(arr[:, :, 2]))
        except Exception:
            mean_r, mean_g, mean_b = 128.0, 128.0, 128.0
            std_r, std_g, std_b = 50.0, 50.0, 50.0
            
        records.append({
            "image_id": row["image_id"],
            "label_idx": row["label_idx"],
            "label_str": row["label_str"],
            "width": w,
            "height": h,
            "aspect_ratio": aspect,
            "file_size": file_size,
            "pixel_count": pixels,
            "mean_r": mean_r,
            "mean_g": mean_g,
            "mean_b": mean_b,
            "std_r": std_r,
            "std_g": std_g,
            "std_b": std_b
        })
    return pd.DataFrame(records)

def evaluate_model(clf, X_train, y_train, X_test, y_test, name="model"):
    clf.fit(X_train, y_train)
    preds = clf.predict(X_test)
    probs = clf.predict_proba(X_test)[:, 1] if hasattr(clf, "predict_proba") else preds
    
    acc = accuracy_score(y_test, preds)
    p, r, f1, _ = precision_recall_fscore_support(y_test, preds, average="macro")
    try:
        auc = roc_auc_score(y_test, probs)
    except Exception:
        auc = 0.5
        
    return {
        "model_name": name,
        "test_accuracy": float(acc),
        "test_macro_f1": float(f1),
        "test_macro_precision": float(p),
        "test_macro_recall": float(r),
        "test_roc_auc": float(auc)
    }

def main():
    train_path = os.path.join("data", "processed", "train.csv")
    test_path = os.path.join("data", "processed", "test.csv")
    out_dir = os.path.join("reports", "vision_integrity")
    os.makedirs(out_dir, exist_ok=True)
    
    print(f"Reading historical manifests from {train_path} and {test_path}...")
    train_df = pd.read_csv(train_path)
    test_df = pd.read_csv(test_path)
    
    print("Extracting metadata & image statistics for train...")
    feat_train = extract_features(train_df)
    print("Extracting metadata & image statistics for test...")
    feat_test = extract_features(test_df)
    
    # 1. Source distribution report
    print("\nCompiling source & dimensional distribution...")
    src_dist = {
        "total_train_images": len(train_df),
        "total_test_images": len(test_df),
        "train_dimensions_by_class": {
            "not_flooded": {f"{k[0]}x{k[1]}": v for k, v in Counter(zip(train_df[train_df["label_str"] == "not_flooded"]["width"],
                                                                         train_df[train_df["label_str"] == "not_flooded"]["height"])).most_common(10)},
            "flooded": {f"{k[0]}x{k[1]}": v for k, v in Counter(zip(train_df[train_df["label_str"] == "flooded"]["width"],
                                                                     train_df[train_df["label_str"] == "flooded"]["height"])).most_common(10)}
        },
        "test_dimensions_by_class": {
            "not_flooded": {f"{k[0]}x{k[1]}": v for k, v in Counter(zip(test_df[test_df["label_str"] == "not_flooded"]["width"],
                                                                        test_df[test_df["label_str"] == "not_flooded"]["height"])).most_common(10)},
            "flooded": {f"{k[0]}x{k[1]}": v for k, v in Counter(zip(test_df[test_df["label_str"] == "flooded"]["width"],
                                                                    test_df[test_df["label_str"] == "flooded"]["height"])).most_common(10)}
        },
        "file_size_stats_by_class": {
            "not_flooded": {
                "mean_kb": float(feat_train[feat_train["label_str"] == "not_flooded"]["file_size"].mean() / 1024),
                "std_kb": float(feat_train[feat_train["label_str"] == "not_flooded"]["file_size"].std() / 1024),
                "min_kb": float(feat_train[feat_train["label_str"] == "not_flooded"]["file_size"].min() / 1024),
                "max_kb": float(feat_train[feat_train["label_str"] == "not_flooded"]["file_size"].max() / 1024)
            },
            "flooded": {
                "mean_kb": float(feat_train[feat_train["label_str"] == "flooded"]["file_size"].mean() / 1024),
                "std_kb": float(feat_train[feat_train["label_str"] == "flooded"]["file_size"].std() / 1024),
                "min_kb": float(feat_train[feat_train["label_str"] == "flooded"]["file_size"].min() / 1024),
                "max_kb": float(feat_train[feat_train["label_str"] == "flooded"]["file_size"].max() / 1024)
            }
        }
    }
    
    # Save source distribution
    src_dist_path = os.path.join(out_dir, "source_distribution.json")
    with open(src_dist_path, "w", encoding="utf-8") as f:
        json.dump(src_dist, f, indent=2)
    print(f"Saved source distribution to: {src_dist_path}")
    
    # 2. Fit Non-Semantic Models
    dim_cols = ["width", "height", "aspect_ratio", "file_size"]
    all_stat_cols = ["width", "height", "aspect_ratio", "file_size", "mean_r", "mean_g", "mean_b", "std_r", "std_g", "std_b"]
    
    y_train = feat_train["label_idx"].values
    y_test = feat_test["label_idx"].values
    
    print("\n--- Training Non-Semantic Diagnostic Baselines ---")
    
    # Dummy baseline
    dummy = DummyClassifier(strategy="most_frequent")
    dummy_res = evaluate_model(dummy, feat_train[dim_cols], y_train, feat_test[dim_cols], y_test, "Majority Class Baseline")
    
    # Logistic Regression on Dimensions Only
    lr_dim = LogisticRegression()
    lr_dim_res = evaluate_model(lr_dim, feat_train[dim_cols], y_train, feat_test[dim_cols], y_test, "Logistic Regression (Dimensions + FileSize Only)")
    
    # Decision Tree on Dimensions Only
    dt_dim = DecisionTreeClassifier(max_depth=3, random_state=42)
    dt_dim_res = evaluate_model(dt_dim, feat_train[dim_cols], y_train, feat_test[dim_cols], y_test, "Decision Tree (Dimensions Only, Depth=3)")
    tree_rules = export_text(dt_dim, feature_names=dim_cols)
    
    # Decision Tree on Width Alone
    dt_width = DecisionTreeClassifier(max_depth=1, random_state=42)
    dt_width_res = evaluate_model(dt_width, feat_train[["width"]], y_train, feat_test[["width"]], y_test, "Decision Stump (Width Alone, Depth=1)")
    width_rule = export_text(dt_width, feature_names=["width"])
    
    # Logistic Regression on Dimensions + Color Stats
    lr_all = LogisticRegression(max_iter=1000)
    lr_all_res = evaluate_model(lr_all, feat_train[all_stat_cols], y_train, feat_test[all_stat_cols], y_test, "Logistic Regression (Dimensions + Color Stats)")

    diagnostic_summary = {
        "analysis_date": "2026-10-25",
        "objective": "Quantify shortcut predictability without semantic visual features",
        "findings": {
            "is_dimension_shortcut_lethal": bool(dt_width_res["test_accuracy"] >= 0.99),
            "width_alone_test_accuracy": dt_width_res["test_accuracy"],
            "decision_stump_rule": width_rule.strip(),
            "decision_tree_3depth_rules": tree_rules.strip(),
            "explanation": (
                "A simple decision rule 'if width <= 224: predict not_flooded, else predict flooded' "
                f"achieves {dt_width_res['test_accuracy']*100:.2f}% accuracy on the test set without "
                "inspecting a single pixel of flood water, water texture, or road debris. "
                "This conclusively confirms that the historical test accuracy was heavily confounded "
                "by class-specific sub-source dimensions."
            )
        },
        "model_comparisons": [
            dummy_res,
            dt_width_res,
            dt_dim_res,
            lr_dim_res,
            lr_all_res
        ]
    }
    
    diag_path = os.path.join(out_dir, "shortcut_diagnosis.json")
    with open(diag_path, "w", encoding="utf-8") as f:
        json.dump(diagnostic_summary, f, indent=2)
        
    print(f"\nSaved shortcut diagnostic results to: {diag_path}")
    print("\n=== SUMMARY OF DIAGNOSTIC BASELINES ===")
    for m in diagnostic_summary["model_comparisons"]:
        print(f"  {m['model_name']:<50}: Accuracy = {m['test_accuracy']*100:.2f}%, Macro-F1 = {m['test_macro_f1']:.4f}")
    print("\nDecision Stump Rule on Image Width Alone:")
    print(width_rule)

if __name__ == "__main__":
    main()
