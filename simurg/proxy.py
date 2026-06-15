"""Primitive proxy drone meshes, so Simurg runs with zero external 3D assets.

These are deliberately crude stand-ins (a body + rotors / wings) — enough to train
and validate the *pipeline* end to end. Swap in real .glb/.fbx models via the config
once the toolchain is confirmed; realism is a Phase-2/3 concern, not a Phase-0 blocker.

NOTE: this module imports `blenderproc`, so it must only be imported *after*
`import blenderproc as bproc` has run in the entrypoint (generate.py).
"""
from __future__ import annotations

import numpy as np

import blenderproc as bproc


def _cube(scale, location=(0, 0, 0)):
    obj = bproc.object.create_primitive("CUBE")
    obj.set_scale([s / 2.0 for s in scale])  # primitive cube spans 2 units
    obj.set_location(location)
    return obj


def _cylinder(radius, depth, location=(0, 0, 0)):
    obj = bproc.object.create_primitive("CYLINDER")
    obj.set_scale([radius, radius, depth / 2.0])
    obj.set_location(location)
    return obj


def _finalize(parts, category_id: int, name: str):
    """Join all parts into a single MeshObject and tag it for segmentation."""
    base = parts[0]
    if len(parts) > 1:
        base.join_with_other_objects(parts[1:])
    base.set_cp("category_id", category_id)
    base.set_name(name)
    return base


def make_quad(category_id: int, name: str, span: float = 1.0):
    """A quadrotor proxy: flat body, 4 arms, 4 rotor discs."""
    parts = []
    body = _cube((0.30 * span, 0.30 * span, 0.08 * span))
    parts.append(body)
    arm_len = 0.45 * span
    for dx, dy in [(1, 1), (1, -1), (-1, 1), (-1, -1)]:
        ax, ay = dx * arm_len * 0.5, dy * arm_len * 0.5
        arm = _cube((arm_len, 0.04 * span, 0.04 * span), location=(ax, ay, 0))
        rotor = _cylinder(0.18 * span, 0.02 * span, location=(dx * arm_len, dy * arm_len, 0.04 * span))
        parts.extend([arm, rotor])
    return _finalize(parts, category_id, name)


def make_fixedwing(category_id: int, name: str, span: float = 1.0):
    """A fixed-wing / loitering-munition proxy: fuselage + wings + tail."""
    parts = []
    fuselage = _cube((0.9 * span, 0.12 * span, 0.12 * span))
    wings = _cube((0.25 * span, 1.1 * span, 0.03 * span))
    tail = _cube((0.15 * span, 0.45 * span, 0.03 * span), location=(-0.45 * span, 0, 0.05 * span))
    parts.extend([fuselage, wings, tail])
    return _finalize(parts, category_id, name)


def make_proxy(shape: str, category_id: int, name: str, span: float = 1.0):
    if shape == "fixedwing":
        return make_fixedwing(category_id, name, span)
    return make_quad(category_id, name, span)


def random_orientation(obj, rng: np.random.Generator):
    obj.set_rotation_euler(list(rng.uniform(-np.pi, np.pi, size=3)))
