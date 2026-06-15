"""BlenderProc scene construction + per-frame domain randomization.

Phase 0–1 scope: place 0..k proxy (or asset) drones near the scene centre, point a
camera at them from a randomized distance (controls apparent size / "range"), and set
a randomized sun + sky background. Later phases extend the randomizer here.

Imports `blenderproc`, so import only after it is imported in generate.py.
"""
from __future__ import annotations

import math
import os
from glob import glob

import numpy as np

import blenderproc as bproc

from .config import Config
from . import proxy


def setup_renderer(cfg: Config) -> None:
    bproc.camera.set_resolution(cfg.width, cfg.height)
    bproc.renderer.set_max_amount_of_samples(cfg.samples)
    if cfg.denoiser:
        try:
            bproc.renderer.set_denoiser("INTEL")
        except Exception:
            pass
    if cfg.out_depth:
        bproc.renderer.enable_depth_output(activate_antialiasing=False)


def enable_segmentation() -> None:
    """Enable instance/category segmentation for the CURRENT frame's objects.

    Must be called AFTER the frame's objects are created and BEFORE render(): in a
    generation loop, objects created after a one-time enable are NOT segmented (they
    come back as background), so the COCO writer would emit zero annotations.

    NOTE: default_values={"category_id": 0} is REQUIRED — without it BlenderProc
    fails to populate category_id and again produces zero annotations.
    """
    bproc.renderer.enable_segmentation_output(
        map_by=["instance", "name", "category_id"],
        default_values={"category_id": 0},
    )


def _list_hdris(cfg: Config) -> list[str]:
    if not cfg.hdri_dir or not os.path.isdir(cfg.hdri_dir):
        return []
    files: list[str] = []
    for ext in ("*.hdr", "*.exr"):
        files.extend(glob(os.path.join(cfg.hdri_dir, ext)))
    # Absolute paths: BlenderProc/Blender runs from its own working directory, so a
    # relative path like "assets/hdris/x.hdr" fails to load.
    return [os.path.abspath(f) for f in files]


def _set_world_color(rgb, strength: float = 1.0) -> None:
    """Set a flat world background colour via bpy directly.

    Done through the world node tree (not a BlenderProc helper) because the
    helper's name/signature has changed across BlenderProc versions; the node
    tree API is stable inside any Blender.
    """
    import bpy  # available inside the Blender-bundled Python

    world = bpy.context.scene.world
    if world is None:
        world = bpy.data.worlds.new("World")
        bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg is None:
        bg = world.node_tree.nodes.new("ShaderNodeBackground")
    bg.inputs[0].default_value = (float(rgb[0]), float(rgb[1]), float(rgb[2]), 1.0)
    bg.inputs[1].default_value = float(strength)


def set_background(cfg: Config, rng: np.random.Generator, hdris: list[str]) -> None:
    """Random HDRI sky if available, else a flat-ish procedural sky colour."""
    if hdris:
        bproc.world.set_world_background_hdr_img(str(rng.choice(hdris)))
        return
    # Flat colour sky: interpolate between configured top/bottom tints.
    t = float(rng.uniform(0, 1))
    top = np.array(cfg.sky_color_top)
    bot = np.array(cfg.sky_color_bottom)
    color = (1 - t) * bot + t * top
    _set_world_color(color, strength=float(rng.uniform(0.6, 1.4)))


def set_lighting(cfg: Config, rng: np.random.Generator):
    light = bproc.types.Light()
    light.set_type("SUN")
    light.set_energy(float(rng.uniform(*cfg.sun_energy)))
    elev = math.radians(float(rng.uniform(*cfg.sun_elevation_deg)))
    azim = math.radians(float(rng.uniform(*cfg.sun_azimuth_deg)))
    # A sun's direction is its rotation; point it from the sampled sky position.
    light.set_rotation_euler([elev, 0.0, azim])
    return light


def build_targets(cfg: Config, rng: np.random.Generator) -> list:
    """Create 0..k drones near the origin. Returns list of MeshObjects (may be empty)."""
    k = int(rng.integers(cfg.n_targets[0], cfg.n_targets[1] + 1))
    objs = []
    for _ in range(k):
        cls = cfg.classes[int(rng.integers(0, len(cfg.classes)))]
        span = float(rng.uniform(*cfg.target_scale_m))
        obj = proxy.make_proxy(cls.shape, cls.id, cls.name, span=span)
        # scatter extra targets a little around the scene centre
        jit = cfg.target_jitter_m
        obj.set_location(list(rng.uniform(-jit, jit, size=3) * np.array([1, 1, 0.5])))
        proxy.random_orientation(obj, rng)
        objs.append(obj)
    return objs


def sample_camera(cfg: Config, rng: np.random.Generator, targets: list):
    """Place the camera at a random distance looking at the target cluster.

    With no targets, look at the origin (produces a clean sky / hard-negative frame).
    """
    fov = math.radians(float(rng.uniform(*cfg.fov_deg)))
    bproc.camera.set_intrinsics_from_blender_params(lens=fov, lens_unit="FOV")

    if targets:
        poi = np.mean([t.get_location() for t in targets], axis=0)
    else:
        poi = np.zeros(3)

    dist = float(rng.uniform(*cfg.distance_m))
    # Random viewing direction, biased so the camera tends to look slightly upward
    # at the target (drone-in-sky composition).
    azim = float(rng.uniform(0, 2 * math.pi))
    elev = float(rng.uniform(math.radians(-25), math.radians(35)))
    direction = np.array([
        math.cos(elev) * math.cos(azim),
        math.cos(elev) * math.sin(azim),
        math.sin(elev),
    ])
    cam_location = poi - direction * dist  # sit 'dist' behind the look direction

    rot = bproc.camera.rotation_from_forward_vec(poi - cam_location)
    cam2world = bproc.math.build_transformation_mat(cam_location, rot)
    bproc.camera.add_camera_pose(cam2world)
    return cam2world


def cleanup(objs: list) -> None:
    """Remove the per-frame objects and lights so the next frame starts clean."""
    for o in objs:
        try:
            o.delete()
        except Exception:
            pass
    # Lights and the rest are cleared via reset_keyframes + delete in the loop.
