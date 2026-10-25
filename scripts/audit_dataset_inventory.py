"""
Phase 2: Comprehensive Dataset Inventory for Vision V4
Scans and profiles all available local datasets:
1. virenbr11/pothole-and-plain-rode-images
2. hhrclemson/flooding-image-dataset
3. roham1/flood-classification-dataset
4. Downloads folders (FloodNet, EU-Flood)

Records:
- Source dataset, subfolder/category, license, provenance
- Total images, valid image counts
- Label distribution (positive / negative / single-class)
- Native dimension statistics (width, height, aspect ratio)
- Domain relevance (ground-level street vs arbitrary imagery)
"""

import os
import glob
import json
import numpy as np
from PIL import Image

def analyze_image_folder(folder_path, max_sample=1000):
    files = [f for f in glob.glob(os.path.join(folder_path, "*")) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    sample = files[:max_sample] if max_sample and len(files) > max_sample else files
    
    widths, heights, aspect_ratios, sizes_kb = [], [], [], []
    corrupt_count = 0
    
    for f in sample:
        try:
            sz = os.path.getsize(f) / 1024.0
            with Image.open(f) as im:
                w, h = im.size
                widths.append(w)
                heights.append(h)
                aspect_ratios.append(round(w / h, 2))
                sizes_kb.append(round(sz, 2))
        except Exception:
            corrupt_count += 1
            
    if not widths:
        return {"total_files": len(files), "valid_images": 0, "corrupt_images": corrupt_count}
        
    return {
        "total_files": len(files),
        "sampled_analyzed": len(widths),
        "corrupt_images": corrupt_count,
        "width": {
            "mean": round(float(np.mean(widths)), 1),
            "min": int(np.min(widths)),
            "max": int(np.max(widths))
        },
        "height": {
            "mean": round(float(np.mean(heights)), 1),
            "min": int(np.min(heights)),
            "max": int(np.max(heights))
        },
        "aspect_ratio": {
            "mean": round(float(np.mean(aspect_ratios)), 2),
            "min": round(float(np.min(aspect_ratios)), 2),
            "max": round(float(np.max(aspect_ratios)), 2)
        },
        "file_size_kb": {
            "mean": round(float(np.mean(sizes_kb)), 1),
            "min": round(float(np.min(sizes_kb)), 1),
            "max": round(float(np.max(sizes_kb)), 1)
        }
    }

def main():
    inventory = {
        "inventory_title": "Sahaay AI Vision V4 Dataset Inventory & Domain Audit",
        "sources": {}
    }

    # 1. Virenbr11
    viren_base = r"C:\Users\MahendraReddy\.cache\kagglehub\datasets\virenbr11\pothole-and-plain-rode-images\versions\1\My Dataset"
    plain_files = glob.glob(os.path.join(viren_base, "**", "Plain", "*"), recursive=True)
    pothole_files = glob.glob(os.path.join(viren_base, "**", "Pothole", "*"), recursive=True)
    
    inventory["sources"]["virenbr11_plain_roads"] = {
        "source_name": "virenbr11/pothole-and-plain-rode-images (Plain)",
        "provenance": "Kaggle Open Dataset (Road Pavement Surface Condition)",
        "license": "Open Database License (ODbL) / Public Domain",
        "ground_truth_class": "non_flood",
        "contains_both_classes": False,
        "domain_type": "Ground-level street photography (dry asphalt, lane markings, curbs, traffic)",
        "suitability_for_hard_negatives": "High (clean urban asphalt roads)",
        "statistics": analyze_image_folder(os.path.dirname(plain_files[0])) if plain_files else {}
    }
    inventory["sources"]["virenbr11_plain_roads"]["total_available_images"] = len(plain_files)

    inventory["sources"]["virenbr11_potholes_hard_negatives"] = {
        "source_name": "virenbr11/pothole-and-plain-rode-images (Pothole)",
        "provenance": "Kaggle Open Dataset (Road Pavement Surface Condition)",
        "license": "Open Database License (ODbL) / Public Domain",
        "ground_truth_class": "non_flood (hard negative)",
        "contains_both_classes": False,
        "domain_type": "Ground-level road inspection (rain puddles, water accumulation, asphalt cracks without inundation)",
        "suitability_for_hard_negatives": "Exceptional (direct hard-negative controls)",
        "statistics": analyze_image_folder(os.path.dirname(pothole_files[0])) if pothole_files else {}
    }
    inventory["sources"]["virenbr11_potholes_hard_negatives"]["total_available_images"] = len(pothole_files)

    # 2. Clemson FloodIMG
    clemson_dir = r"C:\Users\MahendraReddy\.cache\kagglehub\datasets\hhrclemson\flooding-image-dataset\versions\5\Flood Images"
    inventory["sources"]["clemson_floodimg"] = {
        "source_name": "Clemson University FloodIMG (hhrclemson/flooding-image-dataset)",
        "provenance": "Karanjit et al., Data in Brief (2023), DOI: 10.1016/j.dib.2023.109164",
        "license": "Academic Research / Open Access (Creative Commons)",
        "ground_truth_class": "flood",
        "contains_both_classes": False,
        "domain_type": "Ground-level and street-level flood event photography (USGS DOT cams, Twitter/X storm scrapes)",
        "suitability_for_flood_positives": "High (authentic ground inundation)",
        "statistics": analyze_image_folder(clemson_dir, max_sample=1000)
    }
    inventory["sources"]["clemson_floodimg"]["total_available_images"] = len(os.listdir(clemson_dir))

    # 3. Roham1
    roham_base = r"C:\Users\MahendraReddy\.cache\kagglehub\datasets\roham1\flood-classification-dataset\versions\1"
    r_flood_dir = os.path.join(roham_base, "Flood")
    r_non_flood_dir = os.path.join(roham_base, "Non_Flood")

    inventory["sources"]["roham1_flood"] = {
        "source_name": "roham1/flood-classification-dataset (Flood)",
        "provenance": "Kaggle Open Dataset (Aggregated web scraping)",
        "license": "Open Database License / Community Public",
        "ground_truth_class": "flood",
        "contains_both_classes": False,
        "domain_type": "Mixed flood imagery (street floods, aerial river floods, emergency rescues)",
        "suitability_for_flood_positives": "Moderate (contains non-road aerials and water bodies)",
        "statistics": analyze_image_folder(r_flood_dir, max_sample=1000)
    }
    inventory["sources"]["roham1_flood"]["total_available_images"] = len(os.listdir(r_flood_dir))

    inventory["sources"]["roham1_non_flood"] = {
        "source_name": "roham1/flood-classification-dataset (Non_Flood)",
        "provenance": "Kaggle Open Dataset (Aggregated web scraping)",
        "license": "Open Database License / Community Public",
        "ground_truth_class": "non_flood",
        "contains_both_classes": False,
        "domain_type": "Arbitrary non-road imagery (interiors, animals, landscapes, generic objects, 100% 224x224 thumbnail confounded)",
        "suitability_for_hard_negatives": "Severely Defective (lacks road structure, triggers dimension shortcut)",
        "statistics": analyze_image_folder(r_non_flood_dir, max_sample=1000)
    }
    inventory["sources"]["roham1_non_flood"]["total_available_images"] = len(os.listdir(r_non_flood_dir))

    # 4. Downloads Directory Repos
    dl_dir = r"C:\Users\MahendraReddy\Downloads"
    inventory["sources"]["floodnet_download_repo"] = {
        "source_name": "FloodNet-Supervised_v1.0-main",
        "path": os.path.join(dl_dir, "FloodNet-Supervised_v1.0-main"),
        "status": "Incomplete / Code Repo Only (Raw image binary archives require separate external Google Drive access request)",
        "usable_image_count": 1
    }
    inventory["sources"]["eu_flood_download_repo"] = {
        "source_name": "eu-flood-dataset-master",
        "path": os.path.join(dl_dir, "eu-flood-dataset-master"),
        "status": "Incomplete / Metadata Repo Only (Requires scraping 3,500 Wikimedia Commons URLs which returned HTTP 403 Forbidden)",
        "usable_image_count": 1
    }

    # 5. Synthesis & Multi-Class Source Assessment
    inventory["cross_source_assessment"] = {
        "sources_with_both_valid_classes": [],
        "positive_only_sources": ["clemson_floodimg", "roham1_flood"],
        "negative_only_sources": ["virenbr11_plain_roads", "virenbr11_potholes_hard_negatives"],
        "convoluted_sources": ["roham1 (Non_Flood is 100% 224x224 and non-road domain)"],
        "fundamental_finding": (
            "ZERO local datasets contain BOTH high-resolution road floods AND high-resolution non-flooded road surfaces. "
            "All road negatives reside in virenbr11; all high-resolution road floods reside in Clemson. "
            "Therefore, source identity is intrinsically confounded with the binary label across all available local data."
        )
    }

    out_file = "reports/vision_integrity/v4_dataset_inventory.json"
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(inventory, f, indent=2)

    print(f"Dataset inventory saved to: {out_file}")
    print("\n--- Summary of Available Sources ---")
    for sname, sdata in inventory["sources"].items():
        if "total_available_images" in sdata:
            print(f"{sname:<35}: {sdata['total_available_images']} images | Class: {sdata['ground_truth_class']}")

if __name__ == "__main__":
    main()
