# Performance / Packaging Report - Beta.3 Full Offline Bootstrap

## Bundled runtimes (uncompressed)

| Payload | Files | Bytes |
|---|---:|---:|
| CPython 3.13.7 x64 (standard library/DLLs/Tcl; no site-packages) | 8,627 | 213,629,569 |
| Python offline wheelhouse (psutil 7.2.2 + pywin32 312) | 2 | 7,052,035 |
| Solid Edge MCP control + private .NET runtime | 224 | 82,217,639 |
| Solid Edge MCP event + private .NET runtime | 222 | 80,957,374 |

Combined bundled Python and MCP runtime payload: 383,856,617 bytes (~366.1 MiB uncompressed; 9,075 files), excluding the Rhino Yak package and first-party workflow code/docs. The Python wheels are installed into a package-local `.venv` using pip `--no-index`. Both MCP apphosts start and print their version/build identifiers. PDBs and cache files are excluded from the distribution. The Rhino MCP 0.4.0 Yak package is also bundled.

## Test and bootstrap execution

- Pytest: 78 passed.
- Compileall: passed.
- PowerShell installer and release builder parser: passed.
- Full local bootstrap: exit code 0 using bundled CPython 3.13.7 x64.
- Offline venv smoke test: pywin32 and psutil installed/imported successfully without package-index access.
- Rhino MCP 0.4.0 verified in Rhino 8 and Rhino 9; Solid Edge COM registration and 2026 ISO Metric Part template detected.

## CAD conversion performance

RAM/CPU/I/O baselines for a live conversion were not captured during this packaging/restoration cycle. No unsupported performance claim is made for runtime CAD conversion. The live E2E is complete; human visual review of representative CAD geometry and annotations remains outstanding.

## Release archive

The user requested source and documentation updates only; no ZIP was rebuilt for this continuation.


## GitHub source repository

The private GitHub source repository contains 3,907 committed files and 499 Git LFS paths. The remote LFS dry-run found no outstanding uploads; local git lfs fsck passed. Repository: https://github.com/Krishna-Inventaur/inventaur-rhino3d-to-solidedge


## Upstream notices

The package includes Tyler Wagler's original SolidEdge-MCP MIT license and attribution, plus the separate .NET MCP server MIT license. Both are verified as archive manifest entries.
## Documentation-only update — 17 November 2026

The project README, private forum post draft, operator runbook, bootstrap/deployment guide, agent/developer instructions, data contracts, troubleshooting/recovery guides and status records were refreshed. The parent CAD index was checked and its existing canonical workflow entry was retained. This is a documentation update only; no CAD conversion benchmark, runtime payload, installer or release archive was rebuilt. The recorded CAD E2E figures above are unchanged and remain structural/import verification rather than a performance benchmark or visual engineering sign-off.


## Documentation source publication

Documentation-only commit 19b408e (19b408ee931fc532f34d3034a8998207bb28e680) was pushed to the canonical GitHub main branch and verified by remote readback. No runtime benchmark was run for this documentation update and no release package was rebuilt.
