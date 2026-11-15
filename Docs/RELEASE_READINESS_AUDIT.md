# Inventaur Inc. - Release Readiness Audit

**Product:** Rhino3D to Solid Edge Automation  
**Creator:** Krishna Parmar  
**Package version:** 1.0.0-beta.3  
**Audit date:** 15 November 2026

## Packaging contract

- The full offline bootstrap ZIP contains first-party workflow code/tests/docs, portable CPython 3.13.7 x64, exact `psutil`/`pywin32` wheels, self-contained Solid Edge MCP control/event apps with their private .NET runtime files, and the official Rhino MCP Platform 0.4.0 Yak package with its MIT license.
- `INSTALL.bat` verifies both MCP executables, verifies and uses bundled Python, creates/reuses the package `.venv`, installs wheels with pip `--no-index`, installs/verifies the bundled Yak package through each supported Rhino's own `Yak.exe`, and checks Solid Edge COM/template readiness.
- Recipient bootstrap requires Windows x64, Rhino 8.19+/9 and licensed Solid Edge. System Python, Git, the .NET SDK/runtime and internet package downloads are not required.
- `Scripts\Rhino3D_to_SolidEdge.bat` remains the stable legacy-compatible entry point; the branded launcher is equivalent. All BAT entry points are BOM-free.

## Beta.3 verification

- [x] Python regression suite: 78 passed.
- [x] `compileall` passes for Scripts and tests.
- [x] PowerShell syntax parser passes for installer and release builder.
- [x] Batch files checked for UTF-8 BOM; none present.
- [x] Both self-contained MCP executables return valid version/build strings.
- [x] Portable CPython 3.13.7 x64 starts in isolated mode and creates a clean virtual environment.
- [x] Local wheelhouse installs pywin32 312 and psutil 7.2.2 without package-index/network access; imports pass.
- [x] Full local bootstrap completed with exit code 0 using `Runtime/Python/python.exe` (not system Python).
- [x] Rhino-MCP-Platform 0.4.0 verified in Rhino 8 and Rhino 9 package lists.
- [x] SolidEdge.Application COM registration detected.
- [x] Solid Edge 2026 ISO Metric Part template detected.
- [x] Rebuild beta.3 release ZIP and verify archive contents, embedded manifest and SHA-256.
- [x] Extract the final ZIP to a separate directory and repeat offline bootstrap plus both launcher help smoke tests.
- [x] Run the live Rhino MCP + Solid Edge conversion E2E: 45/45 PAR imports; 27/27 nested assemblies; Root.asm 11/11 direct occurrences.
- [ ] Complete human visual CAD review.

## Publication blockers

1. The project-wide license for original Inventaur workflow code remains undecided. `LICENSE_PENDING.txt` is intentional.
2. Confirm redistribution terms for bundled .NET/Python runtime components and ensure all third-party notices remain in the ZIP.
3. The source has been pushed to a verified private GitHub repository; no public release has been created.
4. Human visual sign-off, optional second-workstation validation, first-party licensing and third-party redistribution review remain open before public release.

## Naming policy

Inventaur branding applies to first-party filenames, metadata, installer/launcher names, first-party docs and archive names. Third-party identities, namespaces, source names, copyrights and license notices remain unchanged.


## GitHub source state

Private repository: https://github.com/Frank-estine/inventaur-rhino3d-to-solidedge
Branch: main; initial commit: 6ad58bdb5fd137245c99f45dfd0d1c22f8d3abfc
3,885 files committed; 499 Git LFS paths; remote branch and LFS transfer verified.
