"""Inventaur Inc. | Unit tests for host-independent Solid Edge installation discovery."""

__company__ = "Inventaur Inc."
__author__ = "Krishna Parmar"
__product__ = "Inventaur Rhino3D to Solid Edge Automation"
__version__ = "1.0.0-beta.3"

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Scripts"))

from inventaur_cad_environment import find_iso_metric_part_template


def make_template(root: Path, version: str) -> Path:
    """Create a temporary Solid Edge folder tree containing a synthetic part template."""
    path = root / "Siemens" / f"Solid Edge {version}" / "Template" / "ISO Metric" / "iso metric part.par"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"template")
    return path


def test_discovers_highest_installed_version(tmp_path):
    """Verify that discovers highest installed version."""
    older = make_template(tmp_path, "2024")
    newer = make_template(tmp_path, "2026")
    assert find_iso_metric_part_template(program_files_roots=[tmp_path]) == newer.resolve()
    assert older.exists()


def test_explicit_template_overrides_discovery(tmp_path):
    """Verify that explicit template overrides discovery."""
    explicit = tmp_path / "custom" / "metric.par"
    explicit.parent.mkdir()
    explicit.write_bytes(b"custom")
    make_template(tmp_path, "2026")
    assert find_iso_metric_part_template(explicit=explicit, program_files_roots=[tmp_path]) == explicit.resolve()


def test_missing_template_has_actionable_error(tmp_path):
    """Verify that missing template has actionable error."""
    try:
        find_iso_metric_part_template(program_files_roots=[tmp_path])
    except FileNotFoundError as exc:
        assert "CAD_SOLID_EDGE_PART_TEMPLATE" in str(exc)
    else:
        raise AssertionError("Expected missing-template error")


def test_invalid_explicit_template_is_not_silently_ignored(tmp_path):
    """Verify that invalid explicit template is not silently ignored."""
    try:
        find_iso_metric_part_template(explicit=tmp_path / "missing.par", program_files_roots=[])
    except FileNotFoundError as exc:
        assert "does not exist" in str(exc)
    else:
        raise AssertionError("Expected explicit override validation error")
