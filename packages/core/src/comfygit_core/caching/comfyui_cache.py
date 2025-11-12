"""ComfyUI version cache manager.

Caches ComfyUI installations by version to avoid re-downloading and re-cloning.
Supports releases, commits, and branches.
"""

from dataclasses import dataclass
from pathlib import Path

from .base import ContentCacheBase


@dataclass
class ComfyUISpec:
    """Specification for a ComfyUI version."""
    version: str              # "v0.3.20", "abc123", "main"
    version_type: str         # "release", "commit", "branch"
    commit_sha: str | None = None  # Actual commit SHA (for branches)


class ComfyUICacheManager(ContentCacheBase):
    """Cache manager for ComfyUI versions.

    Caches ComfyUI installations by version, including the .git directory
    for faster cloning and git operations.

    Cache structure:
        store/
            release_v0.3.20/
                content/        # Full ComfyUI directory with .git
                metadata.json   # version, type, commit_sha, size, hash
            commit_abc123/
                content/
                metadata.json
    """

    def __init__(self, cache_base_path: Path | None = None):
        """Initialize ComfyUI cache manager.

        Args:
            cache_base_path: Override cache base path (for testing)
        """
        super().__init__("comfyui", cache_base_path)

    def generate_cache_key(self, spec: ComfyUISpec | str) -> str:
        """Generate cache key from version specification.

        For releases: "release_v0.3.20"
        For commits: "commit_abc123"
        For branches: Use commit SHA for exact caching (branches can change)
        For simple strings: "version_{version}"

        Args:
            spec: ComfyUISpec or simple version string

        Returns:
            Cache key string
        """
        if isinstance(spec, str):
            # Simple string version
            return f"version_{spec}"

        # Use commit SHA for branches (they can change)
        if spec.version_type == "branch" and spec.commit_sha:
            return f"commit_{spec.commit_sha}"

        # For releases and commits, use the version
        return f"{spec.version_type}_{spec.version}"

    def cache_comfyui(self, spec: ComfyUISpec, source_path: Path) -> Path:
        """Cache a ComfyUI installation.

        Args:
            spec: ComfyUI version specification
            source_path: Path to ComfyUI installation (with .git)

        Returns:
            Path to cached content
        """
        cache_key = self.generate_cache_key(spec)

        metadata = {
            "version": spec.version,
            "version_type": spec.version_type,
            "commit_sha": spec.commit_sha
        }

        return self.cache_content(cache_key, source_path, metadata)

    def get_cached_comfyui(self, spec: ComfyUISpec | str) -> Path | None:
        """Get cached ComfyUI path if it exists.

        Args:
            spec: ComfyUISpec or simple version string

        Returns:
            Path to cached ComfyUI content, or None if not cached
        """
        cache_key = self.generate_cache_key(spec)
        return self.get_cached_path(cache_key)
