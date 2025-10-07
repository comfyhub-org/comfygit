"""Auto workflow tracking - all workflows in ComfyUI are automatically managed."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

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
    WorkflowSyncStatus,
    ScoredMatch,
    NodeResolutionContext,
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
            # Compare file contents, ignoring volatile metadata fields
            with open(comfyui_file) as f:
                comfyui_content = json.load(f)
            with open(cec_file) as f:
                cec_content = json.load(f)

            # Normalize by removing volatile fields that change between saves
            comfyui_normalized = self._normalize_workflow_for_comparison(comfyui_content)
            cec_normalized = self._normalize_workflow_for_comparison(cec_content)

            return comfyui_normalized != cec_normalized
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Error comparing workflows '{name}': {e}")
            return True

    def _normalize_workflow_for_comparison(self, workflow: dict) -> dict:
        """Remove volatile fields that change between saves but don't affect functionality.

        Args:
            workflow: Workflow JSON dict

        Returns:
            Normalized workflow dict with volatile fields removed
        """
        import copy
        normalized = copy.deepcopy(workflow)

        # Remove UI state fields that change with pan/zoom
        if 'extra' in normalized:
            # Remove volatile UI state
            normalized['extra'].pop('ds', None)  # Pan/zoom state
            normalized['extra'].pop('frontendVersion', None)  # Frontend version

        # Increment counters don't affect workflow logic if structure is same
        normalized.pop('revision', None)

        # Normalize nodes - remove auto-generated seed values when "randomize" is set
        if 'nodes' in normalized:
            for node in normalized['nodes']:
                if isinstance(node, dict):
                    node_type = node.get('type', '')
                    # For sampler nodes with "randomize" mode, normalize seed to a fixed value
                    if node_type in ('KSampler', 'KSamplerAdvanced', 'SamplerCustom'):
                        widgets_values = node.get('widgets_values', [])
                        # widgets_values format: [seed, control_after_generate, steps, cfg, sampler_name, scheduler, denoise]
                        # If control_after_generate is "randomize" or "increment", seed is auto-generated
                        if len(widgets_values) >= 2 and widgets_values[1] in ('randomize', 'increment'):
                            widgets_values[0] = 0  # Normalize to fixed value

                        api_widget_values = node.get('api_widget_values', [])
                        if len(api_widget_values) >= 2 and api_widget_values[1] in ('randomize', 'increment'):
                            api_widget_values[0] = 0  # Normalize to fixed value

        return normalized

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

        # Build resolution context
        context = NodeResolutionContext(
            installed_packages=self.pyproject.nodes.get_existing(),
            session_resolved={},
            custom_mappings=self.pyproject.node_mappings.get_all_mappings(),
            workflow_name=workflow_name
        )

        # Deduplicate node types (same type appears multiple times in workflow)
        # Prefer nodes with properties when deduplicating
        unique_nodes: dict[str, WorkflowNode] = {}
        for node in analysis.non_builtin_nodes:
            if node.type not in unique_nodes:
                unique_nodes[node.type] = node
            else:
                # Prefer node with properties over one without
                if node.properties.get('cnr_id') and not unique_nodes[node.type].properties.get('cnr_id'):
                    unique_nodes[node.type] = node

        logger.debug(f"Resolving {len(unique_nodes)} unique node types from {len(analysis.non_builtin_nodes)} total nodes")

        # Resolve each unique node type with context
        for node_type, node in unique_nodes.items():
            logger.debug(f"Trying to resolve node: {node}")
            resolved_packages = self.global_node_resolver.resolve_single_node_with_context(node, context)

            if resolved_packages is None:
                # Not resolved - trigger strategy
                logger.debug(f"Node not found: {node}")
                nodes_unresolved.append(node)
            elif len(resolved_packages) == 0:
                # Skip (custom mapping = "skip")
                logger.debug(f"Skipped node: {node_type}")
            elif len(resolved_packages) == 1:
                # Single match - cleanly resolved
                logger.debug(f"Resolved node: {resolved_packages[0]}")
                nodes_resolved.append(resolved_packages[0])
            else:
                # Multiple matches - ambiguous
                logger.debug(f"Ambiguous node: {resolved_packages}")
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
                    node_id = selected.package_data.id if selected.package_data else None
                    logger.info(f"Resolved ambiguous node: {node_id}")
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
                    node_id = selected.package_data.id if selected.package_data else None
                    logger.info(f"Resolved unresolved node: {node_id}")
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
                try:
                    result = model_strategy.handle_missing_model(model_ref)

                    if result is None:
                        # Cancelled or skipped
                        remaining_models_unresolved.append(model_ref)
                        continue

                    action, data = result

                    if action == "select":
                        # User provided explicit path
                        path = data

                        # Look up in index by exact path
                        model = self.model_repository.find_by_exact_path(path)

                        if model:
                            models_to_add.append(model)
                            logger.info(f"Resolved: {model_ref.widget_value} → {path}")
                        else:
                            logger.warning(f"Model not found in index: {path}")
                            remaining_models_unresolved.append(model_ref)

                    elif action == "skip":
                        remaining_models_unresolved.append(model_ref)
                        logger.info(f"Skipped: {model_ref.widget_value}")

                except KeyboardInterrupt:
                    logger.info("Cancelled - model stays unresolved")
                    remaining_models_unresolved.append(model_ref)
                    break
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
        """Apply resolutions for all workflows with proper context."""
        for workflow in detailed_status.analyzed_workflows:
            self.apply_resolution(
                workflow.resolution,
                workflow_name=workflow.name,
                model_refs=workflow.dependencies.found_models
            )

        # Clean up orphaned models after all workflows processed
        self.pyproject.models.cleanup_orphans()

    def apply_resolution(
        self,
        resolution: ResolutionResult,
        workflow_name: str | None = None,
        model_refs: list[WorkflowNodeWidgetRef] | None = None
    ) -> None:
        """Phase 3b: Apply resolution to pyproject.toml and update workflow JSON.

        Takes a ResolutionResult (from resolve_workflow or fix_workflow)
        and persists resolved nodes and models to pyproject.toml, then
        updates workflow JSON files with resolved paths.

        Args:
            resolution: Result with resolved dependencies to apply
            workflow_name: Name of workflow (for model mappings)
            model_refs: Original model references (for mapping preservation)
        """
        if not resolution.nodes_resolved and not resolution.models_resolved:
            logger.info("No resolved dependencies to apply")
            return

        # Extract node pack IDs from resolved nodes
        node_pack_ids = set([pkg.package_id for pkg in resolution.nodes_resolved])

        # Save custom mappings for user-resolved nodes
        # Match types that indicate user intervention (should be persisted):
        # - "user_confirmed": User selected from search results (InteractiveNodeStrategy)
        # - "manual": User manually entered package ID (InteractiveNodeStrategy)
        # - "heuristic": Auto-matched from installed packages (GlobalNodeResolver)
        # This ensures the same node type auto-resolves in future workflows
        user_intervention_types = ("user_confirmed", "manual", "heuristic")
        saved_mappings = 0
        for pkg in resolution.nodes_resolved:
            if pkg.match_type in user_intervention_types:
                self.pyproject.node_mappings.add_mapping(pkg.node_type, pkg.package_id)
                saved_mappings += 1
                logger.debug(f"Saved custom mapping: {pkg.node_type} -> {pkg.package_id}")

        if saved_mappings > 0:
            logger.info(f"Saved {saved_mappings} custom node mapping(s) for future resolution")

        # Update pyproject.toml with model metadata and mappings
        if workflow_name:
            self.pyproject.workflows.apply_resolution(
                workflow_name=workflow_name,
                models=resolution.models_resolved,
                model_refs=model_refs or [],
                node_packs=node_pack_ids
            )

        # Update workflow JSON with stripped paths for ComfyUI compatibility
        # Note: This is needed even with symlinks - see docs/context/comfyui-node-loader-base-directories.md
        if workflow_name and model_refs and resolution.models_resolved:
            self.update_workflow_model_paths(
                workflow_name=workflow_name,
                resolution=resolution,
                model_refs=model_refs
            )

    def update_workflow_model_paths(
        self,
        workflow_name: str,
        resolution: ResolutionResult,
        model_refs: list[WorkflowNodeWidgetRef]
    ) -> None:
        """Update workflow JSON files with resolved and stripped model paths.

        This strips the base directory prefix (e.g., 'checkpoints/') from model paths
        because ComfyUI node loaders automatically prepend their base directories.

        See: docs/context/comfyui-node-loader-base-directories.md for detailed explanation.

        Args:
            workflow_name: Name of workflow to update
            resolution: Resolution result with resolved models
            model_refs: Original model references from workflow analysis
        """
        from ..repositories.workflow_repository import WorkflowRepository

        # Load workflow from ComfyUI directory
        workflow_path = self.comfyui_workflows / f"{workflow_name}.json"
        if not workflow_path.exists():
            logger.warning(f"Workflow {workflow_name} not found at {workflow_path}")
            return

        workflow = WorkflowRepository.load(workflow_path)

        # Update each resolved model's path in the workflow
        for i, model in enumerate(resolution.models_resolved):
            if i < len(model_refs):
                ref = model_refs[i]
                node_id = ref.node_id
                widget_idx = ref.widget_index

                # Update the node's widget value with resolved path
                if node_id in workflow.nodes:
                    node = workflow.nodes[node_id]
                    if widget_idx < len(node.widgets_values):
                        old_path = node.widgets_values[widget_idx]
                        # Strip base directory prefix for ComfyUI node loaders
                        # e.g., "checkpoints/sd15/model.ckpt" → "sd15/model.ckpt"
                        display_path = self._strip_base_directory_for_node(ref.node_type, model.relative_path)
                        node.widgets_values[widget_idx] = display_path
                        logger.debug(f"Updated node {node_id} widget {widget_idx}: {old_path} → {display_path}")

        # Save updated workflow back to ComfyUI
        WorkflowRepository.save(workflow, workflow_path)
        logger.info(f"Updated workflow JSON with stripped paths: {workflow_path}")

        # Note: We intentionally do NOT update .cec here
        # The .cec copy represents "committed state" and should only be updated during commit
        # This ensures workflow status correctly shows as "new" or "modified" until committed

    def _strip_base_directory_for_node(self, node_type: str, relative_path: str) -> str:
        """Strip base directory prefix from path for ComfyUI node loaders.

        ComfyUI node loaders automatically prepend their base directories. For example:
        - CheckpointLoaderSimple prepends "checkpoints/"
        - LoraLoader prepends "loras/"
        - VAELoader prepends "vae/"

        The widget value should NOT include the base directory to avoid path doubling.

        See: docs/context/comfyui-node-loader-base-directories.md for detailed explanation.

        Args:
            node_type: ComfyUI node type (e.g., "CheckpointLoaderSimple")
            relative_path: Full path relative to models/ (e.g., "checkpoints/SD1.5/model.safetensors")

        Returns:
            Path without base directory prefix (e.g., "SD1.5/model.safetensors")

        Examples:
            >>> _strip_base_directory_for_node("CheckpointLoaderSimple", "checkpoints/sd15/model.ckpt")
            "sd15/model.ckpt"

            >>> _strip_base_directory_for_node("LoraLoader", "loras/style.safetensors")
            "style.safetensors"

            >>> _strip_base_directory_for_node("CheckpointLoaderSimple", "checkpoints/a/b/c/model.ckpt")
            "a/b/c/model.ckpt"  # Subdirectories preserved
        """
        from ..configs.model_config import ModelConfig

        model_config = ModelConfig.load()
        base_dirs = model_config.get_directories_for_node(node_type)

        for base_dir in base_dirs:
            prefix = base_dir + "/"
            if relative_path.startswith(prefix):
                # Strip the base directory but preserve subdirectories
                return relative_path[len(prefix):]

        # No matching base directory - return as-is
        # This handles edge cases or unknown node types
        return relative_path

    def find_similar_models(
        self,
        missing_ref: str,
        node_type: str,
        limit: int = 5
    ) -> list[ScoredMatch]:
        """Find models similar to missing reference using fuzzy search.

        Args:
            missing_ref: The missing model reference from workflow
            node_type: ComfyUI node type (e.g., "CheckpointLoaderSimple")
            limit: Maximum number of results to return

        Returns:
            List of ScoredMatch objects sorted by confidence (highest first)
        """
        from difflib import SequenceMatcher
        from ..configs.model_config import ModelConfig

        # Load model config for node type mappings
        model_config = ModelConfig.load()

        # Get directories this node type can load from
        directories = model_config.get_directories_for_node(node_type)

        if not directories:
            # Unknown node type - default to checkpoints
            directories = ["checkpoints"]
            logger.warning(f"Unknown node type '{node_type}', defaulting to checkpoints")

        # Get all models from ANY of those directories
        candidates = []
        for directory in directories:
            models = self.model_repository.get_by_category(directory)
            candidates.extend(models)

        if not candidates:
            logger.info(f"No models found in categories: {directories}")
            return []

        # Score each candidate
        scored = []
        missing_name = Path(missing_ref).stem.lower()

        for model in candidates:
            model_name = Path(model.filename).stem.lower()

            # Use Python's difflib for fuzzy matching
            score = SequenceMatcher(None, missing_name, model_name).ratio()

            if score > 0.4:  # Minimum 40% similarity
                confidence = "high" if score > 0.8 else "good" if score > 0.6 else "possible"
                scored.append(ScoredMatch(
                    model=model,
                    score=score,
                    confidence=confidence
                ))

        # Sort by score descending
        scored.sort(key=lambda x: x.score, reverse=True)

        return scored[:limit]
