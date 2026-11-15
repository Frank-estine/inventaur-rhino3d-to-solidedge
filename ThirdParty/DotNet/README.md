# Inventaur Inc. — Bundled .NET Dependency Notices

This folder accompanies the two self-contained Solid Edge MCP executables shipped by the Inventaur workflow.

- NUGET_PACKAGE_LICENSES.csv inventories the 40 distinct direct and transitive NuGet package identities resolved by the two upstream C# projects, including version, license expression or URL, and copied notice files.
- Package-Licenses contains license and third-party notice files obtained from the corresponding package distributions. Identical notice files are stored once.
- Apache-2.0.txt is the Apache License 2.0 text for the Model Context Protocol .NET SDK.
- Interop.SolidEdge-LICENSE.md is the MIT license supplied by Solid Edge Community for Interop.SolidEdge 108.0.0.
- Microsoft-DotNet-LICENSE.txt and Microsoft-DotNet-ThirdPartyNotices.txt are from the .NET 8 SDK distribution used to build the self-contained executables. Retain them with this package's runtime notices.

The bundled .NET Solid Edge MCP control/event applications come from https://github.com/1337332551-dot/solidedge-mcp-server; its upstream MIT license is retained in SolidEdge-MCP-Server-LICENSE.txt. The separate Tyler Wagler Python SolidEdge-MCP upstream project is credited, with its original MIT license, under ThirdParty/SolidEdge-MCP. The McNeel Rhino MCP package keeps its separate MIT license at ThirdParty/RhinoAI/LICENSE. Python and pywin32 notices are carried within Runtime/Python.

This inventory is an engineering notice package, not a legal opinion. Verify the applicable redistribution conditions for all compiled and transitive components before public or commercial distribution.
