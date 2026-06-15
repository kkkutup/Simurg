"""Merge several COCO datasets (e.g. from parallel render shards) into one.

    python simurg/exporters/coco_merge.py --out out/merged/coco \
        out/shard0/coco out/shard1/coco out/shard2/coco

Each input is a directory containing coco_annotations.json + images/. Image and
annotation ids are remapped to stay unique; categories are unified by NAME (so all
shards must agree on class names). Image files are copied into the merged images/ dir,
renamed by shard to avoid collisions. Pure-Python.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def merge(shard_dirs: list[str], out_dir: str, copy_images: bool = True) -> dict:
    out = Path(out_dir)
    (out / "images").mkdir(parents=True, exist_ok=True)

    # Unify categories by name -> assign fresh contiguous ids (ordered by first sight).
    name_to_id: dict[str, int] = {}
    merged_images: list[dict] = []
    merged_anns: list[dict] = []
    next_img_id = 1
    next_ann_id = 1

    for si, sd in enumerate(shard_dirs):
        sd_path = Path(sd)
        jpath = sd_path / "coco_annotations.json"
        coco = json.loads(jpath.read_text(encoding="utf-8"))

        local_catid_to_name = {c["id"]: c["name"] for c in coco["categories"]}
        for c in coco["categories"]:
            name_to_id.setdefault(c["name"], len(name_to_id) + 1)

        img_id_map: dict[int, int] = {}
        for im in coco["images"]:
            new_id = next_img_id
            next_img_id += 1
            img_id_map[im["id"]] = new_id
            src_name = Path(im["file_name"]).name
            new_name = f"s{si}_{src_name}"
            if copy_images:
                src = (sd_path / im["file_name"]).resolve()
                if src.exists():
                    shutil.copy2(src, out / "images" / new_name)
            merged_images.append({**im, "id": new_id, "file_name": f"images/{new_name}"})

        for a in coco["annotations"]:
            cat_name = local_catid_to_name[a["category_id"]]
            merged_anns.append({
                **a,
                "id": next_ann_id,
                "image_id": img_id_map[a["image_id"]],
                "category_id": name_to_id[cat_name],
            })
            next_ann_id += 1

    categories = [{"id": cid, "name": name, "supercategory": "drone"}
                  for name, cid in sorted(name_to_id.items(), key=lambda kv: kv[1])]
    merged = {"images": merged_images, "annotations": merged_anns, "categories": categories}
    (out / "coco_annotations.json").write_text(json.dumps(merged), encoding="utf-8")

    summary = {"shards": len(shard_dirs), "images": len(merged_images),
               "annotations": len(merged_anns), "classes": list(name_to_id),
               "out": str(out)}
    print(f"[coco_merge] {summary}")
    return summary


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True, help="output coco dir")
    p.add_argument("--no-copy", action="store_true")
    p.add_argument("shards", nargs="+", help="input coco dirs (with coco_annotations.json)")
    args = p.parse_args()
    merge(args.shards, args.out, copy_images=not args.no_copy)


if __name__ == "__main__":
    main()
