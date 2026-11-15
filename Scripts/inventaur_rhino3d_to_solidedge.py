#!/usr/bin/env python
"""Inventaur Inc. | Portable command-line entry point for the Rhino3D-to-Solid-Edge workflow.

This file deliberately contains no conversion logic. It resolves the runner
beside itself and executes it as __main__, keeping CLI behavior identical
whether invoked directly by Python or through the Windows batch launcher.
"""
__company__ = "Inventaur Inc."
__author__ = "Krishna Parmar"
__product__ = "Inventaur Rhino3D to Solid Edge Automation"
__version__ = "1.0.0-beta.3"
from pathlib import Path
import runpy

TARGET = Path(__file__).resolve().with_name("inventaur_run_rhino3d_to_solidedge.py")
if not TARGET.is_file():
    raise FileNotFoundError(f"Workflow runner missing: {TARGET}")
runpy.run_path(str(TARGET), run_name="__main__")
