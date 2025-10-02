"""Factory for creating and discovering workspaces."""

import json
import os
from pathlib import Path

from ..core.workspace import Workspace, WorkspacePaths
from ..logging.logging_config import get_logger
from ..models.exceptions import (
    CDWorkspaceError,
    CDWorkspaceExistsError,
    CDWorkspaceNotFoundError,
)

logger = get_logger(__name__)


class WorkspaceFactory:
    """Factory for creating and discovering ComfyDock workspaces."""

    @staticmethod
    def get_paths(path: Path | None = None) -> WorkspacePaths:
        # Determine workspace path
        if path:
            workspace_path = path
        elif comfydock_home := os.environ.get("COMFYDOCK_HOME"):
            workspace_path = Path(comfydock_home)
        else:
            workspace_path = Path.home() / "comfydock"
        return WorkspacePaths(workspace_path)

    @staticmethod
    def find(path: Path | None = None) -> Workspace:
        """Find an existing workspace.
        
        Args:
            path: Workspace path (defaults to ~/comfydock or COMFYDOCK_HOME)
            
        Returns:
            Workspace instance
            
        Raises:
            CDWorkspaceNotFoundError: If workspace not found
        """
        # Determine workspace path
        workspace_paths = WorkspaceFactory.get_paths(path)
        if not workspace_paths.exists():
            raise CDWorkspaceNotFoundError(f"No workspace found at {workspace_paths.root}")

        return Workspace(workspace_paths)

    @staticmethod
    def create(path: Path | None = None) -> Workspace:
        """Create a new ComfyDock workspace.
        
        Args:
            path: Workspace directory (defaults to ~/comfydock)
            
        Returns:
            Initialized Workspace
            
        Raises:
            CDWorkspaceExistsError: If workspace already exists
            CDWorkspaceError: If directory exists and is not empty
            PermissionError: If cannot create directories
            OSError: If filesystem operations fail
        """
        # Check if already exists
        workspace_paths = WorkspaceFactory.get_paths(path)
        if workspace_paths.exists():
            logger.info(f"Workspace already exists at {workspace_paths.root}")
            raise CDWorkspaceExistsError(f"Workspace already exists at {workspace_paths.root}")

        # Check if path exists but is not empty
        if workspace_paths.root.exists() and any(workspace_paths.root.iterdir()):
            raise CDWorkspaceError(f"Directory exists and is not empty: {workspace_paths.root}")

        try:
            # Create workspace structure
            workspace_paths.ensure_directories()

            # Initialize metadata with current schema
            from datetime import datetime
            metadata = {
                "version": 1,
                "active_environment": "",
                "created_at": datetime.now().isoformat(),
                "global_model_directory": None
            }

            with open(workspace_paths.workspace_file, 'w') as f:
                json.dump(metadata, f, indent=2)


            logger.info(f"Created workspace at {workspace_paths.root}")

            return Workspace(workspace_paths)

        except PermissionError as e:
            raise PermissionError(f"Cannot create workspace at {workspace_paths.root}: insufficient permissions") from e
        except OSError as e:
            # Clean up partial workspace if creation failed
            if workspace_paths.exists() and not any(workspace_paths.root.iterdir()):
                workspace_paths.root.rmdir()
            raise OSError(f"Failed to create workspace at {workspace_paths.root}: {e}") from e
