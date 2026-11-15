> **Inventaur Inc.** - by **Krishna Parmar**

# Solid Edge MCP Bridge

This directory contains the first-party Inventaur Solid Edge MCP bridge used by the conversion workflow. The self-contained community MCP control/event servers are bundled under `runtime/win-x64` with their private .NET 8 runtime files.

## First-party components

- `inventaur_bridge_client.py`: lifecycle and authenticated calls to the local bridge.
- `inventaur_bridge_daemon.py`: loopback bridge owning one Solid Edge MCP stdio session and, when safe, an event MCP session.
- `inventaur_process_policy.py`: Windows process creation policy for hidden/background helpers.

The conversion runner uses this local bridge directly. It does not require a separate Inventaur orchestration service, hosted cloud API, API key or account sign-in.

## Security boundaries

- The bridge binds to `127.0.0.1` only.
- A random per-run token is stored in the run-owned bridge profile and sent in a custom local header.
- The runner provides a run-scoped LOCALAPPDATA profile so bridge state and logs remain isolated to the conversion run.
- Solid Edge control runs with `SE_MCP_FORCE_ISOLATED=1`. It must not attach to the user's unrelated foreground Solid Edge process.
- Read and write calls use separate allowlists. Arbitrary C# script execution is denied.
- A mutating call that times out has an unknown outcome. Reconcile document/process state before any retry.
- The event server is optional. It is enabled only after proving that it observes a unique temporary document opened by the owned Solid Edge session. If identity cannot be proven, event calls remain fenced.

## Recipient requirements

- Windows x64.
- Siemens Solid Edge installed with COM automation registered.
- Bundled CPython 3.13.7 x64 (`Runtime/Python`) and local `psutil`/`pywin32` wheels (`Runtime/Wheels`).
- A valid ISO Metric Part template. The workflow discovers it under Program Files or accepts `CAD_SOLID_EDGE_PART_TEMPLATE`.

Both MCP applications are self-contained .NET 8 x64 builds. No .NET runtime/SDK installation, Git source clone or recipient-side C# build is required.

The upstream C# projects reference Interop.SolidEdge 108.0.0 and the Model Context Protocol SDK. See `THIRD_PARTY_NOTICES.md` for dependency and licensing information.

## Developer-only rebuild

A developer may rebuild the MCP servers using the pinned upstream source and a compatible .NET 8 SDK. This is separate from recipient installation. The release builder includes the already-published binaries from `runtime/win-x64`.
