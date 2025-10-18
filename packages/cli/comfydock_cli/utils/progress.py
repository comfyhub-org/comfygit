"""Progress display utilities for downloads."""

from typing import Callable

from comfydock_core.models.shared import ModelWithLocation
from comfydock_core.models.workflow import BatchDownloadCallbacks
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


def create_batch_download_callbacks() -> BatchDownloadCallbacks:
    """Create CLI callbacks for batch downloads with terminal output.

    Returns:
        BatchDownloadCallbacks configured for CLI rendering
    """
    def on_batch_start(count: int) -> None:
        print(f"\n⬇️  Downloading {count} model(s)...")

    def on_file_start(name: str, idx: int, total: int) -> None:
        print(f"\n[{idx}/{total}] {name}")

    def on_file_complete(name: str, success: bool, error: str | None) -> None:
        if success:
            print("  ✓ Complete")
        else:
            print(f"  ✗ Failed: {error}")

    def on_batch_complete(success: int, total: int) -> None:
        print(f"\n✅ Downloaded {success}/{total} models")

    return BatchDownloadCallbacks(
        on_batch_start=on_batch_start,
        on_file_start=on_file_start,
        on_file_progress=create_progress_callback(),
        on_file_complete=on_file_complete,
        on_batch_complete=on_batch_complete
    )
