#!/usr/bin/env python
"""Inventaur Inc. developer entry point for Rhino3D-to-Solid-Edge automation.

Delegates to the canonical workflow supervisor without duplicating CLI logic.
"""
from pathlib import Path
import runpy

__company__ = "Inventaur Inc."
__author__ = "Krishna Parmar"
__product__ = "Inventaur Rhino3D to Solid Edge Automation"
__version__ = "1.0.0-beta.3"

TARGET = Path(__file__).resolve().parent / "Scripts" / "inventaur_run_rhino3d_to_solidedge.py"
if not TARGET.is_file():
    raise FileNotFoundError(f"Canonical Inventaur workflow supervisor missing: {TARGET}")
runpy.run_path(str(TARGET), run_name="__main__")
