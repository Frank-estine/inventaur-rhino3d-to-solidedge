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

- Test suite: 72 passed.
- Python compileall: passed.
- Installer/release-builder PowerShell parser: passed.
- Bundled CPython 3.13.7 x64: isolated startup and clean venv creation passed.
- Offline wheelhouse: psutil 7.2.2 and pywin32 312 installed/imported without package-index access.
- Full local bootstrap: exit code 0, using `Runtime/Python/python.exe`.
- Solid Edge MCP control/event apphost version checks: passed.
- Rhino MCP 0.4.0: verified in Rhino 8 and 9.
- SolidEdge.Application COM and Solid Edge 2026 ISO Metric template: found.
- Final beta.3 archive build and clean extraction smoke: pending this final packaging pass.
- Live disposable CAD conversion E2E, human visual review and first-party licensing: outstanding.
