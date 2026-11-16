# Bootstrap and Deployment

**Project:** Inventaur Inc. Rhino3D to Solid Edge
**Version:** 1.0.0-beta.3

This document covers obtaining a complete workflow copy and installing its local dependencies. For day-to-day conversion steps, see the [Operator Runbook](OPERATOR_RUNBOOK.md).

## What is included

The full offline workflow payload contains:

- First-party Rhino/Solid Edge workflow scripts, tests and documentation.
- Portable CPython 3.13.7 x64, including its standard library and PSF license.
- Local psutil and pywin32 wheels.
- Self-contained Windows x64 Solid Edge MCP control/event applications with their private .NET runtime files.
- McNeel's Rhino MCP Platform 0.4.0 Yak package and MIT license.
- PowerShell bootstrap, third-party notices and package manifest.

The bundle is designed to be kept together. Do not move or remove files from Runtime/Python, Runtime/Wheels, Scripts/SOLIDEDGE-MCP/runtime/win-x64 or ThirdParty/RhinoAI.

## Obtain the complete payload

The bundled runtimes are stored with Git LFS. For a repository checkout, install Git for Windows and Git LFS and clone as follows:

~~~powershell
git lfs install
git clone https://github.com/Krishna-Inventaur/inventaur-rhino3d-to-solidedge.git
cd inventaur-rhino3d-to-solidedge
git lfs pull
~~~

Confirm that the large runtime files were downloaded and are real files before installation. Do not use GitHub's generated source ZIP as a complete offline installer input because LFS-managed files may be represented by pointer files.

Alternatively, extract the complete offline workflow bundle into a new folder. Do not install from a partial copy of the repository.

## Prerequisites

| Component | Requirement |
|---|---|
| Windows | Windows 10/11 x64 |
| Rhino | Rhino 8.19+ or Rhino 9 |
| Solid Edge | Siemens Solid Edge 2023 or later; installed/licensed with COM automation available |
| Rhino MCP | McNeel Rhino MCP Platform loaded in Rhino |
| MCP client | Connected to the intended Rhino document and exposing run_python |

The live verification baseline is Rhino 9 + Solid Edge 2026. Other combinations should be verified on the target workstation.

## Installation

Run **INSTALL.bat** from the complete extracted workflow root.

It:

1. verifies both self-contained Solid Edge MCP executables and their sibling .NET runtime files;
2. checks that the bundled CPython 3.13.7 x64 runtime starts;
3. creates or reuses the package-local .venv;
4. installs requirements.txt from Runtime/Wheels with pip --no-index;
5. verifies the psutil and pywin32 imports inside that environment;
6. discovers compatible Rhino installations and installs/verifies the bundled local Rhino-MCP-Platform 0.4.0 Yak package where required;
7. reports Solid Edge COM/template readiness.

The complete offline bundle does not require the recipient to install system Python, Git, a .NET SDK/runtime or Python packages from the internet. Git and Git LFS are only needed when obtaining the payload from the source repository.

The installer does not launch Rhino, open a 3DM or establish the live MCP connection. Restart Rhino after the Yak plugin has been installed or updated.

## Connect and run

After installation:

1. Restart Rhino.
2. Open the intended saved 3DM.
3. Run MCPStart, then MCPConnect.
4. Confirm the connected MCP client exposes the document-scoped run_python tool.
5. Run:

~~~powershell
.\Scripts\Rhino3D_to_SolidEdge.bat --source "C:\Models\MyAssembly.3dm"
~~~

The workflow discovers the active document-scoped MCP listener at runtime. Do not hard-code an MCP port. It does not open or switch Rhino documents.

## Runtime and output

- Bundled Python: Runtime/Python/python.exe.
- Offline wheels: Runtime/Wheels.
- Isolated application environment: .venv.
- Solid Edge MCP applications and private .NET files: Scripts/SOLIDEDGE-MCP/runtime/win-x64.
- Rhino MCP Yak package: ThirdParty/RhinoAI.

A conversion writes a new Desktop run folder by default, containing Rhino3D, STEP, Parts, Assemblies and Logs folders plus a run README. Use --output-root to select another location.

## Verification and recovery

The installer checks the local runtime and prerequisites; it does not prove that a CAD model will translate correctly. The conversion runner produces source, STEP, native import, assembly and final acceptance reports. Review those reports and visually inspect representative output parts and assemblies.

For a damaged/incomplete installation, obtain a fresh complete source checkout with Git LFS or extract the full workflow bundle, run INSTALL.bat, restart Rhino and re-establish MCPStart/MCPConnect. Do not copy only the batch file or Python scripts without their adjacent runtimes.

For run recovery, use the exact original source, output root and run ID with --resume only after inspecting the stage reports and confirming prior outputs. See OPERATOR_RUNBOOK.md and TROUBLESHOOTING.md.

## Redistribution and licence status

The first-party workflow licence remains pending in LICENSE_PENDING.txt. Third-party notices are retained with their respective components. Do not infer redistribution rights from repository visibility; review the relevant licence terms before republishing the source or runtime bundle.
