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

## Solid Edge MCP upstream and runtime

- Project: https://github.com/1337332551-dot/solidedge-mcp-server
- Integration: compiled Solid Edge MCP control and event applications are bundled under `Scripts/SOLIDEDGE-MCP/runtime/win-x64`.
- The applications are self-contained .NET 8 Windows x64 builds; no recipient-side .NET SDK/runtime installation or source compilation is required.
- The upstream project license and required third-party notices are included under `ThirdParty/DotNet` where available. The integration is independent and is not an official Siemens MCP.

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
