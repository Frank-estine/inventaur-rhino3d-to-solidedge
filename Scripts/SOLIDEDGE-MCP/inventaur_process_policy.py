"""Inventaur Inc. | Small self-contained process helpers for the packaged Solid Edge bridge."""
from __future__ import annotations

__company__ = "Inventaur Inc."
__author__ = "Krishna Parmar"
__product__ = "Inventaur Rhino3D to Solid Edge Automation"
__version__ = "1.0.0-beta.3"


import os
import subprocess
import sys
from pathlib import Path


def background_python() -> Path:
    """Use pythonw beside the active interpreter when available; otherwise use that interpreter."""
    current = Path(sys.executable).resolve()
    if os.name == "nt":
        candidate = current.with_name("pythonw.exe")
        if candidate.is_file():
            return candidate
    return current


def hidden_subprocess_kwargs() -> dict:
    """Hide bridge console windows while leaving GUI applications visible."""
    if os.name != "nt":
        return {}
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = subprocess.SW_HIDE
    return {
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
        "startupinfo": startup,
    }
