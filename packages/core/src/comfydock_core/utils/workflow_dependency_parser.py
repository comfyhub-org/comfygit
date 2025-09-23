"""Workflow dependency analysis and resolution manager."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, List

from comfydock_core.services.workflow_repository import WorkflowRepository

from ..logging.logging_config import get_logger
from ..services.node_classifier import NodeClassifier
from ..configs.model_config import ModelConfig

if TYPE_CHECKING:
    from comfydock_core.managers.model_index_manager import ModelIndexManager
    from comfydock_core.models.shared import ModelWithLocation
    from ..models.workflow import Workflow, WorkflowNode, ModelReference, ModelResolutionResult

logger = get_logger(__name__)

@dataclass
class WorkflowDependencies:
    """Complete workflow dependency analysis results."""
    resolved_models: list[ModelWithLocation] = field(default_factory=list)
    missing_models: list[dict] = field(default_factory=list)
    builtin_nodes: list[WorkflowNode] = field(default_factory=list)
    custom_nodes: list[WorkflowNode] = field(default_factory=list)
    python_dependencies: list[str] = field(default_factory=list)

    @property
    def total_models(self) -> int:
        """Total number of model references found."""
        return len(self.resolved_models) + len(self.missing_models)

    @property
    def model_hashes(self) -> list[str]:
        """Get all resolved model hashes."""
        return [model.hash for model in self.resolved_models]


class WorkflowDependencyParser:
    """Manages workflow dependency analysis and resolution."""

    def __init__(self, workflow_path: Path, model_index: ModelIndexManager, model_config: ModelConfig | None = None):

        self.model_index = model_index
        self.model_config = model_config or ModelConfig.load()
        self.node_classifier = NodeClassifier()
        self.repository = WorkflowRepository()
        # Load workflow
        self.workflow = self.repository.load(workflow_path)
        logger.debug(f"Loaded workflow {self.workflow}")

        # Keep raw text for legacy string matching
        self.workflow_text = self.repository.load_raw_text(workflow_path)

        # Extract existing metadata if present
        self.existing_metadata = self.workflow.extra.get("_comfydock_metadata") if self.workflow.extra else None
        if self.existing_metadata:
            logger.debug(f"Found existing metadata version {self.existing_metadata.get('version')}")

    def analyze_dependencies(self) -> WorkflowDependencies:
        """Analyze workflow for all dependencies, including model information, node types, and Python dependencies."""
        try:
            nodes_data = self.workflow.nodes

            if not nodes_data:
                logger.warning("No nodes found in workflow")
                return WorkflowDependencies()

            resolved_models, missing_models = self._resolve_model_dependencies(nodes_data)

            # Extract custom and builtin nodes
            all_nodes = self.node_classifier.classify_nodes(self.workflow)
            logger.debug(f"Found {len(all_nodes.builtin_nodes)} builtin nodes and {len(all_nodes.custom_nodes)} custom nodes")
            builtin_nodes = all_nodes.builtin_nodes
            custom_nodes = all_nodes.custom_nodes

            # Log results
            if resolved_models:
                logger.info(f"Found {len(resolved_models)} models in workflow")
            if missing_models:
                logger.warning(f"Found {len(missing_models)} missing models in workflow")
            if custom_nodes:
                logger.info(f"Found {len(custom_nodes)} custom nodes in workflow")

            return WorkflowDependencies(
                resolved_models=resolved_models,
                missing_models=missing_models,
                builtin_nodes=builtin_nodes,
                custom_nodes=custom_nodes,
                python_dependencies=[]
            )

        except Exception as e:
            logger.error(f"Failed to analyze workflow dependencies: {e}")
            return WorkflowDependencies()

    def _resolve_model_dependencies(self, nodes_data) -> tuple[list[ModelWithLocation], list[dict]]:
        # Get model index data
        all_models = self.model_index.get_all_models()
        full_path_models = {model.relative_path: model for model in all_models}

        # Track processing state
        resolved_models: list[ModelWithLocation] = []
        missing_models: list[dict] = []
        processed_hashes = set()
        standard_nodes = set()

        # Process standard loader nodes first
        for node_id, node_info in nodes_data.items():
            node_type = node_info.type

            # Skip non-model loader nodes
            if not self.model_config.is_model_loader_node(node_type):
                continue
            
            standard_nodes.add(node_id)
            model_paths = self._extract_paths_from_node_info(node_type, node_info)

            # Try alternative paths until we find one that exists
            resolved = False
            for full_path in model_paths:
                if full_path in full_path_models:
                    model = full_path_models[full_path]
                    if model.hash not in processed_hashes:
                        resolved_models.append(model)
                        processed_hashes.add(model.hash)
                        logger.debug(
                            f"Resolved standard loader: {node_type} -> {full_path} -> {model.hash}"
                        )
                    else:
                        logger.debug(
                            f"Model already resolved by another node: {node_type} -> {full_path} -> {model.hash}"
                        )
                    resolved = True
                    break

            # Mark as missing if none of the alternatives worked
            if not resolved and model_paths:
                widget_values = node_info.widgets_values
                widget_index = self.model_config.get_widget_index_for_node(
                    node_type
                )
                widget_value = (
                    widget_values[widget_index]
                    if widget_index < len(widget_values)
                    else "unknown"
                )
                missing_models.append(
                    {
                        "relative_path": f"{node_type}:{widget_value}",
                        "attempted_paths": model_paths,
                    }
                )
                logger.warning(
                    f"Standard loader model not found: {node_type} with '{widget_value}' (tried: {model_paths})"
                )

        # Process remaining nodes for model references
        remaining_nodes = {
            k: v for k, v in nodes_data.items() if k not in standard_nodes
        }
        all_model_paths = {model.relative_path for model in all_models}

        for _node_id, node_info in remaining_nodes.items():
            for widget_value in node_info.widgets_values:
                if isinstance(widget_value, str) and widget_value in all_model_paths:
                    # Found direct model path match
                    matching_models = [
                        m for m in all_models if m.relative_path == widget_value
                    ]

                    if len(matching_models) == 1:
                        model = matching_models[0]
                        if model.hash not in processed_hashes:
                            resolved_models.append(model)
                            processed_hashes.add(model.hash)
                            logger.debug(
                                f"Resolved custom node: {node_info.type} -> {widget_value} -> {model.hash}"
                            )
                    elif len(matching_models) > 1:
                        # Disambiguation needed - pick first and warn
                        model = matching_models[0]
                        if model.hash not in processed_hashes:
                            resolved_models.append(model)
                            processed_hashes.add(model.hash)
                            logger.warning(
                                f"Ambiguous model reference in {node_info.type}: '{widget_value}' matches {len(matching_models)} models, using first: {model.hash}"
                            )

        return resolved_models, missing_models

    def _extract_paths_from_node_info(
        self, node_type: str, node_info: WorkflowNode
    ) -> list[str]:
        """Extract model paths from node info using standard loader mappings."""
        widgets_values = node_info.widgets_values if node_info.widgets_values else []
        if not widgets_values:
            return []

        widget_index = self.model_config.get_widget_index_for_node(node_type)
        if widget_index >= len(widgets_values):
            return []

        widget_value = widgets_values[widget_index]
        if not isinstance(widget_value, str) or not widget_value.strip():
            return []

        # Reconstruct full paths using directory mappings
        return self.model_config.reconstruct_model_path(node_type, widget_value)

    def analyze_models_enhanced(self) -> List["ModelResolutionResult"]:
        """Analyze models with enhanced resolution strategies"""
        results = []
        nodes_data = self.workflow.nodes

        metadata_used = 0
        fresh_resolved = 0

        for node_id, node_info in nodes_data.items():
            refs = self._extract_model_refs(node_id, node_info)
            for ref in refs:
                result = self._resolve_with_strategies(ref)
                results.append(result)

                if result.resolution_type == "metadata":
                    metadata_used += 1
                elif result.resolution_type != "not_found" and result.resolution_type != "ambiguous":
                    fresh_resolved += 1

        if metadata_used > 0:
            logger.info(f"Used cached metadata for {metadata_used} models, resolved {fresh_resolved} fresh")

        return results

    def _extract_model_refs(self, node_id: str, node_info: "WorkflowNode") -> List["ModelReference"]:
        """Extract model references from node"""
        from ..models.workflow import ModelReference

        refs = []

        # Handle multi-model nodes specially
        if node_info.type == "CheckpointLoader":
            # Index 0: checkpoint, Index 1: config
            widgets = node_info.widgets_values or []
            if len(widgets) > 0 and widgets[0]:
                refs.append(ModelReference(
                    node_id=node_id,
                    node_type=node_info.type,
                    widget_index=0,
                    widget_value=widgets[0]
                ))
            if len(widgets) > 1 and widgets[1]:
                refs.append(ModelReference(
                    node_id=node_id,
                    node_type=node_info.type,
                    widget_index=1,
                    widget_value=widgets[1]
                ))

        # Standard single-model loaders
        elif self.model_config.is_model_loader_node(node_info.type):
            widget_idx = self.model_config.get_widget_index_for_node(node_info.type)
            widgets = node_info.widgets_values or []
            if widget_idx < len(widgets) and widgets[widget_idx]:
                refs.append(ModelReference(
                    node_id=node_id,
                    node_type=node_info.type,
                    widget_index=widget_idx,
                    widget_value=widgets[widget_idx]
                ))

        # Pattern match all widgets for custom nodes
        else:
            widgets = node_info.widgets_values or []
            for idx, value in enumerate(widgets):
                if self._looks_like_model(value):
                    refs.append(ModelReference(
                        node_id=node_id,
                        node_type=node_info.type,
                        widget_index=idx,
                        widget_value=value
                    ))

        return refs

    def _resolve_with_strategies(self, ref: "ModelReference") -> "ModelResolutionResult":
        """Try multiple resolution strategies"""
        from ..models.workflow import ModelResolutionResult

        widget_value = ref.widget_value

        # Strategy 0: Check existing metadata first
        metadata_result = self._try_metadata_resolution(ref)
        if metadata_result:
            return metadata_result

        # Strategy 1: Exact path match
        candidates = self._try_exact_match(widget_value)
        if len(candidates) == 1:
            ref.resolved_model = candidates[0]
            ref.resolution_confidence = 1.0
            return ModelResolutionResult(ref, candidates, "exact")

        # Strategy 2: Reconstruct paths for native loaders
        if self.model_config.is_model_loader_node(ref.node_type):
            paths = self.model_config.reconstruct_model_path(ref.node_type, widget_value)
            for path in paths:
                candidates = self._try_exact_match(path)
                if len(candidates) == 1:
                    ref.resolved_model = candidates[0]
                    ref.resolution_confidence = 0.9
                    return ModelResolutionResult(ref, candidates, "reconstructed")

        # Strategy 3: Case-insensitive match
        candidates = self._try_case_insensitive_match(widget_value)
        if len(candidates) == 1:
            ref.resolved_model = candidates[0]
            ref.resolution_confidence = 0.8
            return ModelResolutionResult(ref, candidates, "case_insensitive")

        # Strategy 4: Filename-only match
        filename = Path(widget_value).name
        candidates = self.model_index.find_by_filename(filename)
        if len(candidates) == 1:
            ref.resolved_model = candidates[0]
            ref.resolution_confidence = 0.7
            return ModelResolutionResult(ref, candidates, "filename")
        elif len(candidates) > 1:
            # Multiple matches - need disambiguation
            return ModelResolutionResult(ref, candidates, "ambiguous")

        # No matches found
        return ModelResolutionResult(ref, [], "not_found")

    def _try_exact_match(self, path: str) -> List["ModelWithLocation"]:
        """Try exact path match"""
        all_models = self.model_index.get_all_models()
        return [m for m in all_models if m.relative_path == path]

    def _try_case_insensitive_match(self, path: str) -> List["ModelWithLocation"]:
        """Try case-insensitive path match"""
        all_models = self.model_index.get_all_models()
        path_lower = path.lower()
        return [m for m in all_models if m.relative_path.lower() == path_lower]

    def _looks_like_model(self, value: Any) -> bool:
        """Check if value looks like a model path"""
        if not isinstance(value, str):
            return False
        extensions = self.model_config.default_extensions
        return any(value.endswith(ext) for ext in extensions)

    def _try_metadata_resolution(self, ref: "ModelReference") -> "ModelResolutionResult | None":
        """Try to resolve using existing metadata if valid"""
        from ..models.workflow import ModelResolutionResult

        if not self.existing_metadata:
            return None

        # Check if metadata exists for this node
        models_metadata = self.existing_metadata.get("models", {})
        node_metadata = models_metadata.get(str(ref.node_id))
        if not node_metadata:
            return None

        # Find the metadata entry for this widget index
        refs = node_metadata.get("refs", [])
        for metadata_ref in refs:
            if metadata_ref.get("widget_index") != ref.widget_index:
                continue

            # Check if the path in metadata matches current widget value
            metadata_path = metadata_ref.get("path")
            if metadata_path != ref.widget_value:
                logger.debug(f"Metadata path '{metadata_path}' doesn't match current value '{ref.widget_value}'")
                return None  # Path changed, need fresh resolution

            # Validate the hash still exists in our index
            metadata_hash = metadata_ref.get("hash")
            if not metadata_hash:
                logger.debug("No hash in metadata, needs resolution")
                return None

            # Try to find model by hash
            models = self.model_index.find_by_hash(metadata_hash)
            if models and len(models) > 0:
                # Valid metadata - use it
                model = models[0]
                ref.resolved_model = model
                ref.resolution_confidence = 1.0
                logger.debug(f"Resolved from metadata: {ref.widget_value} -> {metadata_hash}")
                return ModelResolutionResult(ref, [model], "metadata")
            else:
                logger.debug(f"Hash {metadata_hash} no longer in index")
                return None  # Hash no longer valid

        return None  # No matching metadata entry found
