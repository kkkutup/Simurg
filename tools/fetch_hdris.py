"""Download + categorize CC0 sky HDRIs from PolyHaven into assets/hdris/.

    python tools/fetch_hdris.py --n 8 --sky-only      # pure-sky only (for air->air)
    python tools/fetch_hdris.py --n 8                  # skies category (mix of sky/horizon)
    python tools/fetch_hdris.py --retag                # (re)tag existing files, no download

No API key needed (PolyHaven public API, all CC0). Each HDRI is classified using
PolyHaven's own categories/tags into `sky_only` (clean sky, no ground — needed for
air->air) vs environment (has horizon/terrain), and recorded in assets/hdris/manifest.yaml
so the Studio can pick the right backgrounds per viewpoint.

Stdlib for HTTP; PyYAML for the manifest. Idempotent.
"""
from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path

import yaml

API = "https://api.polyhaven.com"
UA = {"User-Agent": "simurg-hdri-fetch/1.1 (+https://polyhaven.com)"}
HDRIS = Path(__file__).resolve().parents[1] / "assets" / "hdris"
MANIFEST = HDRIS / "manifest.yaml"

# Tags that imply visible ground / horizon / structures (NOT clean sky).
GROUND_TAGS = {
    "field", "fields", "mountain", "mountains", "hill", "hills", "tree", "trees",
    "forest", "woods", "urban", "city", "building", "buildings", "street", "rock",
    "rocks", "grass", "road", "desert", "beach", "snow", "industrial", "ruins",
    "park", "nature", "farm", "coast", "harbor", "harbour", "bridge", "interior",
    "indoor", "studio", "garden", "ground", "terrain", "village", "house",
}


def _get_json(url: str):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _all_hdri_assets() -> dict:
    """slug -> metadata (name, categories, tags, download_count, ...)."""
    return _get_json(f"{API}/assets?type=hdris")


def classify(slug: str, meta: dict) -> tuple[bool, list[str]]:
    cats = [c.lower() for c in meta.get("categories", [])]
    tags = [t.lower() for t in meta.get("tags", [])]
    allt = set(cats) | set(tags)
    sky_only = ("puresky" in slug.lower()) or ("skies" in cats and not (allt & GROUND_TAGS))
    return bool(sky_only), sorted(allt)


def _slug_from_file(name: str) -> str:
    s = Path(name).stem
    for res in ("_1k", "_2k", "_4k", "_8k"):
        if s.endswith(res):
            return s[: -len(res)]
    return s


def file_url(slug: str, res: str) -> str | None:
    try:
        files = _get_json(f"{API}/files/{slug}")
        hdri = files.get("hdri", {})
        entry = hdri.get(res) or hdri.get("1k") or next(iter(hdri.values()), {})
        return entry.get("hdr", {}).get("url")
    except Exception as e:  # noqa: BLE001
        print(f"[hdri] no files for '{slug}' ({e})")
        return None


def download(url: str, dst: Path) -> bool:
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=180) as r, open(dst, "wb") as f:
            f.write(r.read())
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[hdri] download failed ({e})")
        return False


def _load_manifest() -> dict:
    if MANIFEST.exists():
        return yaml.safe_load(MANIFEST.read_text(encoding="utf-8")) or {}
    return {}


def _save_manifest(man: dict) -> None:
    HDRIS.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(yaml.safe_dump(man, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _upsert(man: dict, entry: dict) -> None:
    skies = man.setdefault("skies", [])
    skies[:] = [s for s in skies if s.get("file") != entry["file"]]
    skies.append(entry)


def retag(assets: dict) -> None:
    """Rebuild manifest tags for files already on disk (no download)."""
    man = _load_manifest()
    n = 0
    for f in sorted(HDRIS.glob("*.hdr")) + sorted(HDRIS.glob("*.exr")):
        slug = _slug_from_file(f.name)
        meta = assets.get(slug, {})
        sky_only, tags = classify(slug, meta)
        _upsert(man, {"file": f.name, "slug": slug, "sky_only": sky_only,
                      "tags": tags, "name": meta.get("name", slug)})
        print(f"[hdri] tag {f.name:<48} sky_only={sky_only}  {tags[:5]}")
        n += 1
    _save_manifest(man)
    print(f"\n[hdri] retagged {n} files -> {MANIFEST}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=8)
    p.add_argument("--res", default="2k", choices=["1k", "2k", "4k"])
    p.add_argument("--sky-only", action="store_true", help="only fetch clean-sky HDRIs (air->air)")
    p.add_argument("--retag", action="store_true", help="(re)tag existing files, no download")
    args = p.parse_args()

    assets = _all_hdri_assets()

    if args.retag:
        retag(assets)
        return

    # candidate slugs sorted by popularity
    def is_candidate(slug, meta):
        sky_only, _ = classify(slug, meta)
        if args.sky_only:
            return sky_only
        return "skies" in [c.lower() for c in meta.get("categories", [])]

    cands = sorted(((s, m) for s, m in assets.items() if is_candidate(s, m)),
                   key=lambda kv: -kv[1].get("download_count", 0))

    man = _load_manifest()
    got = 0
    for slug, meta in cands:
        if got >= args.n:
            break
        dst = HDRIS / f"{slug}_{args.res}.hdr"
        sky_only, tags = classify(slug, meta)
        if dst.exists():
            _upsert(man, {"file": dst.name, "slug": slug, "sky_only": sky_only, "tags": tags, "name": meta.get("name", slug)})
            got += 1
            continue
        url = file_url(slug, args.res)
        if not url:
            continue
        print(f"[hdri] downloading {slug} ({args.res}, sky_only={sky_only}) ...")
        if download(url, dst):
            _upsert(man, {"file": dst.name, "slug": slug, "sky_only": sky_only, "tags": tags, "name": meta.get("name", slug)})
            print(f"[hdri]   -> {dst.name}  ({dst.stat().st_size/1e6:.1f} MB)")
            got += 1

    _save_manifest(man)
    print(f"\n[hdri] done: {got} skies in {HDRIS}/  (manifest tagged)")


if __name__ == "__main__":
    main()
