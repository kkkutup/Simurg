"""Convert a BlenderProc COCO dataset into YOLO (Ultralytics) format.

    python synthrange/exporters/coco_to_yolo.py \
        --coco out/run/coco/coco_annotations.json \
        --out  out/run/yolo

Produces:
    out/yolo/images/*.jpg        (copied/linked from the COCO images)
    out/yolo/labels/*.txt        (class cx cy w h, normalized)
    out/yolo/data.yaml           (Ultralytics dataset descriptor)

Pure-Python (no Blender). Class ids are remapped to a contiguous 0-based index,
ordered by COCO category id, which YOLO expects.
"""
from __future__ import annotations

import argparse
import json
import random
import shutil
from collections import defaultdict
from pathlib import Path


def convert(coco_json: str, out_dir: str, copy_images: bool = True,
            val_split: float = 0.0, seed: int = 0) -> dict:
    """Convert COCO -> YOLO.

    val_split == 0  -> single 'images/' + 'labels/' dir (train == val).
    val_split  > 0  -> deterministic split into images/{train,val} + labels/{train,val}.
    """
    coco_path = Path(coco_json)
    coco = json.loads(coco_path.read_text(encoding="utf-8"))
    coco_root = coco_path.parent  # image file_names are relative to this

    out = Path(out_dir)

    # Contiguous 0-based class indexing, ordered by category id.
    cats = sorted(coco["categories"], key=lambda c: c["id"])
    catid_to_idx = {c["id"]: i for i, c in enumerate(cats)}
    names = [c["name"] for c in cats]

    images = list(coco["images"])
    anns_by_image: dict[int, list] = defaultdict(list)
    for a in coco["annotations"]:
        anns_by_image[a["image_id"]].append(a)

    # Deterministic split assignment.
    split_of: dict[int, str] = {}
    if val_split and val_split > 0:
        order = sorted(images, key=lambda im: im["id"])
        random.Random(seed).shuffle(order)
        n_val = max(1, int(round(len(order) * val_split)))
        val_ids = {im["id"] for im in order[:n_val]}
        for im in images:
            split_of[im["id"]] = "val" if im["id"] in val_ids else "train"
        subsets = ("train", "val")
    else:
        for im in images:
            split_of[im["id"]] = ""  # flat
        subsets = ("",)

    for sub in subsets:
        (out / "images" / sub).mkdir(parents=True, exist_ok=True)
        (out / "labels" / sub).mkdir(parents=True, exist_ok=True)

    n_labels = 0
    counts = {s or "all": 0 for s in subsets}
    for im in images:
        w, h = im["width"], im["height"]
        stem = Path(im["file_name"]).stem
        sub = split_of[im["id"]]
        counts[sub or "all"] += 1

        src = (coco_root / im["file_name"]).resolve()
        dst = out / "images" / sub / Path(im["file_name"]).name
        if copy_images and src.exists() and not dst.exists():
            shutil.copy2(src, dst)

        lines = []
        for a in anns_by_image.get(im["id"], []):
            x, y, bw, bh = a["bbox"]  # COCO: top-left x,y + width,height (pixels)
            cx = (x + bw / 2.0) / w
            cy = (y + bh / 2.0) / h
            idx = catid_to_idx[a["category_id"]]
            lines.append(f"{idx} {cx:.6f} {cy:.6f} {bw / w:.6f} {bh / h:.6f}")
            n_labels += 1
        (out / "labels" / sub / f"{stem}.txt").write_text("\n".join(lines), encoding="utf-8")

    train_dir = "images/train" if val_split else "images"
    val_dir = "images/val" if val_split else "images"
    (out / "data.yaml").write_text(
        "path: {}\n".format(out.resolve().as_posix())
        + f"train: {train_dir}\n"
        + f"val: {val_dir}\n"
        + f"nc: {len(names)}\n"
        + "names: [{}]\n".format(", ".join(names)),
        encoding="utf-8",
    )

    summary = {"images": len(images), "labels": n_labels, "classes": names,
               "split": counts, "out": str(out)}
    print(f"[coco_to_yolo] {summary}")
    return summary


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--coco", required=True, help="path to coco_annotations.json")
    p.add_argument("--out", required=True, help="output YOLO dataset dir")
    p.add_argument("--no-copy", action="store_true", help="do not copy images")
    p.add_argument("--val-split", type=float, default=0.0,
                   help="fraction held out for validation (e.g. 0.1)")
    p.add_argument("--seed", type=int, default=0, help="split shuffle seed")
    args = p.parse_args()
    convert(args.coco, args.out, copy_images=not args.no_copy,
            val_split=args.val_split, seed=args.seed)


if __name__ == "__main__":
    main()
