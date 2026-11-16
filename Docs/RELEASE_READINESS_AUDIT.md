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

Private repository: https://github.com/Krishna-Inventaur/inventaur-rhino3d-to-solidedge
Branch: main; initial commit: 6ad58bdb5fd137245c99f45dfd0d1c22f8d3abfc
3,907 files committed; 499 Git LFS paths; remote branch and LFS transfer verified.


## Upstream credit and prerequisite documentation

- Tyler Wagler's SolidEdge-MCP Python clone is credited in the README and third-party notices; the original MIT license is retained under ThirdParty/SolidEdge-MCP.
- The separate .NET MCP control/event server source has its own attribution and MIT license under ThirdParty/DotNet.
- README prerequisites explicitly cover Rhino/MCPStart/MCPConnect/run_python, Solid Edge 2023+ with COM, and nested block definitions/instances for the assembly hierarchy.
## Community onboarding documentation — 17 November 2026

- [x] Root README explains the Rhino block-to-native-assembly mapping, motivation, conversion stages, accuracy checks, prerequisites, Git LFS acquisition, install, Rhino MCP connection, run command, outputs, diagnostics and limitations.
- [x] Rhino Forum draft uses a community-oriented introduction, concrete prior import failure evidence and clear feedback questions.
- [x] Operator runbook and bootstrap/deployment guide provide matching commands and recovery instructions.
- [x] The existing CAD navigation entry was verified as canonical; repository URLs in the workflow docs use the verified repository path.
- [ ] Public release and redistribution review remain separate open gates. This documentation update does not change the first-party licence decision or third-party redistribution status.


## Documentation source update — 17 November 2026

Documentation-only source commit 19b408e (19b408ee931fc532f34d3034a8998207bb28e680) is pushed to the canonical GitHub main branch; the remote branch was read back at the same hash. This does not close the independent publication blockers above: first-party licensing, third-party redistribution review, human visual sign-off and second-workstation validation remain open. No release archive or public GitHub release was created.
