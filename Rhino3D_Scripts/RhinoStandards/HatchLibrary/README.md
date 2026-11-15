# Rhino Hatch Library

File: McNeel_Rhino_Hatch_Library.pat

This is the consolidated Rhino 9 native hatch library: **59 unique hatch definitions**. It was exported from RhinoCommon HatchPattern.GetDefaultHatchPatterns(), merged with the six supplemental source definitions under their ordinary McNeel/Rhino names, then read back and imported into the active Rhino document hatch table.

The six supplemental definitions use standard names: Concrete, Concrete Reinforced, Earth, Granite, Herringbone and Sand. No Inventaur_ prefixes remain, and no duplicate pattern names were introduced.

## Verification

- RhinoCommon default source count: 59.
- Final PAT header count: 59.
- Unique names: 59.
- Supplemental definitions merged: 6, under their normal names.
- Import return: no newly added names were required because the 59 names were already in the document table.
- Document hatch table after import: 59.
- Missing names: 0.
- Document objects before/after: 0 / 0.

The full report is in Reports/hatch_library_export_20261115.json.
