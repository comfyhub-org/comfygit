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

    def resolve_model(
        self, ref: WorkflowNodeWidgetRef, model_context: ModelResolutionContext
    ) -> list[ResolvedModel] | None:
        """Try multiple resolution strategies"""
        workflow_name = model_context.workflow_name
        widget_value = ref.widget_value

        # Strategy 0: Check existing pyproject model data first
        context_resolution_result = self._try_context_resolution(ref=ref, context=model_context)
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
                    match_type="ambiguous",
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
    
    def _try_context_resolution(self, context: ModelResolutionContext, ref: WorkflowNodeWidgetRef) -> ResolvedModel | None:
        # Build inverse lookup of workflow widget refs to model hashes
        workflow_name = context.workflow_name
        model_mappings = context.model_mappings
        ref_to_hash_map = {}
        for hash, model_node_refs in model_mappings.items():
            for ref in model_node_refs.nodes:
                ref_to_hash_map[(ref.node_id, ref.widget_index)] = hash
                
        # See if ref exists in the table:
        model_hash: str = ""
        if (ref.node_id, ref.widget_index) in ref_to_hash_map:
            model_hash = ref_to_hash_map[(ref.node_id, ref.widget_index)]
        else:
            return None
        
        # See if model exists in required or optional
        if model_hash in context.required_models:
            return ResolvedModel(
                workflow=workflow_name,
                reference=ref,
                match_type="workflow_context",
                resolved_model=context.required_models[model_hash],
                match_confidence=1.0,
            )
        elif model_hash in context.optional_models:
            return ResolvedModel(
                workflow=workflow_name,
                reference=ref,
                match_type="workflow_context",
                resolved_model=context.optional_models[model_hash],
                match_confidence=0.9,
            )
        else:
            return None
        

    def _try_pyproject_resolution(self, workflow_name: str, ref: WorkflowNodeWidgetRef) -> ResolvedModel | None:
        """Try to resolve using existing model data in pyproject.toml if valid.

        Resolution logic:
        1. Check if this model reference exists in the workflow's models section
        2. If found, get the key (could be hash or filename for Type 1 optional)
        3. Look up the key in models.required or models.optional
        4. Return resolved model or skip if marked as optional unresolved
        """
        if not self.pyproject:
            return None

        try:
            config = self.pyproject.load()

            # Step 1: Get workflow section
            workflows = config.get('tool', {}).get('comfydock', {}).get('workflows', {})
            workflow_section = workflows.get(workflow_name)
            if not workflow_section:
                return None  # Workflow not tracked yet

            # Step 2: Find model key by matching node location (node_id + widget_idx)
            # The key could be either a hash (for resolved models) or filename (for Type 1 optional)
            models_mapping = workflow_section.get('models', {})
            model_key = None

            for key, mapping in models_mapping.items():
                # mapping = {nodes = [{node_id = "83", widget_idx = 0}, ...]}
                node_locations = mapping.get('nodes', [])
                for location in node_locations:
                    if (str(location.get('node_id')) == str(ref.node_id) and
                        location.get('widget_idx') == ref.widget_index):
                        model_key = key
                        break
                if model_key:
                    break

            if not model_key:
                return None  # Model not found in workflow mapping (needs fresh resolution)

            # Step 3: Look up key in models.required or models.optional
            models_required = config.get('tool', {}).get('comfydock', {}).get('models', {}).get('required', {})
            models_optional = config.get('tool', {}).get('comfydock', {}).get('models', {}).get('optional', {})

            is_optional = model_key in models_optional
            model_metadata = models_optional.get(model_key) if is_optional else models_required.get(model_key)

            if not model_metadata:
                # Key exists in workflow but not in model sections (data corruption)
                logger.warning(f"Model key {model_key} found in workflow {workflow_name} but not in models sections")
                return None

            # Step 4: Handle Type 1 optional models (unresolved, filename-keyed)
            if is_optional and model_metadata.get('unresolved'):
                logger.debug(f"Model {ref.widget_value} is marked as optional (unresolved), skipping resolution")
                return ResolvedModel(
                    workflow=workflow_name,
                    reference=ref,
                    match_type="optional_unresolved",
                )

            # Step 5: Fetch from repository (model_key should be a hash for resolved models)
            found_model = self.model_repository.get_model(model_key)

            if found_model:
                # Valid existing resolution - use it
                key_display = model_key[:8] + "..." if len(model_key) > 16 else model_key
                logger.debug(f"Resolved from pyproject: {ref.widget_value} -> {key_display}")
                return ResolvedModel(
                    workflow=workflow_name,
                    reference=ref,
                    resolved_model=found_model,
                    match_type="optional" if is_optional else "pyproject",
                    match_confidence=1.0,
                )
            else:
                # Hash no longer valid in index, need fresh resolution
                key_display = model_key[:8] + "..." if len(model_key) > 16 else model_key
                logger.debug(f"Pyproject key {key_display} no longer in index for {ref.widget_value}")
                return None

        except Exception as e:
            logger.debug(f"Error checking pyproject resolution: {e}")
            return None
