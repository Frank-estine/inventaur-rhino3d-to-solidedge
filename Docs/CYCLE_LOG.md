# Cycle Log

## Package/documentation simplification — 2026-11-15

- cycle=1 audit=documentation and installer model verify=repository scan found stale vendored/bundled language in release docs/tests; 69-test baseline available patch=core release/install docs and installer wording verdict=advance
- cycle=2 audit=tests and package contract verify=69 tests after updating tests for install-time upstream; compileall passed patch=portable-launcher and branding test contracts verdict=advance
- cycle=3 audit=release archive verify=beta.2 ZIP SHA-256 `4c5b2e9991cc7c4ee79acb2158470fd7e7d1d725967c8012cc997341bbca2f1f`, 62 files, no upstream/runtime/binary/CAD entries; staging cleanup completed patch=removed stale dist/_staging verdict=advance
- cycle=4 audit=remaining documentation references verify=repository scan identified stale wording in AGENTS, release notes, troubleshooting, launcher, installer and dependency map patch=updated all identified first-party references verdict=advance
- cycle=5 audit=release candidate verify=69 tests passed, compileall passed, beta.2 rebuilt at 190,919 bytes with SHA-256 `4c5b2e9991cc7c4ee79acb2158470fd7e7d1d725967c8012cc997341bbca2f1f`, staging removed patch=none verdict=advance

## Full offline bootstrap restoration - 2026-11-15

- cycle=6 audit=runtime completeness verify=beta.3 still depended on system Python; copied CPython 3.13.7 x64 standard runtime and bundled the psutil 7.2.2 / pywin32 312 wheels patch=installer now uses the bundled interpreter and offline wheelhouse verdict=advance
- cycle=7 audit=clean bootstrap path verify=a new venv was created by Runtime/Python/python.exe; pip installed both wheels with --no-index; both imports passed patch=version detection uses a quote-safe 3|13|64 identity check verdict=advance
- cycle=8 audit=full local bootstrap verify=exit code 0; control/event MCP --version passed; Rhino MCP 0.4.0 found in Rhino 8/9; SolidEdge.Application COM and 2026 ISO Metric template found patch=none verdict=advance
- cycle=9 audit=regression suite verify=72 passed; compileall passed; PowerShell parsers passed; INSTALL.bat and both workflow BAT files are BOM-free patch=updated offline runtime regression coverage verdict=advance

## Current verification

- Regression suite: 78 passed; Python compileall, PowerShell parser checks and launcher/installer BOM checks passed.
- Live Rhino/Solid Edge E2E: 45/45 native PAR imports; 27/27 nested assemblies completed; Root.asm disk-reopened with 11/11 direct occurrences verified; no partial, failed or skipped occurrences.
- Final beta.3 ZIP: 99,904,138 bytes; SHA-256 425d3cc1dc7fe234d2763cb7a950bd23389e33b4a1b5ca07fc706f0ad2df8604; sidecar independently matched.
- Independent extraction: 2,355 manifest-listed file hashes matched; ZIP entry set matched extracted package plus embedded manifest; extracted installer returned 0 and both launchers passed help.
- Private GitHub repository: https://github.com/Frank-estine/inventaur-rhino3d-to-solidedge; initial commit 6ad58bdb5fd137245c99f45dfd0d1c22f8d3abfc; 3,885 files, 499 LFS paths; remote main verified; LFS dry-run clear; local LFS fsck passed.
- Remaining before public release: human visual review, optional second-workstation validation, first-party licensing decision and third-party redistribution review. Repository remains private.
- Scope: live CAD E2E was run in the local Rhino/Solid Edge environment; a second live conversion was not run from the separately extracted ZIP. No visual sign-off or second-workstation validation is claimed.
