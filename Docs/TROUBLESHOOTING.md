> **Inventaur Inc.** - by **Krishna Parmar**

# Troubleshooting

## Rhino MCP is not reachable

The full bootstrap package includes McNeel Rhino-MCP-Platform 0.4.0 under `ThirdParty/RhinoAI`. Run `INSTALL.bat` to verify/install it with the Yak CLI, then restart Rhino, open the intended model and run `MCPStart` and `MCPConnect`.

- Confirm Rhino is running and the source 3DM is already open.
- Confirm the Rhino MCP integration exposes `run_python`.
- The workflow discovers the current listener endpoint; do not assume port 10500 or hard-code another port.
- Check for multiple Rhino sessions and pass `--source` to disambiguate.
- The workflow does not launch Rhino or open/switch documents.

## Bundled Python runtime or wheelhouse is missing

The full beta.3 package must contain `Runtime/Python/python.exe`, its `python313.dll`, the standard library, and these wheels under `Runtime/Wheels`: `psutil-7.2.2-cp37-abi3-win_amd64.whl` and `pywin32-312-cp313-cp313-win_amd64.whl`. Re-extract the complete ZIP if any are missing. The installer must not fall back to a system Python; it fails fast if the bundled runtime is incomplete.

The package creates `.venv` from the bundled CPython and installs dependencies offline with `--no-index`. No system Python or internet connection is required.

## Source path or runtime identity mismatch

The selected path must exactly match the document-scoped path reported by the attached Rhino MCP session. If the document was closed/reopened or the listener changed, stop and repeat preflight. Do not force a path match.

## Snapshot readback fails

Inspect `Logs/Reports/live_document_snapshot.json` and the runner log. Check that the output folder is writable and that Rhino can write/reopen the run snapshot. The original source should remain unchanged.

## Solid Edge ISO Metric template is missing

The importer searches installed Siemens Solid Edge directories under Program Files for `Siemens/Solid Edge */Template/ISO Metric/iso metric part.par`.

For a custom install or template, set:

~~~powershell
$env:CAD_SOLID_EDGE_PART_TEMPLATE = "D:\CAD_Templates\iso metric part.par"
~~~

The override must point to an existing file.

## Solid Edge MCP executable is missing

The full beta.3 ZIP must contain both self-contained servers and their sibling runtime files under `Scripts/SOLIDEDGE-MCP/runtime/win-x64`. Re-extract the **complete** ZIP to a fresh folder and run `INSTALL.bat`. The installer checks `coreclr.dll`, `hostfxr.dll`, `hostpolicy.dll`, `System.Private.CoreLib.dll` and runs each MCP server with `--version`. No recipient-side Git clone, source build, .NET SDK or global .NET runtime is required.

For developer rebuilds only, use the pinned upstream sources and a .NET 8 SDK. Do not point an application at a mismatched framework/runtime.

## `´╗┐@echo` is not recognized or a BAT does not parse

This indicates a UTF-8 BOM was added to a Windows batch file or an old launcher copy is being used. The beta.3 `INSTALL.bat`, `Scripts/Rhino3D_to_SolidEdge.bat` and `Scripts/Inventaur_Rhino3D_to_SolidEdge.bat` are UTF-8 without BOM. Re-extract the complete package; do not resave the BAT through an editor that inserts a BOM.

## Legacy launcher cannot find the branded launcher

Keep the pair of files in the same `Scripts` directory. `Rhino3D_to_SolidEdge.bat` is the compatibility entry point and forwards to `Inventaur_Rhino3D_to_SolidEdge.bat` with the original arguments and process exit code.

## Native import is blocked by a modal dialog

Inspect the exact bridge-owned Solid Edge process and its dialog inventory. Do not dismiss unrelated dialogs, click the user's foreground session, or retry an import while the outcome is uncertain.

## Part imports but is not a solid

Read body/model/construction counts and native import diagnostics. A valid surface body or multiple-body import may be intentional. Use the geometry repair playbook only when source evidence proves a Rhino-side defect.

## Assembly reports missing files

Check every referenced PAR/ASM path and the native import report before rebuilding. Use a new candidate assembly path and verify save/close/reopen. Never overwrite the only accepted assembly during recovery.

## A stage times out

Treat a mutating operation as `UNKNOWN_OUTCOME`. Inspect process identity, active document, stage report and output hashes before continuing. Do not automatically replay a timed-out COM call or placement batch.

## Git checkout contains tiny pointer files or bundled executables are missing

The source repository uses Git LFS for the portable Python runtime and Solid Edge MCP runtime payload. Install Git for Windows and Git LFS, then run git lfs install and git lfs pull from the repository root. A GitHub-generated source ZIP does not perform the LFS checkout and may contain pointer text instead of the actual runtime files. Alternatively, use the complete offline workflow bundle. Do not run INSTALL.bat from a partial folder copy.

## INSTALL.bat reports a missing runtime or dependency

Run INSTALL.bat from the workflow root, not from inside Scripts. Confirm Runtime/Python/python.exe, Runtime/Wheels and both Solid Edge MCP runtime folders are present and contain real files. Review the installer output for the first failed verification. Do not replace the bundled interpreter with a system Python or download unpinned dependencies as a workaround.

## Source is ambiguous or does not match the active Rhino session

Open the intended 3DM in the Rhino session connected through MCPStart/MCPConnect. Pass its exact path with --source. The runner does not open/switch documents and rejects a path that does not match a live document-scoped MCP session. When more than one Rhino document is connected, always pass --source.

## A new run reports that the output folder is not empty

Use a new, empty output root for a fresh run. Do not delete old outputs without first checking their run ID, reports, hashes and recovery value. To continue an existing run, use its original --source, --output-root and --run-id with --resume after verifying its last completed checkpoint.

## A conversion reports incomplete native parts or assemblies

Use Logs/Reports/step_export_e2e.json, native_part_import_e2e.json, assembly_build_e2e.json and final_acceptance_audit.json from the same run. Compare the source and STEP hashes, expected definition/occurrence inventory, native file existence, save/close/reopen state and transform checks. Distinguish missing bodies, invalid bodies, open sheet bodies and multiple bodies. Do not assume a sheet body is a failed solid or silently Boolean/repair it.
