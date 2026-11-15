# Rhino 9 Standards Package

The metric template, installer, AutoLayer entrypoint and hatch definitions are one shared Rhino standards system.

## Structure
- AutoLayer: Rhino startup entrypoint and TEXT / ANNOTATIONS / HATCH routing.
- Installer: idempotent document standards installer and template validator.
- Template: metric architectural template and previous-template rollback.
- HatchLibrary: PAT source and hatch import notes.
- Legacy: preserved v1.0 router and compatibility recovery copy.
- Reports: dated verification evidence.
- manifest.json and TODO.md: integrity inventory and maintenance checklist.

## Runtime deployment

The maintained source is structured here. The runtime copy remains flat for the existing Rhino startup configuration:

C:/Users/krish/Documents/Inventaur/Rhino Standards

Keep the AutoLayer entrypoint, installer, template and PAT file side-by-side in that runtime directory. The source package is structured for maintenance; the runtime layout remains flat for compatibility with the installed startup command.

## Standards baseline

The template baseline has 44 architectural layers, 14 persistent annotation/text styles, 59 Rhino-native hatch definitions and zero geometry objects. Text routes to TEXT, dimensions/leaders to ANNOTATIONS, and hatch objects to HATCH. Ordinary geometry is not moved.

## Hatch naming

The consolidated PAT contains 59 unique Rhino 9 native hatch definitions. Six supplemental definitions were merged under their ordinary names: Concrete, Concrete Reinforced, Earth, Granite, Herringbone and Sand. No Inventaur_ prefixes remain. The PAT was read back and imported into Rhino; the document table contained 59 names afterwards, with zero missing names and no geometry changes.

## Safety

Existing document units, tolerances, geometry and ordinary geometry layer assignments are preserved. Only explicit template generation sets millimetres. Startup validates and reuses a valid template; it does not rebuild it on every launch.
