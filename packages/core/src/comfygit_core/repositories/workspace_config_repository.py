from datetime import datetime
from functools import cached_property
from pathlib import Path
import json
import os

from ..models.workspace_config import WorkspaceConfig, ModelDirectory, APICredentials
from comfygit_core.models.exceptions import ComfyDockError
from ..logging.logging_config import get_logger

logger = get_logger(__name__)


class WorkspaceConfigRepository:

    def __init__(self, config_file: Path):
        self.config_file_path = config_file
        
    @cached_property
    def config_file(self) -> WorkspaceConfig:
        data = self.load()
        if data is None:
            raise ComfyDockError("No workspace config found")
        return data

    def load(self) -> WorkspaceConfig:
        result = None
        try:
            with self.config_file_path.open("r") as f:
                result = WorkspaceConfig.from_dict(json.load(f))
        except Exception as e:
            logger.warning(f"Failed to load workspace config: {e}")
            
        logger.debug(f"Loaded workspace config: {result}")
            
        if result is None:
            logger.info("No workspace config found, creating a new one")
            result = WorkspaceConfig(
                version=1,
                active_environment="",
                created_at=str(datetime.now().isoformat()),
                global_model_directory=None
            )
            self.save(result)
        return result

    def save(self, data: WorkspaceConfig):
        # First serialize to JSON
        with self.config_file_path.open("w") as f:
            data_dict = WorkspaceConfig.to_dict(data)
            json.dump(data_dict, f, indent=2)

    def set_models_directory(self, path: Path):
        logger.info(f"Setting models directory to {path}")
        data = self.config_file
        logger.debug(f"Loaded data: {data}")
        model_dir = ModelDirectory(
            path=str(path),
            added_at=str(datetime.now().isoformat()),
            last_sync=str(datetime.now().isoformat()),
        )
        data.global_model_directory = model_dir
        logger.debug(f"Updated data: {data}, saving...")
        self.save(data)
        logger.info(f"Models directory set to {path}")
        
    def get_models_directory(self) -> Path:
        """Get path to tracked model directory."""
        data = self.config_file
        if data.global_model_directory is None:
            raise ComfyDockError("No models directory set")
        return Path(data.global_model_directory.path)
    
    def update_models_sync_time(self):
        data = self.config_file
        if data.global_model_directory is None:
            raise ComfyDockError("No models directory set")
        data.global_model_directory.last_sync = str(datetime.now().isoformat())
        self.save(data)

    def set_civitai_token(self, token: str | None):
        """Set or clear CivitAI API token."""
        data = self.config_file
        if token:
            if not data.api_credentials:
                data.api_credentials = APICredentials(civitai_token=token)
            else:
                data.api_credentials.civitai_token = token
            logger.info("CivitAI API token configured")
        else:
            if data.api_credentials:
                data.api_credentials.civitai_token = None
            logger.info("CivitAI API token cleared")
        self.save(data)

    def get_civitai_token(self) -> str | None:
        """Get CivitAI API token from config or environment."""
        # Priority: environment variable > config file
        env_token = os.environ.get("CIVITAI_API_TOKEN")
        if env_token:
            logger.debug("Using CivitAI token from environment")
            return env_token

        data = self.config_file
        if data.api_credentials and data.api_credentials.civitai_token:
            logger.debug("Using CivitAI token from config")
            return data.api_credentials.civitai_token

        return None

    def get_prefer_registry_cache(self) -> bool:
        """Get prefer_registry_cache setting (defaults to True)."""
        data = self.config_file
        return data.prefer_registry_cache

    def set_prefer_registry_cache(self, enabled: bool):
        """Set prefer_registry_cache setting."""
        data = self.config_file
        data.prefer_registry_cache = enabled
        self.save(data)
        logger.info(f"Registry cache preference set to: {enabled}")
