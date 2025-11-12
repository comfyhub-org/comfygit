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

@dataclass
class NodeClassifierResultMulti:
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
    
    @staticmethod
    def classify_single_node(node: WorkflowNode) -> str:
        """Classify a single node by type."""
        all_builtin_nodes = set(COMFYUI_BUILTIN_NODES["all_builtin_nodes"])
        if node.type in all_builtin_nodes:
            return "builtin"
        return "custom"
    
    @staticmethod
    def classify_nodes(workflow: Workflow) -> NodeClassifierResultMulti:
        """Classify all nodes by type."""
        all_builtin_nodes = set(COMFYUI_BUILTIN_NODES["all_builtin_nodes"])
        builtin_nodes: list[WorkflowNode] = []
        custom_nodes: list[WorkflowNode] = []

        for node in workflow.nodes.values():
            if node.type in all_builtin_nodes:
                builtin_nodes.append(node)
            else:
                custom_nodes.append(node)

        return NodeClassifierResultMulti(builtin_nodes, custom_nodes)
