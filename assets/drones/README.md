# Drone models

Drop 3D drone meshes (`.obj` / `.glb` / `.fbx` / `.ply` / `.blend`) here. Organize them
into the per-class subfolders so it's clear which class each model trains:

```
assets/drones/
├── quad_consumer/    # DJI Mavic / Phantom-style consumer quads
├── quad_fpv/         # FPV freestyle / racing quads
├── fixedwing_fpv/    # fixed-wing FPV / loitering-munition style
├── fixedwing_mil/    # larger military fixed-wing (TB2-style silhouette)
├── vtol/             # VTOL / hybrid
├── helicopter/       # rotorcraft
└── manifest.yaml     # source + license per model (REQUIRED if you sell the data)
```

- **License hygiene matters** — a buyer (integrator / lab) will ask whether the training
  set is license-clean. Record every model's source + license in `manifest.yaml`
  (or via the admin panel's upload form, which fills it in for you). Prefer CC0 / self-built
  for anything redistributed.
- **No models yet?** SynthRange falls back to built-in primitive proxy drones
  (`synthrange/proxy.py`), so the pipeline still runs.

Binaries are git-ignored — only this README, the `.gitkeep` placeholders, and
`manifest.yaml` are committed.
