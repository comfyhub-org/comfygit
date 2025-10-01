"""Tests for node sync delete/disable strategy."""

from pathlib import Path
from unittest.mock import Mock, patch

from comfydock_core.models.shared import NodeInfo
from comfydock_core.services.node_registry import NodeRegistry


class TestNodeSync:
    """Test node sync delete/disable strategy."""

    def test_sync_deletes_registry_nodes(self, tmp_path):
        """Test that registry nodes are deleted (not disabled) during sync."""
        custom_nodes_dir = tmp_path / "custom_nodes"
        custom_nodes_dir.mkdir()
        cec_dir = tmp_path / ".cec"
        cec_dir.mkdir()

        # Create a registry node that should be removed
        registry_node = custom_nodes_dir / "registry-node"
        registry_node.mkdir()
        (registry_node / "test.py").write_text("test")

        # Expected nodes (empty - this node should be removed)
        expected_nodes = {}

        # Create NodeRegistry instance
        node_registry = NodeRegistry()

        # Mock _check_if_dev_node_from_history to return False (registry node)
        with patch.object(node_registry, '_check_if_dev_node_from_history', return_value=False):
            # Sync nodes
            node_registry.sync_nodes_to_filesystem(expected_nodes, custom_nodes_dir)

        # Verify registry node was deleted (not disabled)
        assert not registry_node.exists()
        assert not (custom_nodes_dir / "registry-node.disabled").exists()

    def test_sync_disables_dev_nodes(self, tmp_path):
        """Test that dev nodes are disabled (not deleted) during sync."""
        custom_nodes_dir = tmp_path / "custom_nodes"
        custom_nodes_dir.mkdir()
        cec_dir = tmp_path / ".cec"
        cec_dir.mkdir()

        # Create a dev node that should be removed
        dev_node = custom_nodes_dir / "my-dev-node"
        dev_node.mkdir()
        (dev_node / "important.py").write_text("my custom code")

        # Expected nodes (empty - this node should be disabled)
        expected_nodes = {}

        # Create NodeRegistry instance
        node_registry = NodeRegistry()

        # Mock _check_if_dev_node_from_history to return True (dev node)
        with patch.object(node_registry, '_check_if_dev_node_from_history', return_value=True):
            # Sync nodes
            node_registry.sync_nodes_to_filesystem(expected_nodes, custom_nodes_dir)

        # Verify dev node was disabled (not deleted)
        assert not dev_node.exists()
        disabled_node = custom_nodes_dir / "my-dev-node.disabled"
        assert disabled_node.exists()
        assert (disabled_node / "important.py").read_text() == "my custom code"

    def test_sync_installs_missing_registry_nodes(self, tmp_path):
        """Test that missing registry nodes are installed during sync."""
        custom_nodes_dir = tmp_path / "custom_nodes"
        custom_nodes_dir.mkdir()

        # Expected node (not currently present)
        node_info = NodeInfo(
            name="new-node",
            registry_id="new-node",
            version="1.0.0",
            source="registry"
        )
        expected_nodes = {"new-node": node_info}

        # Create NodeRegistry instance
        node_registry = NodeRegistry()

        # Mock download_node
        download_called = []
        def mock_download(info, path):
            download_called.append((info.name, path))
            path.mkdir(parents=True, exist_ok=True)
            (path / "installed.txt").write_text("installed")

        with patch.object(node_registry, 'download_node', side_effect=mock_download):
            # Sync nodes
            node_registry.sync_nodes_to_filesystem(expected_nodes, custom_nodes_dir)

        # Verify download was called
        assert len(download_called) == 1
        assert download_called[0][0] == "new-node"

        # Verify node was installed
        assert (custom_nodes_dir / "new-node").exists()
        assert (custom_nodes_dir / "new-node" / "installed.txt").read_text() == "installed"

    def test_sync_skips_dev_nodes_already_present(self, tmp_path):
        """Test that dev nodes already on disk are not downloaded."""
        custom_nodes_dir = tmp_path / "custom_nodes"
        custom_nodes_dir.mkdir()

        # Create existing dev node
        dev_node = custom_nodes_dir / "my-dev-node"
        dev_node.mkdir()
        (dev_node / "code.py").write_text("existing code")

        # Expected dev node (already present)
        node_info = NodeInfo(
            name="my-dev-node",
            version="dev",
            source="development"
        )
        expected_nodes = {"my-dev-node": node_info}

        # Create NodeRegistry instance
        node_registry = NodeRegistry()

        # Mock download_node (should not be called)
        download_called = []
        def mock_download(info, path):
            download_called.append(info.name)

        with patch.object(node_registry, 'download_node', side_effect=mock_download):
            # Sync nodes
            node_registry.sync_nodes_to_filesystem(expected_nodes, custom_nodes_dir)

        # Verify download was NOT called
        assert len(download_called) == 0

        # Verify dev node still exists unchanged
        assert dev_node.exists()
        assert (dev_node / "code.py").read_text() == "existing code"
