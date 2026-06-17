"""Analog video-feed look — a post-render image effect (Phase-2 domain randomization).

Real counter-UAS optical feeds and FPV analog video are noisy, low-bandwidth, and
scan-lined. Applying that look to clean renders both (a) matches the target domain and
(b) is strong augmentation. The geometry is untouched, so COCO/YOLO labels stay valid.

Pure NumPy (+ OpenCV if available, which the BlenderProc env ships). Operates on the
rendered RGB uint8 frame before it is written.
"""
from __future__ import annotations

import numpy as np

try:
    import cv2
except Exception:  # noqa: BLE001
    cv2 = None


def apply_analog(img: np.ndarray, rng: np.random.Generator, strength: float = 1.0) -> np.ndarray:
    """Return an analog-CRT/VHS-styled copy of an RGB uint8 image.

    strength in ~[0,1.2] scales every effect (randomize it per frame for variety).
    """
    h, w = img.shape[:2]
    s = float(max(0.0, strength))
    f = img.astype(np.float32) / 255.0

    # 1. desaturate a touch + subtle analog colour cast
    gray = f.mean(axis=2, keepdims=True)
    f = f * (1.0 - 0.22 * s) + gray * (0.22 * s)
    f *= np.array([1.0, 1.02, 0.96], dtype=np.float32)  # faint green/warm tint

    # 2. chromatic aberration — split R/B horizontally
    sh = int(round(1 + 2 * s))
    if sh > 0:
        f[..., 0] = np.roll(f[..., 0], sh, axis=1)
        f[..., 2] = np.roll(f[..., 2], -sh, axis=1)

    # 3. limited horizontal bandwidth (signal smear)
    if cv2 is not None and s > 0:
        k = 1 + 2 * int(round(s))
        f = cv2.GaussianBlur(f, (k, 1), 0)

    # 4. scanlines (darken alternate rows)
    lines = np.ones((h, 1, 1), dtype=np.float32)
    lines[::2, 0, 0] = 1.0 - 0.18 * s
    f *= lines

    # 5. analog noise
    f += rng.normal(0.0, 0.035 * s, f.shape).astype(np.float32)

    # 6. occasional faint horizontal tear (a shifted band)
    if s > 0 and rng.random() < 0.25 * s:
        y0 = int(rng.integers(0, max(1, h - 8)))
        band = slice(y0, y0 + int(rng.integers(2, 8)))
        f[band] = np.roll(f[band], int(rng.integers(-6, 7)), axis=1)

    # 7. vignette
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cx, cy = w / 2.0, h / 2.0
    rad = np.sqrt(((xx - cx) / cx) ** 2 + ((yy - cy) / cy) ** 2)
    vig = 1.0 - 0.35 * s * np.clip(rad - 0.5, 0.0, 1.0)
    f *= vig[..., None]

    # 8. slight contrast/gamma lift
    f = np.clip(f, 0.0, 1.0) ** (1.0 + 0.10 * s)
    return (np.clip(f, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
