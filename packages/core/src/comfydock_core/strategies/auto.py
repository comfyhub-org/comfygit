"""Auto resolution strategies for workflow dependencies."""

from __future__ import annotations
from typing import TYPE_CHECKING

from comfydock_core.models.protocols import ModelResolutionStrategy, NodeResolutionStrategy

from ..models.shared import ModelWithLocation
from ..models.workflow import WorkflowNodeWidgetRef

if TYPE_CHECKING:
    from ..models.workflow import ResolvedNodePackage


class AutoNodeStrategy(NodeResolutionStrategy):
    """Automatic node resolution - makes best effort choices without user input."""

    def resolve_unknown_node(
        self, node_type: str, possible: list[ResolvedNodePackage]
    ) -> ResolvedNodePackage | None:
        """Pick the top suggestion by confidence, or first if tied."""
        if not possible:
            return None

        # Sort by confidence descending, then just pick first
        sorted_suggestions = sorted(
            possible, key=lambda s: s.match_confidence, reverse=True
        )

        return sorted_suggestions[0]

    def confirm_node_install(self, package: ResolvedNodePackage) -> bool:
        """Always confirm - we're making automated choices."""
        return True


class AutoModelStrategy(ModelResolutionStrategy):
    """Automatic model resolution - makes simple naive choices."""

    def resolve_ambiguous_model(
        self, reference: WorkflowNodeWidgetRef, candidates: list[ModelWithLocation]
    ) -> ModelWithLocation | None:
        """Pick the first candidate from the list."""
        if not candidates:
            return None
        return candidates[0]

    def handle_missing_model(self, reference: WorkflowNodeWidgetRef) -> str | None:
        """Skip missing models - return None."""
        return None
