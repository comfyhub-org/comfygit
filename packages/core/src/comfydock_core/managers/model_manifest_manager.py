"""ModelManifestManager - Environment-level model manifest operations for pyproject.toml."""
from __future__ import annotations
from pathlib import Path

from ..logging.logging_config import get_logger
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from comfydock_core.models.shared import ModelWithLocation
    from ..repositories.model_repository import ModelRepository
    from .pyproject_manager import PyprojectManager

logger = get_logger(__name__)


class ModelManifestManager:
    """Environment-level model manifest operations for pyproject.toml."""

    def __init__(
        self,
        index_manager: ModelRepository,
        pyproject: PyprojectManager,
        global_models_path: Path,
    ):
        """Initialize ModelManifestManager.

        Args:
            index_manager: ModelIndexManager for querying model database
            pyproject: PyprojectManager for manifest operations
        """
        self.index_manager = index_manager
        self.pyproject = pyproject
        self.global_models_path = global_models_path

    def ensure_model_in_manifest(self, model: ModelWithLocation, category: str = "required") -> bool:
        """Ensure model is in pyproject.toml manifest.
        
        Args:
            model_hash: Model hash (short hash)
            category: 'required' or 'optional'
            
        Returns:
            True if added, False if already existed
        """
        model_hash = model.hash
        # Check if already in manifest
        if self.pyproject.models.has_model(model_hash):
            return False

        # Add to manifest - filter out None values
        kwargs = {
            "model_hash": model.hash,
            "filename": model.filename,
            "file_size": model.file_size,
            "category": category,
        }

        # Add optional fields only if they're not None
        if model.blake3_hash is not None:
            kwargs["blake3_hash"] = model.blake3_hash
        if model.sha256_hash is not None:
            kwargs["sha256_hash"] = model.sha256_hash

        # Filter None values from metadata
        if model.metadata:
            filtered_metadata = {k: v for k, v in model.metadata.items() if v is not None}
            kwargs.update(filtered_metadata)

        self.pyproject.models.add_model(**kwargs)

        logger.debug(f"Added model to manifest: {model.filename} ({model_hash[:8]}...)")
        return True

    def prepare_models_for_export(self, progress_callback=None) -> dict:
        """Compute full hashes for all models in manifest.
        
        Args:
            progress_callback: Optional callback(current, total, filename)
            
        Returns:
            Dict with results: models_processed, hashes_computed, ready_for_export
        """
        logger.info("Preparing models for export...")

        # Get all model hashes from manifest
        model_hashes = self.pyproject.models.get_all_model_hashes()
        computed_hashes = {}

        total_models = len(model_hashes)
        current = 0

        for model_hash in model_hashes:
            # Find model in index
            models = self.index_manager.find_model_by_hash(model_hash)
            if not models:
                logger.warning(f"Model {model_hash[:8]}... not found in index")
                continue

            model = models[0]

            # Construct full model path
            model_path = self.global_models_path / model.relative_path
            if not model_path.exists():
                logger.warning(f"Model file not found: {model_path}")
                continue

            current += 1
            if progress_callback:
                progress_callback(current, total_models, model.filename)

            computed = {}

            # Compute blake3 if missing
            blake3_hash = model.blake3_hash
            if not blake3_hash:
                try:
                    logger.info(f"Computing blake3 for {model.filename}...")
                    # blake3_hash = scanner.calculate_model_hash(model.path)
                    blake3_hash = self.index_manager.compute_blake3(model_path)
                    self.index_manager.update_blake3(model.hash, blake3_hash)
                    computed['blake3'] = blake3_hash
                except Exception as e:
                    logger.error(f"Failed to compute blake3 for {model.filename}: {e}")
            else:
                computed['blake3'] = blake3_hash

            # Compute sha256 if missing
            sha256_hash = model.sha256_hash
            if not sha256_hash:
                try:
                    logger.info(f"Computing sha256 for {model.filename}...")
                    sha256_hash = self.index_manager.compute_sha256(model_path)
                    self.index_manager.update_sha256(model.hash, sha256_hash)
                    computed['sha256'] = sha256_hash
                except Exception as e:
                    logger.error(f"Failed to compute sha256 for {model.filename}: {e}")
            else:
                computed['sha256'] = sha256_hash

            # Update manifest with computed hashes
            if computed:
                self.pyproject.models.update_model_metadata(model_hash, **computed)

            computed_hashes[model_hash] = computed

        # Check if all complete
        all_complete = True
        for hashes in computed_hashes.values():
            if not hashes.get('blake3') or not hashes.get('sha256'):
                all_complete = False
                break

        # Update manifest state
        if all_complete and computed_hashes:
            self.pyproject.set_manifest_state('exportable')

        return {
            'models_processed': len(computed_hashes),
            'hashes_computed': computed_hashes,
            'ready_for_export': all_complete
        }

    def clean_orphaned_models(self) -> None:
        """Remove orphaned models from required category.

        Models in the 'optional' category are never removed as they are user-managed.
        Only removes models from 'required' category that are no longer referenced
        by any tracked workflow.
        """
        # Get all models currently referenced by workflows
        referenced_models = self._get_all_referenced_models()

        # Get all models in required category
        required_models = self.pyproject.models.get_category('required')

        # Find orphaned models (in required but not referenced)
        orphaned_models = set(required_models.keys()) - referenced_models

        if orphaned_models:
            logger.info(f"Cleaning up {len(orphaned_models)} orphaned models from required category")
            for model_hash in orphaned_models:
                model_info = required_models[model_hash]
                filename = model_info.get('filename', 'unknown')
                self.pyproject.models.remove_model(model_hash, category='required')
                logger.debug(f"Removed orphaned model: {filename} ({model_hash[:8]}...)")
        else:
            logger.debug("No orphaned models found in required category")
            
    def _get_all_referenced_models(self) -> set[str]:
        """Get all model hashes referenced by currently tracked workflows.

        Returns:
            Set of model hashes referenced by remaining workflows
        """
        referenced_models = set()
        workflow_resolutions = self.pyproject.workflows.get_all_with_resolutions()

        for workflow_config in workflow_resolutions.values():
            requires = workflow_config.get('requires', {})
            models = requires.get('models', [])
            referenced_models.update(models)

        logger.debug(f"Found {len(referenced_models)} models referenced by {len(tracked_workflows)} workflows")
        return referenced_models