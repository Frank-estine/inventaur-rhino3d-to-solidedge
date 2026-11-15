# Rhino Standards Installer

File: Inventaur_RhinoStandards_Install.py
Version: 1.3.2

Installs the shared Rhino metric architectural layers, annotation/text styles, hatch definitions and object-event routing. It also validates and reuses the default metric template.

## Runtime files

The runtime folder is resolved from the current user's Documents folder:
Documents/Inventaur/Rhino Standards

The installer expects the template and PAT file side-by-side with the runtime scripts.

## Hatch import

The installer adds Rhino's native defaults, then imports the PAT through rhinoscriptsyntax.AddHatchPatterns(PAT_PATH, True). It verifies the standard names Concrete, Concrete Reinforced, Earth, Granite, Herringbone and Sand. No Inventaur_ prefix is added to hatch names.

Version 1.3.2 fixes the order of the hatch verification code: expected hatch names are declared before the log formats their count. The runtime directory is resolved portably from the current user's home directory.

## Safety
- Existing document units and tolerances are preserved.
- Only explicit template generation sets millimetres.
- Existing geometry and ordinary geometry-layer assignments are preserved.
- User-selected custom dimension styles are preserved.
- Startup validates/reuses the template; it does not overwrite it.

Verify the installer log under %LOCALAPPDATA%/Inventaur/RhinoStandards/logs.
