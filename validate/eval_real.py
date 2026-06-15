"""Evaluate a synthetic-trained detector on a REAL drone test set — the headline metric.

    python validate/eval_real.py --weights runs/detect/train/weights/best.pt \
        --real validate/real_test/data.yaml

`--real` points at a YOLO-format dataset of hand-checked REAL drone images that was
NEVER used in training. Prints mAP@0.5 (and @0.5:0.95). That number is the product.
"""
from __future__ import annotations

import argparse


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--weights", required=True)
    p.add_argument("--real", required=True, help="YOLO data.yaml for the REAL held-out test set")
    p.add_argument("--imgsz", type=int, default=960)
    args = p.parse_args()

    from ultralytics import YOLO

    data = args.real
    if not data.endswith((".yaml", ".yml")):
        data = data.rstrip("/\\") + "/data.yaml"

    model = YOLO(args.weights)
    metrics = model.val(data=data, imgsz=args.imgsz, split="val")

    print("\n===== SIM-TO-REAL RESULT =====")
    print(f"  mAP@0.5       : {metrics.box.map50:.4f}")
    print(f"  mAP@0.5:0.95  : {metrics.box.map:.4f}")
    print(f"  precision     : {metrics.box.mp:.4f}")
    print(f"  recall        : {metrics.box.mr:.4f}")
    print("==============================")
    print("Record mAP@0.5 — this is your sim-to-real baseline to iterate against.")


if __name__ == "__main__":
    main()
