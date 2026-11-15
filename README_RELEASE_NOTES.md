# Release Notes - Inventaur Rhino3D to Solid Edge Automation

## 1.0.0-beta.3 - Full Offline Bootstrap Restoration

The beta.3 ZIP restores the complete offline bootstrap. It includes portable CPython 3.13.7 x64, a local wheelhouse containing `psutil` and `pywin32`, self-contained Solid Edge MCP control and event executables with their private .NET runtime files, and McNeel's Rhino MCP Platform 0.4.0 Yak package.

It also restores the stable `Scripts\Rhino3D_to_SolidEdge.bat` entry point. All batch files are BOM-free. The installer does not require system Python, Git, a .NET SDK/runtime or internet access for package installation.

Install: extract the full ZIP, run `INSTALL.bat`, restart Rhino, open the source model, execute `MCPStart` and `MCPConnect`, verify `run_python`, then launch `Scripts\Rhino3D_to_SolidEdge.bat`.


## Runtime prerequisites

- Windows 10/11 x64, Rhino 8.19+ or Rhino 9, and licensed Siemens Solid Edge 2023+ with COM automation registered and available. Solid Edge 2026 is the verified baseline.
- Rhino must be open with the intended .3dm active. Run MCPStart then MCPConnect; the connected AI/MCP client must expose run_python.
- The Rhino model must encode assemblies/subassemblies using nested block definitions and block instances. Leaf blocks hold reusable part geometry; use unique block names and an acyclic block hierarchy. Groups alone are insufficient.
