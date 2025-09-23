"""Workflow Management - track and sync ComfyUI workflows."""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Tuple

from comfydock_core.managers.model_manifest_manager import ModelManifestManager
from comfydock_core.utils.workflow_dependency_parser import WorkflowDependencyParser
from comfydock_core.configs.model_config import ModelConfig

from ..logging.logging_config import get_logger
from ..models.environment import WorkflowStatus
from ..models.exceptions import CDEnvironmentError
from ..models.workflow import InstalledPackageInfo, WorkflowAnalysisResult
from ..services.global_node_resolver import GlobalNodeResolver
# from ..utils.workflow_parser import WorkflowParser
from .pyproject_manager import PyprojectManager
from .workflow_metadata_manager import WorkflowMetadataManager

if TYPE_CHECKING:
    from comfydock_core.managers.model_index_manager import ModelIndexManager
    from comfydock_core.services.registry_data_manager import RegistryDataManager
    from comfydock_core.models.workflow import ModelReference, ModelResolutionResult
    from comfydock_core.models.shared import ModelWithLocation

logger = get_logger(__name__)


class SyncAction(Enum):
    """Possible sync actions for workflows."""
    IN_SYNC = "in_sync"
    RESTORED_TO_COMFYUI = "restored_to_comfyui"
    UPDATED_TRACKED = "updated_tracked"
    UPDATED_COMFYUI = "updated_comfyui"
    MISSING_BOTH = "missing_both"


class SyncStatus(Enum):
    """Possible sync statuses for workflows."""
    IN_SYNC = "in_sync"
    MISSING_COMFYUI = "missing_comfyui"
    MISSING_TRACKED = "missing_tracked"
    MISSING_BOTH = "missing_both"
    COMFYUI_NEWER = "comfyui_newer"
    TRACKED_NEWER = "tracked_newer"


@dataclass
class WorkflowStateInfo:
    """Information about a workflow."""
    name: str
    path: Path
    state: str  # 'tracked', 'watched', 'ignored'
    modified: datetime
    dependencies: dict | None = None


class WorkflowManager:
    """Manages workflow tracking and synchronization."""

    def __init__(
        self,
        env_path: Path,
        pyproject: PyprojectManager,
        model_index_manager: ModelIndexManager,
        global_models_path: Path,
        registry_data_manager: RegistryDataManager,
    ):
        self.env_path = env_path
        self.pyproject = pyproject
        self.model_index_manager = model_index_manager
        self.global_models_path = global_models_path
        self.registry_data_manager = registry_data_manager
        self.model_manifest_manager = ModelManifestManager(
            self.model_index_manager, self.pyproject, self.global_models_path
        )
        # Get the path to node_mappings.json (will fetch if needed)
        node_mapper_path = self.registry_data_manager.get_mappings_path()
        self.global_resolver = GlobalNodeResolver(node_mapper_path)
        self.metadata_manager = WorkflowMetadataManager()

        self.comfyui_workflows = env_path / "ComfyUI" / "user" / "default" / "workflows"
        self.tracked_workflows = env_path / ".cec" / "workflows"
        self.cec_path = env_path / ".cec"

        # Ensure directories exist
        self.comfyui_workflows.mkdir(parents=True, exist_ok=True)
        self.tracked_workflows.mkdir(parents=True, exist_ok=True)

    def scan_workflows(self) -> dict[str, WorkflowStateInfo]:
        """Discover all workflows and their states."""
        workflow_state = {}
        tracked_names = set(self.pyproject.workflows.get_tracked().keys())

        # Scan ComfyUI workflows directory
        # TODO: Ignore workflows defined in .comfydockignore
        if self.comfyui_workflows.exists():
            for workflow_file in self.comfyui_workflows.glob("*.json"):
                name = workflow_file.stem
                state = "tracked" if name in tracked_names else "watched"
                workflow_state[name] = WorkflowStateInfo(
                    name=name,
                    path=workflow_file,
                    state=state,
                    modified=datetime.fromtimestamp(workflow_file.stat().st_mtime)
                )

        # Check for tracked workflows that might not exist in ComfyUI dir
        for name in tracked_names:
            if name not in workflow_state:
                tracked_path = self.tracked_workflows / f"{name}.json"
                if tracked_path.exists():
                    workflow_state[name] = WorkflowStateInfo(
                        name=name,
                        path=tracked_path,
                        state="tracked",
                        modified=datetime.fromtimestamp(tracked_path.stat().st_mtime)
                    )

        return workflow_state

    def analyze_workflow(self, name: str) -> WorkflowAnalysisResult:
        """Analyze a workflow's dependencies without side effects.

        Returns:
            WorkflowAnalysisResult with all dependency information.
        """
        workflow_file = self.comfyui_workflows / f"{name}.json"
        if not workflow_file.exists():
            raise CDEnvironmentError(f"Workflow '{name}' not found in ComfyUI workflows")

        # Check if already tracked
        tracked = self.pyproject.workflows.get_tracked()
        already_tracked = name in tracked

        # Initialize result
        result = WorkflowAnalysisResult(
            name=name,
            workflow_path=workflow_file,
            already_tracked=already_tracked
        )

        # Parse dependencies
        dependency_parser = WorkflowDependencyParser(workflow_file, self.model_index_manager)
        workflow_deps = dependency_parser.analyze_dependencies()
        logger.debug(f"Workflow '{name}' parsed - found {len(workflow_deps.resolved_models)} models, "
                     f"{len(workflow_deps.custom_nodes)} custom nodes")

        # Store model information
        result.resolved_models = workflow_deps.resolved_models or []
        result.model_hashes = workflow_deps.model_hashes or []
        result.python_dependencies = workflow_deps.python_dependencies or []
        result.total_custom_nodes = len(workflow_deps.custom_nodes)
        result.total_builtin_nodes = len(workflow_deps.builtin_nodes) if workflow_deps.builtin_nodes else 0

        # Enhanced node resolution using rich node data
        resolution_result = self.global_resolver.resolve_workflow_nodes(workflow_deps.custom_nodes)
        result.resolved_nodes = resolution_result.resolved
        result.unresolved_nodes = resolution_result.unresolved

        # Classify packages as installed vs missing
        existing_nodes = self.pyproject.nodes.get_existing()
        for suggestion in resolution_result.suggested_packages:
            package_id = suggestion.package_id
            if self._is_node_installed(package_id, existing_nodes):
                installed_version = self._get_installed_version(package_id, existing_nodes)
                result.installed_packages.append(InstalledPackageInfo(
                    package_id=package_id,
                    display_name=suggestion.display_name,
                    installed_version=installed_version,
                    suggested_version=suggestion.suggested_version
                ))
            else:
                result.missing_packages.append(suggestion)

        logger.info(f"Analyzed workflow '{name}': "
                   f"{len(result.resolved_nodes)} resolved, "
                   f"{len(result.installed_packages)} installed, "
                   f"{len(result.missing_packages)} missing, "
                   f"{len(result.unresolved_nodes)} unresolved")

        return result

    def track_workflow(self, name: str, analysis: WorkflowAnalysisResult | None = None) -> None:
        """Start tracking a workflow.

        Args:
            name: Workflow name
            analysis: Pre-computed analysis (if None, will analyze)
        """
        if not analysis:
            analysis = self.analyze_workflow(name)

        if analysis.already_tracked:
            raise CDEnvironmentError(f"Workflow '{name}' is already tracked")

        # Copy to tracked directory
        tracked_file = self.tracked_workflows / f"{name}.json"
        shutil.copy2(analysis.workflow_path, tracked_file)

        # Extract resolved models and ensure they're in the manifest
        for model in analysis.resolved_models:
            # Only add if it's a proper ModelWithLocation object
            if hasattr(model, 'hash') and hasattr(model, 'location'):
                self.model_manifest_manager.ensure_model_in_manifest(model)

        # Build requires dict from analysis
        simplified_requires = analysis.to_pyproject_requires()

        # Add to pyproject.toml
        workflow_config = {
            "file": f"workflows/{name}.json",
            "requires": simplified_requires
        }
        self.pyproject.workflows.add(name, workflow_config)

        logger.info(f"Started tracking workflow '{name}'")


    def _is_node_installed(self, package_id: str, existing_nodes: dict) -> bool:
        """Check if node package is already installed."""
        # Check direct package_id match or registry_id match
        for node_info in existing_nodes.values():
            if (hasattr(node_info, 'registry_id') and node_info.registry_id == package_id or
                package_id in str(node_info)):
                return True
        return False

    def _get_installed_version(self, package_id: str, existing_nodes: dict) -> str:
        """Get installed version of a package."""
        for node_info in existing_nodes.values():
            if (hasattr(node_info, 'registry_id') and node_info.registry_id == package_id or
                package_id in str(node_info)):
                return getattr(node_info, 'version', 'unknown') or 'unknown'
        return 'unknown'

    def untrack_workflow(self, name: str) -> None:
        """Stop tracking a workflow."""
        tracked = self.pyproject.workflows.get_tracked()
        if name not in tracked:
            raise CDEnvironmentError(f"Workflow '{name}' is not tracked")

        # Remove from pyproject.toml
        self.pyproject.workflows.remove(name)

        # Remove from tracked directory
        tracked_file = self.tracked_workflows / f"{name}.json"
        if tracked_file.exists():
            tracked_file.unlink()

        # Clean up orphaned models from required category
        self.model_manifest_manager.clean_orphaned_models()

        logger.info(f"Stopped tracking workflow '{name}' (ComfyUI copy preserved)")

    def sync_workflows(self) -> dict[str, str]:
        """Sync tracked workflows between directories."""
        results = {}
        tracked = self.pyproject.workflows.get_tracked()

        for name in tracked:
            comfyui_file = self.comfyui_workflows / f"{name}.json"
            tracked_file = self.tracked_workflows / f"{name}.json"

            # Determine sync direction
            if not comfyui_file.exists() and tracked_file.exists():
                # Copy from tracked to ComfyUI
                shutil.copy2(tracked_file, comfyui_file)
                action = SyncAction.RESTORED_TO_COMFYUI
            elif not tracked_file.exists() and comfyui_file.exists():
                # Copy from ComfyUI to tracked
                shutil.copy2(comfyui_file, tracked_file)
                action = SyncAction.UPDATED_TRACKED
            elif comfyui_file.exists() and tracked_file.exists():
                # Check which is newer
                comfyui_mtime = comfyui_file.stat().st_mtime
                tracked_mtime = tracked_file.stat().st_mtime

                if abs(comfyui_mtime - tracked_mtime) < 1:  # Same within 1 second
                    action = SyncAction.IN_SYNC
                elif comfyui_mtime > tracked_mtime:
                    # ComfyUI is newer, update tracked
                    shutil.copy2(comfyui_file, tracked_file)
                    action = SyncAction.UPDATED_TRACKED
                else:
                    # Tracked is newer, update ComfyUI
                    shutil.copy2(tracked_file, comfyui_file)
                    action = SyncAction.UPDATED_COMFYUI
            else:
                action = SyncAction.MISSING_BOTH

            results[name] = action.value

        return results

    def get_sync_status(self) -> dict[str, str]:
        """Get sync status without modifying files."""
        results = {}
        tracked = self.pyproject.workflows.get_tracked()

        for name in tracked:
            comfyui_file = self.comfyui_workflows / f"{name}.json"
            tracked_file = self.tracked_workflows / f"{name}.json"

            if not comfyui_file.exists() and not tracked_file.exists():
                status = SyncStatus.MISSING_BOTH
            elif not comfyui_file.exists():
                status = SyncStatus.MISSING_COMFYUI
            elif not tracked_file.exists():
                status = SyncStatus.MISSING_TRACKED
            else:
                comfyui_mtime = comfyui_file.stat().st_mtime
                tracked_mtime = tracked_file.stat().st_mtime

                if abs(comfyui_mtime - tracked_mtime) < 1:
                    status = SyncStatus.IN_SYNC
                elif comfyui_mtime > tracked_mtime:
                    status = SyncStatus.COMFYUI_NEWER
                else:
                    status = SyncStatus.TRACKED_NEWER

            results[name] = status.value

        return results

    def get_full_status(self) -> WorkflowStatus:
        """Get complete workflow status with all details encapsulated.

        Returns:
            WorkflowStatus with all workflow information
        """
        # Scan all workflows
        workflows = self.scan_workflows()

        # Get sync status for tracked workflows
        sync_status = self.get_sync_status()

        # Categorize workflows
        tracked = [name for name, info in workflows.items() if info.state == "tracked"]
        watched = [name for name, info in workflows.items() if info.state == "watched"]

        # Check if all tracked workflows are in sync
        in_sync = all(status == SyncStatus.IN_SYNC.value for status in sync_status.values())

        # Build list of changes needed
        changes_needed = []
        for name, status in sync_status.items():
            if status != SyncStatus.IN_SYNC.value:
                changes_needed.append({"name": name, "status": status})

        return WorkflowStatus(
            in_sync=in_sync,
            sync_status=sync_status,
            tracked=tracked,
            watched=watched,
            changes_needed=changes_needed
        )

    def analyze_workflow_models(self, name: str) -> Tuple[List["ModelResolutionResult"], Dict | None]:
        """Analyze workflow models and return resolution results"""
        workflow_file = self.comfyui_workflows / f"{name}.json"

        # Load workflow
        with open(workflow_file) as f:
            workflow_data = json.load(f)

        # Extract existing metadata if present
        existing_metadata = self.metadata_manager.extract_metadata(workflow_data)

        # Parse and analyze
        parser = WorkflowDependencyParser(
            workflow_file,
            self.model_index_manager,
            ModelConfig.load()
        )
        results = parser.analyze_models_enhanced()

        return results, existing_metadata

    def track_workflow_with_resolutions(
        self,
        name: str,
        resolutions: Dict[Tuple[str, int], "ModelWithLocation"] | None = None
    ) -> Tuple[int, int]:
        """Track workflow with user-selected resolutions for ambiguous models

        Args:
            name: Workflow name
            resolutions: {(node_id, widget_index): chosen_model} for ambiguous cases

        Returns:
            (resolved_count, unresolved_count)
        """
        workflow_file = self.comfyui_workflows / f"{name}.json"

        # Load workflow
        with open(workflow_file) as f:
            workflow_data = json.load(f)

        # Get analysis
        results, _ = self.analyze_workflow_models(name)

        # Apply resolutions to ambiguous cases
        all_refs = []
        for result in results:
            ref = result.reference
            if result.resolution_type == "ambiguous" and resolutions:
                key = (ref.node_id, ref.widget_index)
                if key in resolutions:
                    ref.resolved_model = resolutions[key]
                    ref.resolution_confidence = 0.9

            all_refs.append(ref)

        # Inject metadata
        workflow_data = self.metadata_manager.inject_metadata(workflow_data, all_refs)

        # Save to both locations
        tracked_file = self.tracked_workflows / f"{name}.json"
        for path in [tracked_file, workflow_file]:
            with open(path, 'w') as f:
                json.dump(workflow_data, f, indent=2)

        # Add resolved models to manifest
        for ref in all_refs:
            if ref.resolved_model:
                self.model_manifest_manager.ensure_model_in_manifest(
                    ref.resolved_model,
                    category="required"
                )

        # Update pyproject
        resolved_hashes = [ref.resolved_model.hash for ref in all_refs if ref.resolved_model]
        workflow_config = {
            "file": f"workflows/{name}.json",
            "requires": {
                "models": resolved_hashes,
                "nodes": []  # Keep existing
            }
        }
        self.pyproject.workflows.add(name, workflow_config)

        # Return counts
        resolved = sum(1 for ref in all_refs if ref.resolved_model)
        unresolved = len(all_refs) - resolved

        return resolved, unresolved
