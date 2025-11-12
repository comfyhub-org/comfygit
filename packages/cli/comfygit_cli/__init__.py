"""Command-line interface for ComfyUI environment detection."""

from importlib.metadata import version, PackageNotFoundError

from .cli import main

try:
    __version__ = version("comfygit")
except PackageNotFoundError:
    __version__ = "unknown"

__all__ = ['main', '__version__']
