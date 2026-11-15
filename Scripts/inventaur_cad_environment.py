"""Inventaur Inc. | Portable discovery of the Solid Edge templates required by the workflow.

The workflow avoids assuming one drive, one Windows architecture, or one
year-specific Solid Edge installation. Operators can override discovery with
CAD_SOLID_EDGE_PART_TEMPLATE.
"""
from __future__ import annotations
__company__ = "Inventaur Inc."
__author__ = "Krishna Parmar"
__product__ = "Inventaur Rhino3D to Solid Edge Automation"
__version__ = "1.0.0-beta.3"

import os
import re
from pathlib import Path
from typing import Iterable


def _version_key(path: Path) -> tuple[int, ...]:
    """Extract numeric version components so the newest installation sorts first."""
    match = re.search(r"Solid Edge\s+(.*)$", path.parents[2].name, re.IGNORECASE)
    return tuple(int(value) for value in re.findall(r"\d+", match.group(1))) if match else (0,)


def find_iso_metric_part_template(
    explicit: str | os.PathLike[str] | None = None,
    program_files_roots: Iterable[str | os.PathLike[str]] | None = None,
) -> Path:
    """Locate the installed ISO Metric Part template or raise an actionable error.

    Resolution order: explicit run configuration, environment override, then
    installed Siemens Solid Edge folders under Program Files.
    """
    configured = explicit or os.environ.get("CAD_SOLID_EDGE_PART_TEMPLATE")
    if configured:
        candidate = Path(configured).expanduser().resolve()
        if not candidate.is_file():
            raise FileNotFoundError(
                "Configured Solid Edge ISO Metric Part template does not exist: "
                f"{candidate}. Set CAD_SOLID_EDGE_PART_TEMPLATE to a valid .par template."
            )
        return candidate

    roots = list(program_files_roots or [])
    if not roots:
        for variable in ("ProgramFiles", "ProgramFiles(x86)"):
            value = os.environ.get(variable)
            if value and value not in roots:
                roots.append(value)

    candidates: list[Path] = []
    for root in roots:
        siemens = Path(root).expanduser() / "Siemens"
        if not siemens.is_dir():
            continue
        candidates.extend(
            path.resolve()
            for path in siemens.glob("Solid Edge */Template/ISO Metric/iso metric part.par")
            if path.is_file()
        )

    if not candidates:
        searched = ", ".join(str(Path(root) / "Siemens") for root in roots) or "Program Files"
        raise FileNotFoundError(
            "No Solid Edge ISO Metric Part template was found. Searched: "
            f"{searched}. Set CAD_SOLID_EDGE_PART_TEMPLATE to the full path of "
            "your installed 'iso metric part.par' template."
        )

    return max(candidates, key=_version_key)
