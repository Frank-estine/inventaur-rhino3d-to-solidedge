# Third-Party Notices

**Product:** Inventaur Inc. - Rhino3D to Solid Edge Automation  
**First-party creator:** Krishna Parmar

Third-party names, namespaces, original source identities and copyright notices remain unchanged.

## Python runtime

- CPython 3.13.7 x64 is bundled under `Runtime/Python`.
- The Python Software Foundation license and third-party notices are distributed in `Runtime/Python/LICENSE.txt`.
- Official project: https://www.python.org/  
  License: Python Software Foundation License Version 2; see the bundled license file.

## Python wheels

- `psutil 7.2.2`: BSD 3-Clause License. The complete license is included inside `Runtime/Wheels/psutil-7.2.2-cp37-abi3-win_amd64.whl` at `psutil-7.2.2.dist-info/LICENSE`.
- `pywin32 312`: Python Software Foundation License. The wheel includes per-component license files under `pywin32-312.dist-info/licenses` and the relevant module license paths.
- Both wheels are included in the package and installed offline into the package-local `.venv`. They are not installed globally.

## Rhino MCP plugin

- Package: `Rhino-MCP-Platform 0.4.0` (`rhino-mcp-platform-0.4.0-rh8_19-win.yak`).
- Upstream: https://github.com/mcneel/RhinoAI
- Upstream revision: `28c20cbad300f4966d0fe08a4b59b1a44353ac5f`.
- License: MIT; the full license is included at `ThirdParty/RhinoAI/LICENSE`.
- The Yak file is bundled and installed locally by `INSTALL.bat` using the Yak executable distributed with Rhino. Supported target is Rhino 8.19+ / Rhino 9.

## SolidEdge-MCP Python upstream credit

- Project: [tylerwagler/SolidEdge-MCP](https://github.com/tylerwagler/SolidEdge-MCP).
- Author listed in upstream package metadata: Tyler Wagler.
- Credit: original Python Solid Edge MCP repository cloned during development of this workflow.
- License: MIT. The original upstream license is retained without modification at ThirdParty/SolidEdge-MCP/LICENSE; provenance is documented in ThirdParty/SolidEdge-MCP/UPSTREAM.md.
- The beta.3 offline package does not bundle this repository's Python MCP server source or Python server runtime. The repository is credited as upstream work and is not misrepresented as the source of the separate .NET applications below.

## Bundled .NET Solid Edge MCP control and event servers

- Project: [1337332551-dot/solidedge-mcp-server](https://github.com/1337332551-dot/solidedge-mcp-server).
- Role: separate source project for the self-contained .NET 8 Windows x64 control and event MCP applications bundled under Scripts/SOLIDEDGE-MCP/runtime/win-x64.
- License: MIT. The upstream license, including its original copyright notices, is retained at ThirdParty/DotNet/SolidEdge-MCP-Server-LICENSE.txt.
- This is an independent community implementation and is not an official Siemens MCP server.
- The Inventaur loopback bridge Python files under Scripts/SOLIDEDGE-MCP are first-party integration code.

## .NET runtime and managed dependencies

- Microsoft .NET 8 runtime files are distributed as part of the self-contained MCP applications.
- Microsoft license and third-party notice texts are included under `ThirdParty/DotNet`.
- Model Context Protocol packages and Microsoft.Extensions dependencies remain third-party components; see the included package license/notice records and `ThirdParty/DotNet/NUGET_PACKAGE_LICENSES.csv`.

## Solid Edge COM interop

- NuGet package: `Interop.SolidEdge 108.0.0`.
- Project: https://github.com/SolidEdgeCommunity/Interop.SolidEdge
- License: MIT; see `ThirdParty/DotNet/Interop.SolidEdge-LICENSE.md`.
- This package exposes COM type definitions; it is not Siemens-authored or Siemens-endorsed.

## Siemens trademarks and software

Solid Edge is a product and trademark of Siemens Digital Industries Software. Users must have a properly licensed Solid Edge installation. This project grants no rights to Siemens software, trademarks, interfaces or documentation and is not affiliated with or endorsed by Siemens.

## Inventaur first-party source

The original Inventaur workflow source is owned by its copyright holder. No project-wide license has been selected. The absence of a root license does not grant rights to modify, redistribute or commercially use the first-party source. See `LICENSE_PENDING.txt`.
