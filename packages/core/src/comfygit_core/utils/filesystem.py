"""Filesystem manipulation utilities."""

import os
import shutil
from pathlib import Path

from ..logging.logging_config import get_logger

logger = get_logger(__name__)


def flatten_if_single_dir(path: Path) -> bool:
    """Flatten directory structure if it contains a single nested directory.

    Some archives contain: archive.tar.gz/NodeName-v1.0/*
    We want to flatten to just: NodeName/*

    Args:
        path: Path to check and potentially flatten

    Returns:
        True if flattened, False otherwise
    """
    try:
        contents = list(path.iterdir())

        # If there's exactly one directory and no files
        if len(contents) == 1 and contents[0].is_dir():
            single_dir = contents[0]

            logger.info(f"Flattening nested directory: {single_dir.name}")

            # Move all contents up one level
            for item in single_dir.iterdir():
                dest = path / item.name
                # Handle conflicts by removing destination first
                if dest.exists():
                    if dest.is_dir():
                        shutil.rmtree(dest)
                    else:
                        dest.unlink()
                shutil.move(str(item), str(dest))

            # Remove the now-empty nested directory
            single_dir.rmdir()
            return True

    except Exception as e:
        logger.warning(f"Could not flatten directory: {e}")

    return False


def ensure_clean_directory(path: Path) -> None:
    """Ensure a directory exists and is empty.

    Args:
        path: Directory path to prepare
    """
    if path.exists():
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()

    path.mkdir(parents=True, exist_ok=True)


def safe_copy_tree(src: Path, dest: Path) -> bool:
    """Safely copy a directory tree, handling existing destinations.

    Args:
        src: Source directory
        dest: Destination directory

    Returns:
        True if successful, False otherwise
    """
    try:
        # Remove destination if it exists
        if dest.exists():
            if dest.is_dir():
                shutil.rmtree(dest)
            else:
                dest.unlink()

        # Ensure parent directory exists
        dest.parent.mkdir(parents=True, exist_ok=True)

        # Copy the tree
        shutil.copytree(src, dest)
        return True

    except Exception as e:
        logger.error(f"Failed to copy {src} to {dest}: {e}")
        return False


def get_directory_size(path: Path) -> int:
    """Get total size of a directory in bytes.

    Args:
        path: Directory path

    Returns:
        Total size in bytes
    """
    if not path.exists() or not path.is_dir():
        return 0

    total_size = 0
    for item in path.rglob("*"):
        if item.is_file():
            total_size += item.stat().st_size

    return total_size


def find_file_in_tree(root: Path, filename: str) -> Path | None:
    """Find a file anywhere in a directory tree.

    Args:
        root: Root directory to search
        filename: Name of file to find

    Returns:
        Path to first matching file or None
    """
    for path in root.rglob(filename):
        if path.is_file():
            return path
    return None


def calculate_directory_size(path: Path) -> int:
    """Calculate total size of a directory tree in bytes.

    Args:
        path: Directory path to calculate size for

    Returns:
        Total size in bytes
    """
    total_size = 0
    try:
        for dirpath, dirnames, filenames in os.walk(path):
            for filename in filenames:
                filepath = Path(dirpath) / filename
                if filepath.exists():
                    total_size += filepath.stat().st_size
    except Exception as e:
        logger.warning(f"Could not calculate directory size: {e}")

    return total_size


def get_venv_python(env_path: Path) -> Path | None:
    """Get the Python executable path for a virtual environment.

    Cross-platform detection of Python executable in venv.

    Args:
        env_path: Path to the environment directory

    Returns:
        Path to Python executable or None if not found
    """
    # Try Unix/Linux/Mac path first
    venv_python = env_path / ".venv" / "bin" / "python"
    if venv_python.exists():
        return venv_python

    # Try Windows path
    venv_python = env_path / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        return venv_python

    return None
