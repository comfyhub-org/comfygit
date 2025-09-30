"""Auto workflow tracking - all workflows in ComfyUI are automatically managed."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from comfydock_core.models.exceptions import CDPyprojectError
from comfydock_core.models.shared import ModelWithLocation
from comfydock_core.resolvers.global_node_resolver import GlobalNodeResolver
from comfydock_core.services.registry_data_manager import RegistryDataManager

from ..resolvers.model_resolver import ModelResolver
from ..models.workflow import (
    ResolutionResult,
    CommitAnalysis,
    WorkflowNode,
    WorkflowNodeWidgetRef,
    WorkflowAnalysisStatus,
    DetailedWorkflowStatus,
    WorkflowSyncStatus
)
from ..models.protocols import NodeResolutionStrategy, ModelResolutionStrategy
from ..analyzers.workflow_dependency_parser import WorkflowDependencyParser
from ..logging.logging_config import get_logger

if TYPE_CHECKING:
    from .pyproject_manager import PyprojectManager
    from ..repositories.model_repository import ModelRepository
    from ..models.workflow import WorkflowDependencies, ResolvedNodePackage

logger = get_logger(__name__)


class WorkflowManager:
    """Manages all workflows automatically - no explicit tracking needed."""

    def __init__(
        self,
        comfyui_path: Path,
        cec_path: Path,
        pyproject: PyprojectManager,
        model_repository: ModelRepository,
        registry_data_manager: RegistryDataManager,
    ):
        self.comfyui_path = comfyui_path
        self.cec_path = cec_path
        self.pyproject = pyproject
        self.model_repository = model_repository

        self.comfyui_workflows = comfyui_path / "user" / "default" / "workflows"
        self.cec_workflows = cec_path / "workflows"

        # Ensure directories exist
        self.comfyui_workflows.mkdir(parents=True, exist_ok=True)
        self.cec_workflows.mkdir(parents=True, exist_ok=True)

        self.resgistry_data_manager = registry_data_manager
        node_mappings_path = self.resgistry_data_manager.get_mappings_path()

        self.global_node_resolver = GlobalNodeResolver(mappings_path=node_mappings_path)
        self.model_resolver = ModelResolver(
            model_repository=self.model_repository, 
            pyproject_manager=self.pyproject
        )

    def get_workflow_sync_status(self) -> "WorkflowSyncStatus":
        """Get file-level sync status between ComfyUI and .cec.

        Returns:
            WorkflowSyncStatus with categorized workflow lists
        """
        # Get all workflows from ComfyUI
        comfyui_workflows = set()
        if self.comfyui_workflows.exists():
            for workflow_file in self.comfyui_workflows.glob("*.json"):
                comfyui_workflows.add(workflow_file.stem)

        # Get all workflows from .cec
        cec_workflows = set()
        if self.cec_workflows.exists():
            for workflow_file in self.cec_workflows.glob("*.json"):
                cec_workflows.add(workflow_file.stem)

        # Categorize workflows
        new_workflows = []
        modified_workflows = []
        deleted_workflows = []
        synced_workflows = []

        # Check each ComfyUI workflow
        for name in comfyui_workflows:
            if name not in cec_workflows:
                new_workflows.append(name)
            else:
                # Compare contents to detect modifications
                if self._workflows_differ(name):
                    modified_workflows.append(name)
                else:
                    synced_workflows.append(name)

        # Check for deleted workflows (in .cec but not ComfyUI)
        for name in cec_workflows:
            if name not in comfyui_workflows:
                deleted_workflows.append(name)

        return WorkflowSyncStatus(
            new=sorted(new_workflows),
            modified=sorted(modified_workflows),
            deleted=sorted(deleted_workflows),
            synced=sorted(synced_workflows),
        )

    def _workflows_differ(self, name: str) -> bool:
        """Check if workflow differs between ComfyUI and .cec.

        Args:
            name: Workflow name

        Returns:
            True if workflows differ or .cec copy doesn't exist
        """
        comfyui_file = self.comfyui_workflows / f"{name}.json"
        cec_file = self.cec_workflows / f"{name}.json"

        if not cec_file.exists():
            return True

        if not comfyui_file.exists():
            return False

        try:
            # Compare file contents
            with open(comfyui_file) as f:
                comfyui_content = json.load(f)
            with open(cec_file) as f:
                cec_content = json.load(f)

            return comfyui_content != cec_content
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Error comparing workflows '{name}': {e}")
            return True

    def copy_all_workflows(self) -> dict[str, Path | None]:
        """Copy ALL workflows from ComfyUI to .cec for commit.

        Returns:
            Dictionary of workflow names to Path
        """
        results = {}

        if not self.comfyui_workflows.exists():
            logger.info("No ComfyUI workflows directory found")
            return results

        # Copy every workflow from ComfyUI to .cec
        for workflow_file in self.comfyui_workflows.glob("*.json"):
            name = workflow_file.stem
            source = self.comfyui_workflows / f"{name}.json"
            dest = self.cec_workflows / f"{name}.json"

            try:
                shutil.copy2(source, dest)
                results[name] = dest
                logger.debug(f"Copied workflow '{name}' to .cec")
            except Exception as e:
                results[name] = None
                logger.error(f"Failed to copy workflow '{name}': {e}")

        # Remove workflows from .cec that no longer exist in ComfyUI
        if self.cec_workflows.exists():
            comfyui_names = {f.stem for f in self.comfyui_workflows.glob("*.json")}
            for cec_file in self.cec_workflows.glob("*.json"):
                name = cec_file.stem
                if name not in comfyui_names:
                    try:
                        cec_file.unlink()
                        results[name] = "deleted"
                        logger.debug(
                            f"Deleted workflow '{name}' from .cec (no longer in ComfyUI)"
                        )
                    except Exception as e:
                        logger.error(f"Failed to delete workflow '{name}': {e}")

        return results

    def restore_from_cec(self, name: str) -> bool:
        """Restore a workflow from .cec to ComfyUI directory.

        Args:
            name: Workflow name

        Returns:
            True if successful, False if workflow not found
        """
        source = self.cec_workflows / f"{name}.json"
        dest = self.comfyui_workflows / f"{name}.json"

        if not source.exists():
            return False

        try:
            shutil.copy2(source, dest)
            logger.info(f"Restored workflow '{name}' to ComfyUI")
            return True
        except Exception as e:
            logger.error(f"Failed to restore workflow '{name}': {e}")
            return False

    def restore_all_from_cec(self) -> dict[str, str]:
        """Restore all workflows from .cec to ComfyUI (for rollback).

        Returns:
            Dictionary of workflow names to restore status
        """
        results = {}

        if not self.cec_workflows.exists():
            logger.info("No .cec workflows directory found")
            return results

        # Copy every workflow from .cec to ComfyUI
        for workflow_file in self.cec_workflows.glob("*.json"):
            name = workflow_file.stem
            if self.restore_from_cec(name):
                results[name] = "restored"
            else:
                results[name] = "failed"

        # Remove workflows from ComfyUI that don't exist in .cec (cleanup)
        if self.comfyui_workflows.exists():
            cec_names = {f.stem for f in self.cec_workflows.glob("*.json")}
            for comfyui_file in self.comfyui_workflows.glob("*.json"):
                name = comfyui_file.stem
                if name not in cec_names:
                    try:
                        comfyui_file.unlink()
                        results[name] = "removed"
                        logger.debug(
                            f"Removed workflow '{name}' from ComfyUI (not in .cec)"
                        )
                    except Exception as e:
                        logger.error(f"Failed to remove workflow '{name}': {e}")

        return results

    def analyze_single_workflow_status(
        self,
        name: str,
        sync_state: str
    ) -> "WorkflowAnalysisStatus":
        """Analyze a single workflow for dependencies and resolution status.

        This is read-only - no side effects, no copying, just analysis.

        Args:
            name: Workflow name
            sync_state: Sync state ("new", "modified", "deleted", "synced")

        Returns:
            WorkflowAnalysisStatus with complete dependency and resolution info
        """
        # Phase 1: Analyze dependencies (parse workflow JSON)
        dependencies = self.analyze_workflow(name)

        # Phase 2: Attempt resolution (check index, pyproject cache)
        resolution = self.resolve_workflow(dependencies)

        return WorkflowAnalysisStatus(
            name=name,
            sync_state=sync_state,
            dependencies=dependencies,
            resolution=resolution
        )

    def get_workflow_status(self) -> "DetailedWorkflowStatus":
        """Get detailed workflow status with full dependency analysis.

        Analyzes ALL workflows in ComfyUI directory, checking dependencies
        and resolution status. This is read-only - no copying to .cec.

        Returns:
            DetailedWorkflowStatus with sync status and analysis for each workflow
        """
        # Step 1: Get file sync status (fast)
        sync_status = self.get_workflow_sync_status()

        # Step 2: Analyze all workflows (including synced ones)
        all_workflow_names = (
            sync_status.new +
            sync_status.modified +
            sync_status.synced
        )

        analyzed: list["WorkflowAnalysisStatus"] = []

        for name in all_workflow_names:
            # Determine sync state
            if name in sync_status.new:
                state = "new"
            elif name in sync_status.modified:
                state = "modified"
            else:
                state = "synced"

            try:
                analysis = self.analyze_single_workflow_status(name, state)
                analyzed.append(analysis)
            except Exception as e:
                logger.error(f"Failed to analyze workflow {name}: {e}")
                # Continue with other workflows

        return DetailedWorkflowStatus(
            sync_status=sync_status,
            analyzed_workflows=analyzed
        )

    def get_full_status(self) -> "DetailedWorkflowStatus":
        """Get complete workflow status for Environment.status().

        Alias for get_workflow_status() for compatibility.
        """
        return self.get_workflow_status()

    def analyze_all_for_commit(self) -> CommitAnalysis:
        """Analyze ALL workflows for commit - refactored from analyze_commit."""
        # Copy all workflows first
        workflows_copied = self.copy_all_workflows()

        # Analyze each workflow
        analyses = []
        for workflow_name in workflows_copied:
            if workflows_copied[workflow_name] is not None:
                try:
                    analysis = self.analyze_workflow(workflow_name)
                    analyses.append(analysis)
                    logger.debug(f"Workflow analysis results: {analysis}")
                except Exception as e:
                    logger.error(f"Failed to analyze workflow {workflow_name}: {e}")

        # Convert Path values to status strings
        workflows_status = {
            name: "copied" if path else "failed"
            for name, path in workflows_copied.items()
        }

        return CommitAnalysis(workflows_copied=workflows_status, analyses=analyses)

    def analyze_workflow(self, name: str) -> WorkflowDependencies:
        """Analyze a single workflow for dependencies - pure analysis, no side effects."""
        workflow_path = self.comfyui_workflows / f"{name}.json"

        if not workflow_path.exists():
            raise FileNotFoundError(f"Workflow '{name}' not found at {workflow_path}")

        parser = WorkflowDependencyParser(workflow_path)

        # Get dependencies (nodes + models)
        deps = parser.analyze_dependencies()

        return deps

    def resolve_workflow(self, analysis: WorkflowDependencies) -> ResolutionResult:
        """Phase 2: Attempt automatic resolution of workflow dependencies.

        Takes the analysis from Phase 1 and tries to resolve:
        - Missing nodes → node packages from registry/GitHub
        - Model references → actual model files in index

        Returns ResolutionResult showing what was resolved and what remains ambiguous.
        Does NOT modify pyproject.toml - that happens in fix_workflow().

        Args:
            analysis: Workflow dependencies from analyze_workflow()

        Returns:
            ResolutionResult with resolved and unresolved dependencies
        """
        nodes_resolved: list[ResolvedNodePackage] = []
        nodes_unresolved: list[WorkflowNode] = []
        nodes_ambiguous: list[list[ResolvedNodePackage]] = []
        models_resolved: list[ModelWithLocation] = []
        models_ambiguous: list[tuple[WorkflowNodeWidgetRef, list[ModelWithLocation]]] = []
        models_unresolved: list[WorkflowNodeWidgetRef] = []

        workflow_name = analysis.workflow_name

        # Resolve missing nodes
        for node in analysis.missing_nodes:
            resolved_packages = self.global_node_resolver.resolve_single_node(node)

            if not resolved_packages:
                nodes_unresolved.append(node)
            elif len(resolved_packages) == 1:
                # Single match - cleanly resolved
                nodes_resolved.append(resolved_packages[0])
            else:
                # Multiple matches - ambiguous
                nodes_ambiguous.append(resolved_packages)

        # Resolve models
        for model_ref in analysis.found_models:
            result = self.model_resolver.resolve_model(model_ref, workflow_name)

            if not result:
                # Model not found at all
                models_unresolved.append(model_ref)
            elif result.resolved_model:
                # Clean resolution (exact match or from pyproject cache)
                models_resolved.append(result.resolved_model)
                logger.debug(f"Resolved model: {result.resolved_model.filename}")
            elif result.candidates:
                # Ambiguous - multiple matches
                models_ambiguous.append((model_ref, result.candidates))
            else:
                # No resolution possible
                models_unresolved.append(model_ref)

        return ResolutionResult(
            nodes_resolved=nodes_resolved,
            nodes_unresolved=nodes_unresolved,
            nodes_ambiguous=nodes_ambiguous,
            models_resolved=models_resolved,
            models_unresolved=models_unresolved,
            models_ambiguous=models_ambiguous,
        )

    def fix_resolution(
        self,
        resolution: ResolutionResult,
        node_strategy: NodeResolutionStrategy | None = None,
        model_strategy: ModelResolutionStrategy | None = None,
    ) -> ResolutionResult:
        """Phase 3a: Fix remaining issues using strategies.

        Takes ResolutionResult from Phase 2 and uses strategies to resolve ambiguities.
        Does NOT modify pyproject.toml - call apply_resolution() to persist changes.

        Args:
            resolution: Result from resolve_workflow()
            node_strategy: Strategy for handling unresolved/ambiguous nodes
            model_strategy: Strategy for handling ambiguous/missing models

        Returns:
            Updated ResolutionResult with fixes applied
        """
        nodes_to_add = list(resolution.nodes_resolved)
        models_to_add = list(resolution.models_resolved)

        remaining_nodes_ambiguous: list[list[ResolvedNodePackage]] = []
        remaining_nodes_unresolved: list[WorkflowNode] = []
        remaining_models_ambiguous: list[tuple[WorkflowNodeWidgetRef, list[ModelWithLocation]]] = []
        remaining_models_unresolved: list[WorkflowNodeWidgetRef] = []

        # Fix ambiguous nodes using strategy
        if node_strategy:
            for packages in resolution.nodes_ambiguous:
                selected = node_strategy.resolve_unknown_node(packages[0].node_type, packages)
                if selected:
                    nodes_to_add.append(selected)
                    logger.info(f"Resolved ambiguous node: {selected.package_data.id}")
                else:
                    remaining_nodes_ambiguous.append(packages)
        else:
            remaining_nodes_ambiguous = list(resolution.nodes_ambiguous)

        # Handle unresolved nodes using strategy
        if node_strategy:
            for node in resolution.nodes_unresolved:
                selected = node_strategy.resolve_unknown_node(node.type, [])
                if selected:
                    nodes_to_add.append(selected)
                    logger.info(f"Resolved unresolved node: {selected.package_data.id}")
                else:
                    remaining_nodes_unresolved.append(node)
        else:
            remaining_nodes_unresolved = list(resolution.nodes_unresolved)

        # Fix ambiguous models using strategy
        if model_strategy:
            for model_ref, candidates in resolution.models_ambiguous:
                resolved = model_strategy.resolve_ambiguous_model(model_ref, candidates)
                if resolved:
                    models_to_add.append(resolved)
                    logger.info(f"Resolved ambiguous model: {resolved.filename}")
                else:
                    remaining_models_ambiguous.append((model_ref, candidates))
        else:
            remaining_models_ambiguous = list(resolution.models_ambiguous)

        # Handle missing models using strategy
        if model_strategy:
            for model_ref in resolution.models_unresolved:
                resolved = model_strategy.resolve_ambiguous_model(model_ref, [])
                if resolved:
                    models_to_add.append(resolved)
                    logger.info(f"Resolved unresolved model: {resolved.filename}")
                else:
                    remaining_models_unresolved.append(model_ref)
        else:
            remaining_models_unresolved = list(resolution.models_unresolved)

        return ResolutionResult(
            nodes_resolved=nodes_to_add,
            nodes_unresolved=remaining_nodes_unresolved,
            nodes_ambiguous=remaining_nodes_ambiguous,
            models_resolved=models_to_add,
            models_unresolved=remaining_models_unresolved,
            models_ambiguous=remaining_models_ambiguous,
        )
        
    def apply_all_resolution(self, detailed_status: DetailedWorkflowStatus) -> None:
        for workflow in detailed_status.analyzed_workflows:
            self.apply_resolution(workflow.resolution)

    def apply_resolution(self, resolution: ResolutionResult) -> None:
        """Phase 3b: Apply resolution to pyproject.toml.

        Takes a ResolutionResult (from resolve_workflow or fix_workflow)
        and persists resolved nodes and models to pyproject.toml.

        Args:
            resolution: Result with resolved dependencies to apply
        """
        if not resolution.nodes_resolved and not resolution.models_resolved:
            logger.info("No resolved dependencies to apply")
            return

        self._apply_resolution_to_pyproject(
            resolution.nodes_resolved,
            resolution.models_resolved
        )

    def _apply_resolution_to_pyproject(
        self,
        nodes_to_add: list[ResolvedNodePackage],
        models_to_add: list[ModelWithLocation],
    ) -> None:
        """Apply resolved dependencies to pyproject.toml.

        Args:
            nodes_to_add: Node packages to add
            models_to_add: Model files to track
            
        Raises:
            RuntimeError: If no configuration to save or write fails
        """
        # Add resolved models to manifest
        try:
            for model in models_to_add:
                self.pyproject.models.add_model(
                    model_hash=model.hash,
                    filename=model.filename,
                    file_size=model.file_size,
                    relative_path=model.relative_path,
                    category="required",
                )
        except CDPyprojectError as e:
            raise RuntimeError("Failed to save model to pyproject.toml") from e

        logger.info(
            f"Applied {len(models_to_add)} models, "
            f"{len(nodes_to_add)} nodes to pyproject.toml"
        )
