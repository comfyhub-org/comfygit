"""Custom argcomplete completers for ComfyDock CLI."""
import argparse
from typing import Any

from argcomplete.io import warn

from comfygit_core.core.environment import Environment
from comfygit_core.core.workspace import Workspace
from comfygit_core.factories.workspace_factory import WorkspaceFactory
from comfygit_core.models.exceptions import CDWorkspaceNotFoundError


# ============================================================================
# Shared Utilities
# ============================================================================

def get_workspace_safe() -> Workspace | None:
    """Get workspace or return None if not initialized."""
    try:
        return WorkspaceFactory.find()
    except CDWorkspaceNotFoundError:
        return None
    except Exception as e:
        warn(f"Error loading workspace: {e}")
        return None


def get_env_from_args(parsed_args: argparse.Namespace, workspace: Workspace) -> Environment | None:
    """Get environment from -e flag or active environment.

    Args:
        parsed_args: Parsed arguments from argparse
        workspace: Workspace instance

    Returns:
        Environment instance or None
    """
    try:
        # Check for -e/--env flag
        env_name = getattr(parsed_args, 'target_env', None)
        if env_name:
            return workspace.get_environment(env_name, auto_sync=False)

        # Fall back to active environment
        env = workspace.get_active_environment()
        if not env:
            warn("No active environment. Use -e or run 'cg use <env>'")
        return env
    except Exception as e:
        warn(f"Error loading environment: {e}")
        return None


def filter_by_prefix(items: list[str], prefix: str) -> list[str]:
    """Filter items that start with the given prefix."""
    return [item for item in items if item.startswith(prefix)]


# ============================================================================
# Completers
# ============================================================================

def environment_completer(prefix: str, parsed_args: argparse.Namespace, **kwargs: Any) -> list[str]:
    """Complete environment names from workspace.

    Used for:
    - comfygit use <TAB>
    - comfygit delete <TAB>
    - comfygit -e <TAB>
    """
    workspace = get_workspace_safe()
    if not workspace:
        return []

    try:
        envs = workspace.list_environments()
        names = [env.name for env in envs]
        return filter_by_prefix(names, prefix)
    except Exception as e:
        warn(f"Error listing environments: {e}")
        return []


def workflow_completer(prefix: str, parsed_args: argparse.Namespace, **kwargs: Any) -> list[str]:
    """Complete workflow names, prioritizing unresolved workflows.

    Smart ordering:
    1. New/modified workflows (likely need resolution)
    2. Synced workflows

    Used for:
    - comfygit workflow resolve <TAB>
    """
    workspace = get_workspace_safe()
    if not workspace:
        return []

    env = get_env_from_args(parsed_args, workspace)
    if not env:
        return []

    try:
        workflows = env.list_workflows()

        # Build candidates with smart ordering
        candidates = []

        # Priority 1: Unresolved workflows (new/modified)
        candidates.extend(workflows.new)
        candidates.extend(workflows.modified)

        # Priority 2: Synced workflows
        candidates.extend(workflows.synced)

        # Remove .json extension and filter by prefix
        names = [name.replace('.json', '') for name in candidates]
        return filter_by_prefix(names, prefix)

    except Exception as e:
        warn(f"Error listing workflows: {e}")
        return []


def installed_node_completer(prefix: str, parsed_args: argparse.Namespace, **kwargs: Any) -> list[str]:
    """Complete installed node names.

    Used for:
    - comfygit node remove <TAB>
    - comfygit node update <TAB>
    """
    workspace = get_workspace_safe()
    if not workspace:
        return []

    env = get_env_from_args(parsed_args, workspace)
    if not env:
        return []

    try:
        nodes = env.list_nodes()
        # Use registry_id if available, otherwise fall back to name
        names = [node.registry_id or node.name for node in nodes]
        return filter_by_prefix(names, prefix)
    except Exception as e:
        warn(f"Error listing nodes: {e}")
        return []
