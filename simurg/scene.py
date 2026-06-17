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
        # Recursive: picks up both the top level and category subfolders
        # (clear/, overcast/, sunset_dawn/, night/, ...).
        files.extend(glob(os.path.join(cfg.hdri_dir, "**", ext), recursive=True))
    # Sky-only filter (e.g. air->air): keep only HDRIs tagged sky_only in the manifest.
    if cfg.sky_only:
        man_path = os.path.join(cfg.hdri_dir, "manifest.yaml")
        if os.path.isfile(man_path):
            import yaml
            man = yaml.safe_load(open(man_path, encoding="utf-8")) or {}
            skyset = {s.get("file") for s in man.get("skies", []) if s.get("sky_only")}
            sub = [f for f in files if os.path.basename(f) in skyset]
            files = sub or files  # if none tagged, don't strand the render
    # Optional subset: only use skies whose filename is in background.hdri_include.
    if cfg.hdri_include:
        keep = set(cfg.hdri_include)
        sub = [f for f in files if os.path.basename(f) in keep]
        files = sub or files
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


def _flatten_and_normalize(objs):
    """Flatten a loaded model (glb scene graph) into one mesh, centred at the origin
    and scaled so its largest dimension == 1 m. Returns a hidden MeshObject template,
    or None if the file held no meshes.
    """
    import bpy

    meshes = [o for o in objs if getattr(o, "blender_obj", None) and o.blender_obj.type == "MESH"]
    others = [o for o in objs if o not in meshes]
    if not meshes:
        for o in others:
            try:
                o.delete()
            except Exception:
                pass
        return None

    # Bake the full parent-chain world transform onto each mesh (glb puts the up-axis
    # correction on the root empty), then join into one object.
    bpy.ops.object.select_all(action="DESELECT")
    for m in meshes:
        m.blender_obj.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0].blender_obj
    try:
        bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
    except Exception:
        pass
    if len(meshes) > 1:
        bpy.ops.object.join()
    joined_b = bpy.context.view_layer.objects.active
    try:
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    except Exception:
        pass
    for o in others:  # drop leftover empties / armatures
        try:
            o.delete()
        except Exception:
            pass

    obj = bproc.types.MeshObject(joined_b)
    # centre on geometry, then scale to unit size
    bpy.ops.object.select_all(action="DESELECT")
    joined_b.select_set(True)
    bpy.context.view_layer.objects.active = joined_b
    try:
        bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
    except Exception:
        pass
    obj.set_location([0.0, 0.0, 0.0])
    bb = obj.get_bound_box()
    dims = bb.max(axis=0) - bb.min(axis=0)
    s = 1.0 / float(max(dims.max(), 1e-6))
    obj.set_scale([s, s, s])
    obj.persist_transformation_into_mesh()  # bake unit scale into the mesh data
    return obj


def load_model_library(drones_dir: str) -> dict:
    """Load every manifest model once as a normalized, hidden template.
    Returns {class_name: [MeshObject, ...]}. Empty dict => proxies are used.
    """
    import yaml

    mpath = os.path.join(drones_dir, "manifest.yaml")
    if not os.path.isfile(mpath):
        return {}
    man = yaml.safe_load(open(mpath, encoding="utf-8")) or {}
    lib: dict[str, list] = {}
    for m in man.get("models") or []:
        if not m.get("enabled", True):  # toggled off in the UI
            continue
        cls, rel = m.get("class"), m.get("file")
        if not cls or not rel:
            continue
        path = os.path.join(drones_dir, rel)
        if not os.path.isfile(path):
            continue
        try:
            objs = bproc.loader.load_obj(path)
        except Exception as e:  # noqa: BLE001
            print(f"[simurg] model load failed {rel}: {e}", flush=True)
            continue
        tmpl = _flatten_and_normalize(objs)
        if tmpl is None:
            continue
        tmpl.hide(True)  # templates never render; per-frame instances do
        lib.setdefault(cls, []).append(tmpl)
        print(f"[simurg] model template: {cls} <- {rel}", flush=True)
    return lib


def sample_camera(cfg: Config, rng: np.random.Generator) -> dict:
    """Place the camera looking at the origin; return a 'view' (basis + geometry) that
    build_targets uses to scatter drones across the frame without overlap.
    """
    fov = math.radians(float(rng.uniform(*cfg.fov_deg)))
    bproc.camera.set_intrinsics_from_blender_params(lens=fov, lens_unit="FOV")

    poi = np.zeros(3)
    dist = float(rng.uniform(*cfg.distance_m))
    # Viewing-direction elevation comes from the viewpoint mode (camera.elevation_deg):
    #   ground->air = look up (positive), air->air = ~level, air->ground = look down.
    azim = float(rng.uniform(0, 2 * math.pi))
    elev = float(rng.uniform(math.radians(cfg.elevation_deg[0]),
                             math.radians(cfg.elevation_deg[1])))
    direction = np.array([
        math.cos(elev) * math.cos(azim),
        math.cos(elev) * math.sin(azim),
        math.sin(elev),
    ])
    cam_location = poi - direction * dist  # sit 'dist' behind the look direction

    rot = bproc.camera.rotation_from_forward_vec(poi - cam_location)
    cam2world = bproc.math.build_transformation_mat(cam_location, rot)
    bproc.camera.add_camera_pose(cam2world)

    R = np.array(cam2world)[:3, :3]
    return {
        "poi": poi, "dist": dist, "fov": fov,
        "right": R[:, 0], "up": R[:, 1], "forward": direction,
    }


def build_targets(cfg: Config, rng: np.random.Generator, library: dict | None,
                  view: dict) -> list:
    """Create 0..k drones spread across the camera frame with no overlap.

    Targets are positioned in the camera's image plane (right/up basis) and rejection-
    sampled so their projected footprints stay separated — no more stacked boxes. Uses
    real models from `library` when available, else a primitive proxy.
    """
    library = library or {}
    pool = cfg.included_classes()
    k = int(rng.integers(cfg.n_targets[0], cfg.n_targets[1] + 1))

    right, up, fwd, poi = view["right"], view["up"], view["forward"], view["poi"]
    d = view["dist"]
    aspect = cfg.height / max(1, cfg.width)
    half_w = d * math.tan(view["fov"] / 2.0) * 0.82   # keep targets ~within frame
    half_h = half_w * aspect

    objs, placed = [], []  # placed: (u, v, radius) in image-plane metres at depth d
    for _ in range(k):
        cls = pool[int(rng.integers(0, len(pool)))]
        span = float(rng.uniform(*cfg.target_scale_m))
        r = span * 0.55  # footprint radius (image-plane metres)

        uv = None
        for _try in range(40):
            u = float(rng.uniform(-half_w + r, half_w - r))
            v = float(rng.uniform(-half_h + r, half_h - r))
            if all(math.hypot(u - pu, v - pv) > (r + pr) * 1.5 for pu, pv, pr in placed):
                uv = (u, v)
                break
        if uv is None:
            continue  # couldn't place without overlap -> fewer targets this frame
        u, v = uv
        placed.append((u, v, r))

        templates = library.get(cls.name)
        if templates:
            tmpl = templates[int(rng.integers(0, len(templates)))]
            obj = tmpl.duplicate()
            obj.hide(False)
            obj.set_scale([span, span, span])
            obj.set_cp("category_id", cls.id)
            obj.set_name(cls.name)
        else:
            obj = proxy.make_proxy(cls.shape, cls.id, cls.name, span=span)

        depth_off = float(rng.uniform(-0.12 * d, 0.12 * d))  # vary range a little
        pos = poi + right * u + up * v + fwd * depth_off
        obj.set_location([float(pos[0]), float(pos[1]), float(pos[2])])
        # moderate attitude: full yaw, limited pitch/roll (drones aren't usually inverted)
        obj.set_rotation_euler([
            float(rng.uniform(-0.5, 0.5)),
            float(rng.uniform(-0.5, 0.5)),
            float(rng.uniform(-np.pi, np.pi)),
        ])
        objs.append(obj)
    return objs


def cleanup(objs: list) -> None:
    """Remove the per-frame objects and lights so the next frame starts clean."""
    for o in objs:
        try:
            o.delete()
        except Exception:
            pass
    # Lights and the rest are cleared via reset_keyframes + delete in the loop.
