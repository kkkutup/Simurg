"""YAML scene recipe -> typed config objects.

Pure-Python (no BlenderProc import) so it can be unit-tested without Blender.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class DroneClass:
    name: str
    id: int
    shape: str = "quad"  # "quad" | "fixedwing"


@dataclass
class AssetModel:
    path: str
    cls: str  # class name this model belongs to


@dataclass
class Config:
    raw: dict[str, Any]

    name: str
    n: int
    seed: int

    width: int
    height: int
    samples: int
    denoiser: bool

    fov_deg: tuple[float, float]

    classes: list[DroneClass]

    viewpoint: str
    elevation_deg: tuple[float, float]
    include_classes: list[str]
    hdri_include: list[str]

    n_targets: tuple[int, int]
    distance_m: tuple[float, float]
    target_scale_m: tuple[float, float]
    target_jitter_m: float

    sun_energy: tuple[float, float]
    sun_elevation_deg: tuple[float, float]
    sun_azimuth_deg: tuple[float, float]

    sky_color_top: tuple[float, float, float]
    sky_color_bottom: tuple[float, float, float]
    hdri_dir: str
    sky_only: bool

    models: list[AssetModel]

    analog_enabled: bool
    analog_strength: tuple[float, float]

    out_coco: bool
    out_yolo: bool
    out_depth: bool

    # ---- helpers -------------------------------------------------------
    def class_by_name(self, name: str) -> DroneClass:
        for c in self.classes:
            if c.name == name:
                return c
        raise KeyError(f"unknown class '{name}'")

    def category_map(self) -> dict[int, str]:
        return {c.id: c.name for c in self.classes}

    def included_classes(self) -> list[DroneClass]:
        """Classes the renderer may place (subset selected in the UI, or all)."""
        if not self.include_classes:
            return self.classes
        keep = set(self.include_classes)
        sub = [c for c in self.classes if c.name in keep]
        return sub or self.classes

    def validate(self) -> "Config":
        """Sanity-check a recipe; raise ValueError with an actionable message."""
        errs: list[str] = []
        if not self.classes:
            errs.append("no classes defined")
        ids = [c.id for c in self.classes]
        if len(ids) != len(set(ids)):
            errs.append(f"duplicate class ids: {ids}")
        if 0 in ids:
            errs.append("class id 0 is reserved for background; use ids >= 1")
        for c in self.classes:
            if c.shape not in ("quad", "fixedwing"):
                errs.append(f"class '{c.name}' has unknown shape '{c.shape}'")
        if self.width <= 0 or self.height <= 0:
            errs.append(f"bad resolution {self.width}x{self.height}")
        if self.samples <= 0:
            errs.append(f"render.samples must be > 0 (got {self.samples})")
        for label, lo, hi in [
            ("camera.fov_deg", *self.fov_deg),
            ("scene.distance_m", *self.distance_m),
            ("scene.target_scale_m", *self.target_scale_m),
            ("lighting.sun_energy", *self.sun_energy),
            ("lighting.sun_elevation_deg", *self.sun_elevation_deg),
        ]:
            if lo > hi:
                errs.append(f"{label}: min {lo} > max {hi}")
        if self.n_targets[0] < 0 or self.n_targets[0] > self.n_targets[1]:
            errs.append(f"scene.n_targets invalid: {self.n_targets}")
        for c in self.classes:
            if not (0 <= c.id):
                errs.append(f"class '{c.name}' id must be >= 0")
        # Asset model classes must reference a declared class.
        known = {c.name for c in self.classes}
        for m in self.models:
            if m.cls not in known:
                errs.append(f"asset model '{m.path}' references unknown class '{m.cls}'")
        if errs:
            raise ValueError("invalid config:\n  - " + "\n  - ".join(errs))
        return self


def _pair(v, default):
    if v is None:
        return tuple(default)
    if isinstance(v, (int, float)):
        return (v, v)
    return (v[0], v[1])


def load_config(path: str | Path) -> Config:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))

    ds = data.get("dataset", {})
    rn = data.get("render", {})
    cam = data.get("camera", {})
    sc = data.get("scene", {})
    li = data.get("lighting", {})
    bg = data.get("background", {})
    asset = data.get("assets", {})
    out = data.get("outputs", {})
    fx = data.get("effects", {})
    analog = fx.get("analog", {}) or {}

    classes = [DroneClass(**c) for c in data.get("classes", [])]
    models = [AssetModel(path=m["path"], cls=m["class"]) for m in asset.get("models", []) or []]

    return Config(
        raw=data,
        name=ds.get("name", "simurg"),
        n=int(ds.get("n", 100)),
        seed=int(ds.get("seed", 0)),
        width=int(rn.get("width", 1280)),
        height=int(rn.get("height", 720)),
        samples=int(rn.get("samples", 48)),
        denoiser=bool(rn.get("denoiser", True)),
        fov_deg=_pair(cam.get("fov_deg"), (40, 75)),
        classes=classes,
        viewpoint=str(sc.get("viewpoint", "mixed")),
        elevation_deg=_pair(cam.get("elevation_deg"), (-25, 35)),
        include_classes=list(sc.get("include_classes", []) or []),
        hdri_include=list(bg.get("hdri_include", []) or []),
        n_targets=tuple(int(x) for x in _pair(sc.get("n_targets"), (0, 2))),
        distance_m=_pair(sc.get("distance_m"), (8, 200)),
        target_scale_m=_pair(sc.get("target_scale_m"), (0.2, 1.2)),
        target_jitter_m=float(sc.get("target_jitter_m", 4.0)),
        sun_energy=_pair(li.get("sun_energy"), (1.0, 6.0)),
        sun_elevation_deg=_pair(li.get("sun_elevation_deg"), (5, 85)),
        sun_azimuth_deg=_pair(li.get("sun_azimuth_deg"), (0, 360)),
        sky_color_top=tuple(bg.get("sky_color_top", (0.2, 0.45, 0.85))),
        sky_color_bottom=tuple(bg.get("sky_color_bottom", (0.75, 0.85, 0.97))),
        hdri_dir=str(bg.get("hdri_dir", "assets/hdris")),
        sky_only=bool(bg.get("sky_only", False)),
        models=models,
        analog_enabled=bool(analog.get("enabled", False)),
        analog_strength=_pair(analog.get("strength"), (0.4, 1.0)),
        out_coco=bool(out.get("coco", True)),
        out_yolo=bool(out.get("yolo", False)),
        out_depth=bool(out.get("depth", False)),
    ).validate()
