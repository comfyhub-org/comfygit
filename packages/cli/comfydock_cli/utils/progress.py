"""Progress display utilities for downloads."""

from typing import Callable

from comfydock_core.models.shared import ModelWithLocation
from comfydock_core.utils.common import format_size


def create_progress_callback() -> Callable[[int, int | None], None]:
    """Create a reusable progress callback for model downloads.

    Returns:
        Callback function that displays download progress
    """
    def progress_callback(downloaded: int, total: int | None):
        """Display progress bar using carriage return."""
        downloaded_mb = downloaded / (1024 * 1024)
        if total:
            total_mb = total / (1024 * 1024)
            pct = (downloaded / total) * 100
            print(f"\rDownloading... {downloaded_mb:.1f} MB / {total_mb:.1f} MB ({pct:.0f}%)", end='', flush=True)
        else:
            print(f"\rDownloading... {downloaded_mb:.1f} MB", end='', flush=True)

    return progress_callback


def show_download_stats(model: ModelWithLocation | None) -> None:
    """Display statistics after successful download.

    Args:
        model: Downloaded and indexed model
    """
    if not model:
        return
    size_str = format_size(model.file_size)
    print(f"✓ Downloaded and indexed: {model.relative_path}")
    print(f"  Size: {size_str}")
    print(f"  Hash: {model.hash}")
