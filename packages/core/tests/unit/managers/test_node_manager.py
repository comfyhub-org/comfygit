"""Tests for NodeManager utilities."""

from pathlib import Path
from unittest.mock import Mock, patch

from comfydock_core.managers.node_manager import NodeManager


class TestNodeManager:
    """Test NodeManager utility methods."""

    @patch('comfydock_core.managers.node_manager.GlobalNodeResolver')
    def test_is_github_url_https(self, mock_resolver):
        """Test GitHub URL detection for HTTPS URLs."""
        node_manager = NodeManager(
            Mock(), Mock(), Mock(), Mock(), Mock()
        )

        assert node_manager._is_github_url("https://github.com/owner/repo")
        assert node_manager._is_github_url("https://github.com/owner/repo.git")

    @patch('comfydock_core.managers.node_manager.GlobalNodeResolver')
    def test_is_github_url_ssh(self, mock_resolver):
        """Test GitHub URL detection for SSH URLs."""
        node_manager = NodeManager(
            Mock(), Mock(), Mock(), Mock(), Mock()
        )

        assert node_manager._is_github_url("git@github.com:owner/repo.git")
        assert node_manager._is_github_url("ssh://git@github.com/owner/repo")

    @patch('comfydock_core.managers.node_manager.GlobalNodeResolver')
    def test_is_github_url_non_github(self, mock_resolver):
        """Test GitHub URL detection for non-GitHub URLs."""
        node_manager = NodeManager(
            Mock(), Mock(), Mock(), Mock(), Mock()
        )

        assert not node_manager._is_github_url("https://gitlab.com/owner/repo")
        assert not node_manager._is_github_url("registry-package-id")
        assert not node_manager._is_github_url("local-path")
        assert not node_manager._is_github_url("")

    @patch('comfydock_core.managers.node_manager.GlobalNodeResolver')
    def test_is_node_installed_by_registry_id_found(self, mock_resolver):
        """Test checking if node is installed by registry ID when found."""
        mock_pyproject = Mock()
        mock_node_info = Mock()
        mock_node_info.registry_id = "test-package"

        mock_pyproject.nodes.get_existing.return_value = {
            "node1": mock_node_info
        }

        node_manager = NodeManager(
            mock_pyproject, Mock(), Mock(), Mock(), Mock()
        )

        assert node_manager._is_node_installed_by_registry_id("test-package")

    @patch('comfydock_core.managers.node_manager.GlobalNodeResolver')
    def test_is_node_installed_by_registry_id_not_found(self, mock_resolver):
        """Test checking if node is installed by registry ID when not found."""
        mock_pyproject = Mock()
        mock_node_info = Mock()
        mock_node_info.registry_id = "other-package"

        mock_pyproject.nodes.get_existing.return_value = {
            "node1": mock_node_info
        }

        node_manager = NodeManager(
            mock_pyproject, Mock(), Mock(), Mock(), Mock()
        )

        assert not node_manager._is_node_installed_by_registry_id("test-package")

    @patch('comfydock_core.managers.node_manager.GlobalNodeResolver')
    def test_is_node_installed_by_registry_id_no_registry_id(self, mock_resolver):
        """Test checking if node is installed when node has no registry_id."""
        mock_pyproject = Mock()
        mock_node_info = Mock()
        # Mock node without registry_id attribute
        del mock_node_info.registry_id

        mock_pyproject.nodes.get_existing.return_value = {
            "node1": mock_node_info
        }

        node_manager = NodeManager(
            mock_pyproject, Mock(), Mock(), Mock(), Mock()
        )

        assert not node_manager._is_node_installed_by_registry_id("test-package")

    @patch('comfydock_core.managers.node_manager.GlobalNodeResolver')
    def test_get_existing_node_by_registry_id_found(self, mock_resolver):
        """Test getting existing node by registry ID when found."""
        mock_pyproject = Mock()
        mock_node_info = Mock()
        mock_node_info.registry_id = "test-package"
        mock_node_info.name = "Test Node"
        mock_node_info.version = "1.0.0"
        mock_node_info.repository = "https://github.com/owner/repo"
        mock_node_info.source = "git"

        mock_pyproject.nodes.get_existing.return_value = {
            "node1": mock_node_info
        }

        node_manager = NodeManager(
            mock_pyproject, Mock(), Mock(), Mock(), Mock()
        )

        result = node_manager._get_existing_node_by_registry_id("test-package")
        expected = {
            'name': "Test Node",
            'registry_id': "test-package",
            'version': "1.0.0",
            'repository': "https://github.com/owner/repo",
            'source': "git"
        }

        assert result == expected

    @patch('comfydock_core.managers.node_manager.GlobalNodeResolver')
    def test_get_existing_node_by_registry_id_not_found(self, mock_resolver):
        """Test getting existing node by registry ID when not found."""
        mock_pyproject = Mock()
        mock_node_info = Mock()
        mock_node_info.registry_id = "other-package"

        mock_pyproject.nodes.get_existing.return_value = {
            "node1": mock_node_info
        }

        node_manager = NodeManager(
            mock_pyproject, Mock(), Mock(), Mock(), Mock()
        )

        result = node_manager._get_existing_node_by_registry_id("test-package")
        assert result == {}

    @patch('comfydock_core.managers.node_manager.GlobalNodeResolver')
    def test_add_node_cleans_up_disabled_version(self, mock_resolver, tmp_path):
        """Test that add_node removes .disabled version before adding."""
        custom_nodes_dir = tmp_path / "custom_nodes"
        custom_nodes_dir.mkdir()

        # Create a .disabled directory
        disabled_dir = custom_nodes_dir / "test-node.disabled"
        disabled_dir.mkdir()
        (disabled_dir / "old_file.py").write_text("old content")

        mock_pyproject = Mock()
        mock_node_registry = Mock()

        # Mock the node package
        mock_node_info = Mock()
        mock_node_info.name = "test-node"
        mock_node_info.registry_id = "test-node"
        mock_node_info.source = "registry"

        mock_node_package = Mock()
        mock_node_package.name = "test-node"
        mock_node_package.node_info = mock_node_info
        mock_node_package.identifier = "test-node"
        mock_node_package.requirements = []

        mock_node_registry.prepare_node.return_value = mock_node_package

        node_manager = NodeManager(
            mock_pyproject, Mock(), mock_node_registry, Mock(), custom_nodes_dir, Mock()
        )

        # Mock add_node_package to avoid full flow
        node_manager.add_node_package = Mock()

        # Call add_node
        node_manager.add_node("test-node", no_test=True)

        # Verify .disabled was removed
        assert not disabled_dir.exists()
        assert not (custom_nodes_dir / "test-node.disabled").exists()