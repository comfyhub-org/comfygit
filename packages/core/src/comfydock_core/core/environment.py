"""Simplified Environment - owns everything about a single ComfyUI environment."""
from __future__ import annotations

import shutil
import subprocess
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING

from ..analyzers.status_scanner import StatusScanner
from ..factories.uv_factory import create_uv_for_environment
from ..logging.logging_config import get_logger
from ..managers.git_manager import GitManager
from ..managers.model_symlink_manager import ModelSymlinkManager
from ..managers.node_manager import NodeManager
from ..managers.pyproject_manager import PyprojectManager
from ..managers.uv_project_manager import UVProjectManager
from ..managers.workflow_manager import WorkflowManager
from ..models.environment import EnvironmentStatus
from ..models.shared import ModelSourceResult, ModelSourceStatus, NodeInfo
from ..models.sync import SyncResult
from ..services.model_downloader import DownloadRequest
from ..utils.common import run_command
from ..validation.resolution_tester import ResolutionTester

if TYPE_CHECKING:
    from comfydock_core.models.protocols import (
        ExportCallbacks,
        ImportCallbacks,
        ModelResolutionStrategy,
        NodeResolutionStrategy,
        RollbackStrategy,
    )

    from ..models.workflow import (
        BatchDownloadCallbacks,
        DetailedWorkflowStatus,
        ResolutionResult,
        WorkflowSyncStatus,
    )
    from ..repositories.model_repository import ModelRepository
    from ..repositories.node_mappings_repository import NodeMappingsRepository
    from ..repositories.workspace_config_repository import WorkspaceConfigRepository
    from ..services.model_downloader import ModelDownloader
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
        node_mapping_repository: NodeMappingsRepository,
        workspace_config_manager: WorkspaceConfigRepository,
        model_downloader: ModelDownloader,
    ):
        self.name = name
        self.path = path
        self.workspace_paths = workspace_paths
        self.model_repository = model_repository
        self.node_mapping_repository = node_mapping_repository
        self.workspace_config_manager = workspace_config_manager
        self.model_downloader = model_downloader

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
            node_mappings_repository=self.node_mapping_repository,
            workspace_config_repository=self.workspace_config_manager,
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
            self.node_mapping_repository
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
            self.node_mapping_repository,
            self.model_downloader
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

        # Detect missing models
        missing_models = self.detect_missing_models()

        # Assemble final status
        return EnvironmentStatus.create(
            comparison=comparison,
            git_status=git_status,
            workflow_status=workflow_status,
            missing_models=missing_models
        )

    def sync(
        self,
        dry_run: bool = False,
        model_strategy: str = "skip",
        model_callbacks: "BatchDownloadCallbacks | None" = None,
        node_callbacks: "NodeInstallCallbacks | None" = None,
        remove_extra_nodes: bool = True
    ) -> SyncResult:
        """Apply changes: sync packages, nodes, workflows, and models with environment.

        Args:
            dry_run: If True, don't actually apply changes
            model_strategy: Model download strategy - "all", "required", or "skip" (default: skip)
            model_callbacks: Optional callbacks for model download progress
            node_callbacks: Optional callbacks for node installation progress
            remove_extra_nodes: If True, remove extra nodes. If False, only warn (default: True)

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
            # Pass remove_extra flag (default True for aggressive repair behavior)
            self.node_manager.sync_nodes_to_filesystem(
                remove_extra=remove_extra_nodes and not dry_run,
                callbacks=node_callbacks
            )
            # For now, we just note it happened
        except Exception as e:
            logger.error(f"Node sync failed: {e}")
            result.errors.append(f"Node sync failed: {e}")
            result.success = False

        # Restore workflows from .cec/ to ComfyUI (for git pull workflow)
        if not dry_run:
            try:
                self.workflow_manager.restore_all_from_cec()
                logger.info("Restored workflows from .cec/")
            except Exception as e:
                logger.warning(f"Failed to restore workflows: {e}")
                result.errors.append(f"Workflow restore failed: {e}")
                # Non-fatal - continue

        # Handle missing models
        if not dry_run and model_strategy != "skip":
            try:
                # Reuse existing import machinery
                workflows_with_intents = self.prepare_import_with_model_strategy(
                    strategy=model_strategy
                )

                if workflows_with_intents:
                    logger.info(f"Downloading models for {len(workflows_with_intents)} workflow(s)")

                    # Resolve each workflow (triggers downloads)
                    from ..strategies.auto import AutoModelStrategy, AutoNodeStrategy

                    for workflow_name in workflows_with_intents:
                        try:
                            logger.debug(f"Resolving workflow: {workflow_name}")

                            # Resolve workflow (analyzes and prepares downloads)
                            resolution_result = self.resolve_workflow(
                                name=workflow_name,
                                model_strategy=AutoModelStrategy(),
                                node_strategy=AutoNodeStrategy(),
                                download_callbacks=model_callbacks
                            )

                            # Track downloads from actual download results (not stale ResolvedModel objects)
                            # Note: Download results are populated by _execute_pending_downloads() during resolve_workflow()
                            if hasattr(resolution_result, '_download_results'):
                                for dr in resolution_result._download_results:
                                    if dr["success"]:
                                        result.models_downloaded.append(dr["filename"])
                                    else:
                                        result.models_failed.append((dr["filename"], dr.get("error", "Download failed")))

                        except Exception as e:
                            logger.error(f"Failed to resolve {workflow_name}: {e}", exc_info=True)
                            result.errors.append(f"Failed to resolve {workflow_name}: {e}")

            except Exception as e:
                logger.warning(f"Model download failed: {e}", exc_info=True)
                result.errors.append(f"Model download failed: {e}")
                # Non-fatal - continue

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
                        + ("  • Git changes in .cec/\n" if has_git_changes else "")
                        + ("  • Workflow changes in ComfyUI\n" if has_workflow_changes else "")
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

    def add_node(self, identifier: str, is_development: bool = False, no_test: bool = False, force: bool = False) -> NodeInfo:
        """Add a custom node to the environment.

        Raises:
            CDNodeNotFoundError: If node not found
            CDNodeConflictError: If node has dependency conflicts
            CDEnvironmentError: If node with same name already exists
        """
        return self.node_manager.add_node(identifier, is_development, no_test, force)

    def install_nodes_with_progress(
        self,
        node_ids: list[str],
        callbacks: "NodeInstallCallbacks | None" = None
    ) -> tuple[int, list[tuple[str, str]]]:
        """Install multiple nodes with callback support for progress tracking.

        Args:
            node_ids: List of node identifiers to install
            callbacks: Optional callbacks for progress feedback

        Returns:
            Tuple of (success_count, failed_nodes)
            where failed_nodes is a list of (node_id, error_message) tuples

        Raises:
            CDNodeNotFoundError: If a node is not found
        """
        if callbacks and callbacks.on_batch_start:
            callbacks.on_batch_start(len(node_ids))

        success_count = 0
        failed = []

        for idx, node_id in enumerate(node_ids):
            if callbacks and callbacks.on_node_start:
                callbacks.on_node_start(node_id, idx + 1, len(node_ids))

            try:
                self.add_node(node_id)
                success_count += 1
                if callbacks and callbacks.on_node_complete:
                    callbacks.on_node_complete(node_id, True, None)
            except Exception as e:
                failed.append((node_id, str(e)))
                if callbacks and callbacks.on_node_complete:
                    callbacks.on_node_complete(node_id, False, str(e))

        if callbacks and callbacks.on_batch_complete:
            callbacks.on_batch_complete(success_count, len(node_ids))

        return success_count, failed

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

    def resolve_workflow(
        self,
        name: str,
        node_strategy: NodeResolutionStrategy | None = None,
        model_strategy: ModelResolutionStrategy | None = None,
        fix: bool = True,
        download_callbacks: BatchDownloadCallbacks | None = None
    ) -> ResolutionResult:
        """Resolve workflow dependencies - orchestrates analysis and resolution.

        Args:
            name: Workflow name to resolve
            node_strategy: Strategy for resolving missing nodes
            model_strategy: Strategy for resolving ambiguous/missing models
            fix: Attempt to fix unresolved issues with strategies
            download_callbacks: Optional callbacks for batch download progress (CLI provides)

        Returns:
            ResolutionResult with changes made

        Raises:
            FileNotFoundError: If workflow not found
        """
        # Analyze workflow
        analysis = self.workflow_manager.analyze_workflow(name)

        # Then do initial resolve
        result = self.workflow_manager.resolve_workflow(analysis)

        # Apply auto-resolutions (reconcile with pyproject.toml)
        self.workflow_manager.apply_resolution(result)

        # Check if there are any unresolved issues
        if result.has_issues and fix:
            # Fix issues with strategies (progressive writes: models AND nodes saved immediately)
            result = self.workflow_manager.fix_resolution(
                result,
                node_strategy,
                model_strategy
            )

        # Execute pending downloads if any download intents exist
        if result.has_download_intents:
            download_results = self._execute_pending_downloads(result, download_callbacks)
            # Attach results for tracking (used by sync())
            result._download_results = download_results

        return result

    def get_uninstalled_nodes(self, workflow_name: str | None = None) -> list[str]:
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
        if workflow_name:
            if workflow := self.pyproject.workflows.get_workflow(workflow_name):
                workflows = {workflow_name: workflow}
            else:
                logger.warning(f"Workflow '{workflow_name}' not found")
                return []
        else:
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

        # Check if there are any changes to commit (workflows OR git)
        has_workflow_changes = workflow_status.sync_status.has_changes
        has_git_changes = self.git_manager.has_uncommitted_changes()

        if not has_workflow_changes and not has_git_changes:
            logger.error("No changes to commit")
            return

        # Check if changes are safe to commit (no unresolved issues)
        if not workflow_status.is_commit_safe and not allow_issues:
            logger.error("Cannot commit with unresolved issues. Use --allow-issues to force.")
            return

        # Apply auto-resolutions to pyproject.toml for workflows with changes
        logger.info("Committing all changes...")
        for wf_analysis in workflow_status.analyzed_workflows:
            if wf_analysis.sync_state in ("new", "modified"):
                # Apply resolution results to pyproject (writes newly resolved models)
                self.workflow_manager.apply_resolution(wf_analysis.resolution)

        logger.info("Copying workflows from ComfyUI to .cec...")
        copy_results = self.workflow_manager.copy_all_workflows()
        copied_count = len([r for r in copy_results.values() if r and r != "deleted"])
        logger.debug(f"Copied {copied_count} workflow(s)")

        # Clean up deleted workflows from pyproject.toml
        if workflow_status.sync_status.deleted:
            logger.info("Cleaning up deleted workflows from pyproject.toml...")
            removed_count = self.pyproject.workflows.remove_workflows(
                workflow_status.sync_status.deleted
            )
            logger.debug(f"Removed {removed_count} workflow section(s)")

            # Clean up orphaned models (must run AFTER workflow sections are removed)
            self.pyproject.models.cleanup_orphans()

        self.commit(message)

    # =====================================================
    # Model Source Management
    # =====================================================

    def add_model_source(self, identifier: str, url: str) -> ModelSourceResult:
        """Add a download source URL to a model.

        Updates both pyproject.toml and the workspace model index.

        Args:
            identifier: Model hash or filename
            url: Download URL for the model

        Returns:
            ModelSourceResult with success status and model details
        """
        # Find model by hash or filename
        all_models = self.pyproject.models.get_all()

        model = None

        # Try exact hash match first (unambiguous)
        hash_matches = [m for m in all_models if m.hash == identifier]
        if hash_matches:
            model = hash_matches[0]
        else:
            # Try filename match (potentially ambiguous)
            filename_matches = [m for m in all_models if m.filename == identifier]

            if len(filename_matches) == 0:
                return ModelSourceResult(
                    success=False,
                    error="model_not_found",
                    identifier=identifier
                )
            elif len(filename_matches) > 1:
                return ModelSourceResult(
                    success=False,
                    error="ambiguous_filename",
                    identifier=identifier,
                    matches=filename_matches
                )
            else:
                model = filename_matches[0]

        # Check if URL already exists
        if url in model.sources:
            return ModelSourceResult(
                success=False,
                error="url_exists",
                model=model,
                model_hash=model.hash
            )

        # Detect source type
        source_type = self.model_downloader.detect_url_type(url)

        # Update pyproject.toml
        config = self.pyproject.load()
        if url not in config["tool"]["comfydock"]["models"][model.hash].get("sources", []):
            if "sources" not in config["tool"]["comfydock"]["models"][model.hash]:
                config["tool"]["comfydock"]["models"][model.hash]["sources"] = []
            config["tool"]["comfydock"]["models"][model.hash]["sources"].append(url)
            self.pyproject.save(config)

        # Update model repository (SQLite index) - only if model exists locally
        if self.model_repository.has_model(model.hash):
            self.model_repository.add_source(
                model_hash=model.hash,
                source_type=source_type,
                source_url=url
            )

        logger.info(f"Added source to model {model.filename}: {url}")

        return ModelSourceResult(
            success=True,
            model=model,
            model_hash=model.hash,
            source_type=source_type,
            url=url
        )

    def get_models_without_sources(self) -> list[ModelSourceStatus]:
        """Get all models in pyproject that don't have download sources.

        Returns:
            List of ModelSourceStatus objects with model and local availability
        """
        all_models = self.pyproject.models.get_all()

        results = []
        for model in all_models:
            if not model.sources:
                # Check if model exists in local index
                local_model = self.model_repository.get_model(model.hash)

                results.append(ModelSourceStatus(
                    model=model,
                    available_locally=local_model is not None
                ))

        return results

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

    def _execute_pending_downloads(
        self,
        result: ResolutionResult,
        callbacks: BatchDownloadCallbacks | None = None
    ) -> list:
        """Execute batch downloads for all download intents in result.
        All user-facing output is delivered via callbacks.

        Args:
            result: Resolution result containing download intents
            callbacks: Optional callbacks for progress/status (provided by CLI)

        Returns:
            List of download results
        """
        # Collect download intents
        intents = [r for r in result.models_resolved if r.match_type == "download_intent"]

        if not intents:
            return []

        # Notify batch start
        if callbacks and callbacks.on_batch_start:
            callbacks.on_batch_start(len(intents))

        results = []
        for idx, resolved in enumerate(intents, 1):
            filename = resolved.reference.widget_value

            # Notify file start
            if callbacks and callbacks.on_file_start:
                callbacks.on_file_start(filename, idx, len(intents))

            # Check if already downloaded (deduplication)
            if resolved.model_source:
                existing = self.model_repository.find_by_source_url(resolved.model_source)
                if existing:
                    # Reuse existing model - update pyproject with hash
                    self.workflow_manager._update_model_hash(
                        result.workflow_name,
                        resolved.reference,
                        existing.hash
                    )
                    # Notify success (reused existing)
                    if callbacks and callbacks.on_file_complete:
                        callbacks.on_file_complete(filename, True, None)
                    results.append({"success": True, "model": existing, "filename": filename, "reused": True})
                    continue

            # Validate required fields
            if not resolved.target_path or not resolved.model_source:
                error_msg = "Download intent missing target_path or model_source"
                if callbacks and callbacks.on_file_complete:
                    callbacks.on_file_complete(filename, False, error_msg)
                results.append({"success": False, "model": None, "error": error_msg, "filename": filename, "reused": False})
                continue

            # Download new model
            target_path = self.model_downloader.models_dir / resolved.target_path
            request = DownloadRequest(
                url=resolved.model_source,
                target_path=target_path,
                workflow_name=result.workflow_name
            )

            # Use per-file progress callback if provided
            progress_callback = callbacks.on_file_progress if callbacks else None
            download_result = self.model_downloader.download(request, progress_callback=progress_callback)

            if download_result.success and download_result.model:
                # Update pyproject with actual hash
                self.workflow_manager._update_model_hash(
                    result.workflow_name,
                    resolved.reference,
                    download_result.model.hash
                )
                # Notify success
                if callbacks and callbacks.on_file_complete:
                    callbacks.on_file_complete(filename, True, None)
            else:
                # Notify failure (model remains unresolved with source in pyproject)
                if callbacks and callbacks.on_file_complete:
                    callbacks.on_file_complete(filename, False, download_result.error)

            results.append({
                "success": download_result.success,
                "model": download_result.model if download_result.success else None,
                "error": download_result.error if not download_result.success else None,
                "filename": filename,
                "reused": False
            })

        # Notify batch complete
        if callbacks and callbacks.on_batch_complete:
            success_count = sum(1 for r in results if r["success"])
            callbacks.on_batch_complete(success_count, len(results))

        return results

    # =====================================================
    # Export/Import
    # =====================================================

    def export_environment(
        self,
        output_path: Path,
        callbacks: ExportCallbacks | None = None
    ) -> Path:
        """Export environment as .tar.gz bundle.

        Args:
            output_path: Path for output tarball
            callbacks: Optional callbacks for warnings/progress

        Returns:
            Path to created tarball

        Raises:
            CDExportError: If environment has uncommitted changes or unresolved issues
        """
        from ..managers.export_import_manager import ExportImportManager
        from ..models.exceptions import CDExportError, ExportErrorContext

        # Validation: Get workflow status first for comprehensive checks
        status = self.workflow_manager.get_workflow_status()

        # Check for uncommitted workflow changes (new, modified, or deleted)
        if status.sync_status.has_changes:
            context = ExportErrorContext(
                uncommitted_workflows=(
                    status.sync_status.new +
                    status.sync_status.modified +
                    status.sync_status.deleted
                )
            )
            raise CDExportError(
                "Cannot export with uncommitted workflow changes",
                context=context
            )

        # Validation: Check for uncommitted git changes in .cec/
        if self.git_manager.has_uncommitted_changes():
            context = ExportErrorContext(uncommitted_git_changes=True)
            raise CDExportError(
                "Cannot export with uncommitted git changes",
                context=context
            )

        # Validation: Check all workflows are resolved
        if not status.is_commit_safe:
            context = ExportErrorContext(has_unresolved_issues=True)
            raise CDExportError(
                "Cannot export - workflows have unresolved issues",
                context=context
            )

        # Check for models without sources and collect workflow usage
        from ..models.shared import ModelWithoutSourceInfo

        models_without_sources: list[ModelWithoutSourceInfo] = []
        models_by_hash = {m.hash: m for m in self.pyproject.models.get_all() if not m.sources}

        if models_by_hash:
            # Map models to workflows that use them
            all_workflows = self.pyproject.workflows.get_all_with_resolutions()
            for workflow_name in all_workflows.keys():
                workflow_models = self.pyproject.workflows.get_workflow_models(workflow_name)
                for wf_model in workflow_models:
                    if wf_model.hash and wf_model.hash in models_by_hash:
                        # Find or create entry for this model
                        existing = next((m for m in models_without_sources if m.hash == wf_model.hash), None)
                        if existing:
                            existing.workflows.append(workflow_name)
                        else:
                            model_data = models_by_hash[wf_model.hash]
                            models_without_sources.append(
                                ModelWithoutSourceInfo(
                                    filename=model_data.filename,
                                    hash=wf_model.hash,
                                    workflows=[workflow_name]
                                )
                            )

            # Notify callback with structured data
            if callbacks:
                callbacks.on_models_without_sources(models_without_sources)

        # Create export
        manager = ExportImportManager(self.cec_path, self.comfyui_path)
        return manager.create_export(output_path, self.pyproject)

    def detect_missing_models(self) -> list:
        """Detect models in pyproject that don't exist in local index.

        Checks both resolved workflow models (with hash) and models in the global table
        that aren't present in the local repository with valid file locations.

        Returns:
            List of MissingModelInfo for models that need downloading
        """
        from comfydock_core.models.environment import MissingModelInfo

        missing_by_hash: dict[str, MissingModelInfo] = {}

        # First pass: Check all workflow models for missing resolved models
        all_workflows = self.pyproject.workflows.get_all_with_resolutions()
        for workflow_name in all_workflows.keys():
            workflow_models = self.pyproject.workflows.get_workflow_models(workflow_name)

            for wf_model in workflow_models:
                # Check both resolved models and models that reference a filename
                model_hash = wf_model.hash

                # If model has a hash, check if it exists WITH a valid location
                # get_model() returns None if model has no locations (file deleted)
                if model_hash and not self.model_repository.get_model(model_hash):
                    # Model is missing!
                    if model_hash not in missing_by_hash:
                        # Get global model entry
                        global_model = self.pyproject.models.get_by_hash(model_hash)
                        if global_model:
                            missing_by_hash[model_hash] = MissingModelInfo(
                                model=global_model,
                                workflow_names=[workflow_name],
                                criticality=wf_model.criticality,
                                can_download=bool(global_model.sources)
                            )
                    else:
                        # Already tracking this model, add workflow and update criticality
                        missing_info = missing_by_hash[model_hash]
                        if workflow_name not in missing_info.workflow_names:
                            missing_info.workflow_names.append(workflow_name)
                        # Upgrade criticality (required > flexible > optional)
                        if wf_model.criticality == "required":
                            missing_info.criticality = "required"
                        elif wf_model.criticality == "flexible" and missing_info.criticality == "optional":
                            missing_info.criticality = "flexible"

        # Second pass: Check global models table for any models not in repository
        # This catches models that were resolved but file was deleted
        global_models = self.pyproject.models.get_all()
        for global_model in global_models:
            if global_model.hash not in missing_by_hash:
                # Check if this model exists in repository WITH a valid location
                if not self.model_repository.get_model(global_model.hash):
                    # Find which workflows use this model
                    workflows_using_model = []
                    criticality = "flexible"  # Default

                    for workflow_name in all_workflows.keys():
                        workflow_models = self.pyproject.workflows.get_workflow_models(workflow_name)
                        for wf_model in workflow_models:
                            if wf_model.hash == global_model.hash:
                                workflows_using_model.append(workflow_name)
                                # Track highest criticality
                                if wf_model.criticality == "required":
                                    criticality = "required"
                                elif wf_model.criticality == "flexible" and criticality == "optional":
                                    criticality = "flexible"

                    # Only add if used by at least one workflow
                    if workflows_using_model:
                        missing_by_hash[global_model.hash] = MissingModelInfo(
                            model=global_model,
                            workflow_names=workflows_using_model,
                            criticality=criticality,
                            can_download=bool(global_model.sources)
                        )

        return list(missing_by_hash.values())

    def prepare_import_with_model_strategy(
        self,
        strategy: str = "all"
    ) -> list[str]:
        """Prepare import by converting missing models to download intents.

        This is the key import method - it detects which models are missing locally
        and temporarily converts them back to download intents in pyproject.toml.
        The subsequent resolve_workflow() call will download them.

        Args:
            strategy: Model download strategy
                - "all": Download all models with sources
                - "required": Download only required models
                - "skip": Skip all downloads (leave as optional unresolved)

        Returns:
            List of workflow names that had download intents prepared
        """
        logger.info(f"Preparing import with model strategy: {strategy}")

        workflows_with_intents = []

        # Get all workflows from pyproject
        all_workflows = self.pyproject.workflows.get_all_with_resolutions()

        for workflow_name in all_workflows.keys():
            models = self.pyproject.workflows.get_workflow_models(workflow_name)
            models_modified = False

            for idx, model in enumerate(models):
                # Skip if already unresolved (nothing to prepare)
                if model.status == "unresolved":
                    continue

                # Check if model exists locally
                if model.hash:
                    existing = self.model_repository.get_model(model.hash)
                    if existing:
                        # Model exists - enrich SQLite with sources from pyproject
                        global_model = self.pyproject.models.get_by_hash(model.hash)
                        if global_model and global_model.sources:
                            # Get existing sources from SQLite
                            existing_sources_list = self.model_repository.get_sources(model.hash)
                            existing_source_urls = {s["url"] for s in existing_sources_list}

                            # Add any missing sources
                            for source_url in global_model.sources:
                                if source_url not in existing_source_urls:
                                    source_type = self.model_downloader.detect_url_type(source_url)
                                    self.model_repository.add_source(
                                        model_hash=model.hash,
                                        source_type=source_type,
                                        source_url=source_url
                                    )
                                    logger.info(f"Enriched model {global_model.filename} with source: {source_url}")

                        # Model exists - no download needed
                        continue

                # Model missing - check strategy
                if strategy == "skip":
                    # Convert to optional unresolved (no download intent)
                    models[idx].status = "unresolved"
                    models[idx].criticality = "optional"
                    models[idx].hash = None
                    models_modified = True
                    continue

                # Convert to download intent
                # Read sources from global table
                if model.hash:
                    global_model = self.pyproject.models.get_by_hash(model.hash)
                    if global_model and global_model.sources:
                        # Revert to download intent
                        models[idx].status = "unresolved"
                        models[idx].sources = global_model.sources
                        models[idx].relative_path = global_model.relative_path
                        models[idx].hash = None  # Clear hash - will be set after download
                        models_modified = True
                        logger.debug(f"Prepared download intent for {model.filename} in {workflow_name}")

            # Save modified models
            if models_modified:
                self.pyproject.workflows.set_workflow_models(workflow_name, models)

                # Only add to workflows_with_intents if we should attempt downloads
                # For "required" strategy, only if workflow has required models with download intents
                if strategy == "all":
                    workflows_with_intents.append(workflow_name)
                elif strategy == "required":
                    has_required_intents = any(
                        m.status == "unresolved" and m.sources and m.criticality == "required"
                        for m in models
                    )
                    if has_required_intents:
                        workflows_with_intents.append(workflow_name)

        logger.info(f"Prepared {len(workflows_with_intents)} workflows with download intents")
        return workflows_with_intents

    def finalize_import(
        self,
        model_strategy: str = "all",
        callbacks: ImportCallbacks | None = None
    ) -> None:
        """Complete import setup after .cec extraction.

        Assumes .cec directory is already populated (from tarball or git).

        Phases:
            1. Clone/restore ComfyUI from cache
            2. Install dependencies (uv sync)
            3. Initialize git repository
            4. Copy workflows to ComfyUI user directory
            5. Sync custom nodes
            6. Prepare and resolve models based on strategy

        Args:
            model_strategy: "all", "required", or "skip"
            callbacks: Optional progress callbacks

        Raises:
            ValueError: If ComfyUI already exists or .cec not properly initialized
        """
        from ..caching.comfyui_cache import ComfyUICacheManager, ComfyUISpec
        from ..utils.comfyui_ops import clone_comfyui
        from ..utils.git import git_rev_parse

        logger.info(f"Finalizing import for environment: {self.name}")

        # Verify environment state
        if self.comfyui_path.exists():
            raise ValueError("Environment already has ComfyUI - cannot finalize import")

        # Phase 1: Clone or restore ComfyUI from cache
        comfyui_cache = ComfyUICacheManager(cache_base_path=self.workspace_paths.cache)

        # Read ComfyUI version from pyproject.toml
        comfyui_version = None
        comfyui_version_type = None
        try:
            pyproject_data = self.pyproject.load()
            comfydock_config = pyproject_data.get("tool", {}).get("comfydock", {})
            comfyui_version = comfydock_config.get("comfyui_version")
            comfyui_version_type = comfydock_config.get("comfyui_version_type")
        except Exception as e:
            logger.warning(f"Could not read comfyui_version from pyproject.toml: {e}")

        if comfyui_version:
            version_desc = f"{comfyui_version_type} {comfyui_version}" if comfyui_version_type else comfyui_version
            logger.debug(f"Using comfyui_version from pyproject: {version_desc}")

        # Auto-detect version type if not specified
        if not comfyui_version_type and comfyui_version:
            if comfyui_version.startswith('v'):
                comfyui_version_type = "release"
            elif comfyui_version in ("main", "master"):
                comfyui_version_type = "branch"
            else:
                comfyui_version_type = "commit"
            logger.debug(f"Auto-detected version type: {comfyui_version_type}")

        # Create version spec
        spec = ComfyUISpec(
            version=comfyui_version or "main",
            version_type=comfyui_version_type or "branch",
            commit_sha=None
        )

        # Check cache first
        cached_path = comfyui_cache.get_cached_comfyui(spec)

        if cached_path:
            if callbacks:
                callbacks.on_phase("restore_comfyui", f"Restoring ComfyUI {spec.version} from cache...")
            logger.info(f"Restoring ComfyUI {spec.version} from cache")
            shutil.copytree(cached_path, self.comfyui_path)
        else:
            if callbacks:
                callbacks.on_phase("clone_comfyui", f"Cloning ComfyUI {spec.version}...")
            logger.info(f"Cloning ComfyUI {spec.version}")
            clone_comfyui(self.comfyui_path, comfyui_version)

            # Cache the fresh clone
            commit_sha = git_rev_parse(self.comfyui_path, "HEAD")
            if commit_sha:
                spec.commit_sha = commit_sha
                comfyui_cache.cache_comfyui(spec, self.comfyui_path)
                logger.info(f"Cached ComfyUI {spec.version} ({commit_sha[:7]})")
            else:
                logger.warning(f"Could not determine commit SHA for ComfyUI {spec.version}")

        # Remove ComfyUI's default models directory (will be replaced with symlink)
        models_dir = self.comfyui_path / "models"
        if models_dir.exists() and not models_dir.is_symlink():
            shutil.rmtree(models_dir)

        # Phase 2: Install dependencies
        if callbacks:
            callbacks.on_phase("install_deps", "Installing dependencies...")
        self.uv_manager.sync_project(verbose=False)

        # Phase 3: Initialize git
        if callbacks:
            callbacks.on_phase("init_git", "Initializing git repository...")
        self.git_manager.initialize_environment_repo("Imported environment")

        # Phase 4: Copy workflows
        if callbacks:
            callbacks.on_phase("copy_workflows", "Setting up workflows...")

        workflows_src = self.cec_path / "workflows"
        workflows_dst = self.comfyui_path / "user" / "default" / "workflows"
        workflows_dst.mkdir(parents=True, exist_ok=True)

        if workflows_src.exists():
            for workflow_file in workflows_src.glob("*.json"):
                shutil.copy2(workflow_file, workflows_dst / workflow_file.name)
                if callbacks:
                    callbacks.on_workflow_copied(workflow_file.name)

        # Phase 5: Sync custom nodes
        if callbacks:
            callbacks.on_phase("sync_nodes", "Syncing custom nodes...")

        try:
            # During import, don't remove ComfyUI builtins (fresh clone has example files)
            sync_result = self.sync(remove_extra_nodes=False)
            if sync_result.success and sync_result.nodes_installed and callbacks:
                for node_name in sync_result.nodes_installed:
                    callbacks.on_node_installed(node_name)
            elif not sync_result.success and callbacks:
                for error in sync_result.errors:
                    callbacks.on_error(f"Node sync: {error}")
        except Exception as e:
            if callbacks:
                callbacks.on_error(f"Node sync failed: {e}")

        # Phase 6: Prepare and resolve models
        if callbacks:
            callbacks.on_phase("resolve_models", f"Resolving workflows ({model_strategy} strategy)...")

        workflows_to_resolve = []
        if model_strategy != "skip":
            workflows_to_resolve = self.prepare_import_with_model_strategy(model_strategy)

        # Resolve workflows with download intents
        from ..strategies.auto import AutoModelStrategy, AutoNodeStrategy

        download_failures = []

        for workflow_name in workflows_to_resolve:
            try:
                result = self.resolve_workflow(
                    name=workflow_name,
                    model_strategy=AutoModelStrategy(),
                    node_strategy=AutoNodeStrategy()
                )

                # Track successful vs failed downloads
                successful_downloads = sum(
                    1 for m in result.models_resolved
                    if m.match_type == 'download_intent' and m.resolved_model is not None
                )
                failed_downloads = [
                    (workflow_name, m.reference.widget_value)
                    for m in result.models_resolved
                    if m.match_type == 'download_intent' and m.resolved_model is None
                ]

                download_failures.extend(failed_downloads)

                if callbacks:
                    callbacks.on_workflow_resolved(workflow_name, successful_downloads)

            except Exception as e:
                if callbacks:
                    callbacks.on_error(f"Failed to resolve {workflow_name}: {e}")

        # Report download failures
        if download_failures and callbacks:
            callbacks.on_download_failures(download_failures)

        logger.info("Import finalization completed successfully")
