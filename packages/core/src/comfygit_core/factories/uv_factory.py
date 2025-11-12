"""Factory utility for creating UV project manager instances with consistent configuration."""

from pathlib import Path

from ..integrations.uv_command import UVCommand
from ..managers.pyproject_manager import PyprojectManager
from ..managers.uv_project_manager import UVProjectManager


def create_uv_for_environment(
    workspace_path: Path,
    cec_path: Path | None = None,
    venv_path: Path | None = None,
    torch_backend: str | None = None,
) -> UVProjectManager:
    """Create a UV project manager configured for a specific environment.

    This factory ensures consistent UV configuration across the codebase.

    Args:
        workspace_path: Path to the workspace root
        cec_path: Path to the .cec directory (where pyproject.toml lives)
        venv_path: Path to the virtual environment
        torch_backend: PyTorch backend to use (auto, cpu, cu118, cu121, etc.)

    Returns:
        Configured UVProjectManager instance
    """
    # Workspace-level cache directories
    uv_cache_path, uv_python_path = get_uv_cache_paths(workspace_path)

    # Create UV command interface
    uv_command = UVCommand(
        project_env=venv_path,
        cache_dir=uv_cache_path,
        python_install_dir=uv_python_path,
        link_mode="hardlink",
        cwd=cec_path,
        torch_backend=torch_backend,
    )

    # Create PyprojectManager
    pyproject_path = cec_path / "pyproject.toml" if cec_path else Path.cwd() / "pyproject.toml"
    pyproject_manager = PyprojectManager(pyproject_path)

    # Create and return the project manager
    return UVProjectManager(uv_command, pyproject_manager)


def get_uv_cache_paths(workspace_path: Path) -> tuple[Path, Path]:
    """Get the standard UV cache paths for a workspace.

    Args:
        workspace_path: Path to the workspace root

    Returns:
        Tuple of (uv_cache_dir, uv_python_install_dir)
    """
    uv_cache_path = workspace_path / "uv_cache"
    uv_python_path = workspace_path / "uv" / "python"
    return uv_cache_path, uv_python_path
