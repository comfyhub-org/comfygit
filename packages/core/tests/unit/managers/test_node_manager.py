"""Tests for NodeManager utilities."""

from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import tempfile
import shutil

from comfygit_core.managers.node_manager import NodeManager
from comfygit_core.models.shared import NodeInfo
from comfygit_core.utils.git import is_github_url


class TestNodeManager:
    """Test NodeManager utility methods."""

    def test_is_github_url_https(self):
        """Test GitHub URL detection for HTTPS URLs."""
        assert is_github_url("https://github.com/owner/repo")
        assert is_github_url("https://github.com/owner/repo.git")

    def test_is_github_url_ssh(self):
        """Test GitHub URL detection for SSH URLs."""
        assert is_github_url("git@github.com:owner/repo.git")
        assert is_github_url("ssh://git@github.com/owner/repo")

    def test_is_github_url_non_github(self):
        """Test GitHub URL detection for non-GitHub URLs."""
        assert not is_github_url("https://gitlab.com/owner/repo")
        assert not is_github_url("registry-package-id")
        assert not is_github_url("local-path")
        assert not is_github_url("")

    def test_get_existing_node_by_registry_id_found(self):
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
            mock_pyproject, Mock(), Mock(), Mock(), Mock(), Mock()
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

    def test_get_existing_node_by_registry_id_not_found(self):
        """Test getting existing node by registry ID when not found."""
        mock_pyproject = Mock()
        mock_node_info = Mock()
        mock_node_info.registry_id = "other-package"

        mock_pyproject.nodes.get_existing.return_value = {
            "node1": mock_node_info
        }

        node_manager = NodeManager(
            mock_pyproject, Mock(), Mock(), Mock(), Mock(), Mock()
        )

        result = node_manager._get_existing_node_by_registry_id("test-package")
        assert result == {}

    def test_add_node_cleans_up_disabled_version(self, tmp_path):
        """Test that add_node removes .disabled version before adding."""
        custom_nodes_dir = tmp_path / "custom_nodes"
        custom_nodes_dir.mkdir()

        # Create a .disabled directory
        disabled_dir = custom_nodes_dir / "test-node.disabled"
        disabled_dir.mkdir()
        (disabled_dir / "old_file.py").write_text("old content")

        # Create a cache directory for the node
        cache_dir = tmp_path / "cache" / "test-node"
        cache_dir.mkdir(parents=True)
        (cache_dir / "node.py").write_text("node content")

        mock_pyproject = Mock()
        mock_node_lookup = Mock()

        # Mock node info
        mock_node_info = NodeInfo(
            name="test-node",
            registry_id="test-node",
            source="registry"
        )

        mock_node_lookup.get_node.return_value = mock_node_info
        mock_node_lookup.download_to_cache.return_value = cache_dir
        mock_node_lookup.scan_requirements.return_value = []

        # Mock get_existing to return empty dict (no existing nodes)
        mock_pyproject.nodes.get_existing.return_value = {}

        node_manager = NodeManager(
            mock_pyproject, Mock(), mock_node_lookup, Mock(), custom_nodes_dir, Mock()
        )

        # Mock add_node_package to avoid full flow
        node_manager.add_node_package = Mock()

        # Call add_node
        node_manager.add_node("test-node", no_test=True)

        # Verify .disabled was removed
        assert not disabled_dir.exists()
        assert not (custom_nodes_dir / "test-node.disabled").exists()