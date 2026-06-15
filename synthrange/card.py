"""dataset_card.json — a reproducibility record for every generated dataset.

Pure-Python; safe to import anywhere.
"""
from __future__ import annotations

import json
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def write_card(
    output_dir: str | Path,
    *,
    config_raw: dict[str, Any],
    config_path: str,
    n_requested: int,
    n_rendered: int,
    seed: int,
    category_map: dict[int, str],
    per_class_instances: dict[str, int],
    empty_frames: int,
    synthrange_version: str,
) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    card = {
        "generator": "synthrange",
        "version": synthrange_version,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "host": platform.platform(),
        "config_path": config_path,
        "seed": seed,
        "frames": {
            "requested": n_requested,
            "rendered": n_rendered,
            "empty_negative": empty_frames,
        },
        "classes": category_map,
        "instances_per_class": per_class_instances,
        "config": config_raw,
    }
    path = output_dir / "dataset_card.json"
    path.write_text(json.dumps(card, indent=2), encoding="utf-8")
    return path
