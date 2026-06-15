import blenderproc as bproc  # noqa: E402  MUST be the literal first line (BlenderProc enforces this)

# Simurg entrypoint - run under BlenderProc:
#   blenderproc run generate.py --config configs/skywatch.yaml --n 200 --output out/run
# BlenderProc injects the 'blenderproc' module and a Blender-bundled Python, so this
# file MUST be launched via `blenderproc run`, not plain `python`.

import argparse
import os
import sys

import numpy as np

# Make the repo root importable (generate.py lives at the repo root).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from blenderproc.python.utility.LabelIdMapping import LabelIdMapping

from simurg import __version__
from simurg.config import load_config
from simurg import scene as scn
from simurg.card import write_card


def parse_args() -> argparse.Namespace:
    # Strip BlenderProc's own argv separator if present.
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    p = argparse.ArgumentParser(description="Generate a Simurg dataset.")
    p.add_argument("--config", required=True, help="path to a YAML scene recipe")
    p.add_argument("--n", type=int, default=None, help="number of frames (overrides config)")
    p.add_argument("--output", required=True, help="output directory")
    p.add_argument("--seed", type=int, default=None, help="random seed (overrides config)")
    p.add_argument("--samples", type=int, default=None, help="Cycles samples (overrides config)")
    return p.parse_args(argv)


def main() -> None:
    args = parse_args()
    cfg = load_config(args.config)
    if args.samples is not None:
        cfg.samples = args.samples
    n = args.n if args.n is not None else cfg.n
    seed = args.seed if args.seed is not None else cfg.seed
    rng = np.random.default_rng(seed)

    coco_dir = os.path.join(args.output, "coco")
    os.makedirs(coco_dir, exist_ok=True)

    # Stable category names keyed by id, so duplicate object names ("fixedwing_fpv.001"
    # that Blender auto-generates) don't leak into the COCO categories.
    label_mapping = LabelIdMapping.from_dict({c.name: c.id for c in cfg.classes})

    bproc.init()
    scn.setup_renderer(cfg)
    hdris = scn._list_hdris(cfg)

    # Permanent off-screen anchor: BlenderProc's render() refuses to run with zero
    # mesh objects, which would crash hard-negative (empty) frames. This tiny cube
    # sits 10 km below the scene (never in frame) with category_id 0 (background),
    # so it satisfies the renderer without ever producing an annotation.
    anchor = bproc.object.create_primitive("CUBE")
    anchor.set_location([0.0, 0.0, -10000.0])
    anchor.set_scale([0.001, 0.001, 0.001])
    anchor.set_cp("category_id", 0)
    anchor.set_name("__anchor__")

    per_class = {c.name: 0 for c in cfg.classes}
    empty_frames = 0
    rendered = 0

    for i in range(n):
        bproc.utility.reset_keyframes()

        targets = scn.build_targets(cfg, rng)
        if not targets:
            empty_frames += 1
        else:
            for t in targets:
                cid = t.get_cp("category_id")
                name = next((c.name for c in cfg.classes if c.id == cid), str(cid))
                per_class[name] = per_class.get(name, 0) + 1

        light = scn.set_lighting(cfg, rng)
        scn.set_background(cfg, rng, hdris)
        scn.sample_camera(cfg, rng, targets)

        # Segmentation must be enabled AFTER this frame's objects exist (see scene.py).
        scn.enable_segmentation()
        data = bproc.renderer.render()

        bproc.writer.write_coco_annotations(
            coco_dir,
            instance_segmaps=data["instance_segmaps"],
            instance_attribute_maps=data["instance_attribute_maps"],
            colors=data["colors"],
            color_file_format="JPEG",
            # RLE (not "polygon"): BlenderProc's polygon encoder crashes under NumPy 2.x
            # (binary_mask_to_polygon -> inhomogeneous np.array). RLE is valid COCO and
            # the YOLO export uses bboxes, so masks-as-RLE costs us nothing here.
            mask_encoding_format="rle",
            label_mapping=label_mapping,
            append_to_existing_output=(rendered > 0),
        )
        rendered += 1

        # Per-frame cleanup so the next scene starts blank.
        for t in targets:
            try:
                t.delete()
            except Exception:
                pass
        try:
            light.delete()
        except Exception:
            pass

        if (i + 1) % 25 == 0 or i == n - 1:
            print(f"[simurg] rendered {i + 1}/{n}", flush=True)

    write_card(
        args.output,
        config_raw=cfg.raw,
        config_path=args.config,
        n_requested=n,
        n_rendered=rendered,
        seed=seed,
        category_map=cfg.category_map(),
        per_class_instances=per_class,
        empty_frames=empty_frames,
        simurg_version=__version__,
    )
    print(f"[simurg] done -> {args.output}", flush=True)
    print(f"[simurg] instances/class: {per_class}  empty-frames: {empty_frames}", flush=True)


if __name__ == "__main__":
    main()
