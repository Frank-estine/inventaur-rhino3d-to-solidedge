# Rhino AutoLayer Startup Entrypoint

File: Inventaur_RhinoAutoLayer.py
Package: Rhino Standards 1.3.2

This is the startup entrypoint for the shared Rhino standards package. It loads the standards installer, registers document/object event handlers and calls RhinoAI MCPStart in a separate exception path.

## Routing
- TextEntity and TextDot -> TEXT
- Dimensions and leaders -> ANNOTATIONS
- Hatch objects -> HATCH
- Curves, points, surfaces, Breps, meshes, SubD, blocks and furniture geometry remain on their current layers.

This is not a semantic architectural layer classifier.

## Setup

Copy this script and the installer to the flat runtime folder:
C:/Users/krish/Documents/Inventaur/Rhino Standards

In Rhino 9 Options > General > Startup Commands, run the runtime Inventaur_RhinoAutoLayer.py through _-RunPythonScript.

## Verification

Bootstrap log:
%LOCALAPPDATA%/Inventaur/RhinoStandards/logs/Inventaur_RhinoBootstrap.log

Installer log:
%LOCALAPPDATA%/Inventaur/RhinoStandards/logs/Inventaur_RhinoStandards.log

Look for STANDARDS_BOOTSTRAP_OK version=1.3.2 and MCPSTART_RUNSCRIPT_RETURN=True. Verify the cold-start path and Rhino MCPStatus after a normal restart.

Dependencies: Rhino 9 for Windows, RhinoCommon and rhinoscriptsyntax.
