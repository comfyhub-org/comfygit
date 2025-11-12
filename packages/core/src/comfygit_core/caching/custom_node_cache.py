"""Custom node cache manager for storing and retrieving downloaded nodes."""

import hashlib
import json
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from comfygit_core.models.shared import NodeInfo

from ..logging.logging_config import get_logger
from ..utils.common import format_size
from .base import ContentCacheBase

logger = get_logger(__name__)


@dataclass
class CachedNodeInfo:
    """Information about a cached custom node."""

    cache_key: str
    name: str
    install_method: str
    url: str
    ref: str | None = None
    cached_at: str = ""
    last_accessed: str = ""
    access_count: int = 0
    size_bytes: int = 0
    content_hash: str | None = None
    source_info: dict | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "CachedNodeInfo":
        """Create from dictionary."""
        return cls(**data)


class CustomNodeCacheManager(ContentCacheBase):
    """Manages caching of custom node downloads."""

    def __init__(self, cache_base_path: Path | None = None):
        """Initialize the cache manager.

        Args:
            cache_base_path: Base path for cache storage (defaults to platform-specific location)
        """
        super().__init__("custom_nodes", cache_base_path)
        self.lock_file = self.cache_dir / ".lock"

        # Load node-specific index
        self.node_index = self._load_node_index()

    def _load_node_index(self) -> dict[str, CachedNodeInfo]:
        """Load the node-specific cache index from disk."""
        if not self.index_file.exists():
            return {}

        try:
            with open(self.index_file, encoding='utf-8') as f:
                data = json.load(f)

            # Convert to CachedNodeInfo objects
            index = {}
            for key, info_dict in data.get("nodes", {}).items():
                try:
                    index[key] = CachedNodeInfo.from_dict(info_dict)
                except Exception as e:
                    logger.warning(f"Failed to load cache entry {key}: {e}")

            return index

        except Exception as e:
            logger.error(f"Failed to load cache index: {e}")
            return {}

    def _save_node_index(self):
        """Save the node-specific cache index to disk."""
        try:
            # Convert to serializable format
            data = {
                "version": "1.0",
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "nodes": {k: v.to_dict() for k, v in self.node_index.items()},
            }

            # Write atomically
            temp_file = self.index_file.with_suffix(".tmp")
            with open(temp_file, "w", encoding='utf-8') as f:
                json.dump(data, f, indent=2)

            # Replace original
            temp_file.replace(self.index_file)

        except Exception as e:
            logger.error(f"Failed to save cache index: {e}")

    def generate_cache_key(self, node_info: NodeInfo) -> str:
        """Generate a unique cache key for a custom node.

        The key is based on:
        - URL
        - Ref (for git repos)
        - Install method
        """
        # Only add component of node info if not None
        components = [info for info in node_info.__dict__.values() if info is not None]
        key_string = "|".join(components)
        return hashlib.sha256(key_string.encode()).hexdigest()[:16]

    def is_cached(self, node_info: NodeInfo) -> bool:
        """Check if a custom node is already cached."""
        cache_key = self.generate_cache_key(node_info)

        # Check index
        if cache_key not in self.node_index:
            return False

        # Verify the actual files exist
        cache_dir = self.store_dir / cache_key
        content_dir = cache_dir / "content"

        return content_dir.exists() and any(content_dir.iterdir())

    def get_cached_path(self, node_info: NodeInfo) -> Path | None:
        """Get the path to cached node content if it exists.

        Returns:
            Path to the cached content directory, or None if not cached
        """
        logger.info(f"Checking if '{node_info.name}' is cached...")
        if not self.is_cached(node_info):
            logger.info(f"'{node_info.name}' is not cached.")
            return None

        cache_key = self.generate_cache_key(node_info)
        content_path = self.store_dir / cache_key / "content"

        logger.debug(f"Generated cached path for '{node_info.name}': {content_path}")

        # Update access time and count
        if cache_key in self.node_index:
            self.node_index[cache_key].last_accessed = datetime.now(timezone.utc).isoformat()
            self.node_index[cache_key].access_count += 1
            self._save_node_index()

        return content_path

    def cache_node(
        self,
        node_info: NodeInfo,
        source_path: Path,
        archive_path: Path | None = None,
    ) -> Path:
        """Cache a custom node from a source directory.

        Args:
            node_info: The node specification
            source_path: Path to the extracted node content
            archive_path: Optional path to the original archive

        Returns:
            Path to the cached content
        """
        cache_key = self.generate_cache_key(node_info)
        logger.info(f"Caching custom node: {node_info.name}")

        # Build metadata for base class
        metadata = {
            "node_spec": asdict(node_info),
            "has_archive": archive_path is not None,
        }

        # Use base class cache_content method
        content_dir = self.cache_content(cache_key, source_path, metadata)

        # Copy archive if provided
        if archive_path and archive_path.exists():
            cache_dir = self.store_dir / cache_key
            archive_dest = cache_dir / "archive"
            shutil.copy2(archive_path, archive_dest)

        # Get size and hash from base class
        cache_dir = self.store_dir / cache_key
        metadata_file = cache_dir / "metadata.json"
        with open(metadata_file, encoding='utf-8') as f:
            full_metadata = json.load(f)

        # Update node-specific index
        self.node_index[cache_key] = CachedNodeInfo(
            cache_key=cache_key,
            name=node_info.name,
            install_method=node_info.source,
            url=node_info.download_url or node_info.repository or "",
            ref=node_info.version,
            cached_at=full_metadata["cached_at"],
            last_accessed=full_metadata["cached_at"],
            access_count=1,
            size_bytes=full_metadata["size_bytes"],
            content_hash=full_metadata["content_hash"],
            source_info=full_metadata,
        )

        self._save_node_index()
        logger.info(
            f"Cached {node_info.name} ({format_size(full_metadata['size_bytes'])}) with key: {cache_key}"
        )

        return content_dir

    def copy_from_cache(self, node_info: NodeInfo, dest_path: Path) -> bool:
        """Copy a cached node to a destination.

        Args:
            node_spec: The node specification
            dest_path: Destination path for the node

        Returns:
            True if successfully copied, False otherwise
        """
        cached_path = self.get_cached_path(node_info)
        if not cached_path:
            return False

        try:
            # Ensure destination parent exists
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            # Remove destination if it exists
            if dest_path.exists():
                shutil.rmtree(dest_path)

            # Check if cached content has a single root directory that matches a pattern
            # This handles cases like "ComfyUI-Manager-3.35" inside the cache
            cached_items = list(cached_path.iterdir())

            if len(cached_items) == 1 and cached_items[0].is_dir():
                # Single directory - check if it's a versioned directory name
                single_dir = cached_items[0]
                dir_name = single_dir.name

                # Check if this looks like a versioned directory (e.g., "ComfyUI-Manager-3.35")
                # that should be flattened when copying
                base_name = node_info.name
                if dir_name.startswith(base_name) and dir_name != base_name:
                    # This is likely a versioned directory that should be flattened
                    logger.info(
                        f"Flattening nested directory {dir_name} when copying {node_info.name} from cache"
                    )
                    shutil.copytree(single_dir, dest_path)
                    return True

            # Normal copy - preserve structure
            logger.info(f"Copying {node_info.name} from cache to {dest_path}")
            shutil.copytree(cached_path, dest_path)

            return True

        except Exception as e:
            logger.error(f"Failed to copy from cache: {e}")
            return False

    def verify_cache_integrity(self, cache_key: str) -> bool:
        """Verify the integrity of a cached node."""
        if cache_key not in self.node_index:
            return False

        cache_dir = self.store_dir / cache_key
        content_dir = cache_dir / "content"

        if not content_dir.exists():
            return False

        # Recalculate hash using base class method
        current_hash = self._calculate_content_hash(content_dir)
        stored_hash = self.node_index[cache_key].content_hash

        return current_hash == stored_hash

    def clear_cache(self, node_name: str | None = None) -> int:
        """Clear cache entries.

        Args:
            node_name: Specific node name to clear, or None to clear all

        Returns:
            Number of entries cleared
        """
        cleared = 0

        if node_name:
            # Clear specific node
            entries_to_clear = [
                (k, v) for k, v in self.node_index.items() if v.name == node_name
            ]
        else:
            # Clear all
            entries_to_clear = list(self.node_index.items())

        for cache_key, _ in entries_to_clear:
            cache_dir = self.store_dir / cache_key
            if cache_dir.exists():
                shutil.rmtree(cache_dir)

            del self.node_index[cache_key]
            cleared += 1

        self._save_node_index()

        return cleared

    def list_cached_nodes(self) -> list[CachedNodeInfo]:
        """Get a list of all cached nodes."""
        return list(self.node_index.values())
