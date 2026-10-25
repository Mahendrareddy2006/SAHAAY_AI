"""
Diagnostics: Distribution Analysis for Shortcut-Resistant V3 Dataset
Analyzes dimensions, file size, compression (JPEG quality estimation),
and color statistics across candidate flood and non-flood sources.
"""

import os
import glob
import json
import numpy as np
from PIL import Image

def get_all_images(base_dir, subpattern):
    pattern = os.path.join(base_dir, "**", subpattern, "*")
    files = [f for f in glob.glob(pattern, recursive=True) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    return files

def analyze_files(files, sample_limit=None):
    if sample_limit and len(files) > sample_limit:
        files = files[:sample_limit]
        
    widths = []
    heights = []
    aspect_ratios = []
    file_sizes_kb = []
    r_means = []
    g_means = []
    b_means = []
    r_stds = []
    g_stds = []
    b_stds = []
    
    for f in files:
        try:
            sz_kb = os.path.getsize(f) / 1024.0
            with Image.open(f) as img:
                w, h = img.size
                widths.append(w)
                heights.append(h)
                aspect_ratios.append(round(w / h, 2))
                file_sizes_kb.append(sz_kb)
                
                # Color stats
                rgb = img.convert('RGB')
                arr = np.array(rgb, dtype=np.float32)
                r_means.append(float(np.mean(arr[:, :, 0])))
                g_means.append(float(np.mean(arr[:, :, 1])))
                b_means.append(float(np.mean(arr[:, :, 2])))
                r_stds.append(float(np.std(arr[:, :, 0])))
                g_stds.append(float(np.std(arr[:, :, 1])))
                b_stds.append(float(np.std(arr[:, :, 2])))
        except Exception:
            continue
            
    return {
        "count": len(widths),
        "width": {
            "mean": float(np.mean(widths)),
            "std": float(np.std(widths)),
            "min": int(np.min(widths)),
            "p25": float(np.percentile(widths, 25)),
            "p50": float(np.percentile(widths, 50)),
            "p75": float(np.percentile(widths, 75)),
            "max": int(np.max(widths))
        },
        "height": {
            "mean": float(np.mean(heights)),
            "std": float(np.std(heights)),
            "min": int(np.min(heights)),
            "p25": float(np.percentile(heights, 25)),
            "p50": float(np.percentile(heights, 50)),
            "p75": float(np.percentile(heights, 75)),
            "max": int(np.max(heights))
        },
        "aspect_ratio": {
            "mean": float(np.mean(aspect_ratios)),
            "std": float(np.std(aspect_ratios)),
            "min": float(np.min(aspect_ratios)),
            "max": float(np.max(aspect_ratios))
        },
        "file_size_kb": {
            "mean": float(np.mean(file_sizes_kb)),
            "std": float(np.std(file_sizes_kb)),
            "min": float(np.min(file_sizes_kb)),
            "max": float(np.max(file_sizes_kb))
        },
        "color_stats": {
            "r_mean": float(np.mean(r_means)),
            "g_mean": float(np.mean(g_means)),
            "b_mean": float(np.mean(b_means)),
            "r_std": float(np.mean(r_stds)),
            "g_std": float(np.mean(g_stds)),
            "b_std": float(np.mean(b_stds))
        }
    }

def main():
    road_base = r"C:\Users\MahendraReddy\.cache\kagglehub\datasets\virenbr11\pothole-and-plain-rode-images\versions\1\My Dataset"
    clemson_dir = r"C:\Users\MahendraReddy\.cache\kagglehub\datasets\hhrclemson\flooding-image-dataset\versions\5\Flood Images"

    pothole_files = get_all_images(road_base, "Pothole")
    plain_files = get_all_images(road_base, "Plain")
    clemson_files = [f for f in glob.glob(os.path.join(clemson_dir, "*")) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]

    print(f"Found {len(pothole_files)} pothole/puddle hard negative images.")
    print(f"Found {len(plain_files)} plain road negative images.")
    print(f"Found {len(clemson_files)} Clemson flood images.")

    print("Analyzing Virenbr11 Potholes (Hard Negatives)...")
    pothole_stats = analyze_files(pothole_files)

    print("Analyzing Virenbr11 Plain Roads (Dry Negatives)...")
    plain_stats = analyze_files(plain_files)

    print("Analyzing Clemson Flood (Sampling 700)...")
    clemson_stats = analyze_files(clemson_files, sample_limit=700)

    combined_neg_widths = []
    # Combined report
    results = {
        "non_flood_potholes_hard_negatives": pothole_stats,
        "non_flood_plain_roads": plain_stats,
        "flood_clemson_positives": clemson_stats
    }

    out_path = "reports/vision_integrity/v3_source_distribution_analysis.json"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"Saved distribution analysis to {out_path}")
    print("\n--- Summary Comparison ---")
    print(f"Potholes (Wet Negatives): W_mean={pothole_stats['width']['mean']:.1f}, H_mean={pothole_stats['height']['mean']:.1f}, FileSize_mean={pothole_stats['file_size_kb']['mean']:.1f} KB")
    print(f"Plain (Dry Negatives):   W_mean={plain_stats['width']['mean']:.1f}, H_mean={plain_stats['height']['mean']:.1f}, FileSize_mean={plain_stats['file_size_kb']['mean']:.1f} KB")
    print(f"Clemson (Flooded):       W_mean={clemson_stats['width']['mean']:.1f}, H_mean={clemson_stats['height']['mean']:.1f}, FileSize_mean={clemson_stats['file_size_kb']['mean']:.1f} KB")

if __name__ == "__main__":
    main()
