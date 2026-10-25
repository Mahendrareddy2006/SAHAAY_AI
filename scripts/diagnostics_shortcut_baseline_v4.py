"""
Phase 3: Metadata-Only Diagnostic Baseline on Manifest V4
Evaluates non-semantic metadata predictability (width, height, aspect ratio, file size)
on the leakage-free, globally clustered Manifest V4.
"""

import os
import json
import numpy as np
import pandas as pd
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, precision_recall_fscore_support, roc_auc_score

def evaluate_features(train_df, val_df, test_df, features, clf):
    X_train = train_df[features].values
    y_train = train_df['label'].values
    X_val = val_df[features].values
    y_val = val_df['label'].values
    X_test = test_df[features].values
    y_test = test_df['label'].values

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
        "features": features,
        "train_accuracy": round(float(acc_train), 4),
        "val_accuracy": round(float(acc_val), 4),
        "test_accuracy": round(float(acc_test), 4),
        "test_precision": round(float(p), 4),
        "test_recall": round(float(r), 4),
        "test_macro_f1": round(float(f1), 4),
        "test_roc_auc": round(float(auc), 4)
    }

def main():
    train_df = pd.read_csv("data/processed/manifest_v4/train_v4.csv")
    val_df = pd.read_csv("data/processed/manifest_v4/val_v4.csv")
    test_df = pd.read_csv("data/processed/manifest_v4/test_v4.csv")

    results = {}
    
    # 1. Individual feature stumps
    results["width_only"] = evaluate_features(train_df, val_df, test_df, ["width"], DecisionTreeClassifier(max_depth=2, random_state=42))
    results["height_only"] = evaluate_features(train_df, val_df, test_df, ["height"], DecisionTreeClassifier(max_depth=2, random_state=42))
    results["file_size_only"] = evaluate_features(train_df, val_df, test_df, ["file_size_kb"], DecisionTreeClassifier(max_depth=2, random_state=42))
    results["dimensions_only"] = evaluate_features(train_df, val_df, test_df, ["width", "height"], DecisionTreeClassifier(max_depth=2, random_state=42))

    # 2. Random Forest on all non-semantic features
    all_features = ["width", "height", "aspect_ratio", "file_size_kb"]
    rf = RandomForestClassifier(n_estimators=100, max_depth=4, random_state=42)
    results["all_metadata_rf"] = evaluate_features(train_df, val_df, test_df, all_features, rf)
    
    # Feature importances
    rf.fit(train_df[all_features].values, train_df['label'].values)
    results["feature_importances"] = dict(zip(all_features, [round(float(x), 4) for x in rf.feature_importances_]))

    out_path = "reports/vision_integrity/shortcut_diagnosis_v4.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print("\n--- Manifest V4 Metadata Diagnostic Results ---")
    for k, v in results.items():
        if isinstance(v, dict) and "test_accuracy" in v:
            print(f"{k:<20}: Test Acc = {v['test_accuracy']:.4f} | Macro-F1 = {v['test_macro_f1']:.4f} | AUC = {v['test_roc_auc']:.4f}")
    print(f"Feature Importances: {results['feature_importances']}")
    print(f"Report saved to: {out_path}")

if __name__ == "__main__":
    main()
