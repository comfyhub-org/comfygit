"""Simplified Environment - owns everything about a single ComfyUI environment."""
from __future__ import annotations

import subprocess
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING

from ..factories.uv_factory import create_uv_for_environment
from ..logging.logging_config import get_logger
from ..managers.environment_version_manager import EnvironmentVersionManager
from ..managers.git_manager import GitManager
from ..managers.model_path_manager import ModelPathManager
from ..managers.node_manager import NodeManager
from ..managers.pyproject_manager import PyprojectManager
from ..managers.resolution_tester import ResolutionTester
from ..managers.status_scanner import StatusScanner
from ..managers.uv_project_manager import UVProjectManager
from ..managers.workflow_manager import WorkflowManager
from ..models.environment import EnvironmentStatus
from ..models.sync import (
    ModelResolutionMap,
    ModelResolutionStrategy,
    NoOpResolver,
    SyncResult,
    WorkflowResolution,
)
from ..services.node_registry import NodeInfo, NodeRegistry
from ..utils.common import run_command

if TYPE_CHECKING:
    from ..managers.model_index_manager import ModelIndexManager
    from ..managers.workspace_config_manager import WorkspaceConfigManager
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
        model_index_manager: ModelIndexManager,
        workspace_config_manager: WorkspaceConfigManager,
        registry_data_manager: RegistryDataManager
    ):
        self.name = name
        self.path = path
        self.workspace_paths = workspace_paths
        self.model_index_manager = model_index_manager
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
        self.workflows_tracked_path = self.cec_path / "workflows"

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
    def node_registry(self) -> NodeRegistry:
        return NodeRegistry(
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
            self.node_registry,
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
            self.path,
            self.pyproject,
            self.model_index_manager,
            self.global_models_path,
            self.registry_data_manager,
        )

    @cached_property
    def git_manager(self) -> GitManager:
        # TODO: Wrap this into EnvironmentVersionManager
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
        dry_run: bool = False,
        model_resolver: ModelResolutionStrategy | None = None
    ) -> SyncResult:
        """Apply changes: sync packages and custom nodes with environment.

        Args:
            dry_run: If True, don't actually apply changes
            model_resolver: Optional strategy for resolving ambiguous models
                          If None, ambiguous models are left unresolved

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

        # Sync workflows
        workflow_results = self.workflow_manager.sync_workflows()
        result.workflows_synced = {name: str(action) for name, action in workflow_results.items()}
        for name, action in workflow_results.items():
            if action != "in_sync":
                logger.info(f"Workflow '{name}': {action}")

        # Re-analyze workflows if resolver provided
        if model_resolver:
            out_of_sync_workflows = [
                name for name, action in result.workflows_synced.items()
                if action != "in_sync"
            ]
            if out_of_sync_workflows:
                result.workflow_resolutions = self._resolve_workflow_models(
                    out_of_sync_workflows,
                    model_resolver
                )

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

    def _resolve_workflow_models(
        self,
        workflow_names: list[str],
        resolver: ModelResolutionStrategy
    ) -> list[WorkflowResolution]:
        """Re-analyze workflow models and resolve ambiguous references.

        Args:
            workflow_names: Names of workflows to analyze
            resolver: Strategy for resolving ambiguous models

        Returns:
            List of WorkflowResolution results
        """
        resolutions = []

        logger.info(f"Resolving models for {len(workflow_names)} workflows...")

        for name in workflow_names:
            logger.debug(f"Analyzing workflow '{name}'...")

            # Analyze workflow models
            model_results, existing_metadata = self.workflow_manager.analyze_workflow_models(name)

            # Show summary if resolver wants to
            if hasattr(resolver, 'show_summary'):
                resolver.show_summary(model_results)

            # Get ambiguous models for resolution
            ambiguous = [r for r in model_results if r.resolution_type == "ambiguous"]

            # Let resolver handle ambiguous models
            user_resolutions: ModelResolutionMap = {}
            if ambiguous:
                user_resolutions = resolver.resolve_ambiguous(model_results)

            # Update workflow with resolutions
            resolved_count = 0
            unresolved_count = 0

            if user_resolutions or model_results:
                resolved_count, unresolved_count = self.workflow_manager.track_workflow_with_resolutions(
                    name,
                    user_resolutions
                )

            # Create resolution result
            resolution = WorkflowResolution(
                name=name,
                resolved_count=resolved_count,
                unresolved_count=unresolved_count,
                ambiguous_count=len(ambiguous),
                action="resolved"  # Workflow was just resolved
            )
            resolutions.append(resolution)

            # Log summary
            if unresolved_count > 0:
                logger.warning(f"Workflow '{name}': {resolved_count} resolved, {unresolved_count} unresolved")
            else:
                logger.info(f"Workflow '{name}': All {resolved_count} models resolved")

        return resolutions

    def rollback(self, target: str | None = None) -> None:
        """Rollback environment to a previous state and/or discard uncommitted changes.

        If target is provided: Apply files from that version to working directory (unstaged)
        If no target: Just discard uncommitted changes

        Args:
            target: Version identifier (e.g., "v1", "v2") or commit hash

        Raises:
            ValueError: If target version doesn't exist
            OSError: If git commands fail
        """
        version_mgr = EnvironmentVersionManager(self.git_manager)

        if target:
            version_mgr.rollback_to(target)
        else:
            self.git_manager.discard_uncommitted()

        logger.info("Successfully applied changes")

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

    def add_node(self, identifier: str, is_local: bool = False, is_development: bool = False, no_test: bool = False) -> NodeInfo:
        """Add a custom node to the environment.

        Raises:
            CDNodeNotFoundError: If node not found
            CDNodeConflictError: If node has dependency conflicts
            CDEnvironmentError: If node with same name already exists
        """
        return self.node_manager.add_node(identifier, is_local, is_development, no_test)

    def remove_node(self, identifier: str):
        """Remove a custom node.

        Raises:
            CDNodeNotFoundError: If node not found
        """
        self.node_manager.remove_node(identifier)

    # =====================================================
    # Workflow Management
    # =====================================================

    def scan_workflows(self) -> dict:
        """Scan for workflows and their tracking status."""
        return self.workflow_manager.scan_workflows()

    def analyze_workflow(self, name: str):
        """Analyze a workflow's dependencies without side effects.

        Returns:
            WorkflowAnalysisResult with all dependency information
        """
        return self.workflow_manager.analyze_workflow(name)

    def track_workflow(self, name: str, analysis=None) -> None:
        """Start tracking a workflow.

        Args:
            name: Workflow name
            analysis: Pre-computed WorkflowAnalysisResult (optional)
        """
        self.workflow_manager.track_workflow(name, analysis)

    def track_workflow_with_resolution(
        self,
        name: str,
        resolver: ModelResolutionStrategy | None = None
    ) -> WorkflowResolution:
        """Track a workflow with optional model resolution.

        Args:
            name: Workflow name to track
            resolver: Optional resolver strategy (None = no resolution)

        Returns:
            WorkflowResolution with tracking results
        """
        if resolver is None:
            resolver = NoOpResolver()

        results = self._resolve_workflow_models([name], resolver)
        return results[0] if results else WorkflowResolution(name=name)

    def untrack_workflow(self, name: str) -> None:
        """Stop tracking a workflow."""
        self.workflow_manager.untrack_workflow(name)

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
