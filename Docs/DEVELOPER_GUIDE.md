> **Inventaur Inc.** - by **Krishna Parmar**

# Developer Guide

## Execution architecture

~~~text
Open Rhino document + document-scoped MCP
              |
              v
inventaur_run_rhino3d_to_solidedge.py
              |
    source identity + live snapshot
              |
    Rhino-side preparation
              |
    Rhino inventory + identity manifest
              |
        STEP export
              |
   isolated Solid Edge MCP bridge
              |
      native PAR import
              |
  nested/root ASM construction
              |
      disk-reopen audit
~~~

The runner owns a run. Stage scripts receive a run-scoped configuration through `CAD_WORKFLOW_CONFIG`; Rhino stages additionally receive one-call data through `CAD_WORKFLOW_STAGE_PAYLOAD`. Do not introduce mutable global active-run files.

## Stable contracts

- Source identity is the exact saved path plus Rhino runtime identity. A path match alone is not sufficient for a live call.
- A run snapshot is immutable after capture and is bound by SHA-256.
- Reports are run-scoped and should include source identity/hash.
- Definition identity and occurrence identity are separate. A repeated definition reuses a native file; each occurrence keeps its own composed transform.
- Rhino length values are converted to Solid Edge metres by the assembly transform layer.
- Reuse of prior PAR files requires matching STEP source hashes and native reopen checks.
- A successful COM/MCP return is not proof of a valid saved document. Reopen from disk and verify postconditions.
- Timeouts on mutating COM calls have unknown outcomes until state is reconciled. Never blindly retry them.

## Bundled runtimes

Recipients receive portable CPython 3.13.7 x64 under `Runtime/Python` and predownloaded `psutil`/`pywin32` wheels under `Runtime/Wheels`. The installer creates `.venv` and installs dependencies offline; no system Python is required.

The package also contains self-contained `net8.0-windows` Solid Edge MCP control/event applications under `Scripts/SOLIDEDGE-MCP/runtime/win-x64`. Each folder includes its apphost, managed dependencies and private .NET runtime files. Recipients do not download source, build executables or install .NET. The bridge daemon removes inherited `DOTNET_ROOT` overrides so an unrelated machine-wide runtime cannot redirect the bundled apphost.

The Rhino MCP Platform 0.4.0 Yak package is included under `ThirdParty/RhinoAI`; the installer uses each compatible Rhino installation's own `Yak.exe`.

## Development checks

~~~powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m compileall -q .\Scripts .\tests
~~~

The release builder packages the pinned portable Python payload, wheelhouse, self-contained MCP binaries and local Yak package. Rebuilding the upstream C# MCP binaries is a developer-only operation requiring the pinned source and compatible .NET 8 SDK; it is not part of recipient bootstrap.

The Python CI suite is host-independent. It cannot prove RhinoCommon or Solid Edge COM behavior on another machine. Maintain a separate live acceptance procedure using disposable CAD files.


## Fresh checkout and operator handoff

The complete source checkout includes Git LFS-managed runtime payloads. A new development workstation should install Git LFS, clone the canonical repository and pull the LFS objects before trying to run INSTALL.bat. A GitHub-generated source ZIP may contain LFS pointer files and is not a complete runtime checkout. The alternative is the separately prepared complete offline workflow bundle.

For the recipient install/run procedure, follow README.md and Docs/OPERATOR_RUNBOOK.md rather than reconstructing commands from this developer guide. Do not change runtime, installer or release behavior as part of a documentation-only task.

## Validation levels

- Host-independent pytest and compileall validate Python contracts and orchestration logic.
- Installer/launcher checks validate the local bootstrap and entrypoint behavior.
- Live Rhino/Solid Edge E2E validates the real MCP, RhinoCommon and Solid Edge COM path on the tested workstation.
- Human visual inspection validates geometry/appearance and engineering intent; it is not replaced by hashes, counts or unit tests.

Record the exact test command, result, source revision and any live prerequisites. Never describe host-independent tests as proof of live CAD compatibility.
