"""Simplified Environment - owns everything about a single ComfyUI environment."""
from __future__ import annotations

import subprocess
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING

from ..factories.uv_factory import create_uv_for_environment
from ..logging.logging_config import get_logger
from ..managers.git_manager import GitManager
from ..managers.model_symlink_manager import ModelSymlinkManager
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
        RollbackStrategy,
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
    def model_symlink_manager(self) -> ModelSymlinkManager:
        """Get model symlink manager."""
        return ModelSymlinkManager(
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

        workflow_status = self.workflow_manager.get_workflow_status()

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

        # Ensure model symlink exists
        try:
            self.model_symlink_manager.create_symlink()
            result.model_paths_configured = True
        except Exception as e:
            logger.warning(f"Failed to ensure model symlink: {e}")
            result.errors.append(f"Model symlink configuration failed: {e}")
            # Continue anyway - symlink might already exist from environment creation

        if result.success:
            logger.info("Successfully synced environment")
        else:
            logger.warning(f"Sync completed with {len(result.errors)} errors")

        return result

    def rollback(
        self,
        target: str | None = None,
        force: bool = False,
        strategy: RollbackStrategy | None = None
    ) -> None:
        """Rollback environment to a previous state - checkpoint-style instant restoration.

        This is an atomic operation that:
        1. Checks for uncommitted changes (git + workflows)
        2. Snapshots current state
        3. Restores git files (pyproject.toml, uv.lock, workflows/)
        4. Reconciles nodes with full context
        5. Syncs Python packages
        6. Restores workflows to ComfyUI
        7. Auto-commits the rollback as a new version

        Design: Checkpoint-style rollback (like video game saves)
        - Rollback = instant teleportation to old state
        - Auto-commits as new version (preserves history)
        - Requires strategy confirmation or --force to discard uncommitted changes
        - Full history preserved (v1→v2→v3→v4[rollback to v2]→v5)

        Args:
            target: Version identifier (e.g., "v1", "v2") or commit hash
                   If None, discards uncommitted changes
            force: If True, discard uncommitted changes without confirmation
            strategy: Optional strategy for confirming destructive rollback
                     If None and changes exist, raises error (safe default)

        Raises:
            ValueError: If target version doesn't exist
            OSError: If git commands fail
            CDEnvironmentError: If uncommitted changes exist and no strategy/force
        """
        from comfydock_core.models.exceptions import CDEnvironmentError

        # 1. Check for ALL uncommitted changes (both git and workflows)
        if not force:
            has_git_changes = self.git_manager.has_uncommitted_changes()
            status = self.status()
            has_workflow_changes = status.workflow.sync_status.has_changes

            if has_git_changes or has_workflow_changes:
                # Changes detected - need confirmation or force
                if strategy is None:
                    # No strategy provided - strict mode, raise error
                    raise CDEnvironmentError(
                        "Cannot rollback with uncommitted changes.\n"
                        "Uncommitted changes detected:\n"
                        + (f"  • Git changes in .cec/\n" if has_git_changes else "")
                        + (f"  • Workflow changes in ComfyUI\n" if has_workflow_changes else "")
                    )

                # Strategy provided - ask for confirmation
                if not strategy.confirm_destructive_rollback(
                    git_changes=has_git_changes,
                    workflow_changes=has_workflow_changes
                ):
                    raise CDEnvironmentError("Rollback cancelled by user")

        # 2. Snapshot old state BEFORE git changes it
        old_nodes = self.pyproject.nodes.get_existing()

        # 3. Git operations (restore pyproject.toml, uv.lock, .cec/workflows/)
        if target:
            # Get version name for commit message
            target_version = target
            self.git_manager.rollback_to(target, safe=False, force=True)  # Always force after confirmation
        else:
            # Empty rollback = discard uncommitted changes (rollback to current)
            target_version = "HEAD"  # For commit message consistency
            self.git_manager.discard_uncommitted()

        # 4. Check if there were any changes BEFORE doing expensive operations
        # This handles "rollback to current version" case
        had_changes = self.git_manager.has_uncommitted_changes()

        # 5. Force reload pyproject after git changed it (reset lazy handlers)
        self.pyproject.reset_lazy_handlers()
        new_nodes = self.pyproject.nodes.get_existing()

        # 6. Reconcile nodes with full context (no git history needed!)
        self.node_manager.reconcile_nodes_for_rollback(old_nodes, new_nodes)

        # 7. Sync Python environment to match restored uv.lock
        # Note: This may create/modify files (uv.lock updates, cache, etc.)
        self.uv_manager.sync_project(all_groups=True)

        # 8. Restore workflows from .cec to ComfyUI (overwrite active with tracked)
        self.workflow_manager.restore_all_from_cec()

        # 9. Auto-commit only if there were changes initially (checkpoint-style)
        # We check had_changes (before uv sync) not current changes (after uv sync)
        # This prevents committing when rolling back to current version
        if had_changes:
            self.git_manager.commit_all(f"Rollback to {target_version}")
            logger.info(f"Rollback complete: created new version from {target_version}")
        else:
            logger.info(f"Rollback complete: already at {target_version} (no changes)")

    def get_versions(self, limit: int = 10) -> list[dict]:
        """Get simplified version history for this environment.

        Args:
            limit: Maximum number of versions to return

        Returns:
            List of version info dicts with keys: version, hash, message, date
        """
        return self.git_manager.get_version_history(limit)

    def sync_model_paths(self) -> dict | None:
        """Ensure model symlink is configured for this environment.

        Returns:
            Status dictionary
        """
        logger.info(f"Configuring model symlink for environment '{self.name}'")
        try:
            self.model_symlink_manager.create_symlink()
            return {
                "status": "linked",
                "target": str(self.global_models_path),
                "link": str(self.models_path)
            }
        except Exception as e:
            logger.error(f"Failed to configure model symlink: {e}")
            raise

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

    def resolve_workflow(self,
                        name: str,
                        node_strategy: NodeResolutionStrategy | None = None,
                        model_strategy: ModelResolutionStrategy | None = None,
                        fix: bool = True) -> ResolutionResult:
        """Resolve workflow dependencies - orchestrates analysis and resolution.

        Args:
            name: Workflow name to resolve
            node_strategy: Strategy for resolving missing nodes
            model_strategy: Strategy for resolving ambiguous/missing models
            fix: Attempt to fix unresolved issues with strategies

        Returns:
            ResolutionResult with changes made
            
        Raises:
            FileNotFoundError: If workflow not found
        """
        # Analyze workflow
        analysis = self.workflow_manager.analyze_workflow(name)

        # Then do initial resolve
        result = self.workflow_manager.resolve_workflow(analysis)

        # Apply auto-resolutions (idempotent, only writes auto-resolved items)
        self.workflow_manager.apply_resolution(result)

        # Check if there are any unresolved issues
        if result.has_issues and fix:
            # Fix issues with strategies (progressive writes: models AND nodes saved immediately)
            result = self.workflow_manager.fix_resolution(
                result,
                node_strategy,
                model_strategy
            )

        return result

    def get_uninstalled_nodes(self) -> list[str]:
        """Get list of node package IDs referenced in workflows but not installed.

        Compares nodes referenced in workflow sections against installed nodes
        to identify which nodes need installation.

        Returns:
            List of node package IDs that are referenced in workflows but not installed.
            Empty list if all workflow nodes are already installed.

        Example:
            >>> env.resolve_workflow("my_workflow")
            >>> missing = env.get_uninstalled_nodes()
            >>> # ['rgthree-comfy', 'comfyui-depthanythingv2', ...]
        """
        # Get all node IDs referenced in workflows
        workflow_node_ids = set()
        workflows = self.pyproject.workflows.get_all_with_resolutions()

        for workflow_data in workflows.values():
            node_list = workflow_data.get('nodes', [])
            workflow_node_ids.update(node_list)

        logger.debug(f"Workflow node references: {workflow_node_ids}")

        # Get installed node IDs
        installed_nodes = self.pyproject.nodes.get_existing()
        installed_node_ids = set(installed_nodes.keys())
        logger.debug(f"Installed nodes: {installed_node_ids}")

        # Find nodes referenced in workflows but not installed
        uninstalled_ids = list(workflow_node_ids - installed_node_ids)
        logger.debug(f"Uninstalled nodes: {uninstalled_ids}")

        return uninstalled_ids

    def has_committable_changes(self) -> bool:
        """Check if there are any committable changes (workflows OR git).

        This is the clean API for determining if a commit is possible.
        Checks both workflow file sync status AND git uncommitted changes.

        Returns:
            True if there are committable changes, False otherwise
        """
        # Check workflow file changes (new/modified/deleted workflows)
        workflow_status = self.workflow_manager.get_workflow_status()
        has_workflow_changes = workflow_status.sync_status.has_changes

        # Check git uncommitted changes (pyproject.toml, uv.lock, etc.)
        has_git_changes = self.git_manager.has_uncommitted_changes()

        return has_workflow_changes or has_git_changes

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
        allow_issues: bool = False,
    ) -> None:
        """Execute commit using cached or provided analysis.

        Args:
            message: Optional commit message
            allow_issues: Allow committing even with unresolved issues
        """
        # Use provided analysis or prepare a new one
        if not workflow_status:
            workflow_status = self.workflow_manager.get_workflow_status()
            
        def _safe_commit():
            # Copy workflows AFTER resolution (so .cec gets updated paths)
            logger.info("Copying workflows from ComfyUI to .cec...")
            copy_results = self.workflow_manager.copy_all_workflows()
            copied_count = len([r for r in copy_results.values() if r and r != "deleted"])
            logger.debug(f"Copied {copied_count} workflow(s)")
            # TODO: Create message if not provided
            self.commit(message)
            
        # TODO: Check if we need to again resolve and apply resolutions here

        if workflow_status.is_commit_safe:
            logger.info("Committing all changes...")
            _safe_commit()
            return

        # If not safe but allow_issues is True, commit anyway
        if allow_issues:
            logger.warning("Committing with unresolved issues (--allow-issues)")
            _safe_commit()
            return

        logger.error("No changes to commit")

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
