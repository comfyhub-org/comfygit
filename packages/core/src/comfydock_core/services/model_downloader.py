"""Model download service for fetching models from URLs."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import requests
from blake3 import blake3

from ..configs.model_config import ModelConfig
from ..logging.logging_config import get_logger
from ..models.shared import ModelWithLocation
from ..utils.model_categories import get_model_category

if TYPE_CHECKING:
    from ..repositories.model_repository import ModelRepository

logger = get_logger(__name__)


@dataclass
class DownloadRequest:
    """Request to download a model."""
    url: str
    target_path: Path  # Full path in global models directory
    workflow_name: str | None = None


@dataclass
class DownloadResult:
    """Result of a download operation."""
    success: bool
    model: ModelWithLocation | None = None
    error: str | None = None


class ModelDownloader:
    """Handles model downloads with hashing and indexing.

    Responsibilities:
    - Download files from URLs with progress tracking
    - Compute hashes (short + full blake3)
    - Register in ModelRepository
    - Detect URL type (civitai/HF/direct)
    """

    def __init__(self, model_repository: ModelRepository, models_dir: Path):
        """Initialize ModelDownloader.

        Args:
            model_repository: Repository for indexing models
            models_dir: Base models directory path
        """
        self.repository = model_repository
        self.models_dir = models_dir
        self.model_config = ModelConfig.load()

    def detect_url_type(self, url: str) -> str:
        """Detect source type from URL.

        Args:
            url: URL to analyze

        Returns:
            'civitai', 'huggingface', or 'custom'
        """
        url_lower = url.lower()

        if "civitai.com" in url_lower:
            return "civitai"
        elif "huggingface.co" in url_lower or "hf.co" in url_lower:
            return "huggingface"
        else:
            return "custom"

    def suggest_path(
        self,
        url: str,
        node_type: str | None = None,
        filename_hint: str | None = None
    ) -> Path:
        """Suggest download path based on context.

        For known nodes: checkpoints/model.safetensors
        For unknown: Uses filename hint or extracts from URL

        Args:
            url: Download URL
            node_type: Optional node type for category mapping
            filename_hint: Optional filename hint from workflow

        Returns:
            Suggested relative path (including base directory)
        """
        # Extract filename from URL or use hint
        filename = self._extract_filename(url, filename_hint)

        # If node type is known, map to directory
        if node_type and self.model_config.is_model_loader_node(node_type):
            directories = self.model_config.get_directories_for_node(node_type)
            base_dir = directories[0]  # e.g., "checkpoints"
            return Path(base_dir) / filename

        # Fallback: try to extract category from filename hint
        if filename_hint:
            category = get_model_category(filename_hint)
            return Path(category) / filename

        # Last resort: use generic models directory
        return Path("models") / filename

    def _extract_filename(self, url: str, filename_hint: str | None = None) -> str:
        """Extract filename from URL or use hint.

        Args:
            url: Download URL
            filename_hint: Optional filename from workflow

        Returns:
            Filename to use
        """
        # Try to extract from URL path
        parsed = urlparse(url)
        url_filename = Path(parsed.path).name

        # Use URL filename if it looks valid (has extension)
        if url_filename and '.' in url_filename:
            return url_filename

        # Fall back to hint
        if filename_hint:
            # Extract just the filename from hint path
            return Path(filename_hint).name

        # Last resort: generate generic name
        return "downloaded_model.safetensors"

    def download(
        self,
        request: DownloadRequest,
        progress_callback=None
    ) -> DownloadResult:
        """Download and index a model.

        Flow:
        1. Check if URL already downloaded
        2. Validate URL and target path
        3. Download to temp file with progress
        4. Hash during download (streaming)
        5. Move to target location
        6. Register in repository
        7. Add source URL

        Args:
            request: Download request with URL and target path
            progress_callback: Optional callback(bytes_downloaded, total_bytes) for progress updates.
                             total_bytes may be None if server doesn't provide Content-Length.

        Returns:
            DownloadResult with model or error
        """
        temp_path: Path | None = None
        try:
            # Step 1: Check if already downloaded
            existing = self.repository.find_by_source_url(request.url)
            if existing:
                logger.info(f"Model already downloaded from URL: {existing.relative_path}")
                return DownloadResult(success=True, model=existing)

            # Step 2: Validate target path
            request.target_path.parent.mkdir(parents=True, exist_ok=True)

            # Step 3-4: Download with streaming hash calculation
            logger.info(f"Downloading from {request.url}")
            response = requests.get(request.url, stream=True, timeout=300)
            response.raise_for_status()

            # Extract total size from headers (may be None)
            total_size = None
            if 'content-length' in response.headers:
                try:
                    total_size = int(response.headers['content-length'])
                except (ValueError, TypeError):
                    pass

            # Use temp file for atomic move
            with tempfile.NamedTemporaryFile(delete=False, dir=request.target_path.parent) as temp_file:
                temp_path = Path(temp_file.name)

                # Stream download with hash calculation
                hasher = blake3()
                file_size = 0

                chunk_size = 8192
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        temp_file.write(chunk)
                        hasher.update(chunk)
                        file_size += len(chunk)

                        if progress_callback:
                            progress_callback(file_size, total_size)

            # Step 5: Calculate short hash for indexing
            short_hash = self.repository.calculate_short_hash(temp_path)
            blake3_hash = hasher.hexdigest()

            # Step 6: Atomic move to final location
            temp_path.rename(request.target_path)

            # Step 7: Register in repository
            relative_path = request.target_path.relative_to(self.models_dir)
            mtime = request.target_path.stat().st_mtime

            self.repository.ensure_model(
                hash=short_hash,
                file_size=file_size,
                blake3_hash=blake3_hash
            )

            self.repository.add_location(
                model_hash=short_hash,
                relative_path=str(relative_path),
                filename=request.target_path.name,
                mtime=mtime
            )

            # Step 8: Add source URL
            source_type = self.detect_url_type(request.url)
            self.repository.add_source(
                model_hash=short_hash,
                source_type=source_type,
                source_url=request.url
            )

            # Step 9: Create result model
            model = ModelWithLocation(
                hash=short_hash,
                file_size=file_size,
                blake3_hash=blake3_hash,
                sha256_hash=None,
                relative_path=str(relative_path),
                filename=request.target_path.name,
                mtime=mtime,
                last_seen=int(mtime),
                metadata={}
            )

            logger.info(f"Successfully downloaded and indexed: {relative_path}")
            return DownloadResult(success=True, model=model)

        except Exception as e:
            error_msg = f"Download failed: {str(e)}"
            logger.error(error_msg)

            # Clean up temp file if it exists
            if temp_path is not None and temp_path.exists():
                temp_path.unlink()

            return DownloadResult(success=False, error=error_msg)
