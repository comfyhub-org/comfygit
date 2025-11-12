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


class SyncCallbacks(Protocol):
    """Protocol for sync operation callbacks."""

    def on_dependency_group_start(self, group_name: str, is_optional: bool) -> None:
        """Called when starting to install a dependency group.

        Args:
            group_name: Name of the dependency group
            is_optional: Whether this is an optional group
        """
        ...

    def on_dependency_group_complete(self, group_name: str, success: bool, error: str | None = None) -> None:
        """Called when dependency group installation completes.

        Args:
            group_name: Name of the dependency group
            success: Whether the installation succeeded
            error: Error message if failed (None if succeeded)
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

    def on_dependency_group_start(self, group_name: str, is_optional: bool) -> None:
        """Called when starting to install a dependency group.

        Args:
            group_name: Name of the dependency group
            is_optional: Whether this is an optional group
        """
        ...

    def on_dependency_group_complete(self, group_name: str, success: bool, error: str | None = None) -> None:
        """Called when dependency group installation completes.

        Args:
            group_name: Name of the dependency group
            success: Whether the installation succeeded
            error: Error message if failed (None if succeeded)
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

    def on_download_batch_start(self, count: int) -> None:
        """Called when batch model downloads start.

        Args:
            count: Number of models to download
        """
        ...

    def on_download_file_start(self, name: str, idx: int, total: int) -> None:
        """Called when individual model download starts.

        Args:
            name: Model filename
            idx: Current file index (1-based)
            total: Total number of files
        """
        ...

    def on_download_file_progress(self, downloaded: int, total: int | None) -> None:
        """Called during model download progress.

        Args:
            downloaded: Bytes downloaded so far
            total: Total bytes (None if unknown)
        """
        ...

    def on_download_file_complete(self, name: str, success: bool, error: str | None) -> None:
        """Called when model download completes.

        Args:
            name: Model filename
            success: Whether download succeeded
            error: Error message if failed
        """
        ...

    def on_download_batch_complete(self, success: int, total: int) -> None:
        """Called when all downloads complete.

        Args:
            success: Number of successful downloads
            total: Total number of downloads attempted
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
