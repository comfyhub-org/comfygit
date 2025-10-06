"""Workflow dependency analysis and resolution manager."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, List

from comfydock_core.repositories.workflow_repository import WorkflowRepository

from ..logging.logging_config import get_logger
from .node_classifier import NodeClassifier
from ..configs.model_config import ModelConfig
from ..models.workflow import (
    WorkflowNodeWidgetRef,
    WorkflowNode,
    WorkflowDependencies,
)

logger = get_logger(__name__)

class WorkflowDependencyParser:
    """Manages workflow dependency analysis and resolution."""

    def __init__(
        self,
        workflow_path: Path,
        model_config: ModelConfig | None = None
    ):

        self.model_config = model_config or ModelConfig.load()

        # Load workflow
        self.workflow = WorkflowRepository.load(workflow_path)
        logger.debug(f"Loaded workflow {self.workflow}")

        # Store workflow name for pyproject lookup
        self.workflow_name = workflow_path.stem

    def analyze_dependencies(self) -> WorkflowDependencies:
        """Analyze workflow for model information and node types"""
        try:
            nodes_data = self.workflow.nodes

            if not nodes_data:
                logger.warning("No nodes found in workflow")
                return WorkflowDependencies(workflow_name=self.workflow_name)
            
            found_models: list[WorkflowNodeWidgetRef] = []
            builtin_nodes: list[WorkflowNode] = []
            missing_nodes: list[WorkflowNode] = []

            # Analyze and resolve models and nodes
            for node_info in nodes_data.values():
                node_classification = NodeClassifier.classify_single_node(node_info)
                model_refs = self._extract_model_node_refs(node_info)
                
                found_models.extend(model_refs)
                
                if node_classification == 'builtin':
                    builtin_nodes.append(node_info)
                else:
                    missing_nodes.append(node_info)
                    
            # Log results
            if found_models:
                logger.debug(f"Found {len(found_models)} model references in workflow")
            if builtin_nodes:
                logger.debug(f"Found {len(builtin_nodes)} builtin nodes in workflow")
            if missing_nodes:
                logger.debug(f"Found {len(missing_nodes)} missing nodes in workflow")
                
            return WorkflowDependencies(
                workflow_name=self.workflow_name,
                found_models=found_models,
                builtin_nodes=builtin_nodes,
                non_builtin_nodes=missing_nodes
            )

        except Exception as e:
            logger.error(f"Failed to analyze workflow dependencies: {e}")
            return WorkflowDependencies(workflow_name=self.workflow_name)

    def _extract_model_node_refs(self, node_info: WorkflowNode) -> List["WorkflowNodeWidgetRef"]:
        """Extract possible model references from a single node"""

        refs = []

        # Handle multi-model nodes specially
        if node_info.type == "CheckpointLoader":
            # Index 0: checkpoint, Index 1: config
            widgets = node_info.widgets_values or []
            if len(widgets) > 0 and widgets[0]:
                refs.append(WorkflowNodeWidgetRef(
                    node_id=node_info.id,
                    node_type=node_info.type,
                    widget_index=0,
                    widget_value=widgets[0]
                ))
            if len(widgets) > 1 and widgets[1]:
                refs.append(WorkflowNodeWidgetRef(
                    node_id=node_info.id,
                    node_type=node_info.type,
                    widget_index=1,
                    widget_value=widgets[1]
                ))

        # Standard single-model loaders
        elif self.model_config.is_model_loader_node(node_info.type):
            widget_idx = self.model_config.get_widget_index_for_node(node_info.type)
            widgets = node_info.widgets_values or []
            if widget_idx < len(widgets) and widgets[widget_idx]:
                refs.append(WorkflowNodeWidgetRef(
                    node_id=node_info.id,
                    node_type=node_info.type,
                    widget_index=widget_idx,
                    widget_value=widgets[widget_idx]
                ))

        # Pattern match all widgets for custom nodes
        else:
            widgets = node_info.widgets_values or []
            for idx, value in enumerate(widgets):
                if self._looks_like_model(value):
                    refs.append(WorkflowNodeWidgetRef(
                        node_id=node_info.id,
                        node_type=node_info.type,
                        widget_index=idx,
                        widget_value=value
                    ))

        return refs
    
    def _looks_like_model(self, value: Any) -> bool:
        """Check if value looks like a model path"""
        if not isinstance(value, str):
            return False
        extensions = self.model_config.default_extensions
        return any(value.endswith(ext) for ext in extensions)
