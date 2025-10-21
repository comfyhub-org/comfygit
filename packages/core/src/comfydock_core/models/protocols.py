"""Resolution strategy protocols for dependency injection."""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from .workflow import (
    ModelResolutionContext,
    NodeResolutionContext,
    ResolvedModel,
    WorkflowNodeWidgetRef,
)

if TYPE_CHECKING:
    from ..models.workflow import ResolvedNodePackage

class NodeResolutionStrategy(Protocol):
    """Protocol for resolving unknown custom nodes."""

    def resolve_unknown_node(
        self,
        node_type: str,
        possible: list[ResolvedNodePackage],
        context: NodeResolutionContext
    ) -> ResolvedNodePackage | None:
        """Given node type and suggestions, return package ID or None.

        Args:
            node_type: The unknown node type (e.g. "MyCustomNode")
            possible: List of registry suggestions with package_id, confidence
            context: Resolution context with search function and installed packages

        Returns:
            ResolvedNodePackage to install or None to skip
        """
        ...

    def confirm_node_install(self, package: ResolvedNodePackage) -> bool:
        """Confirm whether to install a node package.

        Args:
            package: Resolved node package to confirm

        Returns:
            True to install, False to skip
        """
        ...


class ModelResolutionStrategy(Protocol):
    """Protocol for resolving model references."""

    def resolve_model(
        self,
        reference: WorkflowNodeWidgetRef,
        candidates: list[ResolvedModel],
        context: ModelResolutionContext,
    ) -> ResolvedModel | None:
        """Resolve a model reference (ambiguous or missing).

        Args:
            reference: The model reference from workflow
            candidates: List of potential matches (may be empty for missing models)
            context: Resolution context with search function and workflow info

        Returns:
            ResolvedModel with resolved_model filled (or None for optional unresolved)
            None to skip resolution

        Note:
            - For resolved models: Return ResolvedModel with resolved_model set
            - For optional unresolved: Return ResolvedModel with resolved_model=None, is_optional=True
            - To skip: Return None
        """
        ...


class RollbackStrategy(Protocol):
    """Protocol for confirming destructive rollback operations."""

    def confirm_destructive_rollback(
        self,
        git_changes: bool,
        workflow_changes: bool,
    ) -> bool:
        """Confirm rollback that will discard uncommitted changes.

        Args:
            git_changes: Whether there are uncommitted git changes in .cec/
            workflow_changes: Whether there are modified/new/deleted workflows

        Returns:
            True to proceed with rollback, False to cancel
        """
        ...


class ImportCallbacks(Protocol):
    """Protocol for import operation callbacks."""

    def on_phase(self, phase: str, description: str) -> None:
        """Called when entering a new import phase.

        Args:
            phase: Phase identifier (e.g., "extract", "install_deps", "sync_nodes")
            description: Human-readable phase description
        """
        ...

    def on_workflow_copied(self, workflow_name: str) -> None:
        """Called when a workflow file is copied.

        Args:
            workflow_name: Name of the workflow file
        """
        ...

    def on_node_installed(self, node_name: str) -> None:
        """Called when a custom node is installed.

        Args:
            node_name: Name of the installed node
        """
        ...

    def on_workflow_resolved(self, workflow_name: str, downloads: int) -> None:
        """Called when a workflow is resolved.

        Args:
            workflow_name: Name of the workflow
            downloads: Number of models downloaded for this workflow
        """
        ...

    def on_error(self, error: str) -> None:
        """Called when a non-fatal error occurs.

        Args:
            error: Error message
        """
        ...

    def on_download_failures(self, failures: list[tuple[str, str]]) -> None:
        """Called when model downloads fail during import.

        Args:
            failures: List of (workflow_name, model_filename) tuples
        """
        ...


class ExportCallbacks(Protocol):
    """Protocol for export operation callbacks."""

    def on_models_without_sources(self, models: list) -> None:
        """Called when models are missing source URLs.

        Args:
            models: List of ModelWithoutSourceInfo instances
        """
        ...
