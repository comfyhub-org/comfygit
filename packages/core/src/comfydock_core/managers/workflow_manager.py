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
    ModelResolutionContext,
    ResolutionResult,
    CommitAnalysis,
    ResolvedModel,
    WorkflowNode,
    WorkflowNodeWidgetRef,
    WorkflowAnalysisStatus,
    DetailedWorkflowStatus,
    WorkflowSyncStatus,
    ScoredMatch,
    NodeResolutionContext,
)
from ..repositories.workflow_repository import WorkflowRepository
from ..models.protocols import NodeResolutionStrategy, ModelResolutionStrategy
from ..analyzers.workflow_dependency_parser import WorkflowDependencyParser
from ..logging.logging_config import get_logger

if TYPE_CHECKING:
    from .pyproject_manager import PyprojectManager
    from ..repositories.model_repository import ModelRepository
    from ..models.workflow import WorkflowDependencies, ResolvedNodePackage

logger = get_logger(__name__)

CATEGORY_CRITICALITY_DEFAULTS = {
    "checkpoints": "flexible",
    "vae": "flexible",
    "text_encoders": "flexible",
    "loras": "required",
    "controlnet": "required",
    "clip_vision": "required",
    "style_models": "required",
    "embeddings": "required",
    "upscale_models": "optional",
}


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

    def _normalize_package_id(self, package_id: str) -> str:
        """Normalize GitHub URLs to registry IDs if they exist in the registry.

        This prevents duplicate entries when users manually enter GitHub URLs
        for packages that exist in the registry.

        Args:
            package_id: Package ID (registry ID or GitHub URL)

        Returns:
            Normalized package ID (registry ID if URL matches, otherwise unchanged)
        """
        # Check if it's a GitHub URL
        if package_id.startswith(('https://', 'git@', 'ssh://')):
            # Try to resolve to registry package
            if registry_pkg := self.global_node_resolver.resolve_github_url(package_id):
                return registry_pkg.id

        # Return as-is if not a GitHub URL or not in registry
        return package_id


    def _write_single_model_resolution(
        self,
        workflow_name: str,
        model_ref: WorkflowNodeWidgetRef,
        model: ModelWithLocation | None
    ) -> None:
        """Write a single model resolution immediately (progressive mode).

        Updates both pyproject.toml and workflow JSON for ONE model.
        This enables Ctrl+C safety and auto-resume.

        Args:
            workflow_name: Workflow being resolved
            model_ref: The workflow node widget reference
            model: Resolved model (or None for optional_unresolved)
        """
        # Determine model category
        is_optional = getattr(model, '_is_optional_nice_to_have', False) if model else False
        category = "optional" if is_optional or model is None else "required"

        # Write to pyproject.toml models section
        if model is None:
            # Type 1 optional: filename-based
            self.pyproject.models.add_model(
                model_hash=model_ref.widget_value,  # Filename as key
                filename=model_ref.widget_value,
                file_size=0,
                category="optional",
                unresolved=True
            )
            model_hash = model_ref.widget_value  # For mapping
        else:
            # Regular or Type 2 optional: hash-based
            self.pyproject.models.add_model(
                model_hash=model.hash,
                filename=model.filename,
                file_size=model.file_size,
                relative_path=model.relative_path,
                category=category
            )
            model_hash = model.hash

        # Update workflow mappings in pyproject.toml
        existing_mappings = self.pyproject.workflows.get_model_resolutions(workflow_name)
        if model_hash not in existing_mappings:
            existing_mappings[model_hash].nodes = [] # Initialize

        # Add this node location to the mapping (avoid duplicates)
        if model_ref not in existing_mappings[model_hash].nodes:
            existing_mappings[model_hash].nodes.append(model_ref)

        self.pyproject.workflows.set_model_resolutions(workflow_name, existing_mappings)

        # Update workflow JSON (skip if optional_unresolved or custom node)
        if model and self.model_resolver.model_config.is_model_loader_node(model_ref.node_type):
            workflow_path = self.comfyui_workflows / f"{workflow_name}.json"
            if workflow_path.exists():
                workflow = WorkflowRepository.load(workflow_path)

                # Update the specific node's widget value
                if model_ref.node_id in workflow.nodes:
                    node = workflow.nodes[model_ref.node_id]
                    if model_ref.widget_index < len(node.widgets_values):
                        display_path = self._strip_base_directory_for_node(
                            model_ref.node_type,
                            model.relative_path
                        )
                        node.widgets_values[model_ref.widget_index] = display_path
                        logger.debug(f"Incrementally updated workflow JSON node {model_ref.node_id}")

                # Save immediately
                WorkflowRepository.save(workflow, workflow_path)

    def _write_single_node_resolution(
        self,
        workflow_name: str,
        node_package_id: str
    ) -> None:
        """Write a single node resolution immediately (progressive mode).

        Updates workflow.nodes section in pyproject.toml for ONE node.
        This enables Ctrl+C safety and auto-resume.

        Args:
            workflow_name: Workflow being resolved
            node_package_id: Package ID to add to workflow.nodes
        """
        # Get existing workflow node packages from pyproject
        workflows_config = self.pyproject.workflows.get_all_with_resolutions()
        workflow_config = workflows_config.get(workflow_name, {})
        existing_nodes = set(workflow_config.get('nodes', []))

        # Add new package (set handles deduplication)
        existing_nodes.add(node_package_id)

        # Write back to pyproject
        self.pyproject.workflows.set_node_packs(workflow_name, existing_nodes)
        logger.debug(f"Added {node_package_id} to workflow '{workflow_name}' nodes")

    def get_workflow_path(self, name: str) -> Path:
        """Check if workflow exists in ComfyUI directory and return path.
        
        Args:
            name: Workflow name

        Returns:
            Path to workflow file if it exists
            
        Raises:
            FileNotFoundError
        """
        workflow_path = self.comfyui_workflows / f"{name}.json"
        if workflow_path.exists():
            return workflow_path
        else:
            raise FileNotFoundError(f"Workflow '{name}' not found in ComfyUI directory")

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

        # Phase 3: Calculate uninstalled nodes (for CLI display)
        # Get workflow's declared node requirements from pyproject.toml
        workflows_config = self.pyproject.workflows.get_all_with_resolutions()
        workflow_config = workflows_config.get(name, {})
        workflow_needs = set(workflow_config.get('nodes', []))

        # Get actually installed nodes
        installed = set(self.pyproject.nodes.get_existing().keys())

        # Calculate uninstalled = needed - installed
        uninstalled_nodes = list(workflow_needs - installed)

        return WorkflowAnalysisStatus(
            name=name,
            sync_state=sync_state,
            dependencies=dependencies,
            resolution=resolution,
            uninstalled_nodes=uninstalled_nodes
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

    def analyze_workflow(self, name: str) -> WorkflowDependencies:
        """Analyze a single workflow for dependencies - pure analysis, no side effects.
        
        Args:
            name: Workflow name

        Returns:
            WorkflowDependencies
            
        Raises:
            FileNotFoundError if workflow not found
        """

        workflow_path = self.get_workflow_path(name)

        parser = WorkflowDependencyParser(workflow_path)

        # Get dependencies (nodes + models)
        deps = parser.analyze_dependencies()

        return deps

    def resolve_workflow(self, analysis: WorkflowDependencies) -> ResolutionResult:
        """Attempt automatic resolution of workflow dependencies.

        Takes the provided analysis and tries to resolve:
        - Missing nodes → node packages from registry/GitHub using GlobalNodeResolver
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
        
        models_resolved: list[ResolvedModel] = []
        models_unresolved: list[WorkflowNodeWidgetRef] = []
        models_ambiguous: list[list[ResolvedModel]] = []

        workflow_name = analysis.workflow_name

        # Build node resolution context with per-workflow custom_node_map
        node_context = NodeResolutionContext(
            installed_packages=self.pyproject.nodes.get_existing(),
            custom_mappings=self.pyproject.workflows.get_custom_node_map(workflow_name),
            workflow_name=workflow_name,
            auto_select_ambiguous=True # TODO: Make configurable
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
                    # TODO: Log if the same node type already exists with a different cnr_id
                    unique_nodes[node.type] = node

        logger.debug(f"Resolving {len(unique_nodes)} unique node types from {len(analysis.non_builtin_nodes)} total non-builtin nodes")

        # Resolve each unique node type with context
        for node_type, node in unique_nodes.items():
            logger.debug(f"Trying to resolve node: {node}")
            resolved_packages = self.global_node_resolver.resolve_single_node_with_context(node, node_context)

            if resolved_packages is None:
                # Not resolved - trigger strategy
                logger.debug(f"Node not found: {node}")
                nodes_unresolved.append(node)
            elif len(resolved_packages) == 1:
                # Single match - cleanly resolved
                logger.debug(f"Resolved node: {resolved_packages[0]}")
                nodes_resolved.append(resolved_packages[0])
            else:
                # Multiple matches from registry (ambiguous)
                nodes_ambiguous.append(resolved_packages)
                
        # Build simplified context with previous resolutions lookup
        previous_resolutions = {}
        workflow_models = self.pyproject.workflows.get_workflow_models(workflow_name)

        for manifest_model in workflow_models:
            if manifest_model.hash and manifest_model.status == "resolved":
                for ref in manifest_model.nodes:
                    previous_resolutions[ref] = manifest_model.hash

        model_context = ModelResolutionContext(
            workflow_name=workflow_name,
            previous_resolutions=previous_resolutions,
            auto_select_ambiguous=True # TODO: Make configurable
        )

        # Resolve models - build mapping from ref to resolved model
        for model_ref in analysis.found_models:
            result = self.model_resolver.resolve_model(model_ref, model_context)

            if result is None:
                # Model not found at all
                logger.debug(f"Failed to resolve model: {model_ref}")
                models_unresolved.append(model_ref)
            elif len(result) == 1:
                # Clean resolution (exact match or from pyproject cache)
                logger.debug(f"Resolved model: {result[0]}")
                models_resolved = result
            elif len(result) > 1:
                # Ambiguous - multiple matches
                logger.debug(f"Ambiguous model: {result}")
                models_ambiguous.append(result)
            else:
                # No resolution possible
                logger.debug(f"Failed to resolve model: {model_ref}, result: {result}")
                models_unresolved.append(model_ref)

        return ResolutionResult(
            workflow_name=workflow_name,
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
        model_strategy: ModelResolutionStrategy | None = None
    ) -> ResolutionResult:
        """Fix remaining issues using strategies with progressive writes.

        Takes ResolutionResult from resolve_workflow() and uses strategies to resolve ambiguities.
        ALL user choices are written immediately (progressive mode):
        - Each model resolution writes to pyproject + workflow JSON
        - Each node mapping writes to global node_mappings table
        - Ctrl+C preserves partial progress

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

        # Collect optional node types that user marked
        optional_node_types: list[str] = []

        workflow_name = resolution.workflow_name

        # Fix ambiguous nodes using strategy
        if node_strategy:
            for packages in resolution.nodes_ambiguous:
                selected = node_strategy.resolve_unknown_node(packages[0].node_type, packages)
                if selected:
                    if selected.match_type == 'optional': # TODO: Make this an enum
                        optional_node_types.append(packages[0].node_type)
                        # PROGRESSIVE: Save optional node mapping to per-workflow custom_node_map
                        if workflow_name:
                            self.pyproject.workflows.set_custom_node_mapping(
                                workflow_name, packages[0].node_type, None
                            )
                        logger.info(f"Marked node '{packages[0].node_type}' as optional")
                    else:
                        nodes_to_add.append(selected)
                        node_id = selected.package_data.id if selected.package_data else None

                        # PROGRESSIVE: Save user-confirmed node mapping to per-workflow custom_node_map
                        user_intervention_types = ("user_confirmed", "manual", "heuristic")
                        if selected.match_type in user_intervention_types and node_id and workflow_name:
                            normalized_id = self._normalize_package_id(node_id)
                            self.pyproject.workflows.set_custom_node_mapping(
                                workflow_name, selected.node_type, normalized_id
                            )
                            logger.info(f"Saved custom_node_map for '{workflow_name}': {selected.node_type} -> {normalized_id}")

                        # PROGRESSIVE: Write to workflow.nodes immediately
                        if workflow_name and node_id:
                            normalized_id = self._normalize_package_id(node_id)
                            self._write_single_node_resolution(workflow_name, normalized_id)

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
                    if selected.match_type == 'optional': # TODO: Make this an enum
                        optional_node_types.append(node.type)
                        # PROGRESSIVE: Save optional node mapping to per-workflow custom_node_map
                        if workflow_name:
                            self.pyproject.workflows.set_custom_node_mapping(
                                workflow_name, node.type, None
                            )
                        logger.info(f"Marked node '{node.type}' as optional")
                    else:
                        nodes_to_add.append(selected)
                        node_id = selected.package_data.id if selected.package_data else None

                        # PROGRESSIVE: Save user-confirmed node mapping to per-workflow custom_node_map
                        user_intervention_types = ("user_confirmed", "manual", "heuristic")
                        if selected.match_type in user_intervention_types and node_id and workflow_name:
                            normalized_id = self._normalize_package_id(node_id)
                            self.pyproject.workflows.set_custom_node_mapping(
                                workflow_name, selected.node_type, normalized_id
                            )
                            logger.info(f"Saved custom_node_map for '{workflow_name}': {selected.node_type} -> {normalized_id}")

                        # PROGRESSIVE: Write to workflow.nodes immediately
                        if workflow_name and node_id:
                            normalized_id = self._normalize_package_id(node_id)
                            self._write_single_node_resolution(workflow_name, normalized_id)

                        logger.info(f"Resolved unresolved node: {node_id}")
                else:
                    remaining_nodes_unresolved.append(node)
        else:
            remaining_nodes_unresolved = list(resolution.nodes_unresolved)

        # Fix ambiguous models using strategy
        if model_strategy:
            for candidate_list in resolution.models_ambiguous:
                resolved = model_strategy.resolve_ambiguous_model(model_ref, candidate_list)
                if resolved:
                    # Check if user wants this as optional (Type 2)
                    is_optional = getattr(resolved, '_mark_as_optional', False)

                    # Create ResolvedModel and add to list
                    resolved_model = ResolvedModel(
                        workflow=workflow_name,
                        reference=model_ref,
                        resolved_model=resolved,
                        match_type="optional" if is_optional else "user_confirmed",
                        match_confidence=1.0
                    )
                    models_to_add.append(resolved_model)

                    optional_marker = " (optional)" if is_optional else ""
                    logger.info(f"Resolved ambiguous model{optional_marker}: {resolved.filename}")

                    # PROGRESSIVE: Write immediately
                    if workflow_name:
                        self._write_single_model_resolution(workflow_name, model_ref, resolved)

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
                            # Create ResolvedModel and add to list
                            resolved_model = ResolvedModel(
                                workflow=workflow_name,
                                reference=model_ref,
                                resolved_model=model,
                                match_type="user_confirmed",
                                match_confidence=1.0
                            )
                            models_to_add.append(resolved_model)
                            logger.info(f"Resolved: {model_ref.widget_value} → {path}")

                            # PROGRESSIVE: Write immediately
                            if workflow_name:
                                self._write_single_model_resolution(workflow_name, model_ref, model)

                        else:
                            logger.warning(f"Model not found in index: {path}")
                            remaining_models_unresolved.append(model_ref)

                    elif action == "optional_unresolved":
                        # Type 1: Mark as optional (unresolved, no hash)
                        resolved_model = ResolvedModel(
                            workflow=workflow_name,
                            reference=model_ref,
                            resolved_model=None,
                            match_type="optional_unresolved",
                            match_confidence=1.0
                        )
                        models_to_add.append(resolved_model)
                        logger.info(f"Marked as optional (unresolved): {model_ref.widget_value}")

                        # PROGRESSIVE: Write immediately
                        if workflow_name:
                            self._write_single_model_resolution(workflow_name, model_ref, None)

                    elif action == "skip":
                        remaining_models_unresolved.append(model_ref)
                        logger.info(f"Skipped: {model_ref.widget_value}")

                except KeyboardInterrupt:
                    logger.info("Cancelled - model stays unresolved")
                    remaining_models_unresolved.append(model_ref)
                    break
        else:
            remaining_models_unresolved = list(resolution.models_unresolved)

        # Return result (no need for _optional_node_types metadata anymore)
        return ResolutionResult(
            workflow_name=workflow_name,
            nodes_resolved=nodes_to_add,
            nodes_unresolved=remaining_nodes_unresolved,
            nodes_ambiguous=remaining_nodes_ambiguous,
            models_resolved=models_to_add,
            models_unresolved=remaining_models_unresolved,
            models_ambiguous=remaining_models_ambiguous,
        )

    def apply_resolution(
        self,
        resolution: ResolutionResult
    ) -> None:
        """Apply resolutions with smart defaults and reconciliation.

        Auto-applies sensible criticality defaults, etc.

        Args:
            resolution: Result with auto-resolved dependencies from resolve_workflow()
        """
        from comfydock_core.models.manifest import ManifestWorkflowModel, ManifestModel

        workflow_name = resolution.workflow_name

        # Phase 1: Reconcile nodes (unchanged)
        target_node_pack_ids = set()
        target_node_types = set()

        for pkg in resolution.nodes_resolved:
            if pkg.is_optional:
                target_node_types.add(pkg.node_type)
            elif pkg.package_id is not None:
                normalized_id = self._normalize_package_id(pkg.package_id)
                target_node_pack_ids.add(normalized_id)
                target_node_types.add(pkg.node_type)

        for node in resolution.nodes_unresolved:
            target_node_types.add(node.type)
        for packages in resolution.nodes_ambiguous:
            if packages:
                target_node_types.add(packages[0].node_type)

        if target_node_pack_ids:
            self.pyproject.workflows.set_node_packs(workflow_name, target_node_pack_ids)
        else:
            self.pyproject.workflows.set_node_packs(workflow_name, None)

        # Reconcile custom_node_map
        existing_custom_map = self.pyproject.workflows.get_custom_node_map(workflow_name)
        for node_type in list(existing_custom_map.keys()):
            if node_type not in target_node_types:
                self.pyproject.workflows.remove_custom_node_mapping(workflow_name, node_type)

        # Phase 2: Build ManifestWorkflowModel entries with smart defaults
        manifest_models: list[ManifestWorkflowModel] = []

        # Group resolved models by hash
        hash_to_refs: dict[str, list[WorkflowNodeWidgetRef]] = {}
        for resolved in resolution.models_resolved:
            if resolved.resolved_model:
                model_hash = resolved.resolved_model.hash
                if model_hash not in hash_to_refs:
                    hash_to_refs[model_hash] = []
                hash_to_refs[model_hash].append(resolved.reference)

        # Create manifest entries for resolved models
        for model_hash, refs in hash_to_refs.items():
            # Get model from first resolved entry
            model = next(
                (r.resolved_model for r in resolution.models_resolved if r.resolved_model and r.resolved_model.hash == model_hash),
                None
            )
            if not model:
                continue

            # Determine criticality with smart defaults
            criticality = self._get_default_criticality(model.category)

            manifest_model = ManifestWorkflowModel(
                hash=model.hash,
                filename=model.filename,
                category=model.category,
                criticality=criticality,
                status="resolved",
                nodes=refs,
                sources=[]  # TODO: Get from CivitAI/HF lookup during export
            )
            manifest_models.append(manifest_model)

            # Also add to global models table
            global_model = ManifestModel(
                hash=model.hash,
                filename=model.filename,
                size=model.file_size,
                relative_path=model.relative_path,
                category=model.category,
                sources=[]
            )
            self.pyproject.models.add_model(global_model)

        # Add unresolved models
        for ref in resolution.models_unresolved:
            category = self._get_category_for_node_ref(ref)
            criticality = self._get_default_criticality(category)

            manifest_model = ManifestWorkflowModel(
                filename=ref.widget_value,
                category=category,
                criticality=criticality,
                status="unresolved",
                nodes=[ref],
                sources=[]
            )
            manifest_models.append(manifest_model)

        # Write all models to workflow
        self.pyproject.workflows.set_workflow_models(workflow_name, manifest_models)
        
        # Clean up orphaned models
        self.pyproject.models.cleanup_orphans()

        # Phase 3: Update workflow JSON with resolved paths
        self.update_workflow_model_paths(resolution)

    def update_workflow_model_paths(
        self,
        resolution: ResolutionResult
    ) -> None:
        """Update workflow JSON files with resolved and stripped model paths.

        IMPORTANT: Only updates paths for BUILTIN ComfyUI nodes. Custom nodes are
        skipped to preserve their original widget values and avoid breaking validation.

        This strips the base directory prefix (e.g., 'checkpoints/') from model paths
        because ComfyUI builtin node loaders automatically prepend their base directories.

        See: docs/knowledge/comfyui-node-loader-base-directories.md for detailed explanation.

        Args:
            resolution: Resolution result with ref→model mapping
            
        Raises:
            FileNotFoundError if workflow not found
        """
        workflow_name = resolution.workflow_name

        # Load workflow from ComfyUI directory
        workflow_path = self.get_workflow_path(workflow_name)

        workflow = WorkflowRepository.load(workflow_path)

        updated_count = 0
        skipped_count = 0

        # Update each resolved model's path in the workflow
        for resolved in resolution.models_resolved:
            ref = resolved.reference
            model = resolved.resolved_model

            # Skip if model is None (Type 1 optional unresolved)
            if model is None:
                continue

            node_id = ref.node_id
            widget_idx = ref.widget_index

            # Skip custom nodes - they have undefined path behavior
            if not self.model_resolver.model_config.is_model_loader_node(ref.node_type):
                logger.debug(
                    f"Skipping path update for custom node '{ref.node_type}' "
                    f"(node_id={node_id}, widget={widget_idx}). "
                    f"Custom nodes manage their own model paths."
                )
                skipped_count += 1
                continue

            # Update the node's widget value with resolved path
            if node_id in workflow.nodes:
                node = workflow.nodes[node_id]
                if widget_idx < len(node.widgets_values):
                    old_path = node.widgets_values[widget_idx]
                    # Strip base directory prefix for ComfyUI BUILTIN node loaders
                    # e.g., "checkpoints/sd15/model.ckpt" → "sd15/model.ckpt"
                    display_path = self._strip_base_directory_for_node(ref.node_type, model.relative_path)
                    node.widgets_values[widget_idx] = display_path
                    logger.debug(f"Updated node {node_id} widget {widget_idx}: {old_path} → {display_path}")
                    updated_count += 1

        # Save updated workflow back to ComfyUI
        WorkflowRepository.save(workflow, workflow_path)
        logger.info(
            f"Updated workflow JSON: {workflow_path} "
            f"({updated_count} builtin nodes updated, {skipped_count} custom nodes preserved)"
        )

        # Note: We intentionally do NOT update .cec here
        # The .cec copy represents "committed state" and should only be updated during commit
        # This ensures workflow status correctly shows as "new" or "modified" until committed

    def _get_default_criticality(self, category: str) -> str:
        """Determine smart default criticality based on model category.

        Args:
            category: Model category (checkpoints, loras, etc.)

        Returns:
            Criticality level: "required", "flexible", or "optional"
        """
        return CATEGORY_CRITICALITY_DEFAULTS.get(category, "required")

    def _get_category_for_node_ref(self, node_ref: WorkflowNodeWidgetRef) -> str:
        """Get model category from node type.

        Args:
            node_type: ComfyUI node type

        Returns:
            Model category string
        """
        # First see if node type is explicitly mapped to a category.
        node_type = node_ref.node_type
        directories = self.model_resolver.model_config.get_directories_for_node(node_type)
        if directories:
            logger.debug(f"Found directory mapping for node type '{node_type}': {directories}")
            return directories[0]  # Use first directory as category
        
        # Next check if widget value path can be converted to category:
        from ..utils.model_categories import get_model_category
        category = get_model_category(node_ref.widget_value)
        logger.debug(f"Found directory mapping for widget value '{node_ref.widget_value}': {category}")
        return category

    def _strip_base_directory_for_node(self, node_type: str, relative_path: str) -> str:
        """Strip base directory prefix from path for BUILTIN ComfyUI node loaders.

        ⚠️ IMPORTANT: This function should ONLY be called for builtin node types that
        are in the node_directory_mappings. Custom nodes should skip path updates entirely.

        ComfyUI builtin node loaders automatically prepend their base directories:
        - CheckpointLoaderSimple prepends "checkpoints/"
        - LoraLoader prepends "loras/"
        - VAELoader prepends "vae/"

        The widget value should NOT include the base directory to avoid path doubling.

        See: docs/knowledge/comfyui-node-loader-base-directories.md for detailed explanation.

        Args:
            node_type: BUILTIN ComfyUI node type (e.g., "CheckpointLoaderSimple")
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

        # Warn if called for custom node (should be skipped in caller)
        if not base_dirs:
            logger.warning(
                f"_strip_base_directory_for_node called for unknown/custom node type: {node_type}. "
                f"Custom nodes should skip path updates entirely. Returning path unchanged."
            )
            return relative_path

        for base_dir in base_dirs:
            prefix = base_dir + "/"
            if relative_path.startswith(prefix):
                # Strip the base directory but preserve subdirectories
                return relative_path[len(prefix):]

        # Path doesn't have expected prefix - return unchanged
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
