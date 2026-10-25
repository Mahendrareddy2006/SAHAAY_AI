"""
Diagnostics: Shortcut Baseline on Dataset Manifest V3
Trains simple decision stumps on image width, height, aspect ratio,
and file size to evaluate whether dimensional shortcuts can predict labels.
"""

import os
import json
import numpy as np
import pandas as pd
from sklearn.tree import DecisionTreeClassifier
from sklearn.metrics import accuracy_score, precision_recall_fscore_support, roc_auc_score

def evaluate_stump(train_df, val_df, test_df, feature_cols, name):
    X_train = train_df[feature_cols].values
    y_train = train_df['label'].values

    X_val = val_df[feature_cols].values
    y_val = val_df['label'].values

    X_test = test_df[feature_cols].values
    y_test = test_df['label'].values

    # Train a shallow decision tree (depth 2)
    clf = DecisionTreeClassifier(max_depth=2, random_state=42)
    clf.fit(X_train, y_train)

    train_preds = clf.predict(X_train)
    val_preds = clf.predict(X_val)
    test_preds = clf.predict(X_test)
    test_probs = clf.predict_proba(X_test)[:, 1]

    acc_train = accuracy_score(y_train, train_preds)
    acc_val = accuracy_score(y_val, val_preds)
    acc_test = accuracy_score(y_test, test_preds)
    
    p, r, f1, _ = precision_recall_fscore_support(y_test, test_preds, average='binary', zero_division=0)
    try:
        auc = roc_auc_score(y_test, test_probs)
    except Exception:
        auc = 0.5

    return {
        "features": feature_cols,
        "train_accuracy": round(float(acc_train), 4),
        "val_accuracy": round(float(acc_val), 4),
        "test_accuracy": round(float(acc_test), 4),
        "test_precision": round(float(p), 4),
        "test_recall": round(float(r), 4),
        "test_macro_f1": round(float(f1), 4),
        "test_roc_auc": round(float(auc), 4)
    }

def main():
    train_df = pd.read_csv("data/processed/manifest_v3/train_v3.csv")
    val_df = pd.read_csv("data/processed/manifest_v3/val_v3.csv")
    test_df = pd.read_csv("data/processed/manifest_v3/test_v3.csv")

    results = {}
    results["width_only"] = evaluate_stump(train_df, val_df, test_df, ["width"], "width_only")
    results["dimensions_only"] = evaluate_stump(train_df, val_df, test_df, ["width", "height"], "dimensions_only")
    results["all_metadata_features"] = evaluate_stump(train_df, val_df, test_df, ["width", "height", "aspect_ratio", "file_size_kb"], "all_metadata")

    out_path = "reports/vision_integrity/shortcut_diagnosis_v3.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)

    print("\n--- Shortcut Diagnosis on Manifest V3 ---")
    for k, v in results.items():
        print(f"{k}: Test Acc = {v['test_accuracy']:.4f}, Macro-F1 = {v['test_macro_f1']:.4f}, AUC = {v['test_roc_auc']:.4f}")

if __name__ == "__main__":
    main()
