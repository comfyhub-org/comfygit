from datetime import datetime
from pathlib import Path
import json

from ..configs.workspace_config import WorkspaceConfig, ModelDirectory
from comfydock_core.models.exceptions import ComfyDockError
from ..logging.logging_config import get_logger

logger = get_logger(__name__)


class WorkspaceConfigRepository:

    def __init__(self, config_file: Path):
        self.config_file_path = config_file

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
        data = self.load()
        if data is None:
            raise ComfyDockError("No workspace config found")
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
        data = self.load()
        if data is None:
            raise ComfyDockError("No workspace config found")
        if data.global_model_directory is None:
            raise ComfyDockError("No models directory set")
        return Path(data.global_model_directory.path)
    
    def update_models_sync_time(self):
        data = self.load()
        if data is None:
            raise ComfyDockError("No workspace config found")
        if data.global_model_directory is None:
            raise ComfyDockError("No models directory set")
        data.global_model_directory.last_sync = str(datetime.now().isoformat())
        self.save(data)
