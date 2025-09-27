"""Resolution strategy protocols for dependency injection."""
from __future__ import annotations
from typing import TYPE_CHECKING,Protocol, Optional, List
from abc import abstractmethod

from .workflow import WorkflowNodeWidgetRef
from .shared import ModelWithLocation

if TYPE_CHECKING:
    from ..models.workflow import ResolvedNodePackage

class NodeResolutionStrategy(Protocol):
    """Protocol for resolving unknown custom nodes."""

    def resolve_unknown_node(
        self, node_type: str, possible: List[ResolvedNodePackage]
    ) -> ResolvedNodePackage | None:
        """Given node type and suggestions, return package ID or None.

        Args:
            node_type: The unknown node type (e.g. "MyCustomNode")
            suggestions: List of registry suggestions with package_id, confidence

        Returns:
            Package ID to install or None to skip
        """
        ...

    def confirm_node_install(self, package: ResolvedNodePackage) -> bool:
        """Confirm whether to install a node package.

        Args:
            package_id: Registry package ID
            node_type: The node type being resolved

        Returns:
            True to install, False to skip
        """
        ...


class ModelResolutionStrategy(Protocol):
    """Protocol for resolving model references."""

    def resolve_ambiguous_model(
        self, reference: WorkflowNodeWidgetRef, candidates: List[ModelWithLocation]
    ) -> Optional[ModelWithLocation]:
        """Choose from multiple model matches.

        Args:
            reference: The model reference from workflow
            candidates: List of possible model matches

        Returns:
            Chosen model or None to skip
        """
        ...

    def handle_missing_model(self, reference: WorkflowNodeWidgetRef) -> Optional[str]:
        """Handle completely missing model.

        Args:
            reference: The model reference that couldn't be found

        Returns:
            Download URL or None to skip
        """
        ...
