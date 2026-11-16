# AI Agent Instructions

These instructions apply to AI coding agents, assistants and automation workers operating in this repository.

## Read before acting

1. Read this README and PROJECT_IDENTITY.md.
2. Read Docs/OPERATOR_RUNBOOK.md before running a conversion.
3. Read Docs/BOOTSTRAP_AND_DEPLOYMENT.md before changing installation or runtime setup.
4. Read Docs/DATA_CONTRACTS.md, Docs/CAD_AUTOPILOT_ARCHITECTURE.md and Docs/SUPERVISION_AND_RECOVERY.md before changing pipeline behavior.
5. For geometry defects, read Docs/RHINO_GEOMETRY_REPAIR_PLAYBOOK.md.
6. For diagnostic/report interpretation, read Docs/AI_OPERATOR_GUIDE.md.
7. For code changes, read Docs/DEVELOPER_GUIDE.md and the relevant tests.
8. Read Docs/RELEASE_READINESS_AUDIT.md before changing release or redistribution behavior.

## Source and execution boundaries

- The exact saved Rhino 3DM path and the document-scoped Rhino runtime identity must match the live MCP session before the runner proceeds.
- The source document must already be open in Rhino. The workflow does not launch Rhino, open/switch the source document, save over it, rename it or close it.
- The runner captures current in-memory Rhino state to a separate run-owned snapshot and verifies the snapshot before conversion. Unsaved in-memory edits may therefore appear in the snapshot without being saved back to the user's source document.
- Rhino MCP must expose the document-scoped run_python tool. Discover the live endpoint; never hard-code an MCP port.
- Solid Edge work runs through the run-owned isolated bridge. Do not attach to or mutate an unrelated foreground Solid Edge session.
- Do not run live CAD integration tests casually. Use a disposable model/output and the explicit operator authorization required by the test.

## Model integrity and geometry

- Preserve block-definition identity, occurrence identity and transforms, object IDs, names, layers, RGB/alpha attributes, units and model tolerance unless an explicitly approved operation changes them.
- Use nested block definitions and instances to encode assembly structure. Rhino Groups alone are not assembly definitions.
- Treat invalid Breps, open surfaces, multiple bodies, missing geometry and STEP/Parasolid translation differences as distinct conditions.
- The normal conversion path does not automatically Boolean-union, heal, simplify or loosen tolerance to force a solid.
- Optional JoinBreps and duplicate-candidate BRep repair tools are separate operations. Work on a copy, preserve before/after evidence and require operator approval for topology-changing work.
- Never delete open surfaces, construction geometry, meshes, SubD, curves or nested references merely to make an import report look cleaner.
- AI analysis is diagnostic; RhinoCommon and Solid Edge perform deterministic CAD operations. AI suggestions are not geometry verification.

## Evidence and acceptance

- Bind all stage evidence to the same run ID, source snapshot SHA-256 and script manifest.
- Read the source snapshot, STEP export, native import, assembly and final acceptance reports for that run.
- A native import is not accepted only because COM returned success. Reopen the saved PAR/ASM files from disk and verify hashes, references, occurrence counts and transforms.
- Keep solid/sheet body state, validity, face/edge counts and warnings visible. A valid surface body may be intentional.
- Hash and occurrence checks do not replace human visual inspection of shape, orientation, colour, clearances, annotation or manufacturing requirements.
- Keep verification claims precise: static, unit-test, integration, live CAD or visual sign-off.

## Execution, recovery and reporting

- Use the documented launchers and existing CLI options. Do not invent command-line flags or use stale shortcuts.
- For a fresh run, use a new empty output folder. For recovery, inspect the exact prior run and resume only with its original source, output root and run ID after verifying the saved checkpoint outputs.
- Treat a timeout on a mutating COM/MCP call as UNKNOWN_OUTCOME until the process, open documents, stage reports and output hashes prove what happened. Never blindly replay a mutation.
- Preserve failed run evidence. Do not delete derived output or logs until its ownership, references and recovery value are understood.
- Do not close or terminate user-owned foreground Rhino or Solid Edge processes. Only close a process/document positively identified as owned by the workflow run.
- Report exact files changed, tests run, test results, residual warnings and manual review still required.

## Public repository hygiene

- Keep run data, source CAD models, native PAR/ASM/DFT files, logs, caches, backups, build output and local configuration out of Git.
- The source repository uses Git LFS for large runtime payloads. A complete source checkout requires Git LFS; GitHub's automatically generated source archive is not a substitute for the full offline bootstrap.
- Do not run the release builder, rebuild packages or create/publish a release unless that work is explicitly requested.
- Before any authorized publication, inspect the staged tree for personal paths, usernames, secrets, private model identifiers, live logs and proprietary data.
- Preserve third-party licenses and attribution. Do not imply Siemens or McNeel endorsement.
- The first-party license remains pending; repository visibility does not grant redistribution rights.
