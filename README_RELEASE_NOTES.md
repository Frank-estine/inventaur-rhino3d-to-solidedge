# Release Notes - Inventaur Rhino3D to Solid Edge Automation

## 1.0.0-beta.3 - Full Offline Bootstrap Restoration

The beta.3 ZIP restores the complete offline bootstrap. It includes portable CPython 3.13.7 x64, a local wheelhouse containing `psutil` and `pywin32`, self-contained Solid Edge MCP control and event executables with their private .NET runtime files, and McNeel's Rhino MCP Platform 0.4.0 Yak package.

It also restores the stable `Scripts\Rhino3D_to_SolidEdge.bat` entry point. All batch files are BOM-free. The installer does not require system Python, Git, a .NET SDK/runtime or internet access for package installation.

Install: extract the full ZIP, run `INSTALL.bat`, restart Rhino, open the source model, execute `MCPStart` and `MCPConnect`, verify `run_python`, then launch `Scripts\Rhino3D_to_SolidEdge.bat`.
