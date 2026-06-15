"""Train a YOLO detector on a Simurg (YOLO-format) dataset.

    python validate/train_yolo.py --data out/run/yolo/data.yaml --epochs 50 --model yolov8n.pt

Thin wrapper over Ultralytics so the validation loop is one command. The point is the
*sim-to-real* number from eval_real.py, not this training run on synthetic data.
"""
from __future__ import annotations

import argparse


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data", required=True, help="path to YOLO data.yaml (or its dir)")
    p.add_argument("--model", default="yolov8n.pt", help="base weights")
    p.add_argument("--epochs", type=int, default=50)
    p.add_argument("--imgsz", type=int, default=960)
    p.add_argument("--batch", type=int, default=16)
    args = p.parse_args()

    from ultralytics import YOLO  # imported lazily so --help works without it

    data = args.data
    if not data.endswith((".yaml", ".yml")):
        data = data.rstrip("/\\") + "/data.yaml"

    model = YOLO(args.model)
    model.train(data=data, epochs=args.epochs, imgsz=args.imgsz, batch=args.batch)
    print("[train_yolo] done — best weights under runs/detect/train*/weights/best.pt")


if __name__ == "__main__":
    main()
