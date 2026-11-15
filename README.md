# Inventaur Inc. - Rhino3D to Solid Edge Automation

**By Krishna Parmar**  
**Version 1.0.0-beta.3 - Full Offline Bootstrap Package**

A reusable Windows workflow for converting an already-open Rhino 3D document into verified Solid Edge parts and assemblies.

## What the full package contains

- All first-party Inventaur workflow scripts, tests, recovery logic and operator documentation.
- Portable CPython 3.13.7 x64 under `Runtime/Python`, including its standard library and PSF license.
- A local Python wheelhouse containing the exact `psutil` and `pywin32` wheels. Python dependency installation is offline.
- Self-contained Windows x64 Solid Edge MCP control and event servers, including their private .NET runtime files.
- The official McNeel Rhino MCP Platform 0.4.0 Yak package and MIT license, ready for local installation by Rhino's Yak CLI.
- A PowerShell bootstrap, third-party notices and a SHA-256 package manifest.

The extracted package does not require a separately installed Python, Git, .NET SDK/runtime, or internet connection for Python dependency installation.

## Required software

1. Windows 10/11 x64.
2. Rhino 8.19+ or Rhino 9, licensed.
3. Siemens Solid Edge, licensed, with COM automation available.

Python, the Solid Edge MCP runtimes, Rhino MCP Yak package and Python dependency wheels are included.

## Install

Extract the complete ZIP, then run `INSTALL.bat` once.

The bootstrap:
1. verifies both bundled self-contained Solid Edge MCP servers and their private .NET runtime files;
2. starts the bundled CPython 3.13.7 x64 interpreter and creates/reuses the package-local `.venv`;
3. installs `psutil` and `pywin32` from the included wheelhouse with pip `--no-index`;
4. installs/verifies the bundled `Rhino-MCP-Platform 0.4.0` Yak package for each compatible detected Rhino installation;
5. checks Rhino and Solid Edge prerequisites.

No network download, Git clone, .NET SDK install or source compilation is performed. Restart Rhino after installation so the MCP plugin loads.

## Rhino setup

Open Rhino, then open the intended saved `.3dm`. Run `MCPStart` and `MCPConnect`. Confirm the connected MCP client exposes the document-scoped `run_python` tool.

## Run

Use the stable legacy-compatible entry point:

```bat
Scripts\Rhino3D_to_SolidEdge.bat --source "C:\Models\model.3dm"
```

The branded launcher remains available as `Scripts\Inventaur_Rhino3D_to_SolidEdge.bat`. Both use the same verified runner and propagate its exit code. The original Rhino source is not overwritten.

## Notes

- Bundled Python is in `Runtime/Python`; installed workflow packages are isolated in `.venv`.
- Offline wheels are in `Runtime/Wheels`. Keep them beside the Python runtime.
- The Solid Edge MCP executables are self-contained .NET 8 applications. Their runtime files are under `Scripts/SOLIDEDGE-MCP/runtime/win-x64`.
- The Rhino MCP Yak package is included under `ThirdParty/RhinoAI` and installed by the bootstrap using the Yak executable shipped with Rhino.
- The Rhino MCP plugin must be loaded in Rhino and `run_python` must be available before a conversion run.
- No source CAD models, generated PAR/ASM documents or private run evidence are included in the bootstrap ZIP.

See `Docs/BOOTSTRAP_AND_DEPLOYMENT.md`, `Docs/RHINO_MCP_SETUP.md`, `Docs/OPERATOR_RUNBOOK.md` and `Docs/TROUBLESHOOTING.md`.
