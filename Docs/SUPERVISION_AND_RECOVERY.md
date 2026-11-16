# CAD Workflow Supervision and Recovery

## Main execution

Use the operator procedure in Docs/OPERATOR_RUNBOOK.md. The canonical supervisor is Scripts/inventaur_run_rhino3d_to_solidedge.py and the stable user-facing entry point is Scripts/Rhino3D_to_SolidEdge.bat.

The workflow requires an already-open Rhino document attached to Rhino MCP with run_python available. It verifies the exact source path and runtime identity, snapshots the current in-memory model to a separate run folder, then performs colour policy, inventory/identity, STEP export, native PAR import, nested/root ASM construction and final disk-reopen checks.

## Before a run

- Use the exact source path already open in the intended Rhino MCP document.
- Use a fresh empty output folder for a new run.
- Keep Rhino and its document-scoped MCP session open.
- Do not close or switch the source document while conversion is running.
- Use the isolated Solid Edge bridge; never attach to an unrelated foreground session.

## Failure and recovery

1. Stop launching new work against the same output until the last operation is understood.
2. Read the run README, Logs/Reports/supervisor.json, the stage report for the last operation and the execution log.
3. Bind the evidence to the run ID, source snapshot SHA-256 and script manifest.
4. Check the exact owned Solid Edge process and open documents. Reconcile native output files, hashes and references from disk.
5. Preserve all failed and partial evidence. Do not delete the colourised model, STEP, PAR, ASM or stage reports merely to restart.
6. Resume only with the same source path, output root and run ID using --resume, and only when the existing snapshot and completed stage outputs pass their recorded checks.
7. If a prior mutating COM/MCP call timed out and the result cannot be proven, mark it UNKNOWN_OUTCOME and stop. Do not replay that call or a placement batch until its effect is reconciled.

A fresh run is appropriate only when the previous run has been safely closed out and a new, separate output location is selected. Do not overwrite the only accepted deliverable during recovery.

## What blocks acceptance

A failed STEP write, missing expected model/body, failed PAR save/reopen, missing native reference, incomplete occurrence set or mismatched placement transform blocks the corresponding acceptance criterion. Body.Valid, naked-edge counts, face-count differences and mass-property differences are diagnostics and must be interpreted in the context of source geometry/design intent; they are not universal pass/fail criteria.

## Completion

All expected native part and assembly documents must exist and reopen. Repeated definitions must reference the expected shared native file. Nested/root assemblies must have the expected references and occurrences and match the expected composed transforms. Review source, STEP, native import, assembly and final acceptance reports. Human visual inspection is still required before production/manufacturing use.
