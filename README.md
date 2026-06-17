# Simurg

*A procedural synthetic-data generator for drone / counter-UAS perception.*

Simurg renders large, **perfectly-labelled** datasets of drones across randomized
conditions (pose, range, lighting, weather, background — EO now, simulated IR later),
auto-generating COCO + YOLO annotations. It is the data engine that feeds a drone
detector / make-model classifier.

> **The product is one number, not pretty renders:** a detector trained on
> Simurg-only data that performs on *real* drone images. See `validate/`.

This repo currently implements **Phase 0–1**: a runnable static-image generator with
proxy drone meshes (no external 3D assets needed to start), COCO output via BlenderProc,
and a COCO→YOLO exporter. Later phases (domain-randomization breadth, synthetic-IR,
video/track MOT export) are scaffolded in `simurg/` and `configs/`.

---

## Requirements

- **Python 3.10+**
- **BlenderProc 2** (`pip install blenderproc`) — it downloads/manages its own Blender.
- A CUDA GPU is recommended (Cycles + later YOLO training), CPU works for the spike.
- For the validation loop only: `ultralytics`, `opencv-python`, `pycocotools`.

```powershell
# from the repo root
python -m venv venv
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install -r requirements.txt
# first BlenderProc run downloads Blender (one-time):
.\venv\Scripts\blenderproc.exe quickstart
```

---

## Admin panel (web UI)

A local control panel to manage everything without the command line — edit configs,
download/manage HDRI skies, upload drone models, launch renders with **live progress**,
and browse datasets with **label overlays**.

```powershell
.\run_webui.ps1
# or:  .\venv\Scripts\python.exe webui\app.py
```
Then open <http://127.0.0.1:5000>. Tabs:

- **Studio** — design the scene visually, then render:
  - **Viewpoint / detection geometry** — `ground → air` (C-UAS perimeter, camera looks up), `air → air` (drone-mounted, level), `air → ground` (overwatch, looks down), or `mixed`.
  - **Range** — close / medium / long / mixed (controls apparent target size).
  - **Drones per frame**, **which classes** to include, and **which skies** to use — all as toggles.
  - **Analog video-feed look** toggle — scanlines, chroma shift, noise, vignette (matches real FPV / analog C-UAS feeds; also strong augmentation).
  - Targets are auto-spread across the frame (no overlapping boxes).
  - Render with a live progress bar + log + a **preview strip** of the latest frames with labels.
- **Models** — fetch real drones from Objaverse (one click), upload your own; per-model **enable/disable** toggle, class reassignment, license badge, delete.
- **Skies** — download CC0 skies from PolyHaven; list/delete.
- **Datasets** — every render with stats; gallery with toggleable box overlays; one-click YOLO export.
- **Advanced** — raw config field editor for power users.

## Phase 0 — spike (run this first)

Render a few proxy drones over a flat sky and write COCO. Confirms the toolchain end to end.

```powershell
# BlenderProc must launch the script (it injects the 'blenderproc' module):
.\venv\Scripts\blenderproc.exe run generate.py --config configs/skywatch.yaml --n 20 --output out/spike
```

Outputs:
```
out/spike/
├── coco/
│   ├── coco_annotations.json      # COCO boxes + polygon masks
│   └── images/                    # rendered RGB frames
└── dataset_card.json              # every config value + counts (reproducibility)
```

Overlay the labels to confirm they are pixel-perfect:

```powershell
.\venv\Scripts\python.exe validate\check_coco.py --coco out/spike/coco/coco_annotations.json --images out/spike/coco/images --n 6
```

## Phase 1 — a real batch + YOLO export

```powershell
.\venv\Scripts\blenderproc.exe run generate.py --config configs/skywatch.yaml --n 2000 --output out/skywatch_v0
.\venv\Scripts\python.exe simurg\exporters\coco_to_yolo.py --coco out/skywatch_v0/coco/coco_annotations.json --out out/skywatch_v0/yolo
```

## Dataset tools

```powershell
# QA a dataset: class balance + box-size mix (are there enough tiny/long-range targets?)
.\venv\Scripts\python.exe validate\stats.py --coco out/skywatch_v0/coco/coco_annotations.json

# YOLO export WITH a real train/val split (don't validate on training frames)
.\venv\Scripts\python.exe simurg\exporters\coco_to_yolo.py `
    --coco out/skywatch_v0/coco/coco_annotations.json --out out/skywatch_v0/yolo --val-split 0.1

# Render in parallel shards, then merge them into one dataset (scales across processes)
.\venv\Scripts\python.exe simurg\exporters\coco_merge.py --out out/merged/coco `
    out/shard0/coco out/shard1/coco out/shard2/coco
```

Run the offline suite any time (no Blender needed) to confirm the non-render code is healthy:

```powershell
.\venv\Scripts\python.exe validate\selftest.py
```

## Validation (the metric that matters)

Put 300–800 hand-checked **real** drone images in `validate/real_test/` (YOLO format), then:

```powershell
.\venv\Scripts\python.exe validate\train_yolo.py --data out/skywatch_v0/yolo --epochs 50
.\venv\Scripts\python.exe validate\eval_real.py  --weights runs/detect/train/weights/best.pt --real validate/real_test
```

Record the **mAP@0.5 on real** — that number, however low at first, is the baseline you iterate against.

---

## Add real assets (optional, improves realism)

- **HDRI skies** — fetch CC0 skies from PolyHaven automatically (no API key):
  ```powershell
  .\venv\Scripts\python.exe tools\fetch_hdris.py --n 8 --res 2k
  ```
  They land in `assets/hdris/`; when that folder is non-empty the renderer uses a random
  real sky per frame instead of the flat-colour sky. (Delete any night/dawn skies you don't
  want if you're training a daytime-only detector.)
- **Drone models** — fetch real 3D drones from **Objaverse** (no API key), filtered to
  commercially-usable licenses and sorted into the per-class folders:
  ```powershell
  .\venv\Scripts\python.exe tools\fetch_objaverse_drones.py --per-class 3 --categories drone,helicopter,airplane
  ```
  Each model's source uid + license is recorded in `assets/drones/manifest.yaml`. You can
  also drop your own `.glb`/`.obj`/`.fbx` into `assets/drones/<class>/` and add a manifest
  entry (or use the admin panel's upload form). The renderer loads every manifest model
  once, normalizes it to unit size, and instances it per frame; **classes with a model use
  it, classes without one fall back to the proxy** — so you can mix.

Without any models, Simurg uses built-in **primitive proxy drones** so you can run today.
Model binaries are git-ignored; the manifest (with source uids) is committed, so a fresh
clone re-fetches the same models by re-running the fetcher.

---

## Layout

```
generate.py                  # BlenderProc entrypoint (run via `blenderproc run`)
configs/skywatch.yaml        # scene recipe (classes, ranges, render settings)
simurg/
  config.py                  # YAML -> typed config
  scene.py                   # BlenderProc scene build + domain randomization
  proxy.py                   # primitive proxy drone meshes (no assets needed)
  card.py                    # dataset_card.json writer
  exporters/coco_to_yolo.py  # COCO -> YOLO converter
validate/
  check_coco.py              # overlay COCO labels to verify
  train_yolo.py  eval_real.py
assets/  samples/  out/
```

## Roadmap (from the build plan)

- [x] Phase 0 — spike: proxy drone → COCO
- [x] Phase 1 — static generator + YOLO export + dataset card
- [x] Config validation, dataset QA/stats, train/val split, shard merge, offline test suite
- [x] **Admin panel web UI** (`webui/`) — configs, HDRIs, models, render-with-live-progress, dataset gallery
- [~] Phase 2 — domain randomization: range/pose/sun/HDRI/flat-sky done; weather + sensor noise next
- [~] Phase 3 — multi-class + hard negatives done; synthetic-IR tone-mapper done (`thermal.py`), Blender emission pass pending
- [ ] Phase 4 — sequence/track mode + MOT export
- [ ] Phase 5 — sim-to-real validation + randomization ablations
- [ ] Phase 6 — packaging + public sample release + benchmark page

See `../simurg-build-plan.md` for the full plan.

## Tools quick-reference

| File | What it does | Runs without Blender |
|------|--------------|:--:|
| `generate.py` | Render N frames → COCO (+ dataset card) | no |
| `simurg/exporters/coco_to_yolo.py` | COCO → YOLO, optional `--val-split` | yes |
| `simurg/exporters/coco_merge.py` | Merge parallel render shards | yes |
| `simurg/thermal.py` | Synthetic-IR tone-mapping (palettes + IR noise) | yes |
| `tools/fetch_hdris.py` | Download CC0 sky HDRIs from PolyHaven | yes |
| `tools/fetch_objaverse_drones.py` | Download real 3D drone models from Objaverse | yes |
| `webui/app.py` | Admin panel web UI (configs/HDRIs/models/render/datasets) | yes |
| `validate/stats.py` | Class balance + box-size QA | yes |
| `validate/check_coco.py` | Overlay labels on images to eyeball | yes |
| `validate/train_yolo.py` / `eval_real.py` | Train on synth, eval on real → sim-to-real mAP | yes |
| `validate/selftest.py` | Offline test suite (7 checks) | yes |
