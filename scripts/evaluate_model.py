"""
Sahaay AI - Test Set Evaluation Script
Runs rigorous evaluation on the untouched held-out test set.
"""

import os
import sys
import json

sys.path.insert(0, os.path.abspath("src"))

from sahaay.vision.evaluate import evaluate_checkpoint

def main():
    checkpoint_path = os.path.join("models", "vision", "best_model.pt")
    test_csv = os.path.join("data", "processed", "test.csv")
    output_json = os.path.join("models", "vision", "test_evaluation_results.json")
    
    print("=" * 60)
    print("SAHAAY AI — HELD-OUT TEST SET EVALUATION")
    print(f"Checkpoint: {checkpoint_path}")
    print(f"Test Set:   {test_csv}")
    print("=" * 60)
    
    results = evaluate_checkpoint(
        checkpoint_path=checkpoint_path,
        test_csv=test_csv,
        device_name="auto"
    )
    
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
        
    print(f"\n--- Evaluation Results ---")
    print(f"Test Accuracy:  {results['accuracy']:.4f}")
    print(f"Macro-F1:       {results['macro_f1']:.4f}")
    print(f"Not-Flooded F1: {results['metrics_by_class']['not_flooded']['f1_score']:.4f} (Precision: {results['metrics_by_class']['not_flooded']['precision']:.4f}, Recall: {results['metrics_by_class']['not_flooded']['recall']:.4f})")
    print(f"Flooded F1:     {results['metrics_by_class']['flooded']['f1_score']:.4f} (Precision: {results['metrics_by_class']['flooded']['precision']:.4f}, Recall: {results['metrics_by_class']['flooded']['recall']:.4f})")
    print(f"Confusion Matrix:")
    print(f"  TN={results['confusion_matrix']['true_negatives']} | FP={results['confusion_matrix']['false_positives']}")
    print(f"  FN={results['confusion_matrix']['false_negatives']} | TP={results['confusion_matrix']['true_positives']}")
    print(f"Avg Latency:    {results['inference_benchmark']['average_latency_ms_per_image']} ms / image")
    print(f"Checkpoint Size: {results['inference_benchmark']['checkpoint_size_mb']} MB")
    print(f"\nFull evaluation report saved to: {output_json}")

if __name__ == "__main__":
    main()
