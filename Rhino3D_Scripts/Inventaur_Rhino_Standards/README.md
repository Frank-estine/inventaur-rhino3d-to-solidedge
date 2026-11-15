# Inventaur Rhino 9 Drafting Standards

**Package:** 1.3.1  
**Rhino:** 9.0.26300.9401  
**Runtime copy:** `C:\Users\krish\Documents\Inventaur\Rhino Standards`  
**IvyGPT canonical copy:** `F:\ai\BOT\AUTOMATIONS\CAD\Rhino_Standards`

## Installed defaults

`Inventaur_Architecture_MM.3dm` is the default metric architectural template. A fresh Rhino readback verifies **44 layers, 14 persistent Inventaur styles, 59 hatch definitions and zero geometry objects**. Its current layer is `04_ARCHITECTURE::GENERAL`; its current dimension style is `INV_STD_MM`.

The application adds the following drafting layers: `00_GUIDES`, `01_SITE`, `02_EXISTING`, `03_DEMOLITION`, `04_ARCHITECTURE`, `05_STRUCTURE`, `06_INTERIORS`, `07_FURNITURE`, `08_SERVICES`, `TEXT`, `ANNOTATIONS`, `HATCH`, `DETAILS`, `REFERENCES` and `PRESENTATION`, with discipline sublayers where applicable.

### Annotation styles

- Metric: `INV_STD_MM`, `INV_STD_M`
- Imperial: `INV_STD_IN_DEC`, `INV_STD_IN_FRAC`, `INV_STD_FT_IN`
- Hybrid: `INV_STD_MM_M`, `INV_STD_MM_IN`, `INV_STD_MM_FT_IN`, `INV_STD_M_MM`
- Leader: `INV_STD_LEADER_MM`
- Text heights: `INV_STD_TEXT_2_5MM`, `INV_STD_TEXT_3_5MM`, `INV_STD_TEXT_5_0MM`, `INV_STD_TEXT_7_0MM`

These are normal document styles, not reference-only styles. The template was saved and independently reopened; all 14 styles persist.

### Hatches

The document hatch table starts with Rhino 9 defaults. The installer now imports the six Inventaur PAT definitions through RhinoScriptSyntax `AddHatchPatterns(PAT_PATH, True)` and verifies that all six expected `Inventaur_*` names exist in the document table. Merely placing a `.pat` file on disk is not treated as loading it. The previous RhinoCommon `ReadFromFile()` + manual table-add path was removed because live logs repeatedly showed `added_pat=0`. The PAT source is also installed under Rhino 9's per-user Hatch Patterns folder:

`%APPDATA%\McNeel\Rhinoceros\9.0\Localization\en-US\Hatch Patterns\Inventaur_McNeel_Hatch_Library.pat`

### Automatic object routing

| Object type | Target layer |
|---|---|
| `TextEntity`, `TextDot` | `TEXT` |
| Dimensions and leaders | `ANNOTATIONS` |
| Hatch objects | `HATCH` |

The router does not move ordinary curves, points, surfaces, Breps, meshes, SubD objects, blocks or furniture geometry.

## Existing model safety

- The installer does **not** force existing documents into millimetres and does not reset their tolerances. Only the generated default template is explicitly set to mm.
- Current dimension style selection follows the document unit when the document is still using Rhino's built-in default style. A user-selected custom style is preserved.
- Existing layers and non-annotation object assignments are preserved. The package adds missing standard layers and definitions; it does not rename or delete user layers.
- Startup validates and reuses an existing valid template. It does not regenerate/replace that template on every Rhino launch. A template rebuild is explicit and retains the previous `.3dm` backup.

## Startup

Rhino General Options currently contains this startup command:

```text
_-RunPythonScript "C:\Users\krish\Documents\Inventaur\Rhino Standards\Inventaur_RhinoAutoLayer.py"
```

The entrypoint runs `Inventaur_RhinoStandards_Install.py`, registers the document/object event handlers, applies the standards to the active document, verifies/reuses the existing template, then explicitly calls `Rhino.RhinoApp.RunScript("_MCPStart", False)`. MCP startup is in a separate exception block so installer logging failures cannot skip it. The bootstrap uses `_INV_BOOTSTRAP_LOG_PATH` (not `log`) to avoid collision with the installer's `log()` function. Rhino's RhinoAI plugin remains the owner of its MCP listener and multi-instance port policy.

**Startup bug fixed 2026-11-15:** the previous entrypoint reused the variable name `log` for a path, but the installer defines a `log()` function in the same Python globals. This shadowed the path and caused a `TypeError` before the code reached `_MCPStart`. The entrypoint now uses a dedicated `_INV_BOOTSTRAP_LOG_PATH`. Manual execution of the exact entrypoint verified `STANDARDS_BOOTSTRAP_OK version=1.2.1` and `MCPSTART_RUNSCRIPT_RETURN=True`. The Rhino `_MCPStatus` command then returned `[RhinoAI] MCP server running on http://localhost:10500/`. A cold process restart after this exact fix remains pending to avoid interrupting the open model.

**Cold-start qualification:** the setting and script path are verified, the current Rhino session has v1.2.1 handlers loaded, and the MCP endpoint is reachable. A complete stop/start of the user's active Rhino process has deliberately not been performed during this cleanup because it would interrupt the open project. Verify the next normal Rhino restart using the bootstrap/standards log and `MCPStatus`; see `TODO.md`.

**Runtime compatibility 1.2.2 (2026-11-15):** corrected the startup failure `makedirs() got an unexpected keyword argument 'exist_ok'`. Both the startup entrypoint and installer now create directories without the Python 3-only `exist_ok` parameter, use `codecs.open` for encoded log/source I/O, and avoid `os.replace` and `datetime.isoformat(timespec=...)` in the installer. The entrypoint executes the installer code object through `eval` so the shared-globals execution form works across supported Python runtimes. The template build remains explicit; startup still validates and reuses the existing template. Source compilation and the exact Rhino-command regression are recorded in `verification_report_20261115.json`.

**1.2.2 live regression:** the exact entrypoint was invoked through Rhino's `_-RunPythonScript` command in the separate `test.3dm` Rhino session. The standards installer log records `EVENT_HANDLERS_INSTALLED version=1.2.2`, `APPLIED` with 49 layers / 59 hatches and `routed_existing=0`, followed by `TEMPLATE_REUSED_READBACK_OK`. The Rhino MCP endpoint remained responsive afterwards. The command wrapper timed out before a new `MCPSTART_RUNSCRIPT_RETURN` entry was recorded, so that final bootstrap step and a cold start in the affected user-model process remain open. The `test.3dm` document was not saved or closed.

## Package files

- `Inventaur_RhinoAutoLayer.py` — minimal Rhino startup entrypoint.
- `Inventaur_RhinoStandards_Install.py` — idempotent document standards installer and router.
- `Inventaur_RhinoAutoLayer_legacy_1_0.py` — preserved rollback copy of the earlier text/dimension-only router.
- `Inventaur_Architecture_MM.3dm` — validated default template.
- `Inventaur_Architecture_MM.3dm.previous` — retained prior-template rollback copy.
- `McNeel_Rhino_Hatch_Library.pat` — additional PAT source.
- `README.md`, `TODO.md`, `verification_report_20261115.json`, `manifest.json` — operating documentation and evidence.

## Verification

1. **Template persistence:** `File3dm.Read` and a fresh headless Rhino open both verified 44 layers, 14 Inventaur styles, 59 hatches, zero geometry objects, current style `INV_STD_MM` and current layer `04_ARCHITECTURE::GENERAL`.
2. **Live routing:** real disposable `TextEntity`, `LinearDimension` and Herringbone hatch objects were assigned to `TEXT`, `ANNOTATIONS` and `HATCH`. Each test object was deleted afterwards; the active document's enumerated object count returned to 16.
3. **Unit preservation:** a disposable inch-based document containing a 10-inch line remained in inches, and the line remained 10 inches, after standards application. `INV_STD_IN_DEC` was selected.
4. **Live document:** `test.3dm` received the standards additively (49 layers, 14 Inventaur styles, 59 hatches). Existing geometry was not modified or re-layered; its project file was not overwritten.
5. **MCP:** `http://localhost:10500/` is reachable in the current Rhino session.
6. **Mirrors:** all package files are SHA-256 identical in the Rhino runtime folder and IvyGPT canonical folder.

The working project was backed up before applying standards. The original source model was not overwritten. See `verification_report_20261115.json` for backup paths and exact verification results.

## Authority and maintenance

This folder is the standards package owner, not a task queue. `TODO.md` is an acceptance/maintenance checklist. Assignable work and task status remain in IvyGPT TaskBus `F:/ai/BOT/IvyGpt-SOLO/tasks/todo.sqlite`. The Automation Master Catalogue indexes this folder as `cad_rhino_standards`. The Rhino geometry/Grasshopper agent and Rhino-to-Solid-Edge exporter remain separate owners.

Update the runtime copy, mirror it to the canonical automation folder, refresh `manifest.json`, and verify hashes after any change.
