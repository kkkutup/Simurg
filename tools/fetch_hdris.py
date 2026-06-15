"""Download CC0 sky HDRIs from PolyHaven into assets/hdris/.

    python tools/fetch_hdris.py --n 8 --res 2k

No API key needed (PolyHaven is a free public API, all assets CC0). When assets/hdris/
is populated, SynthRange uses these real skies instead of the flat procedural colour,
which sharply improves realism and sim-to-real transfer.

Stdlib-only (urllib + json). Idempotent: skips files already downloaded.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

API = "https://api.polyhaven.com"
UA = {"User-Agent": "synthrange-hdri-fetch/1.0 (+https://polyhaven.com)"}

# Curated fallback slugs (clear/overcast/sunset variety) used if the API listing fails.
FALLBACK = [
    "kloofendal_43d_clear_puresky",
    "qwantani_puresky",
    "syferfontein_1d_clear_puresky",
    "belfast_sunset_puresky",
    "kloppenheim_06_puresky",
    "wasteland_clouds_puresky",
    "sunflowers_puresky",
    "overcast_soil_puresky",
]


def _get_json(url: str):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def list_sky_ids(limit: int) -> list[str]:
    try:
        data = _get_json(f"{API}/assets?type=hdris&categories=skies")
        # Sort by download count (popularity) when available, else name.
        ids = sorted(data.keys(), key=lambda k: -data[k].get("download_count", 0))
        if ids:
            return ids[: max(limit * 2, limit)]  # extra, in case some lack a res
    except Exception as e:
        print(f"[fetch_hdris] API listing failed ({e}); using curated fallback")
    return FALLBACK


def file_url(asset_id: str, res: str) -> str | None:
    try:
        files = _get_json(f"{API}/files/{asset_id}")
        hdri = files.get("hdri", {})
        entry = hdri.get(res) or hdri.get("1k") or next(iter(hdri.values()), {})
        return entry.get("hdr", {}).get("url")
    except Exception as e:
        print(f"[fetch_hdris] no files for '{asset_id}' ({e})")
        return None


def download(url: str, dst: Path) -> bool:
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=120) as r, open(dst, "wb") as f:
            f.write(r.read())
        return True
    except Exception as e:
        print(f"[fetch_hdris] download failed {url} ({e})")
        return False


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=8, help="how many skies to fetch")
    p.add_argument("--res", default="2k", choices=["1k", "2k", "4k"], help="HDRI resolution")
    p.add_argument("--out", default="assets/hdris", help="destination dir")
    args = p.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    ids = list_sky_ids(args.n)
    got = 0
    for asset_id in ids:
        if got >= args.n:
            break
        dst = out / f"{asset_id}_{args.res}.hdr"
        if dst.exists():
            print(f"[fetch_hdris] have {dst.name}")
            got += 1
            continue
        url = file_url(asset_id, args.res)
        if not url:
            continue
        print(f"[fetch_hdris] downloading {asset_id} ({args.res}) ...")
        if download(url, dst):
            mb = dst.stat().st_size / 1e6
            print(f"[fetch_hdris]   -> {dst.name}  ({mb:.1f} MB)")
            got += 1

    print(f"\n[fetch_hdris] done: {got} skies in {out}/")
    if got == 0:
        print("[fetch_hdris] nothing downloaded — check your connection or try --res 1k")
        sys.exit(1)


if __name__ == "__main__":
    main()
