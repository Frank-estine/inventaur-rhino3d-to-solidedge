# Inventaur Inc. - Rhino MCP Setup

**By Krishna Parmar**

The full bootstrap ZIP includes McNeel's official `Rhino-MCP-Platform 0.4.0` Windows Yak package under `ThirdParty\RhinoAI`.

## Automatic installation

Run `INSTALL.bat` from the extracted workflow package. The installer detects Rhino 8.19+ and Rhino 9 installations, calls each installation's own `System\Yak.exe`, installs the bundled local `.yak` package when version 0.4.0 is not already present, and verifies it through `yak list`.

If the plugin was installed or updated, restart Rhino before use. The installer does not close an open Rhino process.

## Manual installation / repair

Open PowerShell and run the Yak executable shipped with the target Rhino installation, passing the bundled package path:

```powershell
& 'C:\Program Files\Rhino 9\System\Yak.exe' install 'C:\Path\To\Extracted\Workflow\ThirdParty\RhinoAI\rhino-mcp-platform-0.4.0-rh8_19-win.yak'
```

Restart Rhino after installation.

## Connect

1. Open Rhino 8.19+ or Rhino 9.
2. Open the intended saved `.3dm` document.
3. Run `MCPStart`.
4. Run `MCPConnect`.
5. Verify that the connected MCP client exposes the document-scoped `run_python` tool.

The workflow discovers the active MCP connection at runtime. Do not hard-code an MCP port.

## Provenance

The bundled Yak package is McNeel's official Rhino MCP Platform 0.4.0 Windows package. Its MIT license and upstream metadata are retained in `ThirdParty\RhinoAI`.


## Conversion prerequisite

Keep Rhino open with the intended saved .3dm document active. Run MCPStart, then MCPConnect, and verify that the connected AI/MCP client exposes the document-scoped run_python tool. The installer does not create this live session.

The .3dm must encode the intended assembly hierarchy using nested Rhino block definitions and instances: parent blocks for assemblies/subassemblies and leaf blocks for reusable parts. Groups alone do not create native assembly structure. Block names must be unique after case/whitespace normalization and the hierarchy must not contain cycles.
