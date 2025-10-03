"""Simplified Environment - owns everything about a single ComfyUI environment."""
from __future__ import annotations

import subprocess
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING

from ..factories.uv_factory import create_uv_for_environment
from ..logging.logging_config import get_logger
from ..managers.git_manager import GitManager
from ..managers.model_path_manager import ModelPathManager
from ..managers.node_manager import NodeManager
from ..managers.pyproject_manager import PyprojectManager
from ..validation.resolution_tester import ResolutionTester
from ..analyzers.status_scanner import StatusScanner
from ..managers.uv_project_manager import UVProjectManager
from ..managers.workflow_manager import WorkflowManager
from ..models.environment import EnvironmentStatus
from ..models.sync import SyncResult
from ..models.shared import NodeInfo
from ..utils.common import run_command

if TYPE_CHECKING:
    from ..models.workflow import (
        CommitAnalysis,
        WorkflowSyncStatus,
        WorkflowDependencies,
        ResolutionResult,
        DetailedWorkflowStatus
    )
    from comfydock_core.models.protocols import (
        ModelResolutionStrategy,
        NodeResolutionStrategy,
    )
    from ..repositories.model_repository import ModelRepository
    from ..repositories.workspace_config_repository import WorkspaceConfigRepository
    from ..services.registry_data_manager import RegistryDataManager
    from .workspace import WorkspacePaths

logger = get_logger(__name__)


class Environment:
    """A ComfyUI environment - manages its own state through pyproject.toml."""

    def __init__(
        self,
        name: str,
        path: Path,
        workspace_paths: WorkspacePaths,
        model_repository: ModelRepository,
        workspace_config_manager: WorkspaceConfigRepository,
        registry_data_manager: RegistryDataManager
    ):
        self.name = name
        self.path = path
        self.workspace_paths = workspace_paths
        self.model_repository = model_repository
        self.workspace_config_manager = workspace_config_manager
        self.registry_data_manager = registry_data_manager

        # Workspace-level paths
        self.global_models_path = self.workspace_config_manager.get_models_directory()

        # Core paths
        self.cec_path = path / ".cec"
        self.pyproject_path = self.cec_path / "pyproject.toml"
        self.comfyui_path = path / "ComfyUI"
        self.custom_nodes_path = self.comfyui_path / "custom_nodes"
        self.venv_path = path / ".venv"
        self.models_path = self.comfyui_path / "models"

        # Workflow paths
        self.workflows_active_path = self.comfyui_path / "user" / "default" / "workflows"
        self.workflows_cec_path = self.cec_path / "workflows"

    ## Cached properties ##

    @cached_property
    def uv_manager(self) -> UVProjectManager:
        return create_uv_for_environment(
            self.workspace_paths.root,
            cec_path=self.cec_path,
            venv_path=self.venv_path,
        )

    @cached_property
    def pyproject(self) -> PyprojectManager:
        return PyprojectManager(self.pyproject_path)

    @cached_property
    def node_lookup(self):
        from ..services.node_lookup_service import NodeLookupService
        return NodeLookupService(
            workspace_path=self.workspace_paths.root,
            cache_path=self.workspace_paths.cache,
        )

    @cached_property
    def resolution_tester(self) -> ResolutionTester:
        return ResolutionTester(self.workspace_paths.root)

    @cached_property
    def node_manager(self) -> NodeManager:
        return NodeManager(
            self.pyproject,
            self.uv_manager,
            self.node_lookup,
            self.resolution_tester,
            self.custom_nodes_path,
            self.registry_data_manager
        )

    @cached_property
    def model_path_manager(self) -> ModelPathManager:
        """Get model path manager."""
        return ModelPathManager(
            self.comfyui_path, self.global_models_path
        )

    @cached_property
    def workflow_manager(self) -> WorkflowManager:
        return WorkflowManager(
            self.comfyui_path,
            self.cec_path,
            self.pyproject,
            self.model_repository,
            self.registry_data_manager
        )

    @cached_property
    def git_manager(self) -> GitManager:
        return GitManager(self.cec_path)

    ## Public methods ##

    # =====================================================
    # Environment Management
    # =====================================================

    def status(self) -> EnvironmentStatus:
        """Get environment sync and git status."""
        # Each subsystem provides its complete status
        scanner = StatusScanner(
            comfyui_path=self.comfyui_path,
            venv_path=self.venv_path,
            uv=self.uv_manager,
            pyproject=self.pyproject
        )
        comparison = scanner.get_full_comparison()

        git_status = self.git_manager.get_status(self.pyproject)

        workflow_status = self.workflow_manager.get_full_status()

        # Assemble final status
        return EnvironmentStatus.create(
            comparison=comparison,
            git_status=git_status,
            workflow_status=workflow_status
        )

    def sync(
        self,
        dry_run: bool = False
    ) -> SyncResult:
        """Apply changes: sync packages and custom nodes with environment.

        Args:
            dry_run: If True, don't actually apply changes

        Returns:
            SyncResult with details of what was synced

        Raises:
            UVCommandError: If sync fails
        """
        result = SyncResult()

        logger.info("Syncing environment...")

        # Sync packages with UV
        try:
            self.uv_manager.sync_project(all_groups=True, dry_run=dry_run)
            result.packages_synced = True
        except Exception as e:
            logger.error(f"Package sync failed: {e}")
            result.errors.append(f"Package sync failed: {e}")
            result.success = False

        # Sync custom nodes to filesystem
        try:
            # TODO: Enhance node_manager to return what was changed
            self.node_manager.sync_nodes_to_filesystem()
            # For now, we just note it happened
        except Exception as e:
            logger.error(f"Node sync failed: {e}")
            result.errors.append(f"Node sync failed: {e}")
            result.success = False

        # No workflow sync in new architecture - workflows are handled separately

        # Sync model paths to ensure models are available
        try:
            self.model_path_manager.sync_model_paths()
            result.model_paths_configured = True
        except Exception as e:
            logger.warning(f"Failed to configure model paths: {e}")
            result.errors.append(f"Model path configuration failed: {e}")
            # Continue anyway - ComfyUI might still work

        if result.success:
            logger.info("Successfully synced environment")
        else:
            logger.warning(f"Sync completed with {len(result.errors)} errors")

        return result

    def rollback(self, target: str | None = None) -> None:
        """Rollback environment to a previous state - complete imperative operation.

        This is an atomic operation that:
        1. Snapshots current state
        2. Restores git files (pyproject.toml, uv.lock, workflows/)
        3. Reconciles nodes with full context
        4. Syncs Python packages
        5. Restores workflows to ComfyUI

        Args:
            target: Version identifier (e.g., "v1", "v2") or commit hash

        Raises:
            ValueError: If target version doesn't exist
            OSError: If git commands fail
        """
        # 1. Snapshot old state BEFORE git changes it
        old_nodes = self.pyproject.nodes.get_existing()

        # 2. Git operations (restore pyproject.toml, uv.lock, .cec/workflows/)
        if target:
            self.git_manager.rollback_to(target)
        else:
            self.git_manager.discard_uncommitted()

        # 3. Force reload pyproject after git changed it (reset lazy handlers)
        self.pyproject.reset_lazy_handlers()
        new_nodes = self.pyproject.nodes.get_existing()

        # 4. Reconcile nodes with full context (no git history needed!)
        self.node_manager.reconcile_nodes_for_rollback(old_nodes, new_nodes)

        # 5. Sync Python environment to match restored uv.lock
        self.uv_manager.sync_project(all_groups=True)

        # 6. Restore workflows from .cec to ComfyUI (overwrite active with tracked)
        self.workflow_manager.restore_all_from_cec()

        logger.info("Rollback complete")

    def get_versions(self, limit: int = 10) -> list[dict]:
        """Get simplified version history for this environment.

        Args:
            limit: Maximum number of versions to return

        Returns:
            List of version info dicts with keys: version, hash, message, date
        """
        return self.git_manager.get_version_history(limit)

    def sync_model_paths(self) -> dict | None:
        """Configure model paths for this environment.

        Returns:
            Configuration statistics dictionary
        """
        logger.info(f"Configuring model paths for environment '{self.name}'")
        return self.model_path_manager.sync_model_paths()

    # TODO wrap subprocess completed process instance
    def run(self, args: list[str] | None = None) -> subprocess.CompletedProcess:
        """Run ComfyUI in this environment.

        Args:
            args: Arguments to pass to ComfyUI

        Returns:
            CompletedProcess
        """
        python = self.uv_manager.python_executable
        cmd = [str(python), "main.py"] + (args or [])

        logger.info(f"Starting ComfyUI with: {' '.join(cmd)}")
        return run_command(cmd, cwd=self.comfyui_path, capture_output=False, timeout=None)

    # =====================================================
    # Node Management
    # =====================================================

    def add_node(self, identifier: str, is_local: bool = False, is_development: bool = False, no_test: bool = False, force: bool = False) -> NodeInfo:
        """Add a custom node to the environment.

        Raises:
            CDNodeNotFoundError: If node not found
            CDNodeConflictError: If node has dependency conflicts
            CDEnvironmentError: If node with same name already exists
        """
        return self.node_manager.add_node(identifier, is_local, is_development, no_test, force)

    def remove_node(self, identifier: str):
        """Remove a custom node.

        Returns:
            NodeRemovalResult: Details about the removal

        Raises:
            CDNodeNotFoundError: If node not found
        """
        return self.node_manager.remove_node(identifier)

    def update_node(self, identifier: str, confirmation_strategy=None, no_test: bool = False):
        """Update a node based on its source type.

        - Development nodes: Re-scan requirements.txt
        - Registry nodes: Update to latest version
        - Git nodes: Update to latest commit

        Args:
            identifier: Node identifier or name
            confirmation_strategy: Strategy for confirming updates (None = auto-confirm)
            no_test: Skip resolution testing

        Raises:
            CDNodeNotFoundError: If node not found
            CDEnvironmentError: If node cannot be updated
        """
        return self.node_manager.update_node(identifier, confirmation_strategy, no_test)

    def check_development_node_drift(self) -> dict[str, tuple[set[str], set[str]]]:
        """Check if development nodes have requirements drift.

        Returns:
            Dict mapping node_name -> (added_deps, removed_deps)
        """
        return self.node_manager.check_development_node_drift()

    # =====================================================
    # Workflow Management
    # =====================================================

    def list_workflows(self) -> WorkflowSyncStatus:
        """List all workflows categorized by sync status.

        Returns:
            Dict with 'new', 'modified', 'deleted', and 'synced' workflow names
        """
        return self.workflow_manager.get_workflow_sync_status()

    def analyze_workflow(self, name: str) -> ResolutionResult:
        """Analyze workflow dependencies - delegates to WorkflowManager.

        Args:
            name: Workflow name to analyze

        Returns:
            ResolutionResult with dependency and conflict analysis
        """
        result = self.workflow_manager.analyze_workflow(name)

        return self.workflow_manager.resolve_workflow(result)

    def resolve_workflow(self,
                        name: str,
                        resolution: ResolutionResult | None = None,
                        node_strategy: NodeResolutionStrategy | None = None,
                        model_strategy: ModelResolutionStrategy | None = None,
                        fix: bool = True) -> ResolutionResult:
        """Resolve workflow dependencies - orchestrates analysis and resolution.

        Args:
            name: Workflow name to resolve
            node_strategy: Strategy for resolving missing nodes
            model_strategy: Strategy for resolving ambiguous/missing models

        Returns:
            ResolutionResult with changes made
        """
        result = resolution
        if not result:
            # Analyze workflow
            analysis = self.workflow_manager.analyze_workflow(name)

            # Then do initial resolve
            result = self.workflow_manager.resolve_workflow(analysis)

        # Check if there are any unresolved issues
        if result.has_issues and fix:
            # Try to fix issues
            result = self.workflow_manager.fix_resolution(result, node_strategy, model_strategy)

        # Apply resolution to pyproject.toml
        self.workflow_manager.apply_resolution(result)
        return result

    def commit(self, message: str | None = None):
        """Commit changes to git repository.

        Args:
            message: Optional commit message

        Raises:
            OSError: If git commands fail
        """
        return self.git_manager.commit_all(message)

    def execute_commit(
        self,
        workflow_status: DetailedWorkflowStatus | None = None,
        message: str | None = None,
        node_strategy: NodeResolutionStrategy | None = None,
        model_strategy: ModelResolutionStrategy | None = None,
        allow_issues: bool = False,
    ) -> None:
        """Execute commit using cached or provided analysis.

        Args:
            message: Optional commit message
            node_strategy: Optional strategy for resolving missing nodes
            model_strategy: Optional strategy for resolving ambiguous/missing models
            allow_issues: Allow committing even with unresolved issues
        """
        # Copy workflows from ComfyUI to .cec before any analysis or commits
        logger.info("Copying workflows from ComfyUI to .cec...")
        copy_results = self.workflow_manager.copy_all_workflows()
        copied_count = len([r for r in copy_results.values() if r and r != "deleted"])
        logger.debug(f"Copied {copied_count} workflow(s)")

        # Use provided analysis or prepare a new one (after copying)
        if not workflow_status:
            workflow_status = self.workflow_manager.get_full_status()

        if workflow_status.is_commit_safe:
            logger.info("Committing all changes...")
            # Apply all resolutions to pyproject.toml
            self.workflow_manager.apply_all_resolution(workflow_status)
            # TODO: Create message if not provided
            self.commit(message)
            return

        # If not safe but allow_issues is True, commit anyway
        if allow_issues:
            logger.warning("Committing with unresolved issues (--allow-issues)")
            # Apply whatever resolutions we have
            self.workflow_manager.apply_all_resolution(workflow_status)
            self.commit(message)
            return

        # If issues found and strategies provided, resolve them
        is_commit_safe = True
        if node_strategy and model_strategy:
            logger.info("Resolving workflow issues before commit...")
            for workflow_analysis in workflow_status.analyzed_workflows:
                try:
                    result = self.workflow_manager.fix_resolution(
                        workflow_analysis.resolution, node_strategy, model_strategy
                    )
                    if not result.has_issues:
                        logger.info(f"Resolved issues in '{workflow_analysis.name}': {workflow_analysis.issue_summary}")
                    else:
                        logger.warning(f"Failed to resolve issues in '{workflow_analysis.name}': {result.summary}")
                        is_commit_safe = False
                except Exception as e:
                    logger.error(f"Failed to resolve '{workflow_analysis.name}': {e}")

        # Check if there are any actual changes to commit
        if is_commit_safe:
            logger.info("Committing all changes...")
            # Apply all resolutions to pyproject.toml
            self.workflow_manager.apply_all_resolution(workflow_status)
            # TODO: Create message if not provided
            self.commit(message)
            return

        logger.error("No changes to commit")

    def restore_workflow(self, name: str) -> bool:
        """Restore a workflow from .cec to ComfyUI directory.

        Args:
            name: Workflow name to restore

        Returns:
            True if successful, False if workflow not found
        """
        return self.workflow_manager.restore_from_cec(name)

    # =====================================================
    # Constraint Management
    # =====================================================

    def add_constraint(self, package: str) -> None:
        """Add a constraint dependency."""
        self.pyproject.uv_config.add_constraint(package)

    def remove_constraint(self, package: str) -> bool:
        """Remove a constraint dependency."""
        return self.pyproject.uv_config.remove_constraint(package)

    def list_constraints(self) -> list[str]:
        """List constraint dependencies."""
        return self.pyproject.uv_config.get_constraints()
