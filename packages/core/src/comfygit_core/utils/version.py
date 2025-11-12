"""Version comparison and PyTorch utilities."""

import re

from ..constants import PYTORCH_PACKAGE_NAMES


def is_pytorch_package(package_name: str, pytorch_packages: set[str] = PYTORCH_PACKAGE_NAMES) -> bool:
    """Check if a package is PyTorch-related."""
    package_lower = package_name.lower()

    # Check against known PyTorch packages (includes triton now)
    if package_lower in pytorch_packages:
        return True

    # Check for NVIDIA CUDA packages with cu11/cu12 suffix using regex
    # This matches current and future nvidia packages that end with -cu11 or -cu12
    if package_lower.startswith('nvidia-'):
        # Use regex to match nvidia-*-cu11 or nvidia-*-cu12 pattern
        if re.match(r'^nvidia-.*-cu(11|12)$', package_lower):
            return True
        # If it starts with nvidia but doesn't match the pattern, it's not a PyTorch package
        return False

    # Check for other PyTorch-related patterns
    # Note: 'triton' is now in the explicit set, but keeping for backward compatibility
    # Removed 'cuda' and 'cudnn' as standalone patterns to avoid false positives
    if 'torchtext' in package_lower or 'torchaudio' in package_lower:
        return True

    return False


def get_pytorch_index_url(torch_version: str, cuda_torch_version: str | None = None) -> str | None:
    """Determine the appropriate PyTorch index URL based on the installed torch version."""
    if not torch_version:
        return None

    # Parse the torch version to determine the index
    if '+cpu' in torch_version:
        return "https://download.pytorch.org/whl/cpu"

    # Extract CUDA version from torch version string
    cuda_match = re.search(r'\+cu(\d+)', torch_version)
    if cuda_match:
        cuda_ver = cuda_match.group(1)

        # Check if it's a nightly/dev version
        if 'dev' in torch_version or 'nightly' in torch_version:
            return f"https://download.pytorch.org/whl/nightly/cu{cuda_ver}"
        else:
            return f"https://download.pytorch.org/whl/cu{cuda_ver}"

    # Fallback: use the detected CUDA version
    if cuda_torch_version:
        # Remove dots from version (12.8 -> 128)
        cuda_ver = cuda_torch_version.replace('.', '')

        if 'dev' in torch_version or 'nightly' in torch_version:
            return f"https://download.pytorch.org/whl/nightly/cu{cuda_ver}"
        else:
            return f"https://download.pytorch.org/whl/cu{cuda_ver}"

    # If no CUDA info found, assume CPU
    return "https://download.pytorch.org/whl/cpu"


def normalize_package_name(package: str) -> str:
    """Normalize package name for comparison."""
    # Handle packages with extras like torch[cuda]
    if '[' in package:
        package = package.split('[')[0]
    return package.strip().lower()
