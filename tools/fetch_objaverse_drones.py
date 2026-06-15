"""Download drone / aircraft 3D models from Objaverse-LVIS into assets/drones/<class>/.

    python tools/fetch_objaverse_drones.py --per-class 3

No API key needed. Uses the curated Objaverse-LVIS category labels ('drone',
'helicopter', 'airplane', ...) so we get on-topic meshes, filters to commercially
usable licenses by default, downloads the .glb files, sorts them into the per-class
folders, and records source + license in assets/drones/manifest.yaml.

Objaverse objects are Creative Commons; for a dataset you intend to SELL, keep the
default license filter (CC0 / CC-BY) and keep the attribution recorded in the manifest.
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DRONES = ROOT / "assets" / "drones"
MANIFEST = DRONES / "manifest.yaml"

# Objaverse-LVIS category -> our class folder(s) (round-robin when several).
CATEGORY_TO_CLASSES = {
    "drone": ["quad_consumer", "quad_fpv"],
    "helicopter": ["helicopter"],
    "airplane": ["fixedwing_fpv"],
    "seaplane": ["fixedwing_fpv"],
    "jet_plane": ["fixedwing_mil"],
    "fighter_jet": ["fixedwing_mil"],
}
# Licenses safe for a commercial/redistributable dataset (exclude NC / ND).
COMMERCIAL_OK = {"by", "cc0", "cc-by", "cc-by-4.0", "cc0-1.0"}


def _load_manifest() -> dict:
    if MANIFEST.exists():
        return yaml.safe_load(MANIFEST.read_text(encoding="utf-8")) or {}
    return {}


def _save_manifest(man: dict) -> None:
    MANIFEST.write_text(yaml.safe_dump(man, sort_keys=False, allow_unicode=True), encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--per-class", type=int, default=3, help="models per class folder")
    p.add_argument("--categories", default="drone,helicopter,airplane",
                   help="comma list of Objaverse-LVIS categories")
    p.add_argument("--max-mb", type=float, default=40.0, help="skip glbs larger than this")
    p.add_argument("--allow-all-licenses", action="store_true",
                   help="include non-commercial / no-deriv licenses too")
    args = p.parse_args()

    import objaverse  # imported here so --help works without it

    cats = [c.strip() for c in args.categories.split(",") if c.strip()]
    lvis = objaverse.load_lvis_annotations()

    # Build a candidate uid->class plan (over-sample 4x to survive license/size filtering).
    plan: dict[str, str] = {}  # uid -> target class
    for cat in cats:
        if cat not in lvis:
            print(f"[objaverse] unknown category '{cat}' — skipping")
            continue
        classes = CATEGORY_TO_CLASSES.get(cat, [cat])
        uids = lvis[cat][: args.per_class * 4 * len(classes)]
        for i, uid in enumerate(uids):
            plan[uid] = classes[i % len(classes)]
    if not plan:
        print("[objaverse] nothing to fetch")
        return

    print(f"[objaverse] loading annotations for {len(plan)} candidates ...")
    anns = objaverse.load_annotations(list(plan.keys()))

    # License filter + per-class quota.
    chosen: list[tuple[str, str, str, str]] = []  # (uid, cls, license, name)
    quota = {c: args.per_class for cset in CATEGORY_TO_CLASSES.values() for c in cset}
    for uid, cls in plan.items():
        if quota.get(cls, 0) <= 0:
            continue
        meta = anns.get(uid, {})
        lic = str(meta.get("license", "?")).lower()
        if not args.allow_all_licenses and lic not in COMMERCIAL_OK:
            continue
        chosen.append((uid, cls, lic, meta.get("name", uid)))
        quota[cls] = quota.get(cls, 0) - 1

    if not chosen:
        print("[objaverse] no models passed the license filter — try --allow-all-licenses")
        return

    print(f"[objaverse] downloading {len(chosen)} models ...")
    paths = objaverse.load_objects(uids=[c[0] for c in chosen], download_processes=1)

    man = _load_manifest()
    models = man.get("models") or []
    existing = {m.get("file") for m in models}
    added = 0
    for uid, cls, lic, name in chosen:
        src = paths.get(uid)
        if not src or not Path(src).exists():
            continue
        mb = Path(src).stat().st_size / 1e6
        if mb > args.max_mb:
            print(f"[objaverse] skip {uid} ({mb:.0f} MB > {args.max_mb})")
            continue
        rel = f"{cls}/{uid}.glb"
        dst = DRONES / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        if rel not in existing:
            models.append({"file": rel, "class": cls, "license": lic,
                           "source": f"objaverse:{uid}", "name": name})
            existing.add(rel)
        print(f"[objaverse]   + {rel}  ({mb:.1f} MB, {lic})  {name[:40]}")
        added += 1

    man["models"] = models
    _save_manifest(man)
    print(f"\n[objaverse] done: {added} models added. Manifest: {MANIFEST}")
    print("[objaverse] next: render — the scene loader will use these instead of proxies.")


if __name__ == "__main__":
    main()
