"""Integration tests for node dependency isolation and contamination prevention.

Tests that node additions with failing dependencies don't contaminate the environment,
preventing subsequent successful node additions from working.
"""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from comfygit_core.models.shared import NodeInfo
from comfygit_core.models.exceptions import UVCommandError, CDNodeConflictError


class TestNodeDependencyIsolation:
    """Test that failing node installations don't contaminate the environment."""

    def test_failing_node_does_not_contaminate_environment(self, test_env):
        """Test that a node with unresolvable dependencies doesn't block subsequent additions.

        CRITICAL BUG: Currently, when a node's dependencies fail to resolve (e.g., pycairo
        build failure), the node files are installed and dependencies are added to
        pyproject.toml BEFORE testing. This contaminates the environment, causing ALL
        subsequent node additions to fail because uv sync tries to build the problematic
        dependency.

        Expected behavior:
        1. Node A (has pycairo dependency) - test BEFORE install, fails cleanly
        2. Node B (no problematic deps) - should install successfully

        Current buggy behavior:
        1. Node A - files installed, pyproject.toml updated, THEN test fails
        2. Node B - tries to install, but uv sync fails on Node A's pycairo

        This test demonstrates the bug and will pass once fixed.
        """
        # Mock node lookup service to return controlled test nodes
        mock_node_a_info = NodeInfo(
            name="problematic-node",
            registry_id="problematic-node",
            source="registry",
            version="1.0.0",
            download_url="https://example.com/node-a.zip"
        )

        mock_node_b_info = NodeInfo(
            name="good-node",
            registry_id="good-node",
            source="registry",
            version="1.0.0",
            download_url="https://example.com/node-b.zip"
        )

        # Create fake node directories in cache
        cache_node_a = test_env.workspace_paths.cache / "custom_nodes" / "store" / "mock-hash-a" / "content"
        cache_node_a.mkdir(parents=True, exist_ok=True)
        (cache_node_a / "__init__.py").write_text("# Node A")
        (cache_node_a / "requirements.txt").write_text("svglib==1.6.0\n")  # Transitively requires pycairo

        cache_node_b = test_env.workspace_paths.cache / "custom_nodes" / "store" / "mock-hash-b" / "content"
        cache_node_b.mkdir(parents=True, exist_ok=True)
        (cache_node_b / "__init__.py").write_text("# Node B")
        # No requirements - perfectly clean node

        # Patch the node lookup service
        with patch.object(test_env.node_manager.node_lookup, 'get_node') as mock_get_node, \
             patch.object(test_env.node_manager.node_lookup, 'download_to_cache') as mock_download, \
             patch.object(test_env.node_manager.resolution_tester, 'test_resolution') as mock_test_resolution:

            def get_node_side_effect(identifier):
                if identifier == "problematic-node":
                    return mock_node_a_info
                elif identifier == "good-node":
                    return mock_node_b_info
                raise Exception(f"Unknown node: {identifier}")

            def download_side_effect(node_info):
                if node_info.name == "problematic-node":
                    return cache_node_a
                elif node_info.name == "good-node":
                    return cache_node_b
                return None

            mock_get_node.side_effect = get_node_side_effect
            mock_download.side_effect = download_side_effect

            # First resolution test (for Node A) - simulate pycairo build failure
            mock_resolution_result_fail = MagicMock()
            mock_resolution_result_fail.success = False
            mock_resolution_result_fail.conflicts = ["Failed to build pycairo"]

            # Second resolution test (for Node B) - should pass
            mock_resolution_result_success = MagicMock()
            mock_resolution_result_success.success = True
            mock_resolution_result_success.conflicts = []

            mock_test_resolution.side_effect = [mock_resolution_result_fail, mock_resolution_result_success]

            # ACT 1: Try to add problematic node - should fail cleanly
            with pytest.raises(CDNodeConflictError, match="dependency conflicts"):
                test_env.node_manager.add_node("problematic-node", no_test=False)

            # VERIFY: Problematic node should NOT be in pyproject.toml
            existing_nodes = test_env.node_manager.pyproject.nodes.get_existing()
            assert "problematic-node" not in existing_nodes, \
                "Failed node should not be tracked in pyproject.toml"

            # VERIFY: Problematic node files should NOT be installed
            node_a_path = test_env.comfyui_path / "custom_nodes" / "problematic-node"
            assert not node_a_path.exists(), \
                "Failed node files should not be installed to custom_nodes/"

            # ACT 2: Add good node - should succeed without contamination
            result = test_env.node_manager.add_node("good-node", no_test=False)

            # VERIFY: Good node should be installed successfully
            assert result.name == "good-node"
            existing_nodes = test_env.node_manager.pyproject.nodes.get_existing()
            assert "good-node" in existing_nodes, \
                "Good node should be tracked after successful install"

            node_b_path = test_env.comfyui_path / "custom_nodes" / "good-node"
            assert node_b_path.exists(), \
                "Good node files should be installed"


    def test_environment_state_unchanged_after_failed_addition(self, test_env):
        """Test that a failed node addition leaves the environment in original state.

        Tests atomic behavior - if any step fails, the environment should be unchanged.
        """
        # Capture initial state
        initial_nodes = set(test_env.node_manager.pyproject.nodes.get_existing().keys())
        initial_deps = str(test_env.node_manager.pyproject.path.read_text())

        # Mock a node that will fail
        mock_node_info = NodeInfo(
            name="failing-node",
            registry_id="failing-node",
            source="registry",
            version="1.0.0",
            download_url="https://example.com/failing.zip"
        )

        cache_node = test_env.workspace_paths.cache / "custom_nodes" / "store" / "fail-hash" / "content"
        cache_node.mkdir(parents=True, exist_ok=True)
        (cache_node / "__init__.py").write_text("# Failing node")
        (cache_node / "requirements.txt").write_text("impossible-package==999.0.0\n")

        with patch.object(test_env.node_manager.node_lookup, 'get_node', return_value=mock_node_info), \
             patch.object(test_env.node_manager.node_lookup, 'download_to_cache', return_value=cache_node), \
             patch.object(test_env.node_manager.resolution_tester, 'test_resolution') as mock_test:

            mock_result = MagicMock()
            mock_result.success = False
            mock_result.conflicts = ["Package impossible-package not found"]
            mock_test.return_value = mock_result

            # Try to add failing node
            with pytest.raises(CDNodeConflictError):
                test_env.node_manager.add_node("failing-node", no_test=False)

        # Verify state is unchanged
        final_nodes = set(test_env.node_manager.pyproject.nodes.get_existing().keys())
        final_deps = str(test_env.node_manager.pyproject.path.read_text())

        assert initial_nodes == final_nodes, "Node tracking should be unchanged"
        assert initial_deps == final_deps, "pyproject.toml should be unchanged"

        # Verify files not installed
        node_path = test_env.comfyui_path / "custom_nodes" / "failing-node"
        assert not node_path.exists(), "Failed node files should not be installed"
