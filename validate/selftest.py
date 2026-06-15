"""Offline smoke tests for the pure-Python pieces (no Blender required).

    python validate/selftest.py

Covers: config load + validation, COCO->YOLO (flat + split), dataset stats,
thermal tone-mapping, and COCO shard merge.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from simurg.config import load_config, Config  # noqa: E402
from simurg.exporters.coco_to_yolo import convert  # noqa: E402
from simurg.exporters.coco_merge import merge  # noqa: E402


def _fixture_coco(d: Path, n_images: int = 1, sval: int = 2, shard_tag: str = "") -> Path:
    """Write a tiny COCO dataset with one box per image (200x100, box 40x30 @ (50,20))."""
    coco_dir = d / f"coco{shard_tag}"
    (coco_dir / "images").mkdir(parents=True)
    images, anns = [], []
    for i in range(n_images):
        fn = f"{shard_tag}f{i}.jpg"
        images.append({"id": i + 1, "file_name": f"images/{fn}", "width": 200, "height": 100})
        anns.append({"id": i + 1, "image_id": i + 1, "category_id": sval,
                     "bbox": [50, 20, 40, 30], "area": 1200, "iscrowd": 0})
        (coco_dir / "images" / fn).write_bytes(b"\xff\xd8\xff\xd9")
    coco = {"images": images, "annotations": anns,
            "categories": [{"id": 1, "name": "quad_consumer"},
                           {"id": 2, "name": "quad_fpv"},
                           {"id": 3, "name": "fixedwing_fpv"}]}
    (coco_dir / "coco_annotations.json").write_text(json.dumps(coco))
    return coco_dir / "coco_annotations.json"


def test_config() -> None:
    cfg = load_config(ROOT / "configs" / "skywatch.yaml")
    assert cfg.width == 1280 and cfg.height == 720
    assert len(cfg.classes) == 3
    assert cfg.category_map()[1] == "quad_consumer"
    assert cfg.distance_m == (8, 200)
    print("[selftest] config OK:", cfg.name, cfg.category_map())


def test_config_validation() -> None:
    base = load_config(ROOT / "configs" / "skywatch.yaml")
    # duplicate ids
    bad = Config(**{**base.__dict__})
    bad.classes = [base.classes[0], base.classes[0]]
    try:
        bad.validate()
        raise AssertionError("expected duplicate-id failure")
    except ValueError as e:
        assert "duplicate class ids" in str(e)
    # inverted range
    bad2 = Config(**{**base.__dict__})
    bad2.distance_m = (200, 8)
    try:
        bad2.validate()
        raise AssertionError("expected range failure")
    except ValueError as e:
        assert "distance_m" in str(e)
    print("[selftest] config validation OK")


def test_coco_to_yolo_flat() -> None:
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        coco = _fixture_coco(d)
        out = d / "yolo"
        convert(str(coco), str(out))
        label = (out / "labels" / "f0.txt").read_text().strip().split()
        assert label[0] == "1", f"category 2 -> idx 1, got {label[0]}"
        assert abs(float(label[1]) - 70 / 200) < 1e-6
        assert abs(float(label[2]) - 35 / 100) < 1e-6
        assert "nc: 3" in (out / "data.yaml").read_text()
    print("[selftest] coco_to_yolo (flat) OK:", label)


def test_coco_to_yolo_split() -> None:
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        coco = _fixture_coco(d, n_images=10)
        out = d / "yolo"
        summary = convert(str(coco), str(out), val_split=0.2, seed=0)
        assert (out / "images" / "train").is_dir()
        assert (out / "images" / "val").is_dir()
        assert summary["split"]["val"] == 2 and summary["split"]["train"] == 8
        assert "train: images/train" in (out / "data.yaml").read_text()
    print("[selftest] coco_to_yolo (split) OK:", summary["split"])


def test_stats() -> None:
    from stats import analyze  # validate/ is on sys.path via __file__
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        coco = _fixture_coco(d, n_images=4)
        s = analyze(str(coco))
        assert s["images"] == 4 and s["annotations"] == 4
        assert s["per_class"]["quad_fpv"] == 4
        # 40x30 box => area 1200 => 'medium(<96px)' bucket
        assert s["size_hist"]["medium(<96px)"] == 4
    print("[selftest] stats OK:", s["size_hist"])


def test_thermal() -> None:
    import numpy as np
    from simurg import thermal
    grad = np.tile(np.linspace(0, 1, 64), (16, 1))
    img = thermal.apply_palette(grad, "ironbow")
    assert img.shape == (16, 64, 3) and img.dtype == np.uint8
    # white_hot: 0 -> black, 1 -> white
    wh = thermal.apply_palette(np.array([[0.0, 1.0]]), "white_hot")
    assert wh[0, 0].tolist() == [0, 0, 0]
    assert wh[0, 1].tolist() == [255, 255, 255]
    full = thermal.to_thermal(grad * 100.0, np.random.default_rng(1))
    assert full.shape == (16, 64, 3)
    print("[selftest] thermal OK:", thermal.list_palettes())


def test_coco_merge() -> None:
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        s0 = _fixture_coco(d, n_images=2, shard_tag="a_").parent
        s1 = _fixture_coco(d, n_images=3, shard_tag="b_").parent
        out = d / "merged"
        summary = merge([str(s0), str(s1)], str(out))
        assert summary["images"] == 5 and summary["annotations"] == 5
        merged = json.loads((out / "coco_annotations.json").read_text())
        ids = [im["id"] for im in merged["images"]]
        assert len(ids) == len(set(ids)), "image ids must stay unique after merge"
    print("[selftest] coco_merge OK:", summary["images"], "images")


if __name__ == "__main__":
    test_config()
    test_config_validation()
    test_coco_to_yolo_flat()
    test_coco_to_yolo_split()
    test_stats()
    test_thermal()
    test_coco_merge()
    print("\n[selftest] ALL PASSED")
