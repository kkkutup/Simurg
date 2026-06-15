"""Dataset QA — class balance + box-size distribution for a Simurg COCO file.

    python validate/stats.py --coco out/run/coco/coco_annotations.json

Why it matters: a drone detector lives or dies on TINY, far-away targets. This tool
tells you what fraction of your boxes are tiny/small vs medium/large, so you can tune
scene.distance_m / target_scale_m until the size mix matches reality. Pure-Python.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path

# Box-area buckets (pixels^2). 'tiny' is the hard, important case for C-UAS.
BUCKETS = [
    ("tiny  (<16px)", 0, 16 * 16),
    ("small (<32px)", 16 * 16, 32 * 32),
    ("medium(<96px)", 32 * 32, 96 * 96),
    ("large (>=96px)", 96 * 96, math.inf),
]


def analyze(coco_json: str) -> dict:
    coco = json.loads(Path(coco_json).read_text(encoding="utf-8"))
    cats = {c["id"]: c["name"] for c in coco["categories"]}

    per_class = Counter()
    size_hist = Counter()
    images_with_ann = set()
    for a in coco["annotations"]:
        per_class[cats.get(a["category_id"], str(a["category_id"]))] += 1
        images_with_ann.add(a["image_id"])
        _, _, w, h = a["bbox"]
        area = w * h
        for name, lo, hi in BUCKETS:
            if lo <= area < hi:
                size_hist[name] += 1
                break

    n_images = len(coco["images"])
    n_empty = n_images - len(images_with_ann)
    n_ann = len(coco["annotations"])

    return {
        "images": n_images,
        "annotations": n_ann,
        "empty_frames": n_empty,
        "empty_frac": round(n_empty / n_images, 3) if n_images else 0.0,
        "avg_targets_per_image": round(n_ann / n_images, 3) if n_images else 0.0,
        "per_class": dict(per_class),
        "size_hist": {name: size_hist.get(name, 0) for name, _, _ in BUCKETS},
    }


def _bar(frac: float, width: int = 30) -> str:
    return "#" * int(round(frac * width))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--coco", required=True)
    args = p.parse_args()
    s = analyze(args.coco)

    print(f"\nimages              : {s['images']}")
    print(f"annotations         : {s['annotations']}")
    print(f"empty / negatives   : {s['empty_frames']}  ({s['empty_frac']:.0%})")
    print(f"avg targets / image : {s['avg_targets_per_image']}")

    print("\nclass balance:")
    total = max(1, sum(s["per_class"].values()))
    for name, n in sorted(s["per_class"].items(), key=lambda kv: -kv[1]):
        print(f"  {name:<16} {n:>7}  {_bar(n / total)}")

    print("\nbox-size distribution (lower = harder/more realistic for C-UAS):")
    tot = max(1, sum(s["size_hist"].values()))
    for name, n in s["size_hist"].items():
        print(f"  {name:<16} {n:>7}  {_bar(n / tot)}")

    tiny_small = s["size_hist"]["tiny  (<16px)"] + s["size_hist"]["small (<32px)"]
    frac = tiny_small / tot
    print(f"\ntiny+small fraction : {frac:.0%}", end="")
    if frac < 0.25:
        print("  <-- few hard targets; raise scene.distance_m or lower target_scale_m")
    else:
        print("  (good — plenty of hard long-range targets)")


if __name__ == "__main__":
    main()
