# Worklog

## Session 2 — Phase-0 spike debugged on real Blender (GPU verified working)

Ran the actual render on your RTX 2050. Fixed 6 real bugs the offline tests couldn't
catch; the pipeline now renders → segments → writes valid COCO end to end.

1. **BlenderProc import position.** `import blenderproc as bproc` must be the *literal
   first line* — it was below the docstring. Moved it up (docstring → comments).
2. **Segmentation returned only "World".** `enable_segmentation_output` needs
   `default_values={"category_id": 0}`, else category_id never populates → 0 annotations.
3. **Empty/negative frames crashed render()** ("no mesh-objects to render"). Added a
   permanent off-screen anchor cube (10 km below, category_id 0) so hard-negative frames
   still render with no annotation.
4. **Loop produced 0 annotations.** Objects created *after* a one-time
   `enable_segmentation_output` aren't segmented. Moved the enable INTO the per-frame loop
   (after building targets). Proven with a 3-frame probe.
5. **Polygon mask encoder crashed under NumPy 2.x** (`binary_mask_to_polygon` →
   inhomogeneous np.array). Switched COCO masks to `mask_encoding_format="rle"` (YOLO
   export uses bboxes, so no loss).
6. **Duplicate class names** (`fixedwing_fpv.001` from Blender auto-rename) leaked into
   COCO categories. Added `LabelIdMapping` so categories come from the config.

**Verified result:** `--n 12` → 12 images, 11 annotations, 3 hard-negatives, clean class
names, **91% tiny+small targets** (realistic long-range mix). YOLO export + train/val
split + label-overlay QA all confirmed on real output. Offline suite still 7/7.

Sample output left in `out/diag/` for you to inspect (`coco/_check/` has label overlays).

### Added: real HDRI skies (`tools/fetch_hdris.py`)
- Downloads CC0 sky HDRIs from PolyHaven (public API, no key). Fetched 6× 2k skies.
- **Fix:** `_list_hdris` now returns ABSOLUTE paths — Blender runs from its own cwd, so
  relative HDRI paths failed with "Cannot read ...".
- **Verified:** render with HDRIs → realistic dusk/sky backgrounds + tight boxes on the
  proxy drones (see `out/hdritest/coco/_check/`). This is genuinely usable training data.

---

# Worklog — autonomous session (2026-06-15)

You went to sleep and asked me to test, fix, and add features within my limit. Here's
exactly what changed, so you can review fast.

## Fixed
- **scene.py — flat-sky background.** Replaced a BlenderProc helper whose name/signature
  drifts across versions with a stable `bpy` world-node implementation (`_set_world_color`).
  This was the most likely runtime break in the render path. *(Can't run Blender here, so
  verify in the Phase-0 spike — but this removes the known fragile call.)*

## Added (all unit-tested offline — `validate/selftest.py`, 7/7 passing)
1. **Config validation** (`config.py::Config.validate`) — catches duplicate class ids,
   reserved id 0, inverted ranges, bad resolution, unknown shapes, asset-class typos.
   Now runs automatically on `load_config`.
2. **Train/val split** in `coco_to_yolo.py` — `--val-split 0.1` makes real `images/train`
   + `images/val` dirs (before, train and val pointed at the same images → inflated mAP).
3. **Dataset QA** (`validate/stats.py`) — class balance + box-size histogram (tiny/small/
   medium/large) + empty-frame fraction; warns if too few hard long-range targets.
4. **Synthetic-IR tone-mapper** (`synthrange/thermal.py`) — pure-NumPy palettes
   (white_hot/black_hot/ironbow) + percentile auto-gain + IR noise/banding. This is the
   testable half of Phase 3; the Blender emission pass is still to wire into scene.py.
5. **Shard merge** (`synthrange/exporters/coco_merge.py`) — combine COCO outputs from
   parallel render processes into one dataset (unique-id remap, category unify by name).
   Lets you scale rendering horizontally.
6. **Offline test suite** expanded to cover all of the above + syntax-compiled every file.

## Verified
- `python validate/selftest.py` → **ALL PASSED** (7 checks).
- `python -m py_compile` on every `.py` → **clean** (no syntax errors anywhere).
- Could NOT run: the BlenderProc render path (no Blender in this env). `generate.py`,
  `scene.py`, `proxy.py` follow BlenderProc 2 idioms but the Phase-0 spike is their real test.

## Not done (left for you / next session)
- Wire the thermal emission pass into `scene.py` (needs Blender material/emission setup).
- Phase 2 weather + in-render sensor noise (haze, motion blur, compositor noise).
- Phase 4 sequence/track mode + MOT exporter.
- I did **not** commit — `git` is initialized but nothing is committed (per your call).
  When you're ready: `git add -A && git commit -m "SynthRange Phase 0-1 + tooling"`.

## First thing to do when you wake
Run the Phase-0 spike (installs Blender on first run) and eyeball the label overlay:
```powershell
cd "C:\Users\Kutup TAN\Documents\synthrange"
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\blenderproc.exe run generate.py --config configs/skywatch.yaml --n 20 --output out/spike
.\venv\Scripts\python.exe validate\check_coco.py --coco out/spike/coco/coco_annotations.json --images out/spike/coco/images --n 6
.\venv\Scripts\python.exe validate\stats.py --coco out/spike/coco/coco_annotations.json
```
If the boxes hug the proxy drones, the pipeline is real — scale up and start the
train→eval loop for your first sim-to-real number.

## Session 3 — Admin panel (web UI)

Built `webui/` — a local Flask control panel. Verified every endpoint + both job types
(render via blenderproc, YOLO export) end to end against a live server.

- **Backend** `webui/app.py` (Flask) + `webui/jobs.py` (subprocess job runner with live
  progress parsed from "rendered X/Y", log capture, stop via taskkill tree).
- **Frontend** `webui/templates/index.html` + `static/{style.css,app.js}` — dark single-page
  UI, 5 tabs: Render (live progress bar + log + 1-frame preview), Config (form for all
  knobs + add/remove classes + Save As), Skies (PolyHaven download + delete), Models
  (upload .glb/.obj/.fbx + class + license, manifest-tracked), Datasets (list + stats +
  gallery with toggleable box overlays + YOLO export button).
- Added `generate.py --samples` override (used by the panel's quick preview).
- Launch: `.\run_webui.ps1` (or `venv\Scripts\python.exe webui\app.py`) -> http://127.0.0.1:5000
- **Verified live:** /api/configs, /api/hdris (8 skies), /api/datasets (your mytest run
  showed up), /api/config, /api/models, index (200); export job done with train/val split;
  render job launched blenderproc, progressed 0->100%, produced 2 imgs/3 anns. Server then
  stopped + test artifacts cleaned. Offline suite still 7/7.
- New dep: flask>=3.0 (in requirements.txt).
