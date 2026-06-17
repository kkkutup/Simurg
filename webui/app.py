"""Simurg admin panel — a local Flask web UI to manage configs, HDRIs, drone
models, launch renders with live progress, and browse datasets with label overlays.

Run it:
    venv\\Scripts\\python.exe webui\\app.py
then open http://127.0.0.1:5000

The web server runs in the normal venv Python; renders are launched as subprocesses
using venv\\Scripts\\blenderproc.exe so the heavy Blender work stays out of process.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from glob import glob
from pathlib import Path

import yaml
from flask import Flask, jsonify, request, send_file, send_from_directory

ROOT = Path(__file__).resolve().parents[1]
CONFIGS = ROOT / "configs"
HDRIS = ROOT / "assets" / "hdris"
MODELS = ROOT / "assets" / "drones"
OUT = ROOT / "out"
BLENDERPROC = ROOT / "venv" / "Scripts" / ("blenderproc.exe" if os.name == "nt" else "blenderproc")
PYEXE = ROOT / "venv" / "Scripts" / ("python.exe" if os.name == "nt" else "python")

sys.path.insert(0, str(ROOT))
from webui.jobs import JobManager  # noqa: E402

# Load validate/stats.analyze without needing a package.
_spec = importlib.util.spec_from_file_location("sr_stats", ROOT / "validate" / "stats.py")
_stats = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_stats)  # type: ignore[union-attr]

app = Flask(__name__, static_folder="static", template_folder="templates")
jm = JobManager()

ALLOWED_MODEL_EXT = {".obj", ".glb", ".fbx", ".ply", ".blend"}

# Studio presets — the UI picks a name, these become concrete config ranges.
VIEWPOINTS = {
    "ground_to_air": {"label": "Ground → Air", "elevation_deg": [10, 70],
                      "hint": "Camera on the ground looking up at drones (C-UAS perimeter)."},
    "air_to_air":    {"label": "Air → Air", "elevation_deg": [-20, 20],
                      "hint": "Drone-mounted camera, roughly level (interceptor / detect-and-avoid)."},
    "air_to_ground": {"label": "Air → Ground", "elevation_deg": [-70, -10],
                      "hint": "Looking down from above (overwatch / surveillance)."},
    "mixed":         {"label": "Mixed", "elevation_deg": [-30, 70],
                      "hint": "Every angle — most robust, hardest."},
}
RANGES = {
    "close":  {"label": "Close (5–30 m)", "distance_m": [5, 30]},
    "medium": {"label": "Medium (20–120 m)", "distance_m": [20, 120]},
    "long":   {"label": "Long (80–400 m)", "distance_m": [80, 400]},
    "mixed":  {"label": "Mixed (8–300 m)", "distance_m": [8, 300]},
}


# ----------------------------------------------------------------------------- helpers
def _read_yaml(p: Path) -> dict:
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def _write_yaml(p: Path, data: dict) -> None:
    p.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _safe_name(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in "-_") or "untitled"


# ----------------------------------------------------------------------------- pages
@app.route("/")
def index():
    return send_from_directory("templates", "index.html")


# ----------------------------------------------------------------------------- configs
@app.get("/api/configs")
def api_configs():
    files = sorted(p.stem for p in CONFIGS.glob("*.yaml"))
    return jsonify(files)


@app.get("/api/config/<name>")
def api_config_get(name):
    p = CONFIGS / f"{_safe_name(name)}.yaml"
    if not p.exists():
        return jsonify({"error": "not found"}), 404
    return jsonify(_read_yaml(p))


@app.post("/api/config/<name>")
def api_config_save(name):
    data = request.get_json(force=True)
    p = CONFIGS / f"{_safe_name(name)}.yaml"
    _write_yaml(p, data)
    return jsonify({"ok": True, "saved": p.name})


@app.delete("/api/config/<name>")
def api_config_delete(name):
    p = CONFIGS / f"{_safe_name(name)}.yaml"
    if p.exists():
        p.unlink()
    return jsonify({"ok": True})


# ----------------------------------------------------------------------------- HDRIs
@app.get("/api/hdris")
def api_hdris():
    HDRIS.mkdir(parents=True, exist_ok=True)
    items = []
    for f in sorted(HDRIS.glob("*.hdr")) + sorted(HDRIS.glob("*.exr")):
        items.append({"name": f.name, "mb": round(f.stat().st_size / 1e6, 1)})
    return jsonify(items)


@app.post("/api/hdris/fetch")
def api_hdris_fetch():
    body = request.get_json(force=True)
    n = int(body.get("n", 6))
    res = str(body.get("res", "2k"))
    cmd = [str(PYEXE), "tools/fetch_hdris.py", "--n", str(n), "--res", res]
    jid = jm.start(cmd, str(ROOT), kind="fetch")
    return jsonify({"job": jid})


@app.post("/api/hdris/delete")
def api_hdris_delete():
    name = request.get_json(force=True).get("name", "")
    p = HDRIS / Path(name).name
    if p.exists() and p.suffix.lower() in (".hdr", ".exr"):
        p.unlink()
    return jsonify({"ok": True})


# ----------------------------------------------------------------------------- models
def _manifest_path() -> Path:
    return MODELS / "manifest.yaml"


def _all_model_files() -> list[Path]:
    out = []
    if MODELS.exists():
        for f in MODELS.rglob("*"):
            if f.suffix.lower() in ALLOWED_MODEL_EXT:
                out.append(f)
    return out


@app.get("/api/models")
def api_models():
    MODELS.mkdir(parents=True, exist_ok=True)
    man = _read_yaml(_manifest_path()) if _manifest_path().exists() else {}
    by_file = {m.get("file"): m for m in (man.get("models") or [])}
    items = []
    for f in _all_model_files():
        rel = f.relative_to(MODELS).as_posix()
        m = by_file.get(rel, {})
        items.append({
            "file": rel,
            "mb": round(f.stat().st_size / 1e6, 2),
            "class": m.get("class", ""),
            "license": m.get("license", "?"),
            "name": m.get("name", f.stem),
            "enabled": bool(m.get("enabled", True)),
        })
    return jsonify({"models": items})


@app.post("/api/models/update")
def api_models_update():
    body = request.get_json(force=True)
    rel = body.get("file", "")
    man = _read_yaml(_manifest_path()) if _manifest_path().exists() else {}
    models = man.get("models") or []
    found = False
    for m in models:
        if m.get("file") == rel:
            if "enabled" in body:
                m["enabled"] = bool(body["enabled"])
            if body.get("class") is not None:
                m["class"] = body["class"]
            found = True
            break
    if not found:  # file on disk but not yet in manifest
        entry = {"file": rel, "class": body.get("class", ""), "license": "unknown"}
        if "enabled" in body:
            entry["enabled"] = bool(body["enabled"])
        models.append(entry)
    man["models"] = models
    _write_yaml(_manifest_path(), man)
    return jsonify({"ok": True})


@app.post("/api/models/fetch")
def api_models_fetch():
    body = request.get_json(force=True)
    per = int(body.get("per_class", 3))
    cats = str(body.get("categories", "drone,helicopter,airplane"))
    cmd = [str(PYEXE), "tools/fetch_objaverse_drones.py",
           "--per-class", str(per), "--categories", cats]
    if body.get("allow_all_licenses"):
        cmd.append("--allow-all-licenses")
    jid = jm.start(cmd, str(ROOT), kind="fetch")
    return jsonify({"job": jid})


@app.post("/api/models/upload")
def api_models_upload():
    if "file" not in request.files:
        return jsonify({"error": "no file"}), 400
    f = request.files["file"]
    cls = request.form.get("class", "")
    license_ = request.form.get("license", "unknown")
    ext = Path(f.filename or "").suffix.lower()
    if ext not in ALLOWED_MODEL_EXT:
        return jsonify({"error": f"unsupported type {ext}"}), 400
    fname = Path(f.filename).name
    subdir = _safe_name(cls) if cls else ""
    dst = (MODELS / subdir / fname) if subdir else (MODELS / fname)
    dst.parent.mkdir(parents=True, exist_ok=True)
    f.save(dst)
    rel = dst.relative_to(MODELS).as_posix()
    man = _read_yaml(_manifest_path()) if _manifest_path().exists() else {}
    models = [m for m in (man.get("models") or []) if m.get("file") != rel]
    models.append({"file": rel, "class": cls, "license": license_, "enabled": True})
    man["models"] = models
    _write_yaml(_manifest_path(), man)
    return jsonify({"ok": True, "file": rel})


@app.post("/api/models/delete")
def api_models_delete():
    rel = request.get_json(force=True).get("file", "")
    p = (MODELS / rel).resolve()
    # guard against path escapes
    if str(p).startswith(str(MODELS.resolve())) and p.exists() and p.suffix.lower() in ALLOWED_MODEL_EXT:
        p.unlink()
    man = _read_yaml(_manifest_path()) if _manifest_path().exists() else {}
    man["models"] = [m for m in (man.get("models") or []) if m.get("file") != rel]
    _write_yaml(_manifest_path(), man)
    return jsonify({"ok": True})


# ----------------------------------------------------------------------------- studio
@app.get("/api/scene-options")
def api_scene_options():
    base = CONFIGS / "skywatch.yaml"
    cfg = _read_yaml(base) if base.exists() else {}
    classes = [c["name"] for c in cfg.get("classes", [])]
    skies = [f.name for f in sorted(HDRIS.glob("**/*.hdr")) + sorted(HDRIS.glob("**/*.exr"))]
    sc = cfg.get("scene", {})
    bg = cfg.get("background", {})
    return jsonify({
        "viewpoints": [{"id": k, **v} for k, v in VIEWPOINTS.items()],
        "ranges": [{"id": k, **v} for k, v in RANGES.items()],
        "classes": classes,
        "skies": skies,
        "defaults": {
            "viewpoint": sc.get("viewpoint", "ground_to_air"),
            "range": "mixed",
            "n_targets": sc.get("n_targets", [0, 2]),
            "include_classes": sc.get("include_classes", []) or classes,
            "hdri_include": bg.get("hdri_include", []) or skies,
            "samples": cfg.get("render", {}).get("samples", 48),
            "analog": bool(cfg.get("effects", {}).get("analog", {}).get("enabled", False)),
        },
    })


def _build_studio_config(scenario: dict) -> str:
    """Write a derived config (configs/_studio.yaml) from a Studio scenario."""
    base = CONFIGS / "skywatch.yaml"
    cfg = _read_yaml(base) if base.exists() else {}
    vp = scenario.get("viewpoint", "ground_to_air")
    rng = scenario.get("range", "mixed")
    cfg.setdefault("scene", {})
    cfg.setdefault("camera", {})
    cfg.setdefault("background", {})
    cfg.setdefault("render", {})
    cfg["scene"]["viewpoint"] = vp
    cfg["camera"]["elevation_deg"] = VIEWPOINTS.get(vp, VIEWPOINTS["mixed"])["elevation_deg"]
    cfg["scene"]["distance_m"] = RANGES.get(rng, RANGES["mixed"])["distance_m"]
    if scenario.get("n_targets"):
        cfg["scene"]["n_targets"] = scenario["n_targets"]
    if scenario.get("include_classes") is not None:
        cfg["scene"]["include_classes"] = scenario["include_classes"]
    if scenario.get("hdri_include") is not None:
        cfg["background"]["hdri_include"] = scenario["hdri_include"]
    if scenario.get("samples"):
        cfg["render"]["samples"] = int(scenario["samples"])
    cfg.setdefault("effects", {}).setdefault("analog", {})["enabled"] = bool(scenario.get("analog", False))
    cfg.setdefault("dataset", {})["name"] = scenario.get("output", "studio")
    out = CONFIGS / "_studio.yaml"
    _write_yaml(out, cfg)
    return "_studio"


# ----------------------------------------------------------------------------- render
@app.post("/api/render")
def api_render():
    body = request.get_json(force=True)
    n = int(body.get("n", 100))
    seed = body.get("seed")
    samples = body.get("samples")
    if body.get("studio"):  # scenario-driven render from the Studio tab
        cfg = _build_studio_config(body["studio"])
        out_name = _safe_name(body["studio"].get("output", "studio_run"))
    else:                   # raw config render (advanced Config tab)
        cfg = _safe_name(body.get("config", "skywatch"))
        out_name = _safe_name(body.get("output", cfg + "_run"))
    out_rel = f"out/{out_name}"
    cmd = [str(BLENDERPROC), "run", "generate.py",
           "--config", f"configs/{cfg}.yaml", "--n", str(n), "--output", out_rel]
    if samples:
        cmd += ["--samples", str(int(samples))]
    if seed not in (None, ""):
        cmd += ["--seed", str(int(seed))]
    jid = jm.start(cmd, str(ROOT), kind="render", total=n, output=out_name)
    return jsonify({"job": jid})


@app.post("/api/export/<name>")
def api_export(name):
    name = _safe_name(name)
    coco = f"out/{name}/coco/coco_annotations.json"
    val = request.get_json(silent=True) or {}
    split = float(val.get("val_split", 0.1))
    cmd = [str(PYEXE), "simurg/exporters/coco_to_yolo.py",
           "--coco", coco, "--out", f"out/{name}/yolo", "--val-split", str(split)]
    jid = jm.start(cmd, str(ROOT), kind="export", output=name)
    return jsonify({"job": jid})


# ----------------------------------------------------------------------------- jobs
@app.get("/api/jobs")
def api_jobs():
    return jsonify({"active": jm.active(), "jobs": jm.list()})


@app.get("/api/job/<jid>")
def api_job(jid):
    j = jm.get(jid)
    return (jsonify(j), 200) if j else (jsonify({"error": "not found"}), 404)


@app.post("/api/job/<jid>/stop")
def api_job_stop(jid):
    return jsonify({"ok": jm.stop(jid)})


# ----------------------------------------------------------------------------- datasets
def _dataset_dirs() -> list[str]:
    if not OUT.exists():
        return []
    out = []
    for d in sorted(OUT.iterdir()):
        if (d / "coco" / "coco_annotations.json").exists():
            out.append(d.name)
    return out


@app.get("/api/datasets")
def api_datasets():
    res = []
    for name in _dataset_dirs():
        coco = OUT / name / "coco" / "coco_annotations.json"
        try:
            s = _stats.analyze(str(coco))
            res.append({"name": name, "images": s["images"],
                        "annotations": s["annotations"],
                        "empty_frac": s["empty_frac"]})
        except Exception:  # noqa: BLE001
            res.append({"name": name, "images": "?", "annotations": "?", "empty_frac": 0})
    return jsonify(res)


@app.get("/api/dataset/<name>/stats")
def api_dataset_stats(name):
    coco = OUT / _safe_name(name) / "coco" / "coco_annotations.json"
    if not coco.exists():
        return jsonify({"error": "not found"}), 404
    return jsonify(_stats.analyze(str(coco)))


@app.get("/api/dataset/<name>/gallery")
def api_dataset_gallery(name):
    name = _safe_name(name)
    coco_path = OUT / name / "coco" / "coco_annotations.json"
    if not coco_path.exists():
        return jsonify({"error": "not found"}), 404
    coco = json.loads(coco_path.read_text(encoding="utf-8"))
    cats = {c["id"]: c["name"] for c in coco["categories"]}
    anns: dict[int, list] = {}
    for a in coco["annotations"]:
        anns.setdefault(a["image_id"], []).append(
            {"bbox": a["bbox"], "label": cats.get(a["category_id"], "?")})
    limit = int(request.args.get("limit", 60))
    items = []
    for im in coco["images"][:limit]:
        fn = Path(im["file_name"]).name
        items.append({"file": fn, "w": im["width"], "h": im["height"],
                      "boxes": anns.get(im["id"], [])})
    return jsonify({"classes": list(cats.values()), "items": items, "total": len(coco["images"])})


@app.get("/api/dataset/<name>/image/<file>")
def api_dataset_image(name, file):
    p = OUT / _safe_name(name) / "coco" / "images" / Path(file).name
    if not p.exists():
        return "not found", 404
    return send_file(p)


if __name__ == "__main__":
    print("Simurg admin panel -> http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
