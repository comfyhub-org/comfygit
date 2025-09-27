"""ComfyDock workspace - manages multiple environments within a validated workspace."""

import json
import shutil
from functools import cached_property
from pathlib import Path

from comfydock_core.repositories.workspace_config_repository import WorkspaceConfigRepository

from ..factories.environment_factory import EnvironmentFactory
from ..logging.logging_config import get_logger
from ..repositories.model_repository import ModelRepository
from ..analyzers.model_scanner import ModelScanner
from ..models.exceptions import (
    CDEnvironmentExistsError,
    CDEnvironmentNotFoundError,
    CDWorkspaceError,
    ComfyDockError,
)
from ..models.shared import ModelWithLocation, TrackedDirectory
from ..services.registry_data_manager import RegistryDataManager
from .environment import Environment

logger = get_logger(__name__)


class WorkspacePaths:
    """All paths for the workspace."""

    def __init__(self, root: Path):
        self.root = root.resolve()

    @property
    def environments(self) -> Path:
        return self.root / "environments"

    @property
    def metadata(self) -> Path:
        return self.root / ".metadata"

    @property
    def workspace_file(self) -> Path:
        return self.metadata / "workspace.json"

    @property
    def cache(self) -> Path:
        return self.root / "comfydock_cache"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    def exists(self) -> bool:
        return self.root.exists() and self.metadata.exists()

    def ensure_directories(self) -> None:
        self.environments.mkdir(parents=True, exist_ok=True)
        self.metadata.mkdir(parents=True, exist_ok=True)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.logs.mkdir(parents=True, exist_ok=True)

class Workspace:
    """Manages ComfyDock workspace and all environments within it.
    
    Represents an existing, validated workspace - no nullable state.
    """

    def __init__(self, paths: WorkspacePaths):
        """Initialize workspace with validated paths.
        
        Args:
            paths: Validated WorkspacePaths instance
        """
        self.paths = paths


    @property
    def path(self) -> Path:
        """Get workspace path."""
        return self.paths.root

    @cached_property
    def workspace_config_manager(self) -> WorkspaceConfigRepository:
        return WorkspaceConfigRepository(self.paths.workspace_file)

    @cached_property
    def model_index_manager(self) -> ModelRepository:
        db_path = self.paths.cache / "models.db"
        return ModelRepository(db_path)

    @cached_property
    def model_scanner(self) -> ModelScanner:
        from ..configs.model_config import ModelConfig
        config = ModelConfig.load()
        return ModelScanner(self.model_index_manager, config)

    @cached_property
    def registry_data_manager(self) -> RegistryDataManager:
        return RegistryDataManager(self.paths.cache)

    def update_registry_data(self) -> bool:
        """Force update registry data from GitHub.

        Returns:
            True if successful, False otherwise
        """
        return self.registry_data_manager.force_update()

    def get_registry_info(self) -> dict:
        """Get information about cached registry data.

        Returns:
            Dict with cache status and metadata
        """
        return self.registry_data_manager.get_cache_info()

    def list_environments(self) -> list[Environment]:
        """List all environments in the workspace."""
        environments = []

        if not self.paths.environments.exists():
            return environments

        for env_dir in self.paths.environments.iterdir():
            if env_dir.is_dir() and (env_dir / ".cec").exists():
                try:
                    env = Environment(
                        env_dir.name,
                        env_dir,
                        self.paths,
                        self.model_index_manager,
                        self.workspace_config_manager,
                        self.registry_data_manager
                    )
                    environments.append(env)
                except Exception as e:
                    logger.warning(f"Could not load environment {env_dir.name}: {e}")

        return sorted(environments, key=lambda e: e.name)

    def get_environment(self, name: str) -> Environment:
        """Get an environment by name.
        
        Args:
            name: Environment name
            
        Returns:
            Environment instance if found
            
        Raises:
            CDEnvironmentNotFoundError: If environment not found
        """
        env_path = self.paths.environments / name

        if not env_path.exists() or not (env_path / ".cec").exists():
            raise CDEnvironmentNotFoundError(f"Environment '{name}' not found")

        return Environment(
            name,
            env_path,
            self.paths,
            self.model_index_manager,
            self.workspace_config_manager,
            self.registry_data_manager
        )

    def create_environment(
        self,
        name: str,
        python_version: str = "3.12",
        comfyui_version: str | None = None,
        template_path: Path | None = None,
    ) -> Environment:
        """Create a new environment.
        
        Args:
            name: Environment name
            python_version: Python version (e.g., "3.12")
            comfyui_version: ComfyUI version
            template_path: Optional template to copy from
            
        Returns:
            Environment
            
        Raises:
            CDEnvironmentExistsError: If environment already exists
            ComfyDockError: If environment creation fails
            RuntimeError: If environment creation fails
        """
        env_path = self.paths.environments / name

        if env_path.exists():
            raise CDEnvironmentExistsError(f"Environment '{name}' already exists")

        try:
            # Create the environment
            environment = EnvironmentFactory.create(
                name=name,
                env_path=env_path,
                workspace_paths=self.paths,
                model_index_manager=self.model_index_manager,
                workspace_config_manager=self.workspace_config_manager,
                registry_data_manager=self.registry_data_manager,
                python_version=python_version,
                comfyui_version=comfyui_version
            )

            # TODO: Apply template if provided
            if template_path and template_path.exists():
                logger.info(f"Applying template from {template_path}")
                # Copy template pyproject.toml and apply
                pass

            return environment

        except Exception as e:
            logger.error(f"Failed to create environment: {e}")
            if env_path.exists():
                logger.debug(f"Cleaning up partial environment at {env_path}")
                shutil.rmtree(env_path, ignore_errors=True)

            if isinstance(e, ComfyDockError):
                raise
            else:
                raise RuntimeError(f"Failed to create environment '{name}': {e}") from e

    def delete_environment(self, name: str):
        """Delete an environment permanently.
        
        Args:
            name: Environment name
            
        Raises:
            CDEnvironmentNotFoundError: If environment not found
            PermissionError: If deletion fails due to permissions
            OSError: If deletion fails for other reasons
        """
        env_path = self.paths.environments / name
        if not env_path.exists():
            raise CDEnvironmentNotFoundError(f"Environment '{name}' not found")

        # Check if this is the active environment
        active = self.get_active_environment()
        if active and active.name == name:
            self.set_active_environment(None)

        # Delete the directory
        try:
            shutil.rmtree(env_path)
            logger.info(f"Deleted environment '{name}'")
        except PermissionError as e:
            raise PermissionError(f"Cannot delete '{name}': insufficient permissions") from e
        except OSError as e:
            raise OSError(f"Failed to delete environment '{name}': {e}") from e

    def get_active_environment(self) -> Environment | None:
        """Get the currently active environment.
        
        Returns:
            Environment instance if found, None if no active environment
            
        Raises:
            PermissionError: If workspace metadata cannot be read
            json.JSONDecodeError: If workspace metadata is corrupted
            OSError: If workspace metadata cannot be read
        """
        try:
            with open(self.paths.workspace_file) as f:
                metadata = json.load(f)
                active_name = metadata.get("active_environment")

            if active_name:
                try:
                    return self.get_environment(active_name)
                except CDEnvironmentNotFoundError:
                    # Active environment was deleted - clear it
                    logger.warning(f"Active environment '{active_name}' no longer exists")
                    return None

        except PermissionError as e:
            raise PermissionError("Cannot read workspace metadata: insufficient permissions") from e
        except json.JSONDecodeError as e:
            raise CDWorkspaceError(f"Corrupted workspace metadata: {e}") from e
        except OSError as e:
            raise OSError(f"Failed to read workspace metadata: {e}") from e

    def set_active_environment(self, name: str | None):
        """Set the active environment.
        
        Args:
            name: Environment name or None to clear
            
        Raises:
            CDEnvironmentNotFoundError: If environment not found
            PermissionError: If setting active environment fails due to permissions
            OSError: If setting active environment fails for other reasons
        """
        # Validate environment exists if name provided
        if name is not None:
            try:
                self.get_environment(name)
            except CDEnvironmentNotFoundError:
                env_names = [e.name for e in self.list_environments()]
                raise CDEnvironmentNotFoundError(
                    f"Environment '{name}' not found. Available environments: {', '.join(env_names)}"
                )

        try:
            # Read existing metadata
            metadata = {}
            if self.paths.workspace_file.exists():
                with open(self.paths.workspace_file) as f:
                    metadata = json.load(f)

            # Update active environment
            metadata["active_environment"] = name

            # Write back
            with open(self.paths.workspace_file, 'w') as f:
                json.dump(metadata, f, indent=2)

        except PermissionError as e:
            raise PermissionError("Cannot set active environment: insufficient permissions") from e
        except OSError as e:
            raise OSError(f"Failed to set active environment: {e}") from e

    # === Model Management ===

    def list_models(self) -> list[ModelWithLocation]:
        """List models in workspace index.
        
        Args:
            model_type: Optional filter by model type
            
        Returns:
            List of ModelWithLocation objects
        """
        return self.model_index_manager.get_all_models()

    def search_models(self, query: str) -> list[ModelWithLocation]:
        """Search models by hash prefix or filename.
        
        Args:
            query: Search query (hash prefix or filename)
            
        Returns:
            List of matching ModelWithLocation objects
        """
        # Try hash search first if it looks like a hash
        if len(query) >= 6 and all(c in '0123456789abcdef' for c in query.lower()):
            hash_results = self.model_index_manager.find_model_by_hash(query.lower())
            if hash_results:
                return hash_results

        # Fall back to filename search
        return self.model_index_manager.find_by_filename(query)

    def get_model_stats(self):
        """Get model index statistics.
        
        Returns:
            Dictionary with model statistics
        """
        return self.model_index_manager.get_stats()

    # === Model Directory Management ===

    def set_models_directory(self, path: Path) -> Path:
        """Add a model directory to tracking.
        
        Args:
            path: Path to model directory
            
        Returns:
            Path to added directory
            
        Raises:
            ComfyDockError: If directory doesn't exist or is already tracked
        """
        if not path.exists() or not path.is_dir():
            raise ComfyDockError(f"Directory does not exist: {path}")

        path = path.resolve()

        self.workspace_config_manager.set_models_directory(path)

        # Do initial scan
        result = self.model_scanner.scan_directory(path)
        logger.info(f"Added directory {path}: {result.added_count} models indexed")

        # Update paths in all environments for the newly added models
        self._update_all_environment_paths()

        return path

    def get_models_directory(self) -> Path:
        """Get path to tracked model directory."""
        return self.workspace_config_manager.get_models_directory()

    def sync_model_directory(self) -> int:
        """Sync tracked model directories.
        
        Args:
            directory_id: Sync specific directory, or None for all
            
        Returns:
            Number of changes
        """
        logger.info("Syncing models directory...")
        results = 0
        path = self.workspace_config_manager.get_models_directory()
        logger.debug(f"Tracked directory: {path}")
        if path.exists():
            result = self.model_scanner.scan_directory(path)
            logger.debug(f"Found {result.added_count} new, {result.updated_count} updated models")
            results = result.added_count + result.updated_count
            self.workspace_config_manager.update_models_sync_time()
            logger.info(f"Sync complete: {results} changes")
        else:
            logger.warning(f"Tracked directory no longer exists: {path}")

        # After syncing the model index, update paths in all environments
        self._update_all_environment_paths()

        return results

    def _update_all_environment_paths(self) -> None:
        """Update model paths in all environments after model sync."""
        try:
            environments = self.list_environments()
            if not environments:
                return

            # Count environments that need updating
            total_updated = 0
            total_unchanged = 0

            for env in environments:
                try:
                    stats = env.sync_model_paths()
                    if stats:
                        if stats.get("status") == "updated":
                            total_updated += 1
                            changes = stats.get("changes", {})
                            if changes.get("added") or changes.get("removed"):
                                # Detailed changes are already logged by ModelPathManager
                                pass
                        else:
                            total_unchanged += 1
                except Exception as e:
                    logger.warning(f"Failed to update model paths for environment '{env.name}': {e}")
                    # Continue with other environments

            # Summary logging
            if total_updated > 0:
                logger.info(f"Model paths updated: {total_updated} environment(s) modified, {total_unchanged} unchanged")
            else:
                logger.debug(f"Model paths already in sync for all {len(environments)} environment(s)")

        except Exception as e:
            logger.warning(f"Failed to update environment model paths: {e}")
            # Non-fatal - model sync still succeeded
