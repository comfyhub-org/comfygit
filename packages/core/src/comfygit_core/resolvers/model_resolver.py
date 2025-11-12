"""ModelResolver - Resolve model requirements for environment import/export."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any


from ..logging.logging_config import get_logger
from ..models.workflow import (
    ModelResolutionContext,
    WorkflowNodeWidgetRef,
    WorkflowNode,
    ResolvedModel,
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
        self.download_manager = download_manager

    def resolve_model(
        self, ref: WorkflowNodeWidgetRef, model_context: ModelResolutionContext
    ) -> list[ResolvedModel] | None:
        """Try multiple resolution strategies"""
        workflow_name = model_context.workflow_name
        widget_value = ref.widget_value

        # Strategy 0: Check existing pyproject model data first
        context_resolution_result = self._try_context_resolution(widget_ref=ref, context=model_context)
        if context_resolution_result:
            logger.debug(
                f"Resolved {ref} to {context_resolution_result.resolved_model} from pyproject.toml"
            )
            return [context_resolution_result]

        # Strategy 1: Exact path match
        all_models = self.model_repository.get_all_models()
        candidates = self._try_exact_match(widget_value, all_models)
        if len(candidates) == 1:
            logger.debug(f"Resolved {ref} to {candidates[0]} as exact match")
            return [
                ResolvedModel(
                    workflow=workflow_name,
                    reference=ref,
                    match_type="exact",
                    resolved_model=candidates[0],
                    match_confidence=1.0,
                )
            ]

        # Strategy 2: Reconstruct paths for native loaders
        if self.model_config.is_model_loader_node(ref.node_type):
            paths = self.model_config.reconstruct_model_path(
                ref.node_type, widget_value
            )
            for path in paths:
                candidates = self._try_exact_match(path, all_models)
                if len(candidates) == 1:
                    logger.debug(
                        f"Resolved {ref} to {candidates[0]} as reconstructed match"
                    )
                    return [
                        ResolvedModel(
                            workflow=workflow_name,
                            reference=ref,
                            match_type="reconstructed",
                            resolved_model=candidates[0],
                            match_confidence=0.9,
                        )
                    ]

        # Strategy 3: Case-insensitive match
        candidates = self._try_case_insensitive_match(widget_value, all_models)
        if len(candidates) == 1:
            logger.debug(f"Resolved {ref} to {candidates[0]} as case-insensitive match")
            return [
                ResolvedModel(
                    workflow=workflow_name,
                    reference=ref,
                    match_type="case_insensitive",
                    resolved_model=candidates[0],
                    match_confidence=0.8,
                )
            ]
        elif len(candidates) > 1:
            # Multiple matches - need disambiguation
            logger.debug(
                f"Resolved {ref} to {candidates} as case-insensitive match, ambiguous"
            )
            return [
                ResolvedModel(
                    workflow=workflow_name,
                    reference=ref,
                    match_type="case_insensitive",
                    resolved_model=model,
                    match_confidence=0.0,
                )
                for model in candidates
            ]

        # Strategy 4: Filename-only match
        filename = Path(widget_value).name
        candidates = self.model_repository.find_by_filename(filename)
        if len(candidates) == 1:
            logger.debug(f"Resolved {ref} to {candidates[0]} as filename-only match")
            return [
                ResolvedModel(
                    workflow=workflow_name,
                    reference=ref,
                    match_type="filename",
                    resolved_model=candidates[0],
                    match_confidence=0.7,
                )
            ]
        elif len(candidates) > 1:
            # Multiple matches - need disambiguation
            logger.debug(
                f"Resolved {ref} to {candidates} as filename-only match, ambiguous"
            )
            return [
                ResolvedModel(
                    workflow=workflow_name,
                    reference=ref,
                    match_type="filename",
                    resolved_model=model,
                    match_confidence=0.0,
                )
                for model in candidates
            ]

        # No matches found
        logger.debug(f"No matches found in pyproject or model index for {ref}")
        return None

    def _try_exact_match(self, path: str, all_models: list[ModelWithLocation] | None =None) -> list["ModelWithLocation"]:
        """Try exact path match"""
        if all_models is None:
            all_models = self.model_repository.get_all_models()
        return [m for m in all_models if m.relative_path == path]

    def _try_case_insensitive_match(self, path: str, all_models: list[ModelWithLocation] | None =None) -> list["ModelWithLocation"]:
        """Try case-insensitive path match"""
        if all_models is None:
            all_models = self.model_repository.get_all_models()
        path_lower = path.lower()
        return [m for m in all_models if m.relative_path.lower() == path_lower]
    
    def _try_context_resolution(self, context: ModelResolutionContext, widget_ref: WorkflowNodeWidgetRef) -> ResolvedModel | None:
        """Check if this ref was previously resolved using context lookup.

        Now supports download intent detection via full ManifestWorkflowModel objects.
        """
        workflow_name = context.workflow_name

        # Check if ref exists in previous resolutions (now contains full ManifestWorkflowModel)
        manifest_model = context.previous_resolutions.get(widget_ref)

        if not manifest_model:
            return None

        # NEW: Check if download intent (has URL but no hash yet)
        if manifest_model.status == "unresolved" and manifest_model.sources:
            # Download intent found - don't re-prompt user
            from pathlib import Path
            return ResolvedModel(
                workflow=workflow_name,
                reference=widget_ref,
                match_type="download_intent",
                resolved_model=None,
                model_source=manifest_model.sources[0],  # URL from previous session
                target_path=Path(manifest_model.relative_path) if manifest_model.relative_path else None,
                is_optional=False,
                match_confidence=1.0,
            )

        # Handle optional unresolved models (user explicitly marked as optional)
        if manifest_model.status == "unresolved" and not manifest_model.sources:
            # Only treat as optional if user explicitly marked it (criticality="optional")
            # Otherwise it's just unresolved (from interrupted resolution) - return None
            if manifest_model.criticality == "optional":
                return ResolvedModel(
                    workflow=workflow_name,
                    reference=widget_ref,
                    match_type="workflow_context",
                    resolved_model=None,
                    is_optional=True,
                    match_confidence=1.0,
                )
            # Not explicitly optional - this is truly unresolved, let it fall through
            return None

        # Handle resolved models - look up in repository by hash
        if manifest_model.hash:
            resolved_model = self.model_repository.get_model(manifest_model.hash)

            if not resolved_model:
                # Model was previously resolved but doesn't exist locally
                # Check global models table for download sources (fallback path)
                global_model = context.global_models.get(manifest_model.hash)
                if global_model and global_model.sources:
                    # Create download intent from global models table
                    from pathlib import Path
                    logger.info(f"Creating download intent for {manifest_model.filename} from global models table")
                    return ResolvedModel(
                        workflow=workflow_name,
                        reference=widget_ref,
                        match_type="download_intent",
                        resolved_model=None,
                        model_source=global_model.sources[0],
                        target_path=Path(global_model.relative_path) if global_model.relative_path else None,
                        is_optional=False,
                        match_confidence=1.0,
                    )

                logger.warning(f"Model {manifest_model.hash} in previous resolutions but not found in repository or global models")
                return None

            return ResolvedModel(
                workflow=workflow_name,
                reference=widget_ref,
                match_type="workflow_context",
                resolved_model=resolved_model,
                match_confidence=1.0,
            )

        return None
