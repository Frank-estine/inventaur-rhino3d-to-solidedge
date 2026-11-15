> **Inventaur Inc.** — by **Krishna Parmar**

# AI Agent Instructions

These instructions apply to AI coding agents, assistants, and automation workers operating in this repository.

## Read before acting

1. Read PROJECT_IDENTITY.md for the Inventaur ownership/naming and third-party attribution boundary.
2. Read Docs/RELEASE_READINESS_AUDIT.md before changing package/release behavior.

1. Read README.md.
2. Read Docs/OPERATOR_RUNBOOK.md before executing the workflow.
3. Read Docs/DATA_CONTRACTS.md and Docs/SUPERVISION_AND_RECOVERY.md before changing pipeline behavior.
4. For geometry defects, read Docs/RHINO_GEOMETRY_REPAIR_PLAYBOOK.md.
5. For code changes, read Docs/DEVELOPER_GUIDE.md and run the relevant tests.

## Source-of-truth and safety rules

- Treat the currently selected Rhino 3DM and the user's live Rhino document as source data. Never overwrite, save, rename, switch, or close the user's source document as part of preflight or repair.
- The live document must already be open in Rhino and attached to the intended MCP listener. Verify the exact path, document runtime identity, and run_python availability before any mutation.
- Capture the live state to a run-owned snapshot and verify it by reopening and comparing semantic model data. All derived edits must operate on a separate copy.
- Do not add customer project names, model files, source paths, personal usernames, machine names, tokens, local database files, run reports, or private logs to the public repository.
- Preserve object identity and attributes: block-definition identity, occurrence transforms, object IDs, names, layers, colours, alpha, units, and document tolerance must not be discarded without an explicit approved reason.
- Do not Boolean-union parts merely to force a solid. Do not explode Breps into faces. Do not silently delete open surfaces, construction geometry, meshes, SubD, curves, or nested block references.
- Never relax tolerances to force a pass. Report the actual document units and tolerance.
- AI-generated suggestions are not verification. A stage is complete only when its output is reopened and independently checked against expected source evidence.

## Geometry repair workflow

- Treat invalid Breps, naked edges, non-solids, multiple bodies, missing faces, and STEP/Parasolid translation differences as distinct conditions. Do not call all of them "bad geometry".
- Begin read-only: collect the Rhino object ID, block definition, object attributes, validity log, naked-edge count, face/edge count, solid/open state, bounding box, area/volume where available, units and absolute tolerance.
- Produce a diagnosis and a minimal repair plan before editing. Identify which objects will change and what evidence will demonstrate that the change is safe.
- Work on a copy. Keep the pre-repair file and a machine-readable before/after report.
- Use the least destructive operation first. The optional inventaur_repair_breps_for_step_v1.py makes duplicate candidates and writes a new 3DM/report; it is not part of the main conversion path.
- A repair is not accepted merely because Rhino reports success. Recheck validity, face/edge counts, naked edges, solid state, bounding box, area/volume and object attributes. Reject unexplained geometry loss or change.
- Re-export only the repaired copy to STEP and import into a disposable Solid Edge document. Save, close, reopen and compare native topology and file hashes. Keep warnings visible.
- Request human approval before any destructive GUI command, topology-changing operation, tolerance change, Boolean operation, object deletion, source replacement, or production export.

## Execution, recovery and reporting

- Use the packaged CLI and existing stage scripts. Do not invent command-line flags.
- Inspect the latest run configuration, stage report and process ownership before retrying.
- After a timeout, use UNKNOWN_OUTCOME until live state and reports prove what happened. Do not blindly replay a mutating COM call or assembly placement batch.
- Do not close or terminate the user's foreground Rhino or Solid Edge process. Only close a process/document that the workflow can positively identify as owned by its run.
- Preserve failed evidence. Never promote incomplete or unverified files into the deliverable folder.
- Report exact files changed, tests run, test results, residual warnings, and any manual visual review still required.

## Public-repository hygiene

- Keep Runs/, Logs/, dist/, _local/, build outputs, caches, backups and real CAD models out of Git.
- Run tools/build_release.ps1 to create the distributable ZIP. Do not manually zip the working directory.
- Check the generated manifest and search the staging tree for local paths, user names, secrets, private model identifiers and run data before sharing.
- Preserve the upstream license and attribution. Do not imply Siemens endorsement.
