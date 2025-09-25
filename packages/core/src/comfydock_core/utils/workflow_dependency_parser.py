"""Workflow dependency analysis and resolution manager."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, List

from comfydock_core.services.workflow_repository import WorkflowRepository

from ..logging.logging_config import get_logger
from ..services.node_classifier import NodeClassifier
from ..configs.model_config import ModelConfig
from ..models.workflow import WorkflowModelRef, WorkflowNode, ModelResolutionResult

if TYPE_CHECKING:
    from comfydock_core.managers.model_index_manager import ModelIndexManager
    from comfydock_core.models.shared import ModelWithLocation

logger = get_logger(__name__)

@dataclass
class WorkflowDependencies:
    """Complete workflow dependency analysis results."""
    resolved_models: list[WorkflowModelRef] = field(default_factory=list)
    missing_models: list[WorkflowModelRef] = field(default_factory=list)
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
        return [model.resolved_model.hash for model in self.resolved_models if model.resolved_model]


class WorkflowDependencyParser:
    """Manages workflow dependency analysis and resolution."""

    def __init__(self, workflow_path: Path, model_index: ModelIndexManager, model_config: ModelConfig | None = None, pyproject=None):

        self.model_index = model_index
        self.model_config = model_config or ModelConfig.load()
        self.node_classifier = NodeClassifier()
        self.repository = WorkflowRepository()
        self.pyproject = pyproject  # Optional PyprojectManager for checking existing resolutions

        # Load workflow
        self.workflow = self.repository.load(workflow_path)
        logger.debug(f"Loaded workflow {self.workflow}")

        # Store workflow name for pyproject lookup
        self.workflow_name = workflow_path.stem

        # Keep raw text for legacy string matching
        self.workflow_text = self.repository.load_raw_text(workflow_path)

    def analyze_dependencies(self) -> WorkflowDependencies:
        """Analyze workflow for all dependencies, including model information, node types, and Python dependencies."""
        try:
            nodes_data = self.workflow.nodes

            if not nodes_data:
                logger.warning("No nodes found in workflow")
                return WorkflowDependencies()

            resolved_model_results = self.analyze_models()
            resolved_models = [result.reference for result in resolved_model_results if result.reference.resolved_model]
            missing_models = [result.reference for result in resolved_model_results if not result.reference.resolved_model]

            # Extract custom and builtin nodes
            all_nodes = self.node_classifier.classify_nodes(self.workflow)
            logger.debug(f"Found {len(all_nodes.builtin_nodes)} builtin nodes and {len(all_nodes.custom_nodes)} custom nodes")
            builtin_nodes = all_nodes.builtin_nodes
            custom_nodes = all_nodes.custom_nodes

            # Log results
            if resolved_model_results:
                logger.info(f"Found {len(resolved_model_results)} models in workflow")
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

    def analyze_models(self) -> List["ModelResolutionResult"]:
        """Analyze models with enhanced resolution strategies"""
        results = []
        nodes_data = self.workflow.nodes

        pyproject_used = 0
        fresh_resolved = 0

        for node_id, node_info in nodes_data.items():
            refs = self._extract_model_refs(node_id, node_info)
            for ref in refs:
                logger.debug(f"Trying to resolve {ref}")
                result = self._resolve_with_strategies(ref)
                results.append(result)

                if result.resolution_type == "pyproject":
                    pyproject_used += 1
                elif result.resolution_type not in ["not_found", "ambiguous"]:
                    fresh_resolved += 1

        if pyproject_used > 0:
            logger.info(f"Reused {pyproject_used} models from pyproject.toml, resolved {fresh_resolved} fresh")

        return results

    def _extract_model_refs(self, node_id: str, node_info: WorkflowNode) -> List["WorkflowModelRef"]:
        """Extract model references from node"""

        refs = []

        # Handle multi-model nodes specially
        if node_info.type == "CheckpointLoader":
            # Index 0: checkpoint, Index 1: config
            widgets = node_info.widgets_values or []
            if len(widgets) > 0 and widgets[0]:
                refs.append(WorkflowModelRef(
                    node_id=node_id,
                    node_type=node_info.type,
                    widget_index=0,
                    widget_value=widgets[0]
                ))
            if len(widgets) > 1 and widgets[1]:
                refs.append(WorkflowModelRef(
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
                refs.append(WorkflowModelRef(
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
                    refs.append(WorkflowModelRef(
                        node_id=node_id,
                        node_type=node_info.type,
                        widget_index=idx,
                        widget_value=value
                    ))

        return refs

    def _resolve_with_strategies(self, ref: WorkflowModelRef) -> ModelResolutionResult:
        """Try multiple resolution strategies"""
        widget_value = ref.widget_value

        # Strategy 0: Check existing pyproject model data first
        pyproject_result = self._try_pyproject_resolution(ref)
        if pyproject_result:
            logger.debug(f"Resolved {ref} to {pyproject_result.reference.resolved_model} from pyproject.toml")
            return pyproject_result

        # Strategy 1: Exact path match
        candidates = self._try_exact_match(widget_value)
        if len(candidates) == 1:
            ref.resolved_model = candidates[0]
            ref.resolution_confidence = 1.0
            logger.debug(f"Resolved {ref} to {candidates[0]} as exact match")
            return ModelResolutionResult(ref, candidates, "exact")

        # Strategy 2: Reconstruct paths for native loaders
        if self.model_config.is_model_loader_node(ref.node_type):
            paths = self.model_config.reconstruct_model_path(ref.node_type, widget_value)
            for path in paths:
                candidates = self._try_exact_match(path)
                if len(candidates) == 1:
                    ref.resolved_model = candidates[0]
                    ref.resolution_confidence = 0.9
                    logger.debug(f"Resolved {ref} to {candidates[0]} as reconstructed match")
                    return ModelResolutionResult(ref, candidates, "reconstructed")

        # Strategy 3: Case-insensitive match
        candidates = self._try_case_insensitive_match(widget_value)
        if len(candidates) == 1:
            ref.resolved_model = candidates[0]
            ref.resolution_confidence = 0.8
            logger.debug(f"Resolved {ref} to {candidates[0]} as case-insensitive match")
            return ModelResolutionResult(ref, candidates, "case_insensitive")

        # Strategy 4: Filename-only match
        filename = Path(widget_value).name
        candidates = self.model_index.find_by_filename(filename)
        if len(candidates) == 1:
            ref.resolved_model = candidates[0]
            ref.resolution_confidence = 0.7
            logger.debug(f"Resolved {ref} to {candidates[0]} as filename-only match")
            return ModelResolutionResult(ref, candidates, "filename")
        elif len(candidates) > 1:
            # Multiple matches - need disambiguation
            logger.debug(f"Resolved {ref} to {candidates} as filename-only match, ambiguous")
            return ModelResolutionResult(ref, candidates, "ambiguous")

        # No matches found
        logger.debug(f"No matches found in pyproject or model index for {ref}")
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

    def _try_pyproject_resolution(self, ref: "WorkflowModelRef") -> "ModelResolutionResult | None":
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
            workflow_entry = workflows.get(self.workflow_name, {})
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
                        models = self.model_index.find_model_by_hash(model_hash)
                        if models and len(models) > 0:
                            # Valid existing resolution - use it
                            model = models[0]
                            ref.resolved_model = model
                            ref.resolution_confidence = 1.0
                            logger.debug(f"Resolved from pyproject: {ref.widget_value} -> {model_hash[:8]}...")
                            return ModelResolutionResult(ref, [model], "pyproject")
                        else:
                            # Hash no longer valid in index, need fresh resolution
                            logger.debug(f"Pyproject hash {model_hash[:8]}... no longer in index for {ref.widget_value}")
                            return None

            # No matching node_id/widget_idx combination found
            return None

        except Exception as e:
            logger.debug(f"Error checking pyproject resolution: {e}")
            return None
