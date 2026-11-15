# Official McNeel Rhino MCP payload

This folder contains the official Rhino-MCP-Platform Yak package `Rhino-MCP-Platform 0.4.0`, built from McNeel's official Yak-installed release package.

- Upstream: https://github.com/mcneel/RhinoAI
- Official documentation: https://mcneel.github.io/RhinoAI/
- Upstream revision: `28c20cbad300f4966d0fe08a4b59b1a44353ac5f`
- License: MIT; see the accompanying LICENSE.
- Yak distribution: `rhino-mcp-platform-0.4.0-rh8_19-win.yak` (Windows; Rhino 8.19+ / Rhino 9 package target)

The bootstrap installs this package using the Yak executable shipped with each detected Rhino installation. It does not modify or replace Rhino itself. Rhino must be restarted after installing/updating the package so the plugin and router staging are loaded.