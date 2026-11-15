"""Inventaur Inc. | Regression checks for the full portable workflow package."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

__company__ = "Inventaur Inc."
__author__ = "Krishna Parmar"
__product__ = "Inventaur Rhino3D to Solid Edge Automation"
__version__ = "1.0.0-beta.3"

WORKFLOW = Path(__file__).resolve().parents[1]
SCRIPTS = WORKFLOW / "Scripts"
RUNNER_PATH = SCRIPTS / "inventaur_run_rhino3d_to_solidedge.py"
MCP_ROOT = SCRIPTS / "SOLIDEDGE-MCP"
RUNTIME = MCP_ROOT / "runtime" / "win-x64"


class PortableLauncherTests(unittest.TestCase):
    """Verify stable entry points, self-contained runtime assets and relocatable path resolution."""

    def test_runner_uses_invoking_python_and_sibling_mcp_root(self):
        """Runner uses invoking python and sibling mcp root."""
        spec = importlib.util.spec_from_file_location("portable_runner_test", RUNNER_PATH)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        self.assertEqual(module.PY, Path(sys.executable).resolve())
        self.assertEqual(module.SOLID_EDGE_MCP_ROOT, MCP_ROOT.resolve())
        self.assertTrue(module.SOLID_EDGE_MCP_ROOT.is_dir())

    def test_scripts_root_contains_entrypoint_both_launchers_and_bridge_sources(self):
        """Scripts root contains entrypoint both launchers and bridge sources."""
        self.assertTrue((SCRIPTS / "inventaur_rhino3d_to_solidedge.py").is_file())
        self.assertTrue((SCRIPTS / "Inventaur_Rhino3D_to_SolidEdge.bat").is_file())
        self.assertTrue((SCRIPTS / "Rhino3D_to_SolidEdge.bat").is_file())
        for name in ("inventaur_bridge_client.py", "inventaur_bridge_daemon.py", "inventaur_process_policy.py"):
            self.assertTrue((MCP_ROOT / name).is_file())

    def test_full_self_contained_runtime_assets_are_present(self):
        """Full self contained runtime assets are present."""
        for folder, executable in (("control", "solidedge-mcp.exe"), ("events", "solidedge-event-mcp.exe")):
            runtime_dir = RUNTIME / folder
            for name in (executable, "coreclr.dll", "hostfxr.dll", "hostpolicy.dll", "System.Private.CoreLib.dll"):
                self.assertTrue((runtime_dir / name).is_file(), f"Missing bundled runtime file: {runtime_dir / name}")

    def test_bundled_python_runtime_and_offline_wheelhouse_are_present(self):
        """Bundled CPython runtime and offline dependency wheels are present."""
        python_root = WORKFLOW / "Runtime" / "Python"
        self.assertTrue((python_root / "python.exe").is_file())
        self.assertTrue((python_root / "python313.dll").is_file())
        self.assertTrue((python_root / "Lib" / "venv" / "__init__.py").is_file())
        self.assertTrue((python_root / "Lib" / "ensurepip" / "__init__.py").is_file())
        wheels = WORKFLOW / "Runtime" / "Wheels"
        self.assertTrue((wheels / "psutil-7.2.2-cp37-abi3-win_amd64.whl").is_file())
        self.assertTrue((wheels / "pywin32-312-cp313-cp313-win_amd64.whl").is_file())

    def test_installer_verifies_bundled_runtime_and_installs_local_yak_package(self):
        """Installer verifies bundled runtime and installs local yak package."""
        installer = (WORKFLOW / "Inventaur_Install.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("solidedge-mcp.exe", installer)
        self.assertIn("solidedge-event-mcp.exe", installer)
        self.assertIn("YakPackage", installer)
        self.assertIn("yak install", installer.lower())
        self.assertIn("requirements.txt", installer)
        self.assertIn("Runtime\\Python", installer)
        self.assertIn("--no-index", installer)
        self.assertIn("Wheelhouse", installer)
        self.assertNotIn("Get-Command git.exe", installer)
        self.assertNotIn("dotnet-install.ps1", installer)
        self.assertTrue((WORKFLOW / "ThirdParty" / "RhinoAI" / "rhino-mcp-platform-0.4.0-rh8_19-win.yak").is_file())

    def test_bridge_client_and_daemon_resolve_paths_from_their_own_directory(self):
        """Bridge client and daemon resolve paths from their own directory."""
        sys.path.insert(0, str(MCP_ROOT))
        try:
            client_spec = importlib.util.spec_from_file_location("portable_bridge_client_test", MCP_ROOT / "inventaur_bridge_client.py")
            client = importlib.util.module_from_spec(client_spec)
            assert client_spec.loader is not None
            client_spec.loader.exec_module(client)
            self.assertEqual(client.ROOT, MCP_ROOT.resolve())
            self.assertEqual(client.DAEMON, MCP_ROOT / "inventaur_bridge_daemon.py")
            daemon_spec = importlib.util.spec_from_file_location("portable_bridge_daemon_test", MCP_ROOT / "inventaur_bridge_daemon.py")
            daemon = importlib.util.module_from_spec(daemon_spec)
            assert daemon_spec.loader is not None
            daemon_spec.loader.exec_module(daemon)
            self.assertEqual(daemon.ROOT, MCP_ROOT.resolve())
            self.assertEqual(daemon.MCP_EXE, RUNTIME / "control" / "solidedge-mcp.exe")
            self.assertEqual(daemon.EVENT_MCP_EXE, RUNTIME / "events" / "solidedge-event-mcp.exe")
        finally:
            try:
                sys.path.remove(str(MCP_ROOT))
            except ValueError:
                pass

    def test_bridge_cold_start_timeout_covers_self_contained_dotnet_startup(self):
        """Cold self-contained MCP startup gets a bounded 120-second readiness window."""
        source = (MCP_ROOT / "inventaur_bridge_client.py").read_text(encoding="utf-8")
        self.assertIn("START_TIMEOUT_SECONDS = 120", source)
        self.assertIn('"message": f"Bridge startup exceeded {START_TIMEOUT_SECONDS} seconds', source)

    def test_import_stage_has_no_fixed_repository_mcp_paths(self):
        """Import stage has no fixed repository mcp paths."""
        source = (SCRIPTS / "inventaur_import_step_parts_native_v2.py").read_text(encoding="utf-8")
        self.assertNotIn(r"X:\DeveloperWorkspace\PrivateRepo", source)
        self.assertIn('Path(__file__).resolve().parent / "SOLIDEDGE-MCP"', source)
        self.assertIn("exe=MCP_EXE", source)

    def test_branded_launcher_uses_venv_checks_runtime_and_has_no_bom(self):
        """Branded launcher uses venv checks runtime and has no bom."""
        launcher_path = SCRIPTS / "Inventaur_Rhino3D_to_SolidEdge.bat"
        raw = launcher_path.read_bytes()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"), "Windows batch file must be BOM-free")
        launcher = raw.decode("utf-8")
        self.assertIn(".venv", launcher)
        self.assertIn("python.exe", launcher)
        self.assertIn(r"runtime\win-x64", launcher)
        self.assertIn("WORKFLOW COMPLETED SUCCESSFULLY", launcher)
        self.assertIn("WORKFLOW FAILED", launcher)

    def test_legacy_launcher_preserves_original_filename_and_exit_code(self):
        """Legacy launcher preserves original filename and exit code."""
        path = SCRIPTS / "Rhino3D_to_SolidEdge.bat"
        raw = path.read_bytes()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"), "Legacy batch file must be BOM-free")
        source = raw.decode("utf-8")
        self.assertIn("Inventaur_Rhino3D_to_SolidEdge.bat", source)
        self.assertIn("call", source.lower())
        self.assertIn("%ERRORLEVEL%", source)

    def test_release_builder_preserves_full_runtime_and_yak_payload(self):
        """Release builder preserves full runtime and yak payload."""
        builder = (WORKFLOW / "tools" / "build_release.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("self-contained", builder.lower())
        self.assertIn("solidedge-mcp.exe", builder)
        self.assertIn("solidedge-event-mcp.exe", builder)
        self.assertIn("ThirdParty", builder)
        self.assertIn("Runtime", builder)
        self.assertIn("Runtime/Python", builder)
        self.assertIn("RhinoAI", builder)
        self.assertIn("runtime/win-x64", builder)
        self.assertIn("PACKAGE_MANIFEST.sha256", builder)

    def test_all_batch_entrypoints_are_bom_free(self):
        """All batch entrypoints are bom free."""
        for path in (WORKFLOW / "INSTALL.bat", SCRIPTS / "Rhino3D_to_SolidEdge.bat", SCRIPTS / "Inventaur_Rhino3D_to_SolidEdge.bat"):
            self.assertFalse(path.read_bytes().startswith(b"\xef\xbb\xbf"), str(path))


if __name__ == "__main__":
    unittest.main()
