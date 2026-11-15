# Inventaur Inc. - Bootstrap and Deployment

**By Krishna Parmar**  
**Release: 1.0.0-beta.3 - Full Offline Bootstrap Package**

## Package payload

The distribution includes first-party Inventaur sources/docs, portable CPython 3.13.7 x64 with the PSF license, a local wheelhouse for `psutil`/`pywin32`, self-contained Solid Edge MCP control/event applications with private .NET runtime files, and the McNeel Rhino MCP Platform 0.4.0 Yak package with its MIT license. A manifest hashes every packaged file.

The package is intended to be extracted and bootstrapped as a unit. Do not remove files from `Runtime/Python`, `Runtime/Wheels`, `Scripts/SOLIDEDGE-MCP/runtime/win-x64` or `ThirdParty/RhinoAI`.

## Prerequisites

| Component | Requirement |
|---|---|
| Windows | Windows 10/11 x64 |
| Rhino | Rhino 8.19+ or Rhino 9; intended saved .3dm open in the active session |
| Solid Edge | Siemens Solid Edge 2023 or later, installed/licensed, with COM automation registered; Solid Edge 2026 is the verified baseline |

Python 3.13.7 x64, both Python dependency wheels, both Solid Edge MCP servers and the Rhino MCP Yak package are bundled. Git, the .NET SDK/runtime and internet access are not required by recipient bootstrap. Conversion also requires Rhino to be running with Rhino MCP connected (MCPStart, then MCPConnect) and the client to expose run_python.

## Installation

Run `INSTALL.bat` from the extracted package root. It performs these checks and actions:

1. verifies both MCP executables and the self-contained .NET files beside them;
2. runs each MCP executable with `--version` to confirm its apphost/private runtime starts;
3. verifies the included CPython 3.13.7 x64 runtime and creates/reuses `.venv`;
4. installs `requirements.txt` exclusively from `Runtime/Wheels` using pip `--no-index`;
5. verifies pywin32/psutil imports inside the isolated `.venv`;
6. finds compatible Rhino installations and uses each Rhino's own `Yak.exe` to install the included local `Rhino-MCP-Platform 0.4.0` package if absent;
7. verifies the Rhino MCP package listing and reports Solid Edge COM/template readiness.

The installer does not open or modify any CAD model. It does not close or restart Rhino; the operator must restart Rhino after installation.

## Python runtime

The included interpreter is CPython 3.13.7 x64 at `Runtime/Python/python.exe`. The standard library, DLLs and Python Software Foundation license accompany it. Python application dependencies are shipped as wheels at `Runtime/Wheels`; the installer does not access PyPI or any remote package index.

The workflow uses a package-local `.venv`. It does not modify a recipient's system Python installation or global packages.

## Rhino MCP connection

After the installer finishes, restart Rhino, open the intended model, run `MCPStart`, then `MCPConnect`. Verify that the connected MCP client exposes `run_python`. The conversion runner discovers the active document-scoped MCP listener; do not hard-code an MCP port.

The included Yak package is for Rhino 8.19+ / Rhino 9. On older Rhino 8 builds the installer skips this package and reports the version constraint.

## Run and recovery

Use `Scripts/Rhino3D_to_SolidEdge.bat --source "C:\Models\model.3dm"`. The branded `Scripts/Inventaur_Rhino3D_to_SolidEdge.bat` launcher is equivalent. Both preserve the Python runner's exit code; no success message is printed after a failed preflight or run.

For a damaged installation, extract a fresh copy of the complete ZIP, run `INSTALL.bat`, restart Rhino and re-establish MCPStart/MCPConnect. Do not copy only the batch file or Python scripts without the adjacent runtime folders and wheelhouse.

## Verification

The release build runs the Python regression suite and compileall. It checks the archive for the portable Python runtime, offline wheelhouse, both MCP runtimes and Rhino Yak package, validates the embedded file manifest, rejects CAD model data and excludes caches/debug symbols.


## Rhino assembly model requirement

Build the assembly structure with Rhino block definitions and nested block instances before conversion:

- The active document's top-level block instances form the root assembly.
- Parent block definitions containing child block instances represent subassemblies.
- Leaf block definitions hold reusable part geometry.
- Repeated components should be repeated instances of the same block definition, with each instance retaining its own placement transform.
- Block definition names must be unique after case/whitespace normalization, and the nested block-reference graph must be acyclic.
- Groups alone are not assembly definitions. Do not explode the nested block structure before conversion.

Duplicate normalized names and cyclic block references fail preflight. Geometry placed directly inside an assembly definition is treated as local component geometry; dedicated leaf part blocks are preferred.
