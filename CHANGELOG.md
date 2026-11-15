> **Inventaur Inc.** - by **Krishna Parmar**

# Changelog

## 1.0.0-beta.3 - Full Offline Bootstrap Restoration

- Restored the full-bootstrap distribution model instead of the source-only beta.2 package.
- Bundled portable CPython 3.13.7 x64 and the Python Software Foundation license under `Runtime/Python`.
- Bundled exact `psutil 7.2.2` and `pywin32 312` wheels under `Runtime/Wheels`; dependencies install offline with pip `--no-index`.
- Bundled both Solid Edge MCP control/event servers as self-contained Windows x64 applications, including private .NET runtime files (no recipient-side .NET SDK/runtime install or source build).
- Included the official McNeel Rhino-MCP-Platform 0.4.0 Yak package and MIT license; `INSTALL.bat` installs/verifies it through each compatible Rhino installation's Yak CLI.
- Restored and retained `Scripts\Rhino3D_to_SolidEdge.bat` as the stable legacy entry point; it forwards arguments and returns the real launcher exit code.
- Removed the UTF-8 BOM from Windows batch files to prevent the `´╗┐@echo` command error.
- Removed the obsolete .NET 10 `DOTNET_ROOT` override from the bridge daemon.
- Replaced the source-only release builder so it preserves the Python/MCP runtimes, offline wheelhouse and Yak payload while excluding caches, PDBs and CAD model files.
- Updated bootstrap, runtime, licensing, dependency, recovery and operator documentation; expanded regression coverage for full offline setup.

## 1.0.0-beta.2 - Lean Source-Only Distribution (superseded)

- Temporarily converted the public distribution to a source-only package with runtime/source downloads and local .NET build steps.
- This approach is superseded by beta.3 because it removed MCP executables required by the launch path and introduced fragile recipient-side build dependencies.

## 1.0.0-beta.1 - Full Bootstrap Package (restored)

- Earlier release model bundled Python/runtime dependencies, Solid Edge MCP binaries and Rhino MCP Yak content.

## 0.9.0-beta.1 - Public Preview Preparation

- Consolidated the workflow into a self-relative package layout.
- Documented source snapshot, block identity, STEP, native part, nested assembly and disk-reopen verification contracts.
- Added AI agent instructions and a separate Rhino BREP repair playbook.
- Added Solid Edge ISO Metric template discovery with an explicit environment override.
- Added regression tests for installation/template discovery and release hygiene.

## Current tested baseline

- Rhino 9 + Solid Edge 2026.
- Windows x64.
- Bundled CPython 3.13.7 x64; runtime host application compatibility remains Windows-specific.
- Beta package is not a claim of universal Rhino/Solid Edge version compatibility.
