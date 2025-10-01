# models/exceptions.py

from dataclasses import dataclass, field
from typing import Literal


class ComfyDockError(Exception):
    """Base exception for ComfyDock errors."""
    pass

# ====================================================
# Workspace exceptions
# ====================================================

class CDWorkspaceNotFoundError(ComfyDockError):
    """Workspace doesn't exist."""
    pass

class CDWorkspaceExistsError(ComfyDockError):
    """Workspace already exists."""
    pass

class CDWorkspaceError(ComfyDockError):
    """Workspace-related errors."""
    pass

# ===================================================
# Environment exceptions
# ===================================================

class CDEnvironmentError(ComfyDockError):
    """Environment-related errors."""
    pass

class CDEnvironmentNotFoundError(ComfyDockError):
    """Environment doesn't exist."""
    pass

class CDEnvironmentExistsError(ComfyDockError):
    """Environment already exists."""
    pass

# ===================================================
# Resolution exceptions
# ==================================================

class CDResolutionError(ComfyDockError):
    """Resolution errors."""
    pass

# ===================================================
# Node exceptions
# ===================================================

class CDNodeNotFoundError(ComfyDockError):
    """Raised when Node not found."""
    pass

@dataclass
class NodeAction:
    """Represents a possible action to resolve an error."""
    action_type: Literal[
        'remove_node',
        'add_node_dev',
        'add_node_force',
        'rename_directory',
        'update_node'
    ]

    # Parameters needed for the action
    node_identifier: str | None = None
    node_name: str | None = None
    directory_name: str | None = None
    new_name: str | None = None

    # Human-readable description (client-agnostic)
    description: str = ""


@dataclass
class NodeConflictContext:
    """Context about what conflicted and why."""
    conflict_type: Literal[
        'already_tracked',
        'directory_exists_non_git',
        'directory_exists_no_remote',
        'same_repo_exists',
        'different_repo_exists'
    ]

    node_name: str
    identifier: str | None = None
    existing_identifier: str | None = None
    filesystem_path: str | None = None
    local_remote_url: str | None = None
    expected_remote_url: str | None = None
    is_development: bool = False

    # Suggested actions
    suggested_actions: list[NodeAction] = field(default_factory=list)


class CDNodeConflictError(ComfyDockError):
    """Raised when Node has conflicts with enhanced context."""

    def __init__(self, message: str, context: NodeConflictContext | None = None):
        super().__init__(message)
        self.context = context

    def get_actions(self) -> list[NodeAction]:
        """Get suggested actions for resolving this conflict."""
        return self.context.suggested_actions if self.context else []

# ===================================================
# Registry exceptions
# ===================================================

class CDRegistryError(ComfyDockError):
    """Base class for registry errors."""
    pass

class CDRegistryAuthError(CDRegistryError):
    """Authentication/authorization errors with registry."""
    pass

class CDRegistryServerError(CDRegistryError):
    """Registry server errors (5xx)."""
    pass

class CDRegistryConnectionError(CDRegistryError):
    """Network/connection errors to registry."""
    pass

# ===================================================
# Pyproject exceptions
# ===================================================

class CDPyprojectError(ComfyDockError):
    """Errors related to pyproject.toml operations."""
    pass

class CDPyprojectNotFoundError(CDPyprojectError):
    """pyproject.toml file not found."""
    pass

class CDPyprojectInvalidError(CDPyprojectError):
    """pyproject.toml file is invalid or corrupted."""
    pass

# ===================================================
# Dependency exceptions
# ===================================================

class CDDependencyError(ComfyDockError):
    """Dependency-related errors."""
    pass

class CDPackageSyncError(CDDependencyError):
    """Package synchronization errors."""
    pass

# ===================================================
# Index exceptions
# ===================================================

class CDIndexError(ComfyDockError):
    """Index configuration errors."""
    pass

# ===================================================
# Process/Command exceptions
# ===================================================

class CDProcessError(ComfyDockError):
    """Raised when subprocess command execution fails."""

    def __init__(
        self,
        message: str,
        command: list[str] | None = None,
        stderr: str | None = None,
        stdout: str | None = None,
        returncode: int | None = None,
    ):
        super().__init__(message)
        self.command = command
        self.stderr = stderr
        self.stdout = stdout
        self.returncode = returncode


# ===================================================
# UV exceptions
# ==================================================

class UVNotInstalledError(ComfyDockError):
    """Raised when UV is not installed."""
    pass


class UVCommandError(ComfyDockError):
    """Raised when UV command execution fails."""

    def __init__(
        self,
        message: str,
        command: list[str] | None = None,
        stderr: str | None = None,
        stdout: str | None = None,
        returncode: int | None = None,
    ):
        super().__init__(message)
        self.command = command
        self.stderr = stderr
        self.stdout = stdout
        self.returncode = returncode
