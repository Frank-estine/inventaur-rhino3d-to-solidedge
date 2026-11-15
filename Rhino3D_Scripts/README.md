# Rhino3D Reusable Scripts

This is the maintained index of reusable Rhino3D scripts and shared drafting resources owned by CAD/rhino3d_automations. Project-specific model generators, geometry experiments, drawing-set builders and the Rhino-to-Solid-Edge conversion workflow remain in their existing owners and are not duplicated here.

## Reusable package index

| Component | Entry point / resource | Purpose |
|---|---|---|
| Rhino Standards | [RhinoStandards/README.md](RhinoStandards/README.md) | One shared Rhino 9 standards package: metric template, annotation styles, layer routing, hatch definitions and installer. |
| AutoLayer | [RhinoStandards/AutoLayer/README.md](RhinoStandards/AutoLayer/README.md) | Startup entrypoint and automatic TEXT / ANNOTATIONS / HATCH routing. |
| Standards Installer | [RhinoStandards/Installer/README.md](RhinoStandards/Installer/README.md) | Installs/validates document standards and template. |
| Metric Template | [RhinoStandards/Template/README.md](RhinoStandards/Template/README.md) | Default metric architectural template and rollback file. |
| Hatch Library | [RhinoStandards/HatchLibrary/README.md](RhinoStandards/HatchLibrary/README.md) | PAT definitions and Rhino hatch import/readback. |
| Legacy | [RhinoStandards/Legacy/README.md](RhinoStandards/Legacy/README.md) | Retained recovery implementation and compatibility checkpoint. |

## Rules

- Each script/resource owns a private folder and a component README.
- The metric template, installer and hatch definitions remain one RhinoStandards package.
- Use normal Rhino/McNeel hatch names; do not add Inventaur prefixes to hatch names.
- This root README is the overview/index. Component details belong in each component README.
- Reusable tools live here; project/model-specific scripts remain in their existing folders under rhino3d_automations.
- Rhino-to-Solid-Edge exporters/importers remain in the separate Rhino3D_to_SolidEdge_Workflow owner.
