> **Inventaur Inc.** — by **Krishna Parmar**

# CAD Autopilot Architecture

## Pipeline
Rhino3D → colourisation → STEP → PAR → ASM → Root.asm

Python supervises the deterministic stages and evidence. Rhino and Solid Edge perform CAD operations. The conversion path is automated, but a separate human visual-review/sign-off step remains required before production acceptance.

## Mapping
- One unique leaf definition → one shared .par.
- Three nested definitions containing direct geometry → one shared local-geometry companion .par each.
- One nested definition → one reusable .asm.
- Repeated occurrences reference shared native documents.
- Occurrence transforms are applied from the Rhino hierarchy.
- One non-uniform-scale occurrence → one baked geometry variant because Solid Edge occurrence matrices do not retain non-unit scale.

## Verification
Every native part and assembly is saved, closed and reopened before promotion. Root.asm is reopened and checked for references, occurrences and transforms.

## Critical-path policy
No geometry repair, joining, SAT conversion, surface reconstruction, face-signature matching or strict topology/body-validity gate.

## Operator
.\\Runtime\\Python\\python.exe .\\Scripts\\inventaur_rhino3d_to_solidedge.py --help

No-argument mode performs safe source discovery and proceeds only when exactly one saved 3DM path is attached to a reachable Rhino MCP document. It never opens a Windows file picker. Supply --source when discovery is missing or ambiguous.

## Recovery
Use --resume only against the exact run ID after reconciling its reports and files.
