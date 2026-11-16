> **Inventaur Inc.** — by **Krishna Parmar**

# AI Operator Guide

This guide describes the work an AI assistant may help with around the deterministic Rhino-to-Solid-Edge pipeline. The AI is a diagnostic and planning layer; it is not the geometry kernel and is not a substitute for human approval of destructive edits.

## Role separation

| Work | Primary executor | AI role |
|---|---|---|
| Source identity and snapshot | Workflow + Rhino MCP | Check preconditions and interpret reports |
| Inventory, manifests, STEP export | Deterministic scripts + RhinoCommon | Diagnose missing/mismatched objects |
| Native PAR import | Solid Edge MCP + COM automation | Interpret translator warnings and validation evidence |
| Assembly construction | Solid Edge API automation | Analyse occurrence/path/transform mismatches |
| BREP repair | RhinoCommon or an operator in Rhino | Diagnose, propose a minimal repair, compare before/after |
| Visual quality review | Human/operator | Build a review checklist and record sign-off |
| Documentation and release packaging | Build scripts + tests | Audit, document and validate package contents |

## Standard AI work loop

1. **Read the evidence.** Start with the run's README.md, Logs/Reports/supervisor.json, source snapshot report, stage report for the failing step, and relevant execution log.
2. **Bind evidence to the run.** Confirm the run ID, source snapshot SHA-256, script hashes and report timestamps. Do not combine reports from different runs or source revisions.
3. **Classify the failure.** Separate input identity, geometry validity, STEP translation, Solid Edge import, native save/reopen, assembly references/transforms, and visual defects.
4. **Inspect before editing.** Prefer read-only queries. Identify exact definition/object GUIDs, occurrence paths, file paths and transforms.
5. **Plan a minimal change.** List the exact objects and files expected to change, possible side effects, rollback path and acceptance tests.
6. **Obtain approval for destructive work.** Any topology change, geometry deletion/replacement, Boolean, tolerance change, document save, assembly mutation or user-window interaction needs explicit operator approval.
7. **Execute on a copy.** Never alter the original 3DM or an accepted deliverable in place.
8. **Reconcile the result.** Reopen files from disk, compare hashes and geometry signatures, inspect warnings and ensure no unrelated documents/processes were changed.
9. **Report accurately.** Distinguish verified facts, diagnostics, warnings, assumptions and manual sign-off still outstanding.

## Task playbooks

### A. Rhino source will not preflight

- Confirm Rhino is running and the intended 3DM is already open.
- Confirm the MCP endpoint is reachable and its tools/list includes run_python.
- Read the document-scoped path and runtime serial from the attached session.
- Compare the selected saved file path with the live document path. Do not guess between multiple open documents.
- If Modified=True, do not reject it by itself. The runner snapshots current in-memory state without saving the live document.
- Stop if the document identity changes, the saved path is absent, snapshot readback fails, or runtime identity changes.

### B. STEP export is incomplete or reports omitted objects

- Compare the STEP export report to the identity manifest.
- Identify each missing definition and its source object types. Unsupported annotations, meshes and non-Brep content may be omitted by the STEP translator; do not state that they were exported.
- Check export warnings and source object inventory.
- For a missing Brep, inspect object validity and geometry before trying any repair.
- Do not use a broad export retry to mask a source-level defect.

### C. Solid Edge import reports invalid or non-solid bodies

- Separate these states: no model/body, invalid body, open surface body, multiple bodies, and valid solid body.
- Read the full native import report for body count, body validity, face/edge counts, open edges, source STEP hash, native PAR path and reopen status.
- A non-solid surface can be intentional geometry. Do not convert or Boolean it merely because IsSolid=False.
- If a body is invalid, consult the Rhino Geometry Repair Playbook. Propose a Rhino-side repair only when source evidence supports it.
- Require a new STEP export and a new disposable native import before changing the accepted native deliverable.

### D. Assembly has missing files or wrong placements

- Read the assembly report and identity manifest.
- Verify every referenced PAR/ASM path exists before inspecting mates.
- Compare expected versus actual occurrence counts and composed transforms.
- Check unit conversion (Rhino model units to Solid Edge metres), rotation, reflection parity and scale.
- Do not rebuild or replay a placement batch after a timeout until the active assembly and occurrence inventory have been queried.
- Preserve the prior assembly and create a new candidate file. Save, close and reopen it from disk before promotion.

### E. Rhino geometry needs manual repair

- Read the complete Rhino Geometry Repair Playbook.
- Produce a diagnosis table with source ID, definition, validity log, defect type, intended operation and acceptance evidence.
- Use the optional repair script only on a run-owned copy and after checking the document's units/tolerance.
- When manual Rhino UI work is needed, provide exact object selection and command steps; ask the operator to confirm the target objects before applying them.
- Compare before/after geometry and attributes. If the change cannot be justified, roll back and retain the original.

### F. Prepare a public bug report or forum post

- Include package version, Windows/Rhino/Solid Edge versions, exact command, expected behavior and actual behavior.
- Attach only sanitized JSON reports and a minimal synthetic sample if the geometry is needed.
- Remove source 3DMs, native parts/assemblies, local paths, usernames, bridge state, access tokens and unrelated logs.
- State whether the issue was reproduced in a clean sample or only in a customer model.
- Do not post proprietary geometry without the model owner's permission.

## Required AI output format for a repair/diagnostic task

- **Observed:** facts copied from the current run's reports.
- **Diagnosis:** most likely defect class and evidence; state alternatives when uncertain.
- **Proposed change:** exact objects, operation, copy/output path and expected side effects.
- **Rollback:** path/hash of the preserved pre-change source.
- **Acceptance:** checks required after save/reopen and STEP/native re-import.
- **Result:** PASS, FAIL or NEEDS HUMAN REVIEW. Do not use PASS when visual review or a required native reopen is missing.

## Workflow baseline and evidence ownership

The canonical human procedure is Docs/OPERATOR_RUNBOOK.md. For a new conversion, use the documented batch launcher and bind analysis to one run folder. The expected report set is:

- Logs/Reports/live_document_snapshot.json and rhino_source_preflight.json for source identity.
- Logs/Reports/name_identity_manifest.json and step_export_e2e.json for definition identity and STEP export.
- Logs/Reports/native_part_import_e2e.json for native PAR import, body diagnostics and document cleanup.
- Logs/Reports/assembly_build_e2e.json for nested/root ASM references and occurrence transforms.
- Logs/Reports/final_acceptance_audit.json for the consolidated result.
- Logs/script_manifest.json and Logs/workflow_config.json for code/config provenance.

Never combine reports from separate run IDs or source snapshot hashes. A previous report is context only unless the current run explicitly records and verifies reuse of its artifacts.

## Safe resume rule

The CLI supports --resume, but it is not a generic retry switch. Use it only with the original source path, output root and run ID. Confirm that the snapshot and last completed stage outputs exist and match their recorded hashes. If a mutating Solid Edge operation timed out, classify it as UNKNOWN_OUTCOME and reconcile the process, document and artifact state before continuing. Do not delete the previous stage evidence to force a clean restart.

## Geometry and engineering review boundary

The standard pipeline transfers and verifies geometry; it does not guarantee that every imported object is a solid. Surface/sheet bodies can be correct design content. Do not recommend Boolean union, tolerance changes or automatic repair just to increase a solid-body count. Use the separate Rhino Geometry Repair Playbook only when the source-side evidence establishes a repairable defect, and keep original and repaired candidates separate.

A completed automated audit is not a manufacturing approval. Human review remains necessary for representative PAR/ASM geometry, orientation, colour, clearances, dimensions, annotations and downstream design intent.
