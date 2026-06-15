# HDRI skies

Environment maps (`.hdr` / `.exr`) used as random backgrounds + lighting. The renderer
scans this folder **recursively**, so you can either drop files at the top level or sort
them into condition subfolders:

```
assets/hdris/
├── clear/          # clear blue sky
├── partly_cloudy/  # scattered cloud
├── overcast/       # grey / diffuse
├── sunset_dawn/    # golden hour, low sun
└── night/          # dusk / night (skip for a daytime-only detector)
```

Get them free (CC0) from [PolyHaven](https://polyhaven.com/hdris) — or use the built-in
fetcher / the admin panel's **Skies** tab:

```powershell
.\venv\Scripts\python.exe tools\fetch_hdris.py --n 8 --res 2k
```

Sorting into subfolders is optional but lets you curate the lighting mix (e.g. move the
night skies out when training a daytime model). Binaries are git-ignored — only this
README and the `.gitkeep` placeholders are committed.
