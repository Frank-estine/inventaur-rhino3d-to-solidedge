# Operator Runbook — Rhino 3D to Solid Edge

**Project:** Inventaur Inc. Rhino3D to Solid Edge
**Version:** 1.0.0-beta.3

This runbook is for someone using the workflow, not modifying its code. Follow the steps in order; the runner expects Rhino and its document-scoped MCP connection to be ready before the conversion starts.

## 1. Before installation

You need:

- Windows 10/11 x64.
- Rhino 8.19+ or Rhino 9.
- Siemens Solid Edge 2023 or later, installed/licensed, with COM automation available. Solid Edge 2026 is the verified baseline.
- McNeel Rhino MCP Platform installed and loaded.
- An AI/MCP client connected to the active Rhino session and exposing its document-scoped run_python tool.
- A saved 3DM model structured with block definitions/instances for the intended assembly hierarchy.

The portable CPython 3.13.7 x64 runtime, offline Python wheels, Solid Edge MCP control/event applications and Rhino MCP Yak package are included in the complete workflow payload.

## 2. Get a complete copy

### Git repository checkout

The runtime payload uses Git LFS. On a new machine, install Git for Windows and Git LFS, then run:

~~~powershell
git lfs install
git clone https://github.com/Krishna-Inventaur/inventaur-rhino3d-to-solidedge.git
cd inventaur-rhino3d-to-solidedge
git lfs pull
~~~

Do not use GitHub's generated source ZIP in place of a Git LFS checkout; it may contain pointer files instead of the required bundled executables and Python runtime.

Alternatively, extract the complete offline workflow bundle and keep its folder structure intact.

## 3. Install once

From the workflow root, double-click **INSTALL.bat**.

The installer verifies the bundled Solid Edge MCP programs, prepares the package-local .venv using the included CPython, installs psutil and pywin32 from the local wheelhouse with no package-index access, and installs/verifies the bundled Rhino MCP Yak package for compatible Rhino installations.

Wait for the installer to report success. Then restart Rhino so the plugin is loaded. The installer does not open Rhino, select a model or create the live MCP session.

## 4. Prepare the Rhino model

Open the intended saved 3DM in Rhino.

For a native assembly hierarchy, use:

- Top-level block instances for the root assembly.
- Parent block definitions containing child block instances for subassemblies.
- Leaf block definitions containing reusable part geometry.
- Multiple instances of the same block definition for repeated components.

Set each instance's position and orientation in Rhino. The workflow transfers its composed transform to the matching Solid Edge occurrence. Do not explode the block hierarchy. Rhino Groups alone do not create subassemblies.

Preflight also requires unique block definition names after case/whitespace normalization and an acyclic nested block-reference graph. Duplicate normalized names and cyclic definitions stop the run rather than risking ambiguous file mapping.

Geometry directly owned by a parent assembly block is treated as local component geometry, but dedicated leaf part blocks are easier to manage.

## 5. Start Rhino MCP

With the intended document open:

1. Run **MCPStart** in Rhino.
2. Run **MCPConnect**.
3. In the connected MCP client, verify that the active Rhino connection exposes **run_python**.
4. Keep Rhino, the document and the MCP connection open throughout conversion.

The runner does not launch Rhino, open a file, switch documents or hard-code an MCP port. It checks the exact document path and runtime identity before starting Solid Edge.

## 6. Start a new conversion

Open PowerShell in the workflow root and run:

~~~powershell
.\Scripts\Rhino3D_to_SolidEdge.bat --source "C:\Models\MyAssembly.3dm"
~~~

The branded launcher is also available:

~~~powershell
.\Scripts\Inventaur_Rhino3D_to_SolidEdge.bat --source "C:\Models\MyAssembly.3dm"
~~~

Use the exact path of the saved file already open in Rhino. If --source is omitted, the runner can discover the source only when exactly one eligible saved 3DM path is attached to a reachable Rhino MCP document. Use --source whenever more than one Rhino document/session is connected.

The runner captures the **current in-memory document state** to an isolated snapshot. Unsaved in-memory edits are therefore included in that snapshot, but the original 3DM is not saved back or modified.

### Optional output location

By default, a new output folder is created on the Windows Desktop using the source model name and run ID. To choose a location:

~~~powershell
.\Scripts\Rhino3D_to_SolidEdge.bat --source "C:\Models\MyAssembly.3dm" --output-root "D:\CAD\Conversions\MyAssembly"
~~~

Do not point a new run at a non-empty folder. Use a fresh output folder for each new run.

## 7. Understand the output folder

A successful run produces this structure:

~~~text
MyAssembly_<run-id>/
├── Rhino3D/
│   └── source snapshot and prepared Rhino model
├── STEP/
│   └── STEP exchange files
├── Parts/
│   └── native Solid Edge PAR documents
├── Assemblies/
│   └── nested and root ASM documents
├── Logs/
│   └── Reports/
└── README.md
~~~

The run's own README.md summarizes the result. The most useful reports are:

- Logs/Reports/live_document_snapshot.json
- Logs/Reports/rhino_source_preflight.json
- Logs/Reports/step_export_e2e.json
- Logs/Reports/native_part_import_e2e.json
- Logs/Reports/assembly_build_e2e.json
- Logs/Reports/final_acceptance_audit.json
- Logs/script_manifest.json
- Logs/workflow_config.json

## 8. Verify before using the result

A console exit code of zero is useful, but it is not the complete engineering sign-off.

Check that:

1. The source snapshot report identifies the intended Rhino file and has a recorded hash.
2. The STEP report accounts for every requested unique definition and required scaled variant.
3. The native import report shows which PAR files were imported/reused and whether each was saved, closed and reopened successfully.
4. Body counts, solid/sheet status, face/edge counts and open-edge diagnostics are understood. An intentional surface is not automatically a defect.
5. The assembly report shows completed nested/root assemblies with expected files, occurrences and transforms.
6. The root ASM opens in Solid Edge and its placements look correct.
7. Representative PAR files open and the geometry looks as expected.

The automated hash/occurrence checks are structural evidence. They do not replace visual review of form, orientation, colour, clearances, manufacturing detail or annotations.

## 9. Geometry repair is a separate, optional step

The production conversion does not silently repair or Boolean-union source geometry. If preflight or import reports point to an actual Rhino geometry issue, first read **RHINO_GEOMETRY_REPAIR_PLAYBOOK.md**.

The optional **inventaur_join_lowest_block_breps_v2.py** joins Breps in leaf definitions using RhinoCommon JoinBreps; it is not Boolean union. The optional **inventaur_repair_breps_for_step_v1.py** tests repair on duplicate geometry and writes a separate candidate model/report. Run either only on a copy, inspect the before/after report, and review the candidate before using it.

Do not force IsSolid=True, remove naked edges blindly or increase tolerance simply to get a green result. Some sheet/surface bodies are intentional.

## 10. Resume and recovery

If a run stops:

1. Do not immediately start another conversion over the same output.
2. Read the run README, Logs/Reports/supervisor.json, the last completed stage report and the execution log.
3. Identify the exact run ID and source snapshot hash.
4. Check whether the previous stage actually completed and whether its outputs reopen and match the recorded hashes.
5. Resume only with the same source, output root and run ID using --resume.

For example, with the same run ID and output folder:

~~~powershell
.\.venv\Scripts\python.exe .\Scripts\inventaur_run_rhino3d_to_solidedge.py --source "C:\Models\MyAssembly.3dm" --output-root "D:\CAD\Conversions\MyAssembly" --run-id "cad_20261117_120000" --resume
~~~

Do not copy that example run ID literally; use the ID recorded by your run. A timed-out Solid Edge COM operation has an uncertain outcome until the open documents, stage reports and output files are reconciled. Do not blindly replay a mutating operation.

## 11. Known limits

- The recorded live baseline is Rhino 9 + Solid Edge 2026 on Windows.
- Other Rhino/Solid Edge version combinations need target-machine testing.
- The normal conversion path does not automatically heal geometry.
- Native body validity and topology diagnostics are recorded; a sheet body may be intentional.
- A scaled occurrence may require a separately baked geometry variant.
- Human visual review remains required before production/manufacturing use.
