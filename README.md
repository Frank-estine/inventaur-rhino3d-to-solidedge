# Inventaur Inc. - Rhino3D to Solid Edge Automation

**By Krishna Parmar**  
**Version 1.0.0-beta.3 - Full Offline Bootstrap Package**

A reusable Windows workflow for converting an already-open Rhino 3D document into verified Solid Edge parts and assemblies.

## What the full package contains

- All first-party Inventaur workflow scripts, tests, recovery logic and operator documentation.
- Portable CPython 3.13.7 x64 under `Runtime/Python`, including its standard library and PSF license.
- A local Python wheelhouse containing the exact `psutil` and `pywin32` wheels. Python dependency installation is offline.
- Self-contained Windows x64 Solid Edge MCP control and event servers, including their private .NET runtime files (separate upstream project; see credits below).
- The official McNeel Rhino MCP Platform 0.4.0 Yak package and MIT license, ready for local installation by Rhino's Yak CLI.
- A PowerShell bootstrap, third-party notices and a SHA-256 package manifest.

The extracted package does not require a separately installed Python, Git, .NET SDK/runtime, or internet connection for Python dependency installation.

## Prerequisites

| Component | Requirement |
|---|---|
| Windows | Windows 10/11, 64-bit |
| Rhino 3D | Rhino 8.19+ or Rhino 9 installed |
| Solid Edge | Siemens Solid Edge 2023 or later, installed and properly licensed, with COM automation available |
| Rhino MCP | Rhino MCP Platform installed and loaded in Rhino |
| AI/MCP client | Connected to the active Rhino session and exposing the document-scoped run_python tool |
| Rhino model | Intended saved .3dm already open in the active Rhino document and structured with nested blocks for assemblies |

**Verified baseline:** the live conversion workflow was verified with Rhino 9 and Solid Edge 2026. Solid Edge 2023+ is the stated minimum deployment prerequisite; verify compatibility on the target workstation before production use.

Solid Edge must be installed, licensed and COM-accessible. It does not need to be manually left open before conversion; the workflow starts its own isolated Solid Edge session.

## Required Rhino model structure

The Rhino document must encode the assembly hierarchy using actual block definitions and nested block instances. Rhino Groups alone do not create native Solid Edge assembly relationships.

- **Root assembly:** top-level block instances in the active Rhino document represent the root assembly's components.
- **Subassemblies:** create parent block definitions containing child block instances. Nest blocks to represent each subassembly level.
- **Parts:** use leaf block definitions for reusable part geometry.
- **Repeated components:** insert multiple instances of the same block definition. Each instance becomes a separate Solid Edge occurrence while reusing the same native part/subassembly document.
- **Transforms:** position and orient block instances in Rhino at their intended assembly locations. Instance transforms are transferred to Solid Edge.
- **Names:** block definition names must be unique after case/whitespace normalization. Duplicate normalized names stop preflight because the definition-to-file mapping would be ambiguous.
- **Hierarchy:** the block-reference graph must be acyclic. Cyclic nested blocks stop preflight.
- **Mixed assemblies:** geometry placed directly inside an assembly block definition is treated as local component geometry, but dedicated leaf part blocks are preferred.

Do not explode the block hierarchy before conversion. Do not use Rhino Groups as a replacement for nested block definitions. Save the .3dm and keep it open in the active Rhino session.

## Required live Rhino MCP session

The installer prepares the local runtime; it does not open Rhino, open a model or create the live MCP connection.

1. Start Rhino 3D.
2. Open the intended saved .3dm model.
3. Ensure Rhino MCP Platform is installed and loaded. Restart Rhino after installing or updating the plugin.
4. Run MCPStart in Rhino.
5. Run MCPConnect in Rhino.
6. In the connected AI/MCP client, confirm that the active Rhino connection exposes the document-scoped run_python tool.
7. Keep Rhino, the MCP connection and the intended document open for the complete conversion.

## Rhino3D reusable scripts

`Rhino3D_Scripts/Inventaur_Rhino_Standards/` contains the reusable Inventaur Rhino 9 standards scripts, automatic layer routing, annotation routing, hatch/PAT library and metric drafting template. It is kept separate from project-specific modeling scripts.

The hatch installer imports the PAT definitions directly into the active Rhino document; see that folder's README for the import path and maintenance notes.

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
- The bundled Solid Edge MCP executables are self-contained .NET 8 applications under `Scripts/SOLIDEDGE-MCP/runtime/win-x64`; their upstream project is credited separately below.
- The Rhino MCP Yak package is included under `ThirdParty/RhinoAI` and installed by the bootstrap using the Yak executable shipped with Rhino.
- The Rhino MCP plugin must be loaded in Rhino and `run_python` must be available before a conversion run.
- No source CAD models, generated PAR/ASM documents or private run evidence are included in the bootstrap ZIP.

See `Docs/BOOTSTRAP_AND_DEPLOYMENT.md`, `Docs/RHINO_MCP_SETUP.md`, `Docs/OPERATOR_RUNBOOK.md` and `Docs/TROUBLESHOOTING.md`.

## Credits

- **Tyler Wagler** - [SolidEdge-MCP](https://github.com/tylerwagler/SolidEdge-MCP), the original Python MCP repository cloned during development. The upstream MIT notice is retained verbatim at `ThirdParty/SolidEdge-MCP/LICENSE`; clone provenance is at `ThirdParty/SolidEdge-MCP/UPSTREAM.md`.
- **chuanmin qiu and contributors** - [solidedge-mcp-server](https://github.com/1337332551-dot/solidedge-mcp-server), the separate .NET project used for the bundled control/event executables. Its MIT notice is retained at `ThirdParty/DotNet/SolidEdge-MCP-Server-LICENSE.txt`.
- **McNeel** - [RhinoAI / Rhino MCP Platform](https://github.com/mcneel/RhinoAI); see `ThirdParty/RhinoAI`.
- **Solid Edge Community** - Interop.SolidEdge COM type definitions; see the separate notice under `ThirdParty/DotNet`.

The Tyler Wagler Python project is acknowledged as the original clone/reference. It is not represented as the source of the separate .NET executables.
