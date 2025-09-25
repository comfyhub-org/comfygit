"""Auto workflow tracking - all workflows in ComfyUI are automatically managed."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..models.commit import ModelResolutionRequest
from ..models.workflow import WorkflowAnalysisResult, ResolutionResult, CommitAnalysis, ModelResolutionResult
from ..models.protocols import NodeResolutionStrategy, ModelResolutionStrategy
from ..utils.workflow_dependency_parser import WorkflowDependencyParser
from ..logging.logging_config import get_logger

if TYPE_CHECKING:
    from .pyproject_manager import PyprojectManager
    from .model_index_manager import ModelIndexManager
    from ..models.shared import ModelWithLocation
    from ..services.node_classifier import NodeClassifier

logger = get_logger(__name__)


class WorkflowManager:
    """Manages all workflows automatically - no explicit tracking needed."""

    def __init__(
        self,
        comfyui_path: Path,
        cec_path: Path,
        pyproject: PyprojectManager,
        model_index_manager: ModelIndexManager,
    ):
        self.comfyui_path = comfyui_path
        self.cec_path = cec_path
        self.pyproject = pyproject
        self.model_index_manager = model_index_manager

        self.comfyui_workflows = comfyui_path / "user" / "default" / "workflows"
        self.cec_workflows = cec_path / "workflows"

        # Ensure directories exist
        self.comfyui_workflows.mkdir(parents=True, exist_ok=True)
        self.cec_workflows.mkdir(parents=True, exist_ok=True)

    def get_all_workflows(self) -> dict[str, list[str]]:
        """Get all workflows categorized by their sync status.

        Returns:
            Dict with categories: 'new', 'modified', 'deleted', 'synced'
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

        return {
            'new': sorted(new_workflows),
            'modified': sorted(modified_workflows),
            'deleted': sorted(deleted_workflows),
            'synced': sorted(synced_workflows)
        }

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
                        logger.debug(f"Deleted workflow '{name}' from .cec (no longer in ComfyUI)")
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
                        logger.debug(f"Removed workflow '{name}' from ComfyUI (not in .cec)")
                    except Exception as e:
                        logger.error(f"Failed to remove workflow '{name}': {e}")

        return results

    def get_workflow_status(self) -> dict:
        """Get detailed status of all workflows.

        Returns:
            Status summary with counts and workflow lists
        """
        workflows = self.get_all_workflows()

        return {
            'total_workflows': sum(len(workflows[key]) for key in workflows),
            'has_changes': bool(workflows['new'] or workflows['modified'] or workflows['deleted']),
            'changes_summary': self._get_changes_summary(workflows),
            **workflows
        }

    def _get_changes_summary(self, workflows: dict[str, list[str]]) -> str:
        """Generate human-readable summary of workflow changes."""
        parts = []

        if workflows['new']:
            parts.append(f"{len(workflows['new'])} new")
        if workflows['modified']:
            parts.append(f"{len(workflows['modified'])} modified")
        if workflows['deleted']:
            parts.append(f"{len(workflows['deleted'])} deleted")

        if not parts:
            return "No workflow changes"

        return f"Workflow changes: {', '.join(parts)}"

    def get_full_status(self):
        """Get workflow status in the format expected by EnvironmentStatus."""
        from ..models.environment import WorkflowStatus

        workflows = self.get_all_workflows()

        return WorkflowStatus(
            new=workflows['new'],
            modified=workflows['modified'],
            deleted=workflows['deleted'],
            synced=workflows['synced']
        )

    def analyze_workflow(self, name: str) -> WorkflowAnalysisResult:
        """Analyze a single workflow for dependencies - pure analysis, no side effects."""
        workflow_path = self.comfyui_workflows / f"{name}.json"

        if not workflow_path.exists():
            raise FileNotFoundError(f"Workflow '{name}' not found at {workflow_path}")

        parser = WorkflowDependencyParser(
            workflow_path,
            self.model_index_manager
        )

        # Get dependencies (nodes + models)
        deps = parser.analyze_dependencies()

        # Get model resolutions using enhanced strategies
        model_results = parser.analyze_models()

        # Check which nodes are already installed
        existing_nodes = self.pyproject.nodes.get_existing()

        # Convert node lists to strings (deps contains lists of strings, not nodes)
        builtin_node_names = [str(node) for node in deps.builtin_nodes]
        custom_node_names = [str(node) for node in deps.custom_nodes]

        # Categorize nodes by name
        custom_nodes_installed = {
            node_name: existing_nodes[node_name]
            for node_name in custom_node_names
            if node_name in existing_nodes
        }
        custom_nodes_missing = [
            node_name for node_name in custom_node_names
            if node_name not in existing_nodes
        ]

        # Categorize models by resolution type
        models_resolved = []
        models_ambiguous = []
        models_missing = []

        for result in model_results:
            if result.resolution_type in ["exact", "reconstructed", "metadata", "case_insensitive", "filename"]:
                models_resolved.append(result)
            elif result.resolution_type == "ambiguous":
                models_ambiguous.append(result)
            elif result.resolution_type == "not_found":
                models_missing.append(result)

        # Check if already tracked
        # try:
        #     tracked = self.pyproject.workflows.list()
        #     already_tracked = name in tracked
        # except AttributeError:
        #     # Fallback if method doesn't exist
        #     already_tracked = False

        return WorkflowAnalysisResult(
            workflow_name=name,
            workflow_path=workflow_path,
            custom_nodes_installed=custom_nodes_installed,
            custom_nodes_missing=custom_nodes_missing,
            models_resolved=models_resolved,
            models_ambiguous=models_ambiguous,
            models_missing=models_missing,
            model_resolution_results=model_results,
            builtin_nodes=builtin_node_names,
            custom_nodes_found=custom_node_names,
            already_tracked=False # TODO
        )

    def resolve_workflow(self,
                        analysis: WorkflowAnalysisResult,
                        node_strategy: NodeResolutionStrategy,
                        model_strategy: ModelResolutionStrategy) -> ResolutionResult:
        """Apply resolution strategies to workflow analysis."""
        nodes_added = []
        models_resolved = []
        external_models_added = []

        # Resolve missing nodes
        # Note: We'll need node suggestions logic - for now just log what we'd resolve
        for node_type in analysis.custom_nodes_missing:
            # TODO: Get suggestions from node registry
            suggestions = []  # Placeholder

            if suggestions:
                package_id = node_strategy.resolve_unknown_node(node_type, suggestions)
                if package_id and node_strategy.confirm_node_install(package_id, node_type):
                    # Add to pyproject
                    try:
                        # We'd need access to node_manager here - for now just track the ID
                        nodes_added.append(package_id)
                        logger.info(f"Would add node: {package_id} for {node_type}")
                    except Exception as e:
                        logger.error(f"Failed to add node {package_id}: {e}")

        # Resolve ambiguous models
        for ambiguous_result in analysis.models_ambiguous:
            resolved = model_strategy.resolve_ambiguous_model(
                ambiguous_result.reference,
                ambiguous_result.candidates
            )
            if resolved:
                models_resolved.append(resolved)
                logger.info(f"Resolved model: {resolved.filename}")

        # Handle missing models
        for missing_result in analysis.models_missing:
            url = model_strategy.handle_missing_model(missing_result.reference)
            if url:
                external_models_added.append(url)
                logger.info(f"Added external model: {url}")

        # Apply changes to pyproject if any
        changes_made = bool(nodes_added or models_resolved or external_models_added)
        if changes_made:
            self._apply_resolution_to_pyproject(
                nodes_added, models_resolved, external_models_added
            )

        return ResolutionResult(
            nodes_added=nodes_added,
            models_resolved=models_resolved,
            external_models_added=external_models_added,
            changes_made=changes_made
        )

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

        return CommitAnalysis(
            workflows_copied=workflows_status,
            analyses=analyses
        )

    def _apply_resolution_to_pyproject(self,
                                      nodes_added: list[str],
                                      models_resolved: list,
                                      external_models_added: list[str]) -> None:
        """Apply resolution results to pyproject.toml."""
        # Add resolved models to manifest
        for model in models_resolved:
            self.pyproject.models.add_model(
                model_hash=model.hash,
                filename=model.filename,
                file_size=model.file_size,
                relative_path=model.relative_path,
                category="required"
            )

        # Add external models as URLs
        for url in external_models_added:
            # This would need to be implemented in pyproject manager
            logger.info(f"Would add external model URL: {url}")

        logger.info(f"Applied {len(models_resolved)} models to pyproject.toml")

