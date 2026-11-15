# Inventaur Inc. - Project Identity

**Product:** Inventaur Inc. | Rhino3D to Solid Edge Automation  
**Creator and maintainer:** Krishna Parmar  
**Brand website:** https://inventaur.in  
**Release:** 1.0.0-beta.3 - Full Offline Bootstrap Package

The existing local development directory name is retained as `Rhino3D_to_SolidEdge_Workflow` to preserve continuity with existing workspace/registry references. First-party file/module names, product metadata, installer/launcher names and the distributable ZIP root use the Inventaur Inc. brand.

This project provides a deterministic, inspectable workflow for translating Rhino 3DM block structures into reusable native Solid Edge parts and assemblies.

## Naming and source ownership

- First-party product surfaces, installer names, package metadata, documentation and release archives use the Inventaur Inc. brand.
- First-party Python modules expose the `__company__`, `__author__` and `__product__` metadata constants. Functional identifiers remain descriptive and stable.
- Portable CPython 3.13.7 x64 is bundled under `Runtime/Python`; `psutil` and `pywin32` wheels are bundled under `Runtime/Wheels`. The recipient package does not require a separately installed Python runtime.
- Solid Edge MCP control/event servers are distributed as self-contained Windows x64 binaries under `Scripts/SOLIDEDGE-MCP/runtime/win-x64`. Their upstream namespaces and API names remain intact; third-party notices are retained.
- The official McNeel Rhino-MCP-Platform 0.4.0 Yak package is bundled under `ThirdParty/RhinoAI` and installed by the bootstrap using the Yak executable shipped with Rhino. It is a third-party product, not an Inventaur-authored plugin.
- Rhino and Solid Edge remain external licensed applications. Git and a .NET SDK/runtime are not required by recipients.

## Copyright and permissions

The project-wide licence for original workflow code remains undecided. See `LICENSE_PENDING.txt`. Do not describe the original workflow as open source or imply that public visibility grants redistribution or commercial-use rights. Third-party licences remain separate and continue to govern their respective components.
