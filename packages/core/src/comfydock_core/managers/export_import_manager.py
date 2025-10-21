"""Export/Import manager for bundling and extracting environments."""
from __future__ import annotations

import json
import shutil
import tarfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from ..logging.logging_config import get_logger

if TYPE_CHECKING:
    from ..core.environment import Environment
    from ..models.protocols import ImportCallbacks
    from .pyproject_manager import PyprojectManager

logger = get_logger(__name__)


@dataclass
class ExportManifest:
    """Metadata for an exported environment."""
    timestamp: str
    comfydock_version: str
    environment_name: str
    workflows: list[str]
    python_version: str
    comfyui_version: str | None
    platform: str
    total_models: int
    total_nodes: int
    dev_nodes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "comfydock_version": self.comfydock_version,
            "environment_name": self.environment_name,
            "workflows": self.workflows,
            "python_version": self.python_version,
            "comfyui_version": self.comfyui_version,
            "platform": self.platform,
            "total_models": self.total_models,
            "total_nodes": self.total_nodes,
            "dev_nodes": self.dev_nodes
        }

    @classmethod
    def from_dict(cls, data: dict) -> ExportManifest:
        return cls(
            timestamp=data["timestamp"],
            comfydock_version=data["comfydock_version"],
            environment_name=data["environment_name"],
            workflows=data["workflows"],
            python_version=data["python_version"],
            comfyui_version=data.get("comfyui_version"),
            platform=data["platform"],
            total_models=data["total_models"],
            total_nodes=data["total_nodes"],
            dev_nodes=data.get("dev_nodes", [])
        )


class ExportImportManager:
    """Manages environment export and import operations."""

    def __init__(self, cec_path: Path, comfyui_path: Path):
        self.cec_path = cec_path
        self.comfyui_path = comfyui_path

    def create_export(
        self,
        output_path: Path,
        manifest: ExportManifest,
        pyproject_manager: PyprojectManager
    ) -> Path:
        """Create export tarball.

        Args:
            output_path: Output .tar.gz file path
            manifest: Export metadata
            pyproject_manager: PyprojectManager for reading config

        Returns:
            Path to created tarball
        """
        logger.info(f"Creating export at {output_path}")

        with tarfile.open(output_path, "w:gz") as tar:
            # Add manifest
            manifest_data = json.dumps(manifest.to_dict(), indent=2).encode()
            manifest_info = tarfile.TarInfo(name="manifest.json")
            manifest_info.size = len(manifest_data)
            import io
            tar.addfile(manifest_info, fileobj=io.BytesIO(manifest_data))

            # Add pyproject.toml
            pyproject_path = self.cec_path / "pyproject.toml"
            if pyproject_path.exists():
                tar.add(pyproject_path, arcname="pyproject.toml")

            # Add uv.lock
            lock_path = self.cec_path / "uv.lock"
            if lock_path.exists():
                tar.add(lock_path, arcname="uv.lock")

            # Add .python-version
            python_version_path = self.cec_path / ".python-version"
            if python_version_path.exists():
                tar.add(python_version_path, arcname=".python-version")

            # Add workflows
            workflows_path = self.cec_path / "workflows"
            if workflows_path.exists():
                for workflow_file in workflows_path.glob("*.json"):
                    tar.add(workflow_file, arcname=f"workflows/{workflow_file.name}")

            # Add dev nodes
            custom_nodes_path = self.comfyui_path / "custom_nodes"
            if custom_nodes_path.exists():
                for node_name in manifest.dev_nodes:
                    node_path = custom_nodes_path / node_name
                    if node_path.exists():
                        # Add recursively, respecting .gitignore
                        self._add_filtered_directory(tar, node_path, f"dev_nodes/{node_name}")

        logger.info(f"Export created successfully: {output_path}")
        return output_path

    def extract_import(self, tarball_path: Path, target_cec_path: Path) -> ExportManifest:
        """Extract import tarball to target .cec directory.

        Args:
            tarball_path: Path to .tar.gz file
            target_cec_path: Target .cec directory (must not exist)

        Returns:
            ExportManifest from tarball

        Raises:
            ValueError: If target already exists or tarball is invalid
        """
        if target_cec_path.exists():
            raise ValueError(f"Target path already exists: {target_cec_path}")

        logger.info(f"Extracting import from {tarball_path}")

        # Create target directory
        target_cec_path.mkdir(parents=True)

        # Extract tarball
        with tarfile.open(tarball_path, "r:gz") as tar:
            # Read manifest first
            try:
                manifest_member = tar.getmember("manifest.json")
                manifest_file = tar.extractfile(manifest_member)
                if not manifest_file:
                    raise ValueError("Invalid tarball: manifest.json is empty")
                manifest_data = json.loads(manifest_file.read())
                manifest = ExportManifest.from_dict(manifest_data)
            except KeyError:
                raise ValueError("Invalid tarball: missing manifest.json")

            # Extract all other files (use data filter for Python 3.14+ compatibility)
            tar.extractall(target_cec_path, filter='data')

        logger.info(f"Import extracted successfully to {target_cec_path}")
        return manifest

    def _add_filtered_directory(self, tar: tarfile.TarFile, source_path: Path, arcname: str):
        """Add directory to tarball, filtering by .gitignore.

        Args:
            tar: Open tarfile
            source_path: Source directory
            arcname: Archive name prefix
        """
        # Simple implementation - add all files (MVP)
        # TODO: Add .gitignore filtering if needed
        for item in source_path.rglob("*"):
            if item.is_file():
                # Skip __pycache__ and .pyc files
                if "__pycache__" in item.parts or item.suffix == ".pyc":
                    continue
                relative = item.relative_to(source_path)
                tar.add(item, arcname=f"{arcname}/{relative}")

    def import_bundle(
        self,
        env: Environment,
        tarball_path: Path,
        model_strategy: str = "all",
        callbacks: ImportCallbacks | None = None
    ) -> ExportManifest:
        """Complete import flow - extract, install dependencies, sync nodes, resolve workflows.

        Args:
            env: Target environment (must be freshly created with .cec extracted)
            tarball_path: Path to .tar.gz bundle
            model_strategy: "all", "required", or "skip"
            callbacks: Optional callbacks for progress updates

        Returns:
            ExportManifest from the imported bundle

        Raises:
            ValueError: If environment already has ComfyUI or is not properly initialized
        """
        logger.info(f"Starting import from {tarball_path}")

        # Verify environment is in correct state
        if env.comfyui_path.exists():
            raise ValueError("Environment already has ComfyUI - cannot import")

        # Extract bundle (already done during env creation, but we need the manifest)
        manifest_path = env.cec_path / "manifest.json"
        if not manifest_path.exists():
            raise ValueError("Invalid import state: manifest.json not found in .cec")

        manifest = ExportManifest.from_dict(json.loads(manifest_path.read_text()))

        # Phase 1: Clone ComfyUI
        if callbacks:
            callbacks.on_phase("clone_comfyui", "Cloning ComfyUI...")

        from ..utils.comfyui_ops import clone_comfyui
        clone_comfyui(env.comfyui_path, None)

        # Remove ComfyUI's default models directory (will be replaced with symlink)
        models_dir = env.comfyui_path / "models"
        if models_dir.exists() and not models_dir.is_symlink():
            shutil.rmtree(models_dir)

        # Phase 2: Install dependencies
        if callbacks:
            callbacks.on_phase("install_deps", "Installing dependencies...")

        env.uv_manager.sync_project(verbose=False)

        # Phase 3: Initialize git
        if callbacks:
            callbacks.on_phase("init_git", "Initializing git repository...")

        env.git_manager.initialize_environment_repo(f"Imported from {tarball_path.name}")

        # Phase 4: Copy workflows
        if callbacks:
            callbacks.on_phase("copy_workflows", "Setting up workflows...")

        workflows_src = env.cec_path / "workflows"
        workflows_dst = env.comfyui_path / "user" / "default" / "workflows"
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
            sync_result = env.sync()
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
            workflows_to_resolve = env.prepare_import_with_model_strategy(model_strategy)

        # Resolve workflows with download intents
        from ..strategies.auto import AutoModelStrategy, AutoNodeStrategy

        download_failures = []

        for workflow_name in workflows_to_resolve:
            try:
                result = env.resolve_workflow(
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

        logger.info("Import completed successfully")
        return manifest
