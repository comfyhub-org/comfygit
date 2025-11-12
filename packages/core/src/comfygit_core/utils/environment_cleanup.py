"""Cross-platform environment directory cleanup utilities."""
import os
import platform
import shutil
import stat
import time
from pathlib import Path

from ..logging.logging_config import get_logger

logger = get_logger(__name__)

# Marker file indicating environment creation completed successfully
COMPLETION_MARKER = ".complete"


def _handle_remove_readonly(func, path, exc_info):
    """Handle Windows readonly/locked files during deletion.

    Args:
        func: Function that failed (e.g., os.unlink)
        path: Path that couldn't be removed
        exc_info: Exception info tuple
    """
    try:
        os.chmod(path, stat.S_IWRITE)
        time.sleep(0.05)  # Brief delay for handle release
        func(path)
    except Exception:
        pass  # Let rmtree handle final error


def remove_environment_directory(env_path: Path) -> None:
    """Remove environment directory with platform-specific handling.

    This handles Windows file locks and permission issues that commonly
    occur when Python processes or uv operations are interrupted.

    Args:
        env_path: Path to environment directory

    Raises:
        PermissionError: If deletion fails due to permissions
        OSError: If deletion fails for other reasons
    """
    if not env_path.exists():
        return

    try:
        if platform.system() == "Windows":
            shutil.rmtree(env_path, onexc=_handle_remove_readonly)
        else:
            shutil.rmtree(env_path)
        logger.debug(f"Removed environment directory: {env_path}")
    except PermissionError as e:
        raise PermissionError(
            f"Cannot delete '{env_path.name}': files may be in use. "
            f"Try closing applications using this environment."
        ) from e
    except OSError as e:
        raise OSError(f"Failed to delete environment '{env_path.name}': {e}") from e


def cleanup_partial_environment(env_path: Path) -> bool:
    """Clean up partial environment after creation failure.

    Uses platform-specific cleanup and provides user feedback on failure.

    Args:
        env_path: Path to partial environment directory

    Returns:
        True if cleanup succeeded, False if manual intervention needed
    """
    if not env_path.exists():
        return True

    logger.debug(f"Cleaning up partial environment at {env_path}")

    try:
        remove_environment_directory(env_path)
        return True
    except (PermissionError, OSError) as e:
        logger.warning(f"Failed to clean up partial environment: {e}")
        return False


def mark_environment_complete(cec_path: Path) -> None:
    """Mark environment as fully initialized.

    Creates a completion marker file that list_environments() uses to
    filter out partial/broken environments.

    Args:
        cec_path: Path to .cec directory
    """
    marker_file = cec_path / COMPLETION_MARKER
    marker_file.touch()
    logger.debug(f"Marked environment as complete: {marker_file}")


def is_environment_complete(cec_path: Path) -> bool:
    """Check if environment was fully initialized.

    Args:
        cec_path: Path to .cec directory

    Returns:
        True if environment has completion marker
    """
    return (cec_path / COMPLETION_MARKER).exists()
