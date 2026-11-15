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

The final beta.3 archive was rebuilt and independently verified. Size: 99,904,138 bytes. SHA-256: 425d3cc1dc7fe234d2763cb7a950bd23389e33b4a1b5ca07fc706f0ad2df8604. The sidecar matched independently; 2,355 manifest-listed file hashes and the exact archive entry set were verified.


## GitHub source repository

The private GitHub source repository contains 3,885 committed files and 499 Git LFS paths. The remote LFS dry-run found no outstanding uploads; local git lfs fsck passed. Repository: https://github.com/Frank-estine/inventaur-rhino3d-to-solidedge
