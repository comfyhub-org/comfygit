"""Export/Import manager for bundling and extracting environments."""
from __future__ import annotations

import shutil
import tarfile
from pathlib import Path
from typing import TYPE_CHECKING

from ..logging.logging_config import get_logger

if TYPE_CHECKING:
    from ..core.environment import Environment
    from ..models.protocols import ImportCallbacks
    from .pyproject_manager import PyprojectManager

logger = get_logger(__name__)


class ExportImportManager:
    """Manages environment export and import operations."""

    def __init__(self, cec_path: Path, comfyui_path: Path):
        self.cec_path = cec_path
        self.comfyui_path = comfyui_path

    def create_export(
        self,
        output_path: Path,
        pyproject_manager: PyprojectManager
    ) -> Path:
        """Create export tarball.

        Args:
            output_path: Output .tar.gz file path
            pyproject_manager: PyprojectManager for reading config

        Returns:
            Path to created tarball
        """
        logger.info(f"Creating export at {output_path}")

        with tarfile.open(output_path, "w:gz") as tar:
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

            # Add dev nodes (read from pyproject.toml)
            pyproject_data = pyproject_manager.load()
            nodes_config = pyproject_data.get("tool", {}).get("comfydock", {}).get("nodes", {})
            dev_nodes = [name for name, node in nodes_config.items() if node.get("source") == "development"]

            custom_nodes_path = self.comfyui_path / "custom_nodes"
            if custom_nodes_path.exists():
                for node_name in dev_nodes:
                    node_path = custom_nodes_path / node_name
                    if node_path.exists():
                        self._add_filtered_directory(tar, node_path, f"dev_nodes/{node_name}")

        logger.info(f"Export created successfully: {output_path}")
        return output_path

    def extract_import(self, tarball_path: Path, target_cec_path: Path) -> None:
        """Extract import tarball to target .cec directory.

        Args:
            tarball_path: Path to .tar.gz file
            target_cec_path: Target .cec directory (must not exist)

        Raises:
            ValueError: If target already exists
        """
        if target_cec_path.exists():
            raise ValueError(f"Target path already exists: {target_cec_path}")

        logger.info(f"Extracting import from {tarball_path}")

        # Create target directory
        target_cec_path.mkdir(parents=True)

        # Extract tarball (use data filter for Python 3.14+ compatibility)
        with tarfile.open(tarball_path, "r:gz") as tar:
            tar.extractall(target_cec_path, filter='data')

        logger.info(f"Import extracted successfully to {target_cec_path}")

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
    ) -> None:
        """Complete import flow - extract, install dependencies, sync nodes, resolve workflows.

        Args:
            env: Target environment (must be freshly created with .cec extracted)
            tarball_path: Path to .tar.gz bundle
            model_strategy: "all", "required", or "skip"
            callbacks: Optional callbacks for progress updates

        Raises:
            ValueError: If environment already has ComfyUI or is not properly initialized
        """
        logger.info(f"Starting import from {tarball_path}")

        # Verify environment is in correct state
        if env.comfyui_path.exists():
            raise ValueError("Environment already has ComfyUI - cannot import")

        # Determine ComfyUI version to clone from pyproject.toml
        comfyui_version = None
        comfyui_version_type = None
        try:
            pyproject_data = env.pyproject.load()
            comfydock_config = pyproject_data.get("tool", {}).get("comfydock", {})
            comfyui_version = comfydock_config.get("comfyui_version")
            comfyui_version_type = comfydock_config.get("comfyui_version_type")
        except Exception as e:
            logger.warning(f"Could not read comfyui_version from pyproject.toml: {e}")

        if comfyui_version:
            version_desc = f"{comfyui_version_type} {comfyui_version}" if comfyui_version_type else comfyui_version
            logger.debug(f"Using comfyui_version from pyproject: {version_desc}")

        # Auto-detect version type if not specified (for old exports)
        if not comfyui_version_type and comfyui_version:
            if comfyui_version.startswith('v'):
                comfyui_version_type = "release"
            elif comfyui_version in ("main", "master"):
                comfyui_version_type = "branch"
            else:
                comfyui_version_type = "commit"
            logger.debug(f"Auto-detected version type: {comfyui_version_type}")

        # Phase 1: Clone or restore ComfyUI from cache
        from ..caching.comfyui_cache import ComfyUICacheManager, ComfyUISpec
        from ..utils.comfyui_ops import clone_comfyui
        from ..utils.git import git_rev_parse

        comfyui_cache = ComfyUICacheManager(cache_base_path=env.workspace_paths.cache)

        # Create version spec for caching
        spec = ComfyUISpec(
            version=comfyui_version or "main",
            version_type=comfyui_version_type or "branch",
            commit_sha=None  # Will be set after cloning
        )

        # Check cache first
        cached_path = comfyui_cache.get_cached_comfyui(spec)

        if cached_path:
            # Restore from cache
            if callbacks:
                callbacks.on_phase("restore_comfyui", f"Restoring ComfyUI {spec.version} from cache...")
            logger.info(f"Restoring ComfyUI {spec.version} from cache")
            shutil.copytree(cached_path, env.comfyui_path)
        else:
            # Clone fresh
            if callbacks:
                callbacks.on_phase("clone_comfyui", f"Cloning ComfyUI {spec.version}...")
            logger.info(f"Cloning ComfyUI {spec.version}")
            clone_comfyui(env.comfyui_path, comfyui_version)

            # Get commit SHA and cache it
            commit_sha = git_rev_parse(env.comfyui_path, "HEAD")
            spec.commit_sha = commit_sha
            comfyui_cache.cache_comfyui(spec, env.comfyui_path)
            logger.info(f"Cached ComfyUI {spec.version} ({commit_sha[:7]})")

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
