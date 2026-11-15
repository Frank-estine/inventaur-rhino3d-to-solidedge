# Inventaur Inc. - Operator Runbook

**By Krishna Parmar**  
**Release: 1.0.0-beta.3 - Full Offline Bootstrap Package**

## Required starting state

1. Windows 10/11 x64; Rhino 8.19+ or Rhino 9; Siemens Solid Edge installed.
2. Extract the complete package and run `INSTALL.bat` once. It verifies the bundled self-contained Solid Edge MCP servers, uses bundled CPython 3.13.7 to create `.venv`, installs pywin32/psutil from the local wheelhouse, installs/verifies the bundled Rhino MCP 0.4.0 Yak package, and checks Solid Edge prerequisites.
3. Restart Rhino after bootstrap. Open the intended source `.3dm`, run `MCPStart`, then `MCPConnect`, and verify the connected MCP client exposes `run_python`.
4. Keep Rhino, its MCP integration and the intended document open throughout the workflow.

The production runner attaches to the already-open Rhino document. It does not launch Rhino, open/switch documents, save the source or change its Modified flag. The runner captures the current in-memory state to a run-local snapshot and verifies that snapshot before conversion.

## Run

Use the restored stable entry point (also compatible with previous shortcuts/callers):

```bat
Scripts\Rhino3D_to_SolidEdge.bat --source "C:\Models\model.3dm"
```

The branded equivalent is `Scripts\Inventaur_Rhino3D_to_SolidEdge.bat`. Both call the same Python supervisor and propagate its actual exit code. A success message is printed only for exit code 0.

Direct Python execution:

```powershell
.\.venv\Scripts\python.exe .\Scripts\inventaur_rhino3d_to_solidedge.py --source "C:\Models\model.3dm"
```

When `--source` is omitted, the runner infers it only when exactly one saved 3DM path is attached to a live Rhino MCP document. Supply `--source` when multiple sessions are eligible.

## Package setup and updates

- Keep the extracted package together; do not move individual scripts or runtime files.
- Re-extract the complete ZIP into a new or backed-up folder for an update, then run `INSTALL.bat`.
- Portable CPython is in `Runtime/Python`; pinned wheels are in `Runtime/Wheels`; the application environment is `.venv`.
- Both self-contained MCP applications and their private .NET runtime files live under `Scripts\SOLIDEDGE-MCP\runtime\win-x64\control` and `events`.
- The McNeel Rhino MCP Yak package is included under `ThirdParty\RhinoAI`; the bootstrap installs it locally using each Rhino installation's `Yak.exe`.
- Restart Rhino after plugin installation/update.
- For a non-standard Solid Edge template, set `CAD_SOLID_EDGE_PART_TEMPLATE` to the full template path.

## Rhino session identity

The runner discovers the current MCP URL and verifies the exact document path and runtime identity. Do not hard-code an MCP port. The source document must already be open and attached to the live MCP session.

If the MCP session disappears during a run, restore the intended Rhino/MCP session, inspect the run supervisor and stage reports, then resume only the same verified run. Do not close Rhino or switch its document while execution continues.

## Resume

Use `.venv\Scripts\python.exe` with `Scripts\inventaur_rhino3d_to_solidedge.py`, the original `--source` path, the existing `--run-id` and `--resume`.

## Success condition

Exit code 0 is necessary but not sufficient for engineering sign-off. Review the source snapshot, STEP export report, native import report, assembly report, final hash audit and warnings. Confirm expected native files were saved, closed, reopened and matched to the source manifest. Complete the separate visual viewport review.
