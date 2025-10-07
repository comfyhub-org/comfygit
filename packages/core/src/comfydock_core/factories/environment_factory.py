"""Factory for creating new environments."""
from __future__ import annotations

from pathlib import Path

from comfydock_core.core.environment import Environment

from ..logging.logging_config import get_logger
from ..managers.git_manager import GitManager
from ..models.exceptions import (
    CDEnvironmentExistsError,
)
from ..utils.comfyui_ops import clone_comfyui

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from comfydock_core.core.workspace import WorkspacePaths
    from comfydock_core.repositories.model_repository import ModelRepository
    from comfydock_core.repositories.workspace_config_repository import WorkspaceConfigRepository
    from comfydock_core.services.registry_data_manager import RegistryDataManager

logger = get_logger(__name__)

class EnvironmentFactory:

    @staticmethod
    def create(
        name: str,
        env_path: Path,
        workspace_paths: WorkspacePaths,
        model_index_manager: ModelRepository,
        workspace_config_manager: WorkspaceConfigRepository,
        registry_data_manager: RegistryDataManager,
        python_version: str = "3.12",
        comfyui_version: str | None = None,
    ) -> Environment:
        """Create a new environment."""
        if env_path.exists():
            raise CDEnvironmentExistsError(f"Environment path already exists: {env_path}")

        # Create structure
        env_path.mkdir(parents=True)
        cec_path = env_path / ".cec"
        cec_path.mkdir()

        # Initialize environment
        env = Environment(
            name,
            env_path,
            workspace_paths,
            model_index_manager,
            workspace_config_manager,
            registry_data_manager,
        )

        # Clone ComfyUI
        logger.info("Cloning ComfyUI (this may take a moment)...")
        try:
            comfyui_version = clone_comfyui(env.comfyui_path, comfyui_version)
            if comfyui_version:
                logger.info(f"Successfully cloned ComfyUI version: {comfyui_version}")
            else:
                logger.warning("ComfyUI clone failed")
                raise RuntimeError("ComfyUI clone failed")
        except Exception as e:
            logger.warning(f"ComfyUI clone failed: {e}")
            raise e

        # Create initial pyproject.toml
        config = EnvironmentFactory._create_initial_pyproject(name, python_version, comfyui_version)
        env.pyproject.save(config)

        # Get requirements from ComfyUI and add them
        comfyui_reqs = env.comfyui_path / "requirements.txt"
        if comfyui_reqs.exists():
            logger.info("Adding ComfyUI requirements...")
            env.uv_manager.add_requirements_with_sources(comfyui_reqs, frozen=True)

        # Initial UV sync to create venv
        logger.info("Creating virtual environment...")
        env.uv_manager.sync_project()

        # Use GitManager for repository initialization
        git_mgr = GitManager(cec_path)
        git_mgr.initialize_environment_repo("Initial environment setup")

        # Create model symlink (FATAL if fails - environment won't work without models)
        try:
            env.model_symlink_manager.create_symlink()
            logger.info("Model directory linked successfully")
        except Exception as e:
            logger.error(f"Failed to create model symlink: {e}")
            raise  # FATAL - environment won't work without models

        logger.info(f"Environment '{name}' created successfully")
        return env

    @staticmethod
    def _create_initial_pyproject(name: str, python_version: str, comfyui_version: str) -> dict:
        """Create the initial pyproject.toml."""
        config = {
            "project": {
                "name": f"comfydock-env-{name}",
                "version": "0.1.0",
                "requires-python": f">={python_version}",
                "dependencies": []
            },
            "tool": {
                "comfydock": {
                    "comfyui_version": comfyui_version,
                    "python_version": python_version,
                    "nodes": {}
                }
            }
        }
        return config
