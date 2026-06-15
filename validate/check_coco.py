"""Overlay COCO boxes on the rendered images to confirm labels are pixel-perfect.

    python validate/check_coco.py --coco out/run/coco/coco_annotations.json \
        --images out/run/coco/images --n 6 --out out/run/_check

Writes annotated copies you can eyeball. Pure-Python (needs opencv-python).
"""
from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from pathlib import Path

import cv2


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--coco", required=True)
    p.add_argument("--images", required=True)
    p.add_argument("--n", type=int, default=6)
    p.add_argument("--out", default=None)
    args = p.parse_args()

    coco = json.loads(Path(args.coco).read_text(encoding="utf-8"))
    cats = {c["id"]: c["name"] for c in coco["categories"]}
    anns = defaultdict(list)
    for a in coco["annotations"]:
        anns[a["image_id"]].append(a)

    out_dir = Path(args.out) if args.out else Path(args.images).parent / "_check"
    out_dir.mkdir(parents=True, exist_ok=True)

    shown = 0
    for im in coco["images"]:
        if shown >= args.n:
            break
        path = os.path.join(args.images, os.path.basename(im["file_name"]))
        img = cv2.imread(path)
        if img is None:
            continue
        for a in anns.get(im["id"], []):
            x, y, w, h = [int(v) for v in a["bbox"]]
            cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 0), 2)
            cv2.putText(img, cats.get(a["category_id"], "?"), (x, max(0, y - 5)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        dst = out_dir / f"check_{shown:03d}.jpg"
        cv2.imwrite(str(dst), img)
        shown += 1

    print(f"[check_coco] wrote {shown} annotated images to {out_dir}")


if __name__ == "__main__":
    main()
