#!/usr/bin/env python3
"""Check version compatibility across workspace packages."""

import sys
from pathlib import Path
import tomllib

def get_version(pyproject_path):
    """Extract version from pyproject.toml."""
    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)
        return data["project"]["version"]

def parse_version(version):
    """Parse version string into (major, minor, patch)."""
    parts = version.split(".")
    return tuple(int(p) for p in parts)

def check_compatibility():
    """Check if all packages have compatible versions."""
    root = Path(__file__).parent.parent.parent

    packages = {
        "core": root / "packages/core/pyproject.toml",
        "cli": root / "packages/cli/pyproject.toml",
    }

    versions = {}
    for name, path in packages.items():
        if path.exists():
            versions[name] = get_version(path)
            print(f"{name:10} {versions[name]}")

    # Check major versions
    major_versions = set()
    for name, version in versions.items():
        major, _, _ = parse_version(version)
        major_versions.add(major)
    
    if len(major_versions) > 1:
        print("\n⚠️  WARNING: Packages have different major versions!")
        print("This may cause compatibility issues.")
        return False
    
    print("\n✅ All packages have compatible versions (same major version)")
    return True

if __name__ == "__main__":
    if not check_compatibility():
        sys.exit(1)