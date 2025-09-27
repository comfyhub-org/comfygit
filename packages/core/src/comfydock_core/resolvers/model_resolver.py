"""ModelResolver - Resolve model requirements for environment import/export."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, List

from ..logging.logging_config import get_logger
from ..models.workflow import (
    WorkflowNodeWidgetRef,
    WorkflowNode,
    ModelResolutionResult,
    NodeResolutionResult,
    WorkflowDependencies,
)
from ..configs.model_config import ModelConfig

if TYPE_CHECKING:
    from ..managers.pyproject_manager import PyprojectManager
    from ..repositories.model_repository import ModelRepository
    from ..models.shared import ModelWithLocation

logger = get_logger(__name__)


class ModelResolver:
    """Resolve model requirements for environments using multiple strategies."""

    def __init__(
        self,
        model_repository: ModelRepository,
        pyproject_manager: PyprojectManager,
        model_config: ModelConfig | None = None, 
        download_manager=None,
    ):
        """Initialize ModelResolver.

        Args:
            index_manager: ModelIndexManager for lookups
            download_manager: Optional ModelDownloadManager for downloading
        """
        self.model_repository = model_repository
        self.model_config = model_config or ModelConfig.load()
        self.pyproject = pyproject_manager
        self.download_manager = download_manager

    def resolve_model(self, ref: WorkflowNodeWidgetRef, workflow_name: str) -> ModelResolutionResult | None:
        """Try multiple resolution strategies"""
        widget_value = ref.widget_value

        # Strategy 0: Check existing pyproject model data first
        pyproject_result = self._try_pyproject_resolution(workflow_name, ref)
        if pyproject_result:
            logger.debug(f"Resolved {ref} to {pyproject_result.resolved_model} from pyproject.toml")
            return pyproject_result

        # Strategy 1: Exact path match
        candidates = self._try_exact_match(widget_value)
        if len(candidates) == 1:
            logger.debug(f"Resolved {ref} to {candidates[0]} as exact match")
            return ModelResolutionResult(
                reference=ref,
                candidates=candidates,
                resolution_type="exact",
                resolved_model=candidates[0],
                resolution_confidence=1.0,
            )

        # Strategy 2: Reconstruct paths for native loaders
        if self.model_config.is_model_loader_node(ref.node_type):
            paths = self.model_config.reconstruct_model_path(ref.node_type, widget_value)
            for path in paths:
                candidates = self._try_exact_match(path)
                if len(candidates) == 1:
                    logger.debug(f"Resolved {ref} to {candidates[0]} as reconstructed match")
                    return ModelResolutionResult(
                        reference=ref,
                        candidates=candidates,
                        resolution_type="reconstructed",
                        resolved_model=candidates[0],
                        resolution_confidence=0.9,
                    )

        # Strategy 3: Case-insensitive match
        candidates = self._try_case_insensitive_match(widget_value)
        if len(candidates) == 1:
            logger.debug(f"Resolved {ref} to {candidates[0]} as case-insensitive match")
            return ModelResolutionResult(
                reference=ref,
                candidates=candidates,
                resolution_type="case_insensitive",
                resolved_model=candidates[0],
                resolution_confidence=0.8,
            )

        # Strategy 4: Filename-only match
        filename = Path(widget_value).name
        candidates = self.model_repository.find_by_filename(filename)
        if len(candidates) == 1:
            logger.debug(f"Resolved {ref} to {candidates[0]} as filename-only match")
            return ModelResolutionResult(
                reference=ref,
                candidates=candidates,
                resolution_type="filename",
                resolved_model=candidates[0],
                resolution_confidence=0.7,
            )
        elif len(candidates) > 1:
            # Multiple matches - need disambiguation
            logger.debug(f"Resolved {ref} to {candidates} as filename-only match, ambiguous")
            return ModelResolutionResult(
                reference=ref,
                candidates=candidates,
                resolution_type="ambiguous",
                resolved_model=None,
                resolution_confidence=0.0,
            )

        # No matches found
        logger.debug(f"No matches found in pyproject or model index for {ref}")
        return None

    def _try_exact_match(self, path: str) -> List["ModelWithLocation"]:
        """Try exact path match"""
        all_models = self.model_repository.get_all_models()
        return [m for m in all_models if m.relative_path == path]

    def _try_case_insensitive_match(self, path: str) -> List["ModelWithLocation"]:
        """Try case-insensitive path match"""
        all_models = self.model_repository.get_all_models()
        path_lower = path.lower()
        return [m for m in all_models if m.relative_path.lower() == path_lower]

    def _looks_like_model(self, value: Any) -> bool:
        """Check if value looks like a model path"""
        if not isinstance(value, str):
            return False
        extensions = self.model_config.default_extensions
        return any(value.endswith(ext) for ext in extensions)

    def _try_pyproject_resolution(self, workflow_name: str, ref: "WorkflowNodeWidgetRef") -> "ModelResolutionResult | None":
        """Try to resolve using existing model data in pyproject.toml if valid"""
        # No pyproject manager available, can't check existing resolutions
        if not self.pyproject:
            return None

        try:
            # Load the pyproject config
            config = self.pyproject.load()

            # Navigate to tool.comfydock.workflows section
            workflows = config.get('tool', {}).get('comfydock', {}).get('workflows', {})

            # Check if this workflow has entries
            workflow_entry = workflows.get(workflow_name, {})
            if not workflow_entry:
                return None

            # Get model mappings for this workflow
            models_section = workflow_entry.get('models', {})
            if not models_section:
                return None

            # Search through all model entries for matching node_id and widget_idx
            for model_hash, model_data in models_section.items():
                nodes = model_data.get('nodes', [])

                # Check if this node_id and widget_index combination exists
                for node_entry in nodes:
                    if (node_entry.get('node_id') == ref.node_id and
                        node_entry.get('widget_idx') == ref.widget_index):

                        # Found a match! Now verify the model still exists in the index
                        models = self.model_repository.find_model_by_hash(model_hash)
                        if models and len(models) > 0:
                            # Valid existing resolution - use it
                            model = models[0]
                            logger.debug(f"Resolved from pyproject: {ref.widget_value} -> {model_hash[:8]}...")
                            return ModelResolutionResult(
                                reference=ref,
                                candidates=models,
                                resolution_type="pyproject",
                                resolved_model=model,
                                resolution_confidence=1.0,
                            )
                        else:
                            # Hash no longer valid in index, need fresh resolution
                            logger.debug(f"Pyproject hash {model_hash[:8]}... no longer in index for {ref.widget_value}")
                            return None

            # No matching node_id/widget_idx combination found
            return None

        except Exception as e:
            logger.debug(f"Error checking pyproject resolution: {e}")
            return None

    # def resolve_with_downloads(self, manifest: dict, auto_download: bool = False) -> ResolutionResult:
    #     """Resolve models with automatic downloading of missing models.
        
    #     Args:
    #         manifest: Model manifest to resolve
    #         auto_download: Automatically download missing models
            
    #     Returns:
    #         ResolutionResult with download attempts included
    #     """
    #     if not self.download_manager:
    #         logger.warning("No download manager available - skipping downloads")
    #         return self.resolve_models(manifest)

    #     # First pass: standard resolution
    #     result = self.resolve_models(manifest)

    #     if not result.downloadable:
    #         return result

    #     logger.info(f"Found {len(result.downloadable)} downloadable models")

    #     # Download missing models
    #     for short_hash, model_spec in result.downloadable.copy().items():
    #         sources = model_spec.get('sources', [])
    #         if not sources:
    #             continue

    #         if auto_download:
    #             success = self._attempt_download(short_hash, sources, result)
    #             if success:
    #                 # Move from downloadable to resolved
    #                 del result.downloadable[short_hash]
    #         else:
    #             logger.info(f"Model {short_hash[:8]}... available for download from {sources[0]['type']}")

    #     return result

    # def _attempt_download(self, short_hash: str, sources: list[dict], result: ResolutionResult) -> bool:
    #     """Attempt to download model from available sources.
        
    #     Args:
    #         short_hash: Model short hash
    #         sources: List of source dictionaries
    #         result: ResolutionResult to update
            
    #     Returns:
    #         True if download successful
    #     """
    #     for source in sources:
    #         try:
    #             url = source.get('url')
    #             if not url:
    #                 continue

    #             logger.info(f"Downloading {short_hash[:8]}... from {source.get('type', 'unknown')}")
    #             model = self.download_manager.download_from_url(url)

    #             # Add to resolved models
    #             result.resolved[short_hash] = model
    #             logger.info(f"✓ Downloaded and resolved: {short_hash[:8]}...")
    #             return True

    #         except Exception as e:
    #             logger.warning(f"Download failed for {short_hash[:8]}... from {url}: {e}")
    #             continue

    #     return False

    # def generate_export_manifest(self, model_hashes: list[str]) -> dict:
    #     """Generate export manifest with full metadata for models.
        
    #     Args:
    #         model_hashes: List of model hashes to include
            
    #     Returns:
    #         Export manifest with complete model metadata
    #     """
    #     export_manifest = {
    #         'required': {},
    #         'optional': {}
    #     }

    #     for model_hash in model_hashes:
    #         models = self.model_repository.find_model_by_hash(model_hash)
    #         if not models:
    #             logger.warning(f"Model not found for export: {model_hash[:8]}...")
    #             continue

    #         model = models[0]

    #         # Get all known sources
    #         sources = self.model_repository.get_sources(model_hash)

    #         # Compute additional hashes if needed
    #         model_path = Path(model.path)
    #         blake3_hash = None
    #         sha256_hash = None

    #         if model_path.exists():
    #             # Only compute if we don't already have them
    #             existing_models = self.model_repository.find_model_by_hash(model_hash)
    #             if existing_models:
    #                 # Check if we need to compute additional hashes
    #                 try:
    #                     sha256_hash = self.model_repository.compute_sha256(model_path)
    #                     self.model_repository.update_sha256(model_hash, sha256_hash)
    #                 except Exception as e:
    #                     logger.warning(f"Failed to compute SHA256 for {model_hash[:8]}...: {e}")

    #         # Build manifest entry
    #         manifest_entry = {
    #             'filename': model.filename,
    #             'type': model.model_type,
    #             'size': model.file_size,
    #         }

    #         # Add hashes if available
    #         if blake3_hash:
    #             manifest_entry['blake3'] = blake3_hash
    #         if sha256_hash:
    #             manifest_entry['sha256'] = sha256_hash

    #         # Add sources if available
    #         if sources:
    #             manifest_entry['sources'] = []
    #             for source in sources:
    #                 source_entry = {
    #                     'type': source['type'],
    #                     'url': source['url']
    #                 }
    #                 if 'data' in source:
    #                     source_entry.update(source['data'])
    #                 manifest_entry['sources'].append(source_entry)

    #         # For now, put everything in required - could be made configurable
    #         export_manifest['required'][model_hash] = manifest_entry

    #     return export_manifest

    # def _format_size(self, size_bytes: int) -> str:
    #     """Format file size in human readable form."""
    #     size = float(size_bytes)
    #     for unit in ['B', 'KB', 'MB', 'GB']:
    #         if size < 1024.0:
    #             return f"{size:.1f} {unit}"
    #         size /= 1024.0
    #     return f"{size:.1f} TB"

