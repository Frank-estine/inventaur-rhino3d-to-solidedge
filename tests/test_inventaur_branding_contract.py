"""Inventaur Inc. | Static source-branding and documentation contracts for the public workflow.

These tests protect first-party module identity and docstring coverage while
keeping the separately attributed upstream Solid Edge implementation intact.
"""
from __future__ import annotations

__company__ = "Inventaur Inc."
__author__ = "Krishna Parmar"
__product__ = "Inventaur Rhino3D to Solid Edge Automation"
__version__ = "1.0.0-beta.3"


import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class InventaurBrandingContractTests(unittest.TestCase):
    """Protect the first-party naming, authorship and source-documentation contract."""

    def _first_party_python_files(self):
        """Return maintained Inventaur Python files without traversing the upstream vendor tree."""
        files = list(ROOT.glob("*.py"))
        files.extend(path for path in (ROOT / "Scripts").rglob("*.py") if "upstream" not in path.parts)
        files.extend((ROOT / "tests").rglob("*.py"))
        return sorted(set(files))

    def test_first_party_script_filenames_use_the_inventaur_prefix(self):
        """Verify that every first-party Python workflow script has a branded filename."""
        for folder in [ROOT / "Scripts", ROOT / "Scripts" / "SOLIDEDGE-MCP"]:
            for path in folder.glob("*.py"):
                self.assertTrue(
                    path.name.startswith("inventaur_"),
                    f"First-party script filename is not branded: {path.relative_to(ROOT)}",
                )

    def test_first_party_python_modules_declare_company_author_product_and_version(self):
        """Verify that every first-party Python module publishes consistent Inventaur ownership metadata."""
        for path in self._first_party_python_files():
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
            assignments = {
                target.id: node.value.value
                for node in ast.walk(tree)
                if isinstance(node, ast.Assign)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
                for target in node.targets
                if isinstance(target, ast.Name)
            }
            self.assertEqual(assignments.get("__company__"), "Inventaur Inc.", str(path))
            self.assertEqual(assignments.get("__author__"), "Krishna Parmar", str(path))
            self.assertEqual(assignments.get("__product__"), "Inventaur Rhino3D to Solid Edge Automation", str(path))
            self.assertEqual(assignments.get("__version__"), "1.0.0-beta.3", str(path))

    def test_release_dependencies_and_dotnet_targets_are_declared(self):
        """Verify the full bootstrap requirements and bundled self-contained .NET runtime contract."""
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("psutil", requirements)
        self.assertIn("pywin32", requirements)
        installer = (ROOT / "Inventaur_Install.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("Yak.exe", installer)
        self.assertIn("yak install", installer.lower())
        self.assertIn("Rhino-MCP-Platform", installer)
        self.assertIn("MCPStart", installer)
        self.assertIn("MCPConnect", installer)
        dependency_map = (ROOT / "DEPENDENCY_MAP.json").read_text(encoding="utf-8")
        self.assertIn("net8.0-windows", dependency_map)
        self.assertIn("self_contained", dependency_map)
        self.assertNotIn(".NET 10 SDK", dependency_map)
    def test_first_party_python_modules_classes_and_functions_have_docstrings(self):
        """Verify that maintained first-party Python modules, classes and functions are self-describing."""
        for path in self._first_party_python_files():
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            self.assertTrue(ast.get_docstring(tree), f"Missing module docstring: {path.relative_to(ROOT)}")
            for node in ast.walk(tree):
                if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    self.assertTrue(
                        ast.get_docstring(node),
                        f"Missing {type(node).__name__} docstring: {path.relative_to(ROOT)}:{node.lineno}:{node.name}",
                    )


if __name__ == "__main__":
    unittest.main()
