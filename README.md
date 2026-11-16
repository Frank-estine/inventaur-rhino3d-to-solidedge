# Rhino 3D to Solid Edge: block-aware parts and assemblies

Hi everyone — I wanted to share a Rhino-to-Solid Edge workflow I have been building for projects that use nested and repeated Rhino blocks.

I started working on it after running into frustrating results when moving some of my Rhino assemblies into Solid Edge. In one earlier import attempt, a subassembly was reported as **24 sheet bodies and 0 solid bodies**, alongside Parasolid B-rep creation errors. I also wanted a better way to preserve repeated and nested Rhino block instances as a reusable Solid Edge assembly, rather than treating every occurrence as a completely separate part.

The aim is to make that hand-off more predictable and, just as importantly, make every stage inspectable. Rather than relying on a single import operation, the workflow inventories the Rhino assembly, exports definition geometry, creates native Solid Edge parts, rebuilds the assembly hierarchy, and checks the saved files again from disk.

**Project:** Inventaur Inc. · **Author:** Krishna Parmar · **Version:** 1.0.0-beta.3

[GitHub repository](https://github.com/Krishna-Inventaur/inventaur-rhino3d-to-solidedge)

## What it does

The workflow takes a saved Rhino 3DM that is already open in Rhino and converts its block structure into native Solid Edge PAR and ASM documents.

- A unique Rhino part/block definition becomes one reusable native Solid Edge part file.
- A nested Rhino assembly definition becomes a reusable Solid Edge subassembly.
- Repeated instances reference the same native part or subassembly file, while each occurrence keeps its own placement.
- The nested/root assembly is rebuilt from the Rhino hierarchy, rather than flattening the whole model into unrelated parts.

For example, if a bolt block appears 40 times in the Rhino model, the workflow aims to create one bolt PAR and place 40 occurrences of that file in the Solid Edge assembly. It does not need 40 duplicate bolt part files.

## Why I built a staged workflow

The transfer is deliberately split into stages so a failure can be traced to its source:

1. **Connect to the intended Rhino document.** The runner checks the exact saved 3DM path and live document identity through Rhino MCP.
2. **Capture a run snapshot.** The current in-memory Rhino document is written to a separate run folder and checked. The original Rhino document is not saved over, renamed, switched, closed or modified by the workflow.
3. **Inventory the model.** It records block definitions, nested references, unique part identities, object attributes and occurrence transforms.
4. **Prepare and export definition geometry.** The workflow applies its colour policy and writes STEP files for unique definitions. It creates a separate baked geometry variant for a scaled occurrence when Solid Edge assembly placement cannot represent that scale directly.
5. **Import native parts.** STEP files are imported into native Solid Edge PAR documents through the controlled Solid Edge bridge.
6. **Build assemblies.** Nested ASM files and the root assembly are created from the Rhino block hierarchy, with occurrence transforms applied.
7. **Reopen and audit.** Native parts and assemblies are saved, closed and reopened from disk. Run reports check file identity, hashes, expected references, occurrence counts and placement data.

This is a Windows workflow using RhinoCommon and Solid Edge automation. The conversion stages are deterministic; an AI model is not used to generate or repair the geometry. The connected MCP client provides the document-scoped Rhino run_python bridge used by the runner.

## Geometry, transforms and accuracy

There are two separate concerns here: preserving the model during translation, and repairing geometry that is already defective.

### What the normal conversion path preserves and checks

- Rhino block-definition identity and repeated occurrence identity.
- Nested block relationships and composed instance transforms.
- Model units and conversion of Rhino lengths into Solid Edge metres.
- Rotation, reflection and placement data.
- Object RGB/alpha attributes where supported by the export path.
- Source, STEP and native output hashes and the reports that connect them.

A non-unit-scale occurrence is handled as an explicit baked geometry variant where the Solid Edge occurrence transform cannot represent the scale. The variant is recorded separately; the workflow does not silently discard the scale.

### What it does not silently do

The standard conversion path does **not** automatically Boolean-union, heal, simplify or change the topology of the source model. It also does not loosen the Rhino document tolerance just to force an import to pass.

There are separate, optional Rhino-side utilities for:

- Joining Breps in leaf block definitions with RhinoCommon JoinBreps (not Boolean union).
- Testing B-rep repair on duplicate geometry and writing a separate repaired model and report.

Those tools can change topology, so they are not automatic stages in the main conversion. Use them only on a copy, inspect their before/after reports, and review the result before exporting it. A valid open surface or sheet body may be intentional; the workflow does not assume that every object must become a closed solid.

See [the Rhino Geometry Repair Playbook](Docs/RHINO_GEOMETRY_REPAIR_PLAYBOOK.md) for the safeguards and decision process.

## Tested baseline and current limitations

The recorded live end-to-end baseline was run on Windows with **Rhino 9 and Solid Edge 2026**:

- 45/45 planned native PAR imports completed verification.
- 27/27 nested assembly builds completed.
- The root assembly was reopened and its 11/11 direct occurrences were checked.

These are the recorded automated run results, not a claim of universal compatibility or a substitute for visual inspection. A native import may contain a valid sheet/surface body rather than a solid; body validity, face/edge counts and open-edge information are retained as diagnostics. Review the actual reports for the model being converted.

The current release is beta software. Human visual review of representative part geometry, assembly placement and annotations remains part of engineering sign-off. A second-workstation installation is not claimed as verified.

## Requirements

| Component | Requirement |
|---|---|
| Operating system | Windows 10/11, 64-bit |
| Rhino | Rhino 8.19+ or Rhino 9 |
| Solid Edge | Siemens Solid Edge 2023 or later, installed and licensed, with COM automation available |
| Rhino connection | McNeel Rhino MCP Platform installed and loaded |
| MCP client | Connected to the intended Rhino session and exposing the document-scoped run_python tool |
| Source model | A saved 3DM already open in that Rhino session, with nested block definitions for the intended assembly hierarchy |

**Verified baseline:** Rhino 9 + Solid Edge 2026. Other supported-version combinations should be tested on the target workstation before production use.

### Prepare the Rhino model

For the assembly hierarchy to be reconstructed correctly, use Rhino **block definitions and nested block instances**, not Groups alone:

- Top-level block instances in the active document form the root assembly.
- Parent block definitions containing child block instances form subassemblies.
- Leaf block definitions contain reusable part geometry.
- Repeated components should be repeated instances of the same block definition.
- Position and orient each instance in Rhino; its transform is transferred to the assembly.
- Block definition names must be unique after case/whitespace normalization.
- The nested block-reference hierarchy must not contain cycles.

Do not explode the nested block structure before conversion. A Rhino Group is not a substitute for a nested block definition.

## Install

There are two ways to obtain the complete workflow files.

### Option A — Clone the repository

The portable Python runtime, offline wheels and bundled Solid Edge MCP runtime include Git LFS payloads. Install Git for Windows and Git LFS, then clone the repository and pull the large files:

~~~powershell
git lfs install
git clone https://github.com/Krishna-Inventaur/inventaur-rhino3d-to-solidedge.git
cd inventaur-rhino3d-to-solidedge
git lfs pull
~~~

Do not use GitHub's automatically generated **Source code (zip)** as a substitute for a complete checkout: Git LFS-managed runtime files may be represented by small pointer files rather than the actual binaries.

### Option B — Use the complete offline workflow bundle

Extract the complete beta.3 offline bundle to a folder. Keep the extracted directory structure intact. Do not run the installer from a partial copy of Scripts or Runtime.

### Run the installer

From the extracted repository or complete bundle root, double-click **INSTALL.bat** once.

The bootstrap:

1. verifies the bundled Solid Edge MCP control and event applications and their private runtime files;
2. creates or reuses the local .venv using the bundled CPython 3.13.7 x64 runtime;
3. installs the bundled psutil and pywin32 wheels with pip --no-index;
4. installs or verifies McNeel's Rhino-MCP-Platform 0.4.0 Yak package for compatible Rhino installations;
5. checks Rhino and Solid Edge prerequisites, including Solid Edge COM/template readiness.

For the complete offline bundle, Python dependency installation does not download from PyPI and does not require a system Python or a separately installed .NET runtime. After installation, **restart Rhino** so the MCP plugin is loaded.

## Connect Rhino

1. Start Rhino 8.19+ or Rhino 9.
2. Open the saved 3DM you want to convert.
3. In the Rhino command line, run **MCPStart**.
4. Then run **MCPConnect**.
5. In your connected AI/MCP client, confirm the active Rhino connection exposes the document-scoped run_python tool.
6. Keep Rhino, the MCP connection and the intended document open while the conversion runs.

The installer prepares the software; it does not open Rhino, choose your model or establish the live MCP session. The runner discovers the active listener, so you should not need to hard-code an MCP port.

## Run a conversion

Open a terminal in the workflow folder and run:

~~~powershell
.\Scripts\Rhino3D_to_SolidEdge.bat --source "C:\Models\MyAssembly.3dm"
~~~

The branded equivalent is:

~~~powershell
.\Scripts\Inventaur_Rhino3D_to_SolidEdge.bat --source "C:\Models\MyAssembly.3dm"
~~~

Both launch the same runner and return its actual exit code. The --source path must be the exact saved 3DM already open in the connected Rhino session.

If exactly one eligible saved 3DM is attached to a reachable Rhino MCP document, the runner can discover it without --source. When more than one document is connected, specify the source path explicitly.

### Where the results go

By default, the workflow creates a new folder on the Windows Desktop using the source model name and run ID. It does not open a folder picker.

~~~text
MyAssembly_<run-id>/
├── Rhino3D/       source snapshot and prepared Rhino model
├── STEP/          STEP exchange files
├── Parts/         native Solid Edge PAR files
├── Assemblies/    nested and root ASM files
├── Logs/
│   └── Reports/   source, STEP, native import, assembly and acceptance reports
└── README.md      run-specific handoff and result summary
~~~

You can choose another output location with --output-root:

~~~powershell
.\Scripts\Rhino3D_to_SolidEdge.bat --source "C:\Models\MyAssembly.3dm" --output-root "D:\CAD\Conversions\MyAssembly"
~~~

## Check the result

Do not rely on the console's success message alone. Open the generated run folder and review:

- **README.md** — summary of that run.
- **Logs/Reports/live_document_snapshot.json** — identity and hash of the captured Rhino state.
- **Logs/Reports/step_export_e2e.json** — requested and verified STEP exports.
- **Logs/Reports/native_part_import_e2e.json** — native import results and body diagnostics.
- **Logs/Reports/assembly_build_e2e.json** — nested/root assembly results and occurrence checks.
- **Logs/Reports/final_acceptance_audit.json** — final acceptance summary.

Open the ASM and representative PAR files in Solid Edge and visually inspect geometry, orientation, materials/colours and clearances before using them downstream. Hash and occurrence checks prove file/structure consistency; they do not replace an engineering review.

## Troubleshooting and recovery

- **run_python is missing:** restart Rhino, run MCPStart and MCPConnect, then verify that the connected client is attached to the intended document.
- **The wrong Rhino file is detected:** specify the exact --source path and confirm that same file is open in the MCP-connected Rhino document.
- **Block hierarchy preflight fails:** check duplicate normalized block names, cyclic nested references, and whether the model uses actual block definitions rather than Groups.
- **A part imports as a sheet body:** check whether the source is intentionally open, then inspect the native import report. Do not Boolean-union or repair it just to force a solid.
- **A native part or assembly is missing:** inspect the STEP/native/assembly reports and hashes before retrying. Do not rerun a timed-out COM operation blindly.
- **A run needs to be resumed:** use the same source, output root and run ID with --resume; resume only when the run reports confirm that the prior stage outputs are still valid.

See the [Operator Runbook](Docs/OPERATOR_RUNBOOK.md), [Bootstrap and Deployment Guide](Docs/BOOTSTRAP_AND_DEPLOYMENT.md) and [Troubleshooting Guide](Docs/TROUBLESHOOTING.md) for more detail.

## Documentation map

- [Operator Runbook](Docs/OPERATOR_RUNBOOK.md) — install, prepare Rhino, connect MCP, run, inspect and resume a conversion.
- [Bootstrap and Deployment](Docs/BOOTSTRAP_AND_DEPLOYMENT.md) — complete Git LFS checkout, offline bundle and installer behavior.
- [CAD Autopilot Architecture](Docs/CAD_AUTOPILOT_ARCHITECTURE.md) and [Data Contracts](Docs/DATA_CONTRACTS.md) — stage ownership, source identity, mapping and verification contracts.
- [Rhino Geometry Repair Playbook](Docs/RHINO_GEOMETRY_REPAIR_PLAYBOOK.md) — optional, separate and reviewable geometry repair procedures.
- [Troubleshooting](Docs/TROUBLESHOOTING.md) and [Supervision and Recovery](Docs/SUPERVISION_AND_RECOVERY.md) — diagnosis, uncertain outcomes and safe resume.
- [AI Operator Guide](Docs/AI_OPERATOR_GUIDE.md) and [Developer Guide](Docs/DEVELOPER_GUIDE.md) — assistant boundaries and development workflow.

A parent block definition can contain both child block instances and geometry owned directly by that definition. That directly owned geometry is handled as local component geometry; a companion native part may be created alongside the subassembly. Dedicated leaf part blocks are generally easier to understand and reuse.

## Feedback welcome

I would especially appreciate feedback on:

- Rhino/Solid Edge version combinations beyond the tested baseline.
- STEP translation of complex Breps, multi-body parts and intentional sheet/surface geometry.
- Mirrored and scaled block occurrences.
- Large nested assemblies and repeated-component performance.
- Any mismatch between Rhino source geometry and the reopened native Solid Edge result.

For a reproducible issue, a small synthetic 3DM with no customer or proprietary geometry is ideal. Please include the Rhino/Solid Edge versions, the relevant sanitized JSON report and the exact stage that failed. Do not post customer models, personal file paths, tokens or private run logs publicly.

## Credits and licensing

- [McNeel RhinoAI / Rhino MCP Platform](https://github.com/mcneel/RhinoAI) — official Rhino MCP integration; its third-party license and package metadata are retained under ThirdParty/RhinoAI.
- [Tyler Wagler's SolidEdge-MCP](https://github.com/tylerwagler/SolidEdge-MCP) — original Python MCP repository referenced during development; attribution and its MIT license are retained under ThirdParty/SolidEdge-MCP.
- [solidedge-mcp-server](https://github.com/1337332551-dot/solidedge-mcp-server) — separate .NET MCP control/event server source; attribution and license are retained under ThirdParty/DotNet.

The first-party workflow license is still marked pending in LICENSE_PENDING.txt. Do not assume that repository visibility grants permission to redistribute the first-party code or bundled third-party runtimes. This project is not affiliated with or endorsed by McNeel or Siemens.
