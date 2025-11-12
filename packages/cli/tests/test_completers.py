"""Tests for argcomplete completers."""
from argparse import Namespace
from unittest.mock import Mock, patch

import pytest

from comfygit_cli.completers import (
    environment_completer,
    filter_by_prefix,
    get_env_from_args,
    get_workspace_safe,
    installed_node_completer,
    workflow_completer,
)
from comfygit_core.models.exceptions import CDWorkspaceNotFoundError
from comfygit_core.models.workflow import WorkflowSyncStatus


class TestSharedUtilities:
    """Test shared utility functions."""

    def test_filter_by_prefix(self):
        """Test filtering items by prefix."""
        items = ["apple", "application", "banana", "apply"]
        result = filter_by_prefix(items, "app")
        assert result == ["apple", "application", "apply"]

    def test_filter_by_prefix_empty(self):
        """Test filtering with empty prefix returns all items."""
        items = ["apple", "banana", "cherry"]
        result = filter_by_prefix(items, "")
        assert result == items

    def test_filter_by_prefix_no_matches(self):
        """Test filtering with no matches."""
        items = ["apple", "banana", "cherry"]
        result = filter_by_prefix(items, "xyz")
        assert result == []

    @patch('comfygit_cli.completers.WorkspaceFactory.find')
    def test_get_workspace_safe_success(self, mock_find):
        """Test getting workspace successfully."""
        mock_workspace = Mock()
        mock_find.return_value = mock_workspace

        result = get_workspace_safe()
        assert result == mock_workspace

    @patch('comfygit_cli.completers.WorkspaceFactory.find')
    def test_get_workspace_safe_not_found(self, mock_find):
        """Test get_workspace_safe returns None when not found."""
        mock_find.side_effect = CDWorkspaceNotFoundError("Not found")

        result = get_workspace_safe()
        assert result is None

    def test_get_env_from_args_with_target_env(self):
        """Test getting environment from -e flag."""
        mock_workspace = Mock()
        mock_env = Mock()
        mock_workspace.get_environment.return_value = mock_env

        parsed_args = Namespace(target_env="test-env")
        result = get_env_from_args(parsed_args, mock_workspace)

        assert result == mock_env
        mock_workspace.get_environment.assert_called_once_with("test-env", auto_sync=False)

    def test_get_env_from_args_active_env(self):
        """Test getting active environment when no -e flag."""
        mock_workspace = Mock()
        mock_env = Mock()
        mock_workspace.get_active_environment.return_value = mock_env

        parsed_args = Namespace()
        result = get_env_from_args(parsed_args, mock_workspace)

        assert result == mock_env
        mock_workspace.get_active_environment.assert_called_once()


class TestEnvironmentCompleter:
    """Test environment_completer function."""

    @patch('comfygit_cli.completers.get_workspace_safe')
    def test_complete_environment_names(self, mock_get_workspace):
        """Test completing environment names."""
        # Setup mock environments
        mock_env1 = Mock()
        mock_env1.name = "stable"
        mock_env2 = Mock()
        mock_env2.name = "testing"
        mock_env3 = Mock()
        mock_env3.name = "experimental"

        mock_workspace = Mock()
        mock_workspace.list_environments.return_value = [mock_env1, mock_env2, mock_env3]
        mock_get_workspace.return_value = mock_workspace

        # Test completion
        result = environment_completer("test", Mock())
        assert result == ["testing"]

    @patch('comfygit_cli.completers.get_workspace_safe')
    def test_complete_all_environments(self, mock_get_workspace):
        """Test completing with empty prefix returns all environments."""
        mock_env1 = Mock()
        mock_env1.name = "stable"
        mock_env2 = Mock()
        mock_env2.name = "testing"

        mock_workspace = Mock()
        mock_workspace.list_environments.return_value = [mock_env1, mock_env2]
        mock_get_workspace.return_value = mock_workspace

        result = environment_completer("", Mock())
        assert result == ["stable", "testing"]

    @patch('comfygit_cli.completers.get_workspace_safe')
    def test_no_workspace_returns_empty(self, mock_get_workspace):
        """Test returns empty list when no workspace."""
        mock_get_workspace.return_value = None

        result = environment_completer("", Mock())
        assert result == []


class TestWorkflowCompleter:
    """Test workflow_completer function."""

    @patch('comfygit_cli.completers.get_env_from_args')
    @patch('comfygit_cli.completers.get_workspace_safe')
    def test_complete_workflow_names(self, mock_get_workspace, mock_get_env):
        """Test completing workflow names."""
        # Setup mocks
        mock_workspace = Mock()
        mock_get_workspace.return_value = mock_workspace

        mock_env = Mock()
        workflows = WorkflowSyncStatus(
            new=["workflow1.json"],
            modified=["workflow2.json"],
            synced=["workflow3.json"],
            deleted=[]
        )
        mock_env.list_workflows.return_value = workflows
        mock_get_env.return_value = mock_env

        # Test completion
        result = workflow_completer("work", Mock())
        assert result == ["workflow1", "workflow2", "workflow3"]

    @patch('comfygit_cli.completers.get_env_from_args')
    @patch('comfygit_cli.completers.get_workspace_safe')
    def test_workflow_priority_ordering(self, mock_get_workspace, mock_get_env):
        """Test workflows are ordered with new/modified first."""
        mock_workspace = Mock()
        mock_get_workspace.return_value = mock_workspace

        mock_env = Mock()
        workflows = WorkflowSyncStatus(
            new=["new-workflow.json"],
            modified=["modified-workflow.json"],
            synced=["synced-workflow.json"],
            deleted=[]
        )
        mock_env.list_workflows.return_value = workflows
        mock_get_env.return_value = mock_env

        result = workflow_completer("", Mock())
        # Check order: new first, then modified, then synced
        assert result == ["new-workflow", "modified-workflow", "synced-workflow"]

    @patch('comfygit_cli.completers.get_env_from_args')
    @patch('comfygit_cli.completers.get_workspace_safe')
    def test_no_environment_returns_empty(self, mock_get_workspace, mock_get_env):
        """Test returns empty list when no environment."""
        mock_workspace = Mock()
        mock_get_workspace.return_value = mock_workspace
        mock_get_env.return_value = None

        result = workflow_completer("", Mock())
        assert result == []


class TestInstalledNodeCompleter:
    """Test installed_node_completer function."""

    @patch('comfygit_cli.completers.get_env_from_args')
    @patch('comfygit_cli.completers.get_workspace_safe')
    def test_complete_installed_nodes(self, mock_get_workspace, mock_get_env):
        """Test completing installed node names."""
        mock_workspace = Mock()
        mock_get_workspace.return_value = mock_workspace

        mock_env = Mock()
        # Create mock nodes with registry_id
        node1 = Mock()
        node1.registry_id = "comfyui-manager"
        node1.name = "ComfyUI-Manager"

        node2 = Mock()
        node2.registry_id = "animatediff"
        node2.name = "AnimateDiff"

        node3 = Mock()
        node3.registry_id = None
        node3.name = "custom-node"

        mock_env.list_nodes.return_value = [node1, node2, node3]
        mock_get_env.return_value = mock_env

        result = installed_node_completer("", Mock())
        assert result == ["comfyui-manager", "animatediff", "custom-node"]

    @patch('comfygit_cli.completers.get_env_from_args')
    @patch('comfygit_cli.completers.get_workspace_safe')
    def test_complete_with_prefix(self, mock_get_workspace, mock_get_env):
        """Test completing nodes with prefix filter."""
        mock_workspace = Mock()
        mock_get_workspace.return_value = mock_workspace

        mock_env = Mock()
        node1 = Mock()
        node1.registry_id = "comfyui-manager"
        node1.name = "ComfyUI-Manager"

        node2 = Mock()
        node2.registry_id = "comfyui-inspire-pack"
        node2.name = "ComfyUI-Inspire-Pack"

        node3 = Mock()
        node3.registry_id = "animatediff"
        node3.name = "AnimateDiff"

        mock_env.list_nodes.return_value = [node1, node2, node3]
        mock_get_env.return_value = mock_env

        result = installed_node_completer("comfyui", Mock())
        assert result == ["comfyui-manager", "comfyui-inspire-pack"]

    @patch('comfygit_cli.completers.get_env_from_args')
    @patch('comfygit_cli.completers.get_workspace_safe')
    def test_no_environment_returns_empty(self, mock_get_workspace, mock_get_env):
        """Test returns empty list when no environment."""
        mock_workspace = Mock()
        mock_get_workspace.return_value = mock_workspace
        mock_get_env.return_value = None

        result = installed_node_completer("", Mock())
        assert result == []
