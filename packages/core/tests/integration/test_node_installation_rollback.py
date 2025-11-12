"""Integration tests for transactional node installation with rollback.

Tests that node installation is atomic - if any step fails, the environment
is rolled back to its previous state with no contamination.
"""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from comfygit_core.models.shared import NodeInfo
from comfygit_core.models.exceptions import UVCommandError, CDNodeConflictError


class TestNodeInstallationRollback:
    """Test that node installation is atomic with proper rollback on failure."""

    def test_sync_failure_rolls_back_pyproject_and_filesystem(self, test_env):
        """Test that UV sync failure triggers complete rollback.

        CURRENT BUG:
        1. Node files are copied to custom_nodes/
        2. Dependencies added to pyproject.toml
        3. UV sync fails (e.g., pycairo build error)
        4. Exception raised BUT pyproject.toml and filesystem NOT rolled back
        5. Environment contaminated

        EXPECTED BEHAVIOR (after fix):
        1. Node files copied
        2. Dependencies added to pyproject.toml
        3. UV sync fails
        4. Pyproject.toml restored to pre-installation state
        5. Node files removed from filesystem
        6. Environment clean, subsequent nodes can install
        """
        # Create fake node in cache with requirements that will cause sync to fail
        problematic_node_info = NodeInfo(
            name="problematic-node",
            registry_id="problematic-node",
            source="registry",
            version="1.0.0",
            download_url="https://example.com/node.zip"
        )

        cache_path = test_env.workspace_paths.cache / "custom_nodes" / "store" / "test-hash" / "content"
        cache_path.mkdir(parents=True, exist_ok=True)
        (cache_path / "__init__.py").write_text("# Test node")
        (cache_path / "requirements.txt").write_text("test-package>=1.0.0\n")

        # Snapshot state BEFORE attempted installation
        pyproject_before = test_env.pyproject.load()
        nodes_before = set(test_env.pyproject.nodes.get_existing().keys())
        dep_groups_before = set(test_env.pyproject.dependencies.get_groups().keys())

        # Mock node lookup and download
        with patch.object(test_env.node_manager.node_lookup, 'get_node') as mock_get_node, \
             patch.object(test_env.node_manager.node_lookup, 'download_to_cache') as mock_download, \
             patch.object(test_env.node_manager.uv, 'sync_project') as mock_sync:

            mock_get_node.return_value = problematic_node_info
            mock_download.return_value = cache_path

            # Simulate UV sync failure (pycairo build error, disk full, etc.)
            mock_sync.side_effect = UVCommandError(
                "UV sync failed",
                command=["uv", "sync", "--all-groups"],
                stderr="Failed to build pycairo==1.28.0",
                returncode=1
            )

            # ACT: Try to install node - should fail
            target_path = test_env.custom_nodes_path / "problematic-node"

            with pytest.raises((CDNodeConflictError, UVCommandError)):
                test_env.node_manager.add_node("problematic-node", no_test=True)

            # ASSERT: Complete rollback should have occurred

            # 1. Filesystem should be clean (node NOT installed)
            assert not target_path.exists(), \
                f"Node directory should be removed on rollback, but found: {target_path}"

            # 2. Pyproject.toml should be restored (no new nodes)
            pyproject_after = test_env.pyproject.load()
            nodes_after = set(test_env.pyproject.nodes.get_existing().keys())

            assert nodes_after == nodes_before, \
                f"Nodes section should be unchanged after rollback. " \
                f"Before: {nodes_before}, After: {nodes_after}"

            # 3. Dependency groups should be restored (no new groups)
            dep_groups_after = set(test_env.pyproject.dependencies.get_groups().keys())

            assert dep_groups_after == dep_groups_before, \
                f"Dependency groups should be unchanged after rollback. " \
                f"Before: {dep_groups_before}, After: {dep_groups_after}"

            # 4. Tool.uv sections should be restored (no new sources)
            sources_before = pyproject_before.get('tool', {}).get('uv', {}).get('sources', {})
            sources_after = pyproject_after.get('tool', {}).get('uv', {}).get('sources', {})

            assert sources_after == sources_before, \
                f"UV sources should be unchanged after rollback. " \
                f"Before: {sources_before}, After: {sources_after}"

    def test_subsequent_node_installs_after_rollback(self, test_env):
        """Test that environment remains usable after a failed installation.

        This is the critical contamination test:
        1. Node A fails during sync → rolls back cleanly
        2. Node B should install successfully (no contamination)
        """
        # Create two nodes in cache
        node_a_info = NodeInfo(
            name="failing-node",
            registry_id="failing-node",
            source="registry",
            version="1.0.0"
        )

        node_b_info = NodeInfo(
            name="good-node",
            registry_id="good-node",
            source="registry",
            version="1.0.0"
        )

        cache_a = test_env.workspace_paths.cache / "custom_nodes" / "store" / "hash-a" / "content"
        cache_a.mkdir(parents=True, exist_ok=True)
        (cache_a / "__init__.py").write_text("# Node A")
        (cache_a / "requirements.txt").write_text("problematic-package>=1.0.0\n")

        cache_b = test_env.workspace_paths.cache / "custom_nodes" / "store" / "hash-b" / "content"
        cache_b.mkdir(parents=True, exist_ok=True)
        (cache_b / "__init__.py").write_text("# Node B")
        # No requirements - clean node

        with patch.object(test_env.node_manager.node_lookup, 'get_node') as mock_get_node, \
             patch.object(test_env.node_manager.node_lookup, 'download_to_cache') as mock_download, \
             patch.object(test_env.node_manager.uv, 'sync_project') as mock_sync:

            # Track which node is being installed to control sync behavior
            current_node = {"name": None}

            def get_node_side_effect(identifier):
                current_node["name"] = identifier
                return node_a_info if identifier == "failing-node" else node_b_info

            def download_side_effect(node_info):
                return cache_a if node_info.name == "failing-node" else cache_b

            def sync_side_effect(*args, **kwargs):
                # Fail only for failing-node, succeed for good-node
                if current_node["name"] == "failing-node":
                    raise UVCommandError("Build failed", returncode=1, stderr="pycairo error")
                # good-node succeeds (return None = success)
                return None

            mock_get_node.side_effect = get_node_side_effect
            mock_download.side_effect = download_side_effect
            mock_sync.side_effect = sync_side_effect

            # ACT 1: Install failing node - should fail and rollback
            with pytest.raises((CDNodeConflictError, UVCommandError)):
                test_env.node_manager.add_node("failing-node", no_test=True)

            # Verify rollback happened
            assert not (test_env.custom_nodes_path / "failing-node").exists()
            assert "failing-node" not in test_env.pyproject.nodes.get_existing()

            # ACT 2: Install good node - should succeed (no contamination!)
            result = test_env.node_manager.add_node("good-node", no_test=True)

            # ASSERT: Good node installed successfully
            assert result.name == "good-node"
            assert (test_env.custom_nodes_path / "good-node").exists()
            assert "good-node" in test_env.pyproject.nodes.get_existing()

    def test_pyproject_error_triggers_filesystem_rollback(self, test_env):
        """Test that pyproject.toml save failure also triggers filesystem cleanup."""
        node_info = NodeInfo(
            name="test-node",
            registry_id="test-node",
            source="registry",
            version="1.0.0"
        )

        cache_path = test_env.workspace_paths.cache / "custom_nodes" / "store" / "hash" / "content"
        cache_path.mkdir(parents=True, exist_ok=True)
        (cache_path / "__init__.py").write_text("# Test")

        with patch.object(test_env.node_manager.node_lookup, 'get_node') as mock_get_node, \
             patch.object(test_env.node_manager.node_lookup, 'download_to_cache') as mock_download, \
             patch.object(test_env.pyproject, 'save') as mock_save:

            mock_get_node.return_value = node_info
            mock_download.return_value = cache_path

            # Simulate pyproject.toml write failure (disk full, permissions, etc.)
            from comfygit_core.models.exceptions import CDPyprojectError
            mock_save.side_effect = CDPyprojectError("Disk full")

            # ACT: Try to install - should fail during pyproject update
            target_path = test_env.custom_nodes_path / "test-node"

            with pytest.raises((CDPyprojectError, Exception)):
                test_env.node_manager.add_node("test-node", no_test=True)

            # ASSERT: Filesystem should be cleaned up even though pyproject failed
            assert not target_path.exists(), \
                "Node files should be removed even when pyproject save fails"

    def test_disabled_directory_handling_on_rollback(self, test_env):
        """Test that .disabled directory cleanup is handled correctly during rollback.

        Scenario:
        1. Node has a .disabled version on filesystem
        2. Installation starts, deletes .disabled
        3. Installation fails during sync
        4. Rollback occurs

        Current limitation: Cannot restore .disabled (it was deleted)
        Expected: At least warn user, don't fail rollback
        """
        node_info = NodeInfo(
            name="test-node",
            registry_id="test-node",
            source="registry",
            version="1.0.0"
        )

        # Create .disabled version
        disabled_path = test_env.custom_nodes_path / "test-node.disabled"
        disabled_path.mkdir(parents=True)
        (disabled_path / "old_code.py").write_text("# Old version")

        cache_path = test_env.workspace_paths.cache / "custom_nodes" / "store" / "hash" / "content"
        cache_path.mkdir(parents=True, exist_ok=True)
        (cache_path / "__init__.py").write_text("# New version")

        with patch.object(test_env.node_manager.node_lookup, 'get_node') as mock_get_node, \
             patch.object(test_env.node_manager.node_lookup, 'download_to_cache') as mock_download, \
             patch.object(test_env.node_manager.uv, 'sync_project') as mock_sync:

            mock_get_node.return_value = node_info
            mock_download.return_value = cache_path
            mock_sync.side_effect = UVCommandError("Sync failed", returncode=1)

            # ACT: Try to install - will delete .disabled, then fail
            with pytest.raises((CDNodeConflictError, UVCommandError)):
                test_env.node_manager.add_node("test-node", no_test=True)

            # ASSERT: Rollback should complete without error
            # .disabled cannot be restored (data loss), but rollback shouldn't crash
            assert not (test_env.custom_nodes_path / "test-node").exists(), \
                "New installation should be removed"
            # Note: .disabled is lost - documented limitation
