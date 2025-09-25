"""Node classification service for workflow analysis."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import TYPE_CHECKING

from ..logging.logging_config import get_logger
from ..configs.comfyui_builtin_nodes import COMFYUI_BUILTIN_NODES

if TYPE_CHECKING:
    from ..configs.model_config import ModelConfig
    from ..models.workflow import Workflow, WorkflowNode

logger = get_logger(__name__)

# Cache for builtin nodes (loaded once)
_BUILTIN_NODES: set[str] | None = None

@dataclass
class NodeClassifierResult:
    builtin_nodes: list[WorkflowNode]
    custom_nodes: list[WorkflowNode]
    
class NodeClassifier:
    """Service for classifying and categorizing workflow nodes."""

    def __init__(self):
        self.builtin_nodes = set(COMFYUI_BUILTIN_NODES["all_builtin_nodes"])

    def get_custom_node_types(self, workflow: Workflow) -> set[str]:
        """Get custom node types from workflow."""
        return workflow.node_types - self.builtin_nodes

    def get_model_loader_nodes(self, workflow: Workflow, model_config: ModelConfig) -> list[WorkflowNode]:
        """Get model loader nodes from workflow."""
        return [node for node in workflow.nodes.values() if model_config.is_model_loader_node(node.type)]

    def classify_nodes(self, workflow: Workflow) -> NodeClassifierResult:
        """Classify all nodes by type."""
        builtin_nodes: list[WorkflowNode] = []
        custom_nodes: list[WorkflowNode] = []

        for node in workflow.nodes.values():
            if node.type in self.builtin_nodes:
                builtin_nodes.append(node)
            else:
                custom_nodes.append(node)

        return NodeClassifierResult(builtin_nodes, custom_nodes)
