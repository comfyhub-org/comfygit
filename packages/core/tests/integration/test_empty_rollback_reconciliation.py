"""Integration test for empty rollback node reconciliation bug.

Bug Report:
When running `comfygit rollback` without a target (to discard uncommitted changes),
the system correctly reverts .cec/ git changes but does NOT clean up custom node
directories that were added after the last commit.

Expected Behavior:
Empty rollback should reconcile nodes just like targeted rollback:
- Remove extra nodes from filesystem (registry/git → delete, dev → disable)
- Install missing nodes (from cache)
- Maintain consistent state between pyproject.toml and filesystem

Current Bug:
Early return at environment.py:296 skips node reconciliation for empty rollback,
leaving "extra nodes on filesystem" as shown in status output.
"""
import pytest
from pathlib import Path
from unittest.mock import patch

from comfygit_core.models.shared import NodeInfo


class TestEmptyRollbackReconciliation:
    """Test that empty rollback properly reconciles filesystem nodes."""

    def test_empty_rollback_removes_extra_registry_nodes(self, test_env):
        """Test that registry nodes added after commit are deleted on empty rollback.

        Scenario:
        1. Commit v1 with node-a
        2. Add node-b (registry node, uncommitted)
        3. Run empty rollback (no target)
        4. Expected: node-b deleted from filesystem
        5. Current bug: node-b remains, shows as "extra node on filesystem"
        """
        # ARRANGE: Create initial state with one node
        node_a_info = NodeInfo(
            name="node-a",
            registry_id="node-a",
            source="registry",
            version="1.0.0"
        )

        # Setup cache for both nodes
        cache_a = test_env.workspace_paths.cache / "custom_nodes" / "store" / "hash-a" / "content"
        cache_a.mkdir(parents=True, exist_ok=True)
        (cache_a / "__init__.py").write_text("# Node A")

        cache_b = test_env.workspace_paths.cache / "custom_nodes" / "store" / "hash-b" / "content"
        cache_b.mkdir(parents=True, exist_ok=True)
        (cache_b / "__init__.py").write_text("# Node B")

        with patch.object(test_env.node_manager.node_lookup, 'get_node') as mock_get, \
             patch.object(test_env.node_manager.node_lookup, 'download_to_cache') as mock_dl, \
             patch.object(test_env.node_manager.uv, 'sync_project'):

            # Install node-a
            node_b_info = NodeInfo(
                name="node-b",
                registry_id="node-b",
                source="registry",
                version="1.0.0"
            )

            def get_node_mock(identifier):
                return node_a_info if identifier == "node-a" else node_b_info

            def download_mock(node_info):
                return cache_a if node_info.name == "node-a" else cache_b

            mock_get.side_effect = get_node_mock
            mock_dl.side_effect = download_mock

            # Install node-a and commit (v1)
            test_env.node_manager.add_node("node-a", no_test=True)
            test_env.git_manager.commit_all("v1: Initial node")

            # Verify v1 state
            assert (test_env.custom_nodes_path / "node-a").exists()
            assert "node-a" in test_env.pyproject.nodes.get_existing()

            # Install node-b (uncommitted)
            test_env.node_manager.add_node("node-b", no_test=True)

            # Verify both nodes exist before rollback
            assert (test_env.custom_nodes_path / "node-a").exists()
            assert (test_env.custom_nodes_path / "node-b").exists()
            assert "node-a" in test_env.pyproject.nodes.get_existing()
            assert "node-b" in test_env.pyproject.nodes.get_existing()

        # ACT: Empty rollback (discard uncommitted changes)
        test_env.rollback(target=None, force=True)

        # ASSERT: node-b should be DELETED (registry node, cached globally)
        assert (test_env.custom_nodes_path / "node-a").exists(), \
            "node-a should still exist (was in v1)"

        # THIS IS THE BUG - node-b should be deleted but currently remains
        assert not (test_env.custom_nodes_path / "node-b").exists(), \
            "node-b should be deleted (was not in v1, registry node cached)"

        # Verify pyproject.toml only has node-a
        nodes = test_env.pyproject.nodes.get_existing()
        assert "node-a" in nodes, "node-a should be in pyproject.toml"
        assert "node-b" not in nodes, "node-b should NOT be in pyproject.toml"

    def test_empty_rollback_disables_extra_dev_nodes(self, test_env):
        """Test that dev nodes added after commit are disabled on empty rollback.

        Development nodes should be preserved with .disabled suffix, not deleted.
        """
        # ARRANGE: Start with no nodes, commit v1
        test_env.git_manager.commit_all("v1: Empty state")

        # Create dev node directory manually (simulates user's local clone)
        dev_node_path = test_env.custom_nodes_path / "my-dev-node"
        dev_node_path.mkdir(parents=True)
        (dev_node_path / "__init__.py").write_text("# My dev node")
        (dev_node_path / "requirements.txt").write_text("numpy>=1.0.0\n")

        with patch.object(test_env.node_manager.uv, 'sync_project'):
            # Track as dev node (adds to pyproject, uncommitted)
            test_env.node_manager.add_node("my-dev-node", is_development=True, no_test=True)

        # Verify dev node is tracked
        assert dev_node_path.exists()
        nodes = test_env.pyproject.nodes.get_existing()
        assert "my-dev-node" in nodes
        assert nodes["my-dev-node"].source == "development"

        # ACT: Empty rollback
        test_env.rollback(target=None, force=True)

        # ASSERT: Dev node should be DISABLED (not deleted)
        disabled_path = test_env.custom_nodes_path / "my-dev-node.disabled"

        assert not dev_node_path.exists(), \
            "Original dev node path should be gone"

        # THIS IS THE BUG - dev node should be disabled but currently remains active
        assert disabled_path.exists(), \
            "Dev node should be renamed to .disabled (preserves user's work)"

        # Verify code is preserved
        assert (disabled_path / "__init__.py").exists(), \
            "Dev node code should be preserved in .disabled"

        # Verify pyproject.toml doesn't have the dev node
        nodes = test_env.pyproject.nodes.get_existing()
        assert "my-dev-node" not in nodes

    def test_empty_rollback_installs_missing_nodes(self, test_env):
        """Test that nodes removed after commit are reinstalled on empty rollback.

        This tests the reverse case: nodes that existed in v1 but were removed
        should be reinstalled from cache.
        """
        # ARRANGE: Install node-a and commit v1
        node_a_info = NodeInfo(
            name="node-a",
            registry_id="node-a",
            source="registry",
            version="1.0.0"
        )

        cache_a = test_env.workspace_paths.cache / "custom_nodes" / "store" / "hash-a" / "content"
        cache_a.mkdir(parents=True, exist_ok=True)
        (cache_a / "__init__.py").write_text("# Node A")

        with patch.object(test_env.node_manager.node_lookup, 'get_node') as mock_get, \
             patch.object(test_env.node_manager.node_lookup, 'download_to_cache') as mock_dl, \
             patch.object(test_env.node_manager.uv, 'sync_project'):

            mock_get.return_value = node_a_info
            mock_dl.return_value = cache_a

            # Install and commit
            test_env.node_manager.add_node("node-a", no_test=True)
            test_env.git_manager.commit_all("v1: With node-a")

            # Remove node-a (uncommitted)
            test_env.node_manager.remove_node("node-a")

        # Verify node-a is gone
        assert not (test_env.custom_nodes_path / "node-a").exists()
        assert "node-a" not in test_env.pyproject.nodes.get_existing()

        # ACT: Empty rollback (should restore node-a from v1)
        with patch.object(test_env.node_manager.node_lookup, 'download_to_cache') as mock_dl:
            mock_dl.return_value = cache_a
            test_env.rollback(target=None, force=True)

        # ASSERT: node-a should be REINSTALLED
        # THIS IS THE BUG - node stays deleted instead of being reinstalled
        assert (test_env.custom_nodes_path / "node-a").exists(), \
            "node-a should be reinstalled from cache (was in v1)"

        # Verify pyproject.toml has node-a
        nodes = test_env.pyproject.nodes.get_existing()
        assert "node-a" in nodes

    def test_empty_rollback_with_mixed_node_changes(self, test_env):
        """Test complex scenario with multiple node changes.

        This is the scenario from the bug report:
        - v1 has: node-a, node-b, node-c
        - After v1: add 17 more nodes (uncommitted)
        - Empty rollback should: delete the 17 extra nodes
        """
        # ARRANGE: Create v1 with 3 nodes
        base_nodes = ["node-a", "node-b", "node-c"]
        extra_nodes = [f"extra-node-{i}" for i in range(1, 18)]  # 17 extra nodes

        cache_base = test_env.workspace_paths.cache / "custom_nodes" / "store"
        cache_base.mkdir(parents=True, exist_ok=True)

        # Create cache for all nodes
        for node_name in base_nodes + extra_nodes:
            cache_path = cache_base / f"{node_name}-hash" / "content"
            cache_path.mkdir(parents=True, exist_ok=True)
            (cache_path / "__init__.py").write_text(f"# {node_name}")

        def create_node_info(name):
            return NodeInfo(name=name, registry_id=name, source="registry", version="1.0.0")

        def get_cache_for_node(node_info):
            return cache_base / f"{node_info.name}-hash" / "content"

        with patch.object(test_env.node_manager.node_lookup, 'get_node') as mock_get, \
             patch.object(test_env.node_manager.node_lookup, 'download_to_cache') as mock_dl, \
             patch.object(test_env.node_manager.uv, 'sync_project'):

            mock_get.side_effect = lambda id: create_node_info(id)
            mock_dl.side_effect = get_cache_for_node

            # Install base 3 nodes and commit v1
            for node_name in base_nodes:
                test_env.node_manager.add_node(node_name, no_test=True)

            test_env.git_manager.commit_all("v1: Initial 3 nodes")

            # Install 17 extra nodes (uncommitted)
            for node_name in extra_nodes:
                test_env.node_manager.add_node(node_name, no_test=True)

        # Verify all 20 nodes exist
        all_nodes = base_nodes + extra_nodes
        for node_name in all_nodes:
            assert (test_env.custom_nodes_path / node_name).exists()

        nodes = test_env.pyproject.nodes.get_existing()
        assert len(nodes) == 20

        # ACT: Empty rollback
        test_env.rollback(target=None, force=True)

        # ASSERT: Only base 3 nodes should remain
        for node_name in base_nodes:
            assert (test_env.custom_nodes_path / node_name).exists(), \
                f"{node_name} should exist (was in v1)"

        # THIS IS THE BUG - extra nodes should be deleted but currently remain
        for node_name in extra_nodes:
            assert not (test_env.custom_nodes_path / node_name).exists(), \
                f"{node_name} should be deleted (was not in v1)"

        # Verify pyproject.toml only has 3 base nodes
        nodes = test_env.pyproject.nodes.get_existing()
        assert len(nodes) == 3, f"Should have 3 nodes, got {len(nodes)}"
        for node_name in base_nodes:
            assert node_name in nodes

    def test_empty_rollback_no_op_when_no_changes(self, test_env):
        """Test that empty rollback with no uncommitted changes is a no-op.

        This is the edge case where rollback is called but there's nothing to do.
        Should not crash or cause issues.
        """
        # ARRANGE: Commit v1 with no changes
        test_env.git_manager.commit_all("v1: Initial state")

        # ACT: Empty rollback (nothing to discard)
        test_env.rollback(target=None, force=True)

        # ASSERT: Should complete without error
        # No assertion needed - test passes if no exception raised
        assert True, "Empty rollback with no changes should be safe"
