# Inventaur Rhino 9 Drafting Standards — TODO

**Package version:** 1.3.1  
**State:** IMPLEMENTED; live functionality, template persistence, unit safety, explicit MCP start and 1.2.2 runtime-compatibility patch source checks verified. Cold-start in the affected Rhino process remains.  
**This file is a maintenance checklist, not a second task queue.** Assignable task state remains in IvyGPT TaskBus `F:/ai/BOT/IvyGpt-SOLO/tasks/todo.sqlite`.

## Completed and verified

- [x] Install the Rhino 9 metric architectural default template.
- [x] Persist the 44-layer architectural base structure and set `04_ARCHITECTURE::GENERAL` as the template's current layer.
- [x] Add 14 persistent Inventaur dimension, leader and text styles; verify them after reopening the `.3dm`.
- [x] Import the six Inventaur PAT definitions through RhinoScriptSyntax `AddHatchPatterns()` and verify all six names in the document hatch table.
- [x] Install the PAT source in Rhino 9's per-user Hatch Patterns folder.
- [x] Route newly created `TextEntity` / `TextDot` objects to `TEXT`.
- [x] Route newly created dimensions and leaders to `ANNOTATIONS`.
- [x] Route newly created hatch objects to `HATCH`.
- [x] Test all three routing paths with real disposable Rhino objects; delete the test objects afterwards.
- [x] Confirm the template reopens with 44 layers, 14 Inventaur styles, 59 hatches, zero geometry objects, `INV_STD_MM` and `04_ARCHITECTURE::GENERAL` current.
- [x] Verify unit safety in a disposable inch-based document: document remains Inches and a 10-inch line remains 10 inches; current style becomes `INV_STD_IN_DEC`.
- [x] Make startup idempotent: validate/reuse an existing template instead of regenerating it on every Rhino launch.
- [x] Preserve user-selected non-default annotation styles and existing geometry/layer assignments.
- [x] Preserve an older template and the v1.0 router as rollback assets.
- [x] Keep runtime and IvyGPT canonical copies SHA-256 identical.
- [x] Register `cad_rhino_standards` in the Automation Master Catalogue and expose this README/TODO through CAD navigation.
- [x] Add explicit `Rhino.RhinoApp.RunScript("_MCPStart", False)` to the Rhino startup entrypoint, independent of installer error handling.
- [x] Fix bootstrap variable collision (`log` path was shadowed by the installer's `log()` function), which previously could prevent MCP start from being reached.
- [x] Remove `os.makedirs(..., exist_ok=True)` from the startup and installer paths; directory creation now works without the Python 3-only keyword.
- [x] Use `codecs.open` for encoded log/source I/O, `strftime` for timestamps, and `os.rename` after explicit destination cleanup for cross-runtime file handling.
- [x] Keep the existing template validate-and-reuse path; compatibility patch does not trigger a template rebuild or model rescale.
- [x] Run the 1.2.2 entrypoint through Rhino `_-RunPythonScript` in the separate `test.3dm` session; installer log confirms 49 layers, 14 Inventaur styles, 59 hatches, no existing-object rerouting and template reuse.
- [x] Execute the exact updated startup entrypoint in the active Rhino process: bootstrap log records `STANDARDS_BOOTSTRAP_OK version=1.2.1` and `MCPSTART_RUNSCRIPT_RETURN=True`.
- [x] Run Rhino `_MCPStatus`; it returns `[RhinoAI] MCP server running on http://localhost:10500/`.

## Remaining acceptance

- [ ] On the next normal Rhino restart **after the 1.3.1 hatch import patch**, verify the General Options startup command launches `Inventaur_RhinoAutoLayer.py` automatically (without manually running the script) and the bootstrap log records installer version `1.2.2`.
- [ ] In that fresh process, verify `_MCPStart` is invoked by the startup entrypoint, the RhinoAI endpoint responds to `MCPStatus`, and the registered document event handlers are active.
- [ ] Create a new document through Rhino's normal New command and confirm it inherits the metric template, 59 hatches, 14 styles, `INV_STD_MM`, and `04_ARCHITECTURE::GENERAL`; verify text/dimension/hatch routing again after the cold start.
- [ ] Confirm an existing non-mm document can be opened in the fresh process without unit conversion or tolerance reset.

## Maintenance rules

1. Do not rebuild or overwrite `Inventaur_Architecture_MM.3dm` automatically at Rhino startup. Rebuild only as an explicit standards update; retain the prior `.3dm` backup.
2. Never force an existing user document into millimetres. Only the generated default template is always mm.
3. Do not move regular geometry or rename/delete user layers. Auto-routing is limited to text, annotation and hatch object types.
4. Do not delete `Inventaur_RhinoAutoLayer_legacy_1_0.py` or `Inventaur_Architecture_MM.3dm.previous` until a later release has its own verified rollback point.
5. Keep this folder mirrored between `C:\Users\krish\Documents\Inventaur\Rhino Standards` and `F:\ai\BOT\AUTOMATIONS\CAD\Rhino_Standards`; refresh `manifest.json` and compare hashes after every package change.
6. Update `CAD/README.md`, `AUTOMATIONS_MASTER.md` and `AUTOMATIONS_MASTER.sqlite` when ownership or package entrypoints change. Do not create a duplicate task queue here.

## Evidence and recovery

- Verification report: `verification_report_20261115.json`.
- Pre-1.2.2 source and documentation backups: `F:\ai\BOT\AUTOMATIONS\state\backups\rhino_standards_compat_1_2_2_20261115`.
- Runtime log: `%LOCALAPPDATA%\Inventaur\RhinoStandards\logs\Inventaur_RhinoStandards.log`.
- Startup command: Rhino Options → General → Run these commands every time Rhino starts.
- Default template: `Inventaur_Architecture_MM.3dm`.
- Rollback template: `Inventaur_Architecture_MM.3dm.previous`.
- Rollback router: `Inventaur_RhinoAutoLayer_legacy_1_0.py`.
- Pre-change model backups are in the source `test.3dm` directory; paths and hashes are recorded in the verification report.

## Hatch import 1.3.1

- [x] Replace the ineffective `HatchPattern.ReadFromFile()` + manual add path with RhinoScriptSyntax `AddHatchPatterns(PAT_PATH, True)`.
- [x] Add explicit six-name verification for the Inventaur PAT definitions.
- [ ] Confirm the six custom names appear in the Hatch command UI after a fresh Rhino restart.
