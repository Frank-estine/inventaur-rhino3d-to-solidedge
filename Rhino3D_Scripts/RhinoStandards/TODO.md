# Rhino 9 Standards — Maintenance Checklist

Package version: 1.3.2
Canonical source: CAD/rhino3d_automations/Rhino3D_Scripts/RhinoStandards/
Runtime mirror: %USERPROFILE%/Documents/Inventaur/Rhino Standards
Task authority: IvyGPT TaskBus. This file is a package checklist, not a task queue.

## Implemented and verified

- [x] Keep the metric architectural template, installer, AutoLayer entrypoint and hatch library together as one RhinoStandards package.
- [x] Keep reusable Rhino tools under CAD/rhino3d_automations/Rhino3D_Scripts/; project-specific modeling scripts remain in their project owners.
- [x] Give AutoLayer, Installer, Template, HatchLibrary and Legacy their own folders and README files; keep this package README as the component overview.
- [x] Preserve the validated metric template: 44 architectural layers, 14 persistent Inventaur annotation/text styles, 59 hatch definitions and zero geometry objects.
- [x] Preserve the normal layer routes: text/text dots to TEXT; dimensions/leaders to ANNOTATIONS; hatch objects to HATCH.
- [x] Preserve ordinary geometry and existing object-layer assignments.
- [x] Preserve existing document units/tolerances; millimetres are applied only during explicit template generation.
- [x] Validate and reuse the existing template on startup; do not rebuild it automatically.
- [x] Use portable current-user Documents paths in the startup entrypoint and installer.
- [x] Keep the runtime deployment flat because the existing Rhino startup command expects side-by-side script/resource files.
- [x] Generate one complete Rhino 9 PAT library from HatchPattern.GetDefaultHatchPatterns(): 59 unique definition headers.
- [x] Merge the six supplemental PAT definitions under normal Rhino/McNeel names; no Inventaur_ prefixes or duplicate aliases remain.
- [x] Read the final PAT back and verify 59 unique names.
- [x] Import the final PAT in Rhino; document hatch table remained at 59, with zero missing names and no document-object count change.
- [x] Correct the installer variable-order defect in ensure_hatches().
- [x] Correct template validation thresholds from 64 to the real Rhino 9 native hatch count of 59.
- [x] Run the 1.3.2 installer in a disposable headless Rhino document: 59 hatches, 44 layers, 14 styles, zero objects; existing template readback passed.
- [x] Execute the 1.3.2 startup entrypoint in the current Rhino process; logs confirm event handlers installed, standards applied and template reused.
- [x] Verify source/runtime hashes for the deployed startup scripts, template and PAT library.
- [x] Refresh this package manifest and reports.

## Remaining acceptance

- [ ] On the next normal Rhino cold start, verify the startup command runs automatically without manual script execution.
- [ ] In that fresh process, verify MCPStart, MCPStatus and active document event handlers.
- [ ] Create a new document through Rhino's normal New command and verify 44 layers, 14 styles, 59 hatches, INV_STD_MM and 04_ARCHITECTURE::GENERAL.
- [ ] Re-test new text, dimension and hatch routing after cold start.
- [ ] Confirm an existing non-millimetre document opens without unit conversion or tolerance reset.

The active Rhino process has intentionally not been closed during this package migration. Cold-start acceptance is therefore still pending.

## Maintenance rules

1. Do not rebuild or overwrite Inventaur_Architecture_MM.3dm during ordinary startup. Keep the .previous rollback copy.
2. Never force an existing user document into millimetres or reset its tolerances.
3. Do not move ordinary geometry or rename/delete user layers.
4. Retain the legacy AutoLayer script and previous template until a later release has its own verified rollback.
5. Keep the flat runtime mirror hash-identical to the active package resources; update manifest.json after changes.
6. Update CAD/README.md, rhino3d_automations/README.md and AUTOMATIONS_MASTER.md when package ownership or entrypoints change.

## Reports

- Reports/hatch_library_export_20261115.json — RhinoCommon export, 59-pattern PAT readback and document-table import.
- Reports/standards_headless_regression_20261115.json — disposable headless installer regression.
- Reports/verification_report_20261115.json — historical baseline, routing and unit-preservation evidence (version 1.2.2).
