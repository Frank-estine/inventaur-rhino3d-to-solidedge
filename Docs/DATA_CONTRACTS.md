> **Inventaur Inc.** — by **Krishna Parmar**

# CAD Autopilot Data Contracts

| Stage | Input | Output | Next |
|---|---|---|---|
| Source | selected `.3dm` + live Rhino document | immutable snapshot, SHA-256, preflight | colour |
| Colour | source snapshot | colourized `.3dm`, RGB/alpha report | inventory |
| Inventory | colourized `.3dm` | unique definitions, children, occurrence transforms | identity |
| Identity | inventory + colour report | one `.par`/`.asm` path per unique definition | STEP, assembly |
| Scaled variant | colourized source + occurrence transform | baked STEP/PAR only where Solid Edge cannot represent source scale | native import, assembly |
| STEP | colourized source + manifest | one STEP and hash per native part request | native import |
| Native import | STEP + manifest | saved/reopened PAR, native hash, document cleanup | assembly |
| Assembly | inventory + manifest + native import report | reusable nested/root ASM, occurrence path/matrix audit | acceptance |

## Native part acceptance

A part must contain an imported native body, save to the manifest path, close and reopen from disk, and match its recorded file hash. `Body.Valid`, face count, open-edge count and face-area/volume signatures are retained as diagnostics only.

## Transform contract

A repeated Rhino definition reuses the exact same native `.par` or `.asm`; each occurrence carries its own composed transform. Any required baked-scale variant is an explicit exception for a transform the Solid Edge placement API cannot represent.

## Source contract

The original `.3dm` is never saved. Colourisation writes a separate derived file. STEP exports read that colourized file and copy object RGB/alpha.


## Acceptance and geometry interpretation

- The exact saved 3DM path and document-scoped Rhino runtime identity are required; current in-memory state is captured to a separate run-owned snapshot and bound by SHA-256.
- A unique block definition is the reusable identity; each block instance is a distinct occurrence with its own composed transform. Repeated occurrences reuse the native file where the transform contract permits.
- Non-unit scale that cannot be represented by the Solid Edge occurrence transform is handled as a separate baked geometry variant and recorded in the identity/import reports.
- A parent definition may contain its own geometry as well as child block instances; directly owned geometry is represented as local component geometry.
- Native body validity, open/sheet state, face/edge counts and area/volume signatures are diagnostics. They must be interpreted against design intent and translator output; they are not a blanket requirement that every imported object be a closed solid.
- Automated hashes, save/close/reopen checks and occurrence-transform audits establish structural consistency, not visual or manufacturing sign-off.
