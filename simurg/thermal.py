"""Synthetic-IR (thermal) tone-mapping — Phase-3 scaffold.

Two halves:
  * The *rendering* half (a Blender emission pass where material emission ∝ assigned
    temperature) belongs in scene.py and needs BlenderProc — stubbed there later.
  * The *tone-mapping* half here is pure NumPy and unit-tested: it turns a single-channel
    "radiometric" array into a thermal-looking image with IR-style artefacts.

Keeping this pure-Python means the thermal palette + noise model are verifiable today,
before the Blender pass exists.
"""
from __future__ import annotations

import numpy as np

# Simple control-point palettes (value 0..1 -> RGB 0..1). Interpolated linearly.
_PALETTES: dict[str, list[tuple[float, tuple[float, float, float]]]] = {
    "white_hot": [(0.0, (0, 0, 0)), (1.0, (1, 1, 1))],
    "black_hot": [(0.0, (1, 1, 1)), (1.0, (0, 0, 0))],
    "ironbow": [
        (0.00, (0.0, 0.0, 0.0)),
        (0.25, (0.3, 0.0, 0.5)),
        (0.50, (0.8, 0.2, 0.2)),
        (0.75, (1.0, 0.6, 0.0)),
        (1.00, (1.0, 1.0, 0.8)),
    ],
}


def list_palettes() -> list[str]:
    return list(_PALETTES)


def apply_palette(gray: np.ndarray, palette: str = "white_hot") -> np.ndarray:
    """Map a float array in [0,1] to an RGB uint8 image via a named palette."""
    if palette not in _PALETTES:
        raise KeyError(f"unknown palette '{palette}'; have {list_palettes()}")
    g = np.clip(gray.astype(np.float32), 0.0, 1.0)
    pts = _PALETTES[palette]
    xs = np.array([p[0] for p in pts])
    cols = np.array([p[1] for p in pts])  # (k,3)
    out = np.empty(g.shape + (3,), dtype=np.float32)
    for ch in range(3):
        out[..., ch] = np.interp(g, xs, cols[:, ch])
    return (out * 255.0 + 0.5).astype(np.uint8)


def normalize(radiometric: np.ndarray, lo_pct: float = 2.0, hi_pct: float = 98.0) -> np.ndarray:
    """Percentile-stretch a radiometric array to [0,1] (mimics auto-gain / NUC)."""
    r = radiometric.astype(np.float32)
    lo = np.percentile(r, lo_pct)
    hi = np.percentile(r, hi_pct)
    if hi <= lo:
        return np.zeros_like(r)
    return np.clip((r - lo) / (hi - lo), 0.0, 1.0)


def add_ir_artifacts(
    gray: np.ndarray,
    rng: np.random.Generator,
    noise_std: float = 0.02,
    banding: float = 0.015,
) -> np.ndarray:
    """Add IR-sensor-style noise + horizontal fixed-pattern banding to a [0,1] image."""
    g = gray.astype(np.float32)
    g = g + rng.normal(0.0, noise_std, size=g.shape)
    if banding > 0 and g.ndim == 2:
        rows = rng.normal(0.0, banding, size=(g.shape[0], 1))
        g = g + rows  # broadcast across columns -> row banding
    return np.clip(g, 0.0, 1.0)


def to_thermal(
    radiometric: np.ndarray,
    rng: np.random.Generator | None = None,
    palette: str = "ironbow",
    noise_std: float = 0.02,
) -> np.ndarray:
    """Full pipeline: radiometric array -> thermal-looking RGB uint8 image."""
    rng = rng or np.random.default_rng(0)
    g = normalize(radiometric)
    g = add_ir_artifacts(g, rng, noise_std=noise_std)
    return apply_palette(g, palette)
