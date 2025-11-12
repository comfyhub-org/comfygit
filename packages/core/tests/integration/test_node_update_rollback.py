"""Integration tests for atomic node update with rollback on failure.

Tests that when a node update fails during installation, the old node
is preserved and the environment is left in a working state.

Bug: Currently update follows remove-then-add pattern with no rollback,
leaving environment broken if installation fails.
"""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from comfygit_core.models.shared import NodeInfo
from comfygit_core.models.exceptions import CDEnvironmentError, CDNodeConflictError
from comfygit_core.models.registry import RegistryNodeInfo, RegistryNodeVersion
from comfygit_core.clients.github_client import GitHubRepoInfo
from comfygit_core.validation.resolution_tester import ResolutionResult
from comfygit_core.strategies.confirmation import AutoConfirmStrategy


class TestNodeUpdateRollback:
    """Test node update rollback behavior when installation fails."""

    def test_update_registry_node_preserves_old_when_download_fails(self, test_env):
        """Test that failed registry node update preserves old node.

        Given: Node v1.0.0 is installed
        When: Update to v2.0.0 fails during download
        Then: Old v1.0.0 is still installed and functional

        BUG: Currently this fails - old node is removed and not restored.
        """
        # ARRANGE: Install initial version 1.0.0
        node_info_v1 = NodeInfo(
            name="test-node",
            registry_id="test-node",
            source="registry",
            version="1.0.0",
            download_url="https://example.com/v1.0.0.zip"
        )

        cache_path_v1 = test_env.workspace_paths.cache / "custom_nodes" / "store" / "hash-v1" / "content"
        cache_path_v1.mkdir(parents=True, exist_ok=True)
        (cache_path_v1 / "__init__.py").write_text("# v1.0.0")
        (cache_path_v1 / "requirements.txt").write_text("requests==2.28.0")

        with patch.object(test_env.node_manager.node_lookup, 'get_node') as mock_get_node, \
             patch.object(test_env.node_manager.node_lookup, 'download_to_cache') as mock_download, \
             patch.object(test_env.node_manager.node_lookup, 'scan_requirements') as mock_scan:

            mock_get_node.return_value = node_info_v1
            mock_download.return_value = cache_path_v1
            mock_scan.return_value = ["requests==2.28.0"]

            test_env.node_manager.add_node("test-node@1.0.0", no_test=True)

        # Verify v1.0.0 is installed
        nodes = test_env.pyproject.nodes.get_existing()
        assert "test-node" in nodes
        assert nodes["test-node"].version == "1.0.0"

        node_path = test_env.custom_nodes_path / "test-node"
        assert node_path.exists()
        assert (node_path / "__init__.py").read_text() == "# v1.0.0"

        # Setup mocks for failed update
        registry_node_v2 = RegistryNodeInfo(
            id="test-node",
            name="test-node",
            description="Test node",
            repository="https://github.com/example/test-node",
            latest_version=RegistryNodeVersion(
                changelog="",
                dependencies=[],
                deprecated=False,
                id="test-node-v2.0.0",
                version="2.0.0",
                download_url="https://example.com/v2.0.0.zip"
            )
        )

        with patch.object(test_env.node_manager.node_lookup.registry_client, 'get_node') as mock_registry_get, \
             patch.object(test_env.node_manager.node_lookup.registry_client, 'install_node') as mock_install, \
             patch.object(test_env.node_manager.node_lookup, 'download_to_cache') as mock_download:

            mock_registry_get.return_value = registry_node_v2
            mock_install.return_value = registry_node_v2.latest_version
            # Simulate download failure
            mock_download.return_value = None  # download_to_cache returns None on failure

            # ACT: Attempt update (should fail but preserve old node)
            strategy = AutoConfirmStrategy()
            with pytest.raises(CDEnvironmentError) as exc_info:
                test_env.node_manager.update_node("test-node", confirmation_strategy=strategy, no_test=True)

            assert "Failed to download" in str(exc_info.value)

        # ASSERT: Old node v1.0.0 should still be present and functional
        nodes = test_env.pyproject.nodes.get_existing()
        assert "test-node" in nodes, "Node should still be tracked in pyproject.toml"
        assert nodes["test-node"].version == "1.0.0", "Old version should be preserved"

        # Filesystem should have old node
        assert node_path.exists(), "Old node directory should exist"
        assert (node_path / "__init__.py").read_text() == "# v1.0.0", "Old node content should be unchanged"

        # Python environment should still have old requirements
        pyproject_content = test_env.pyproject.path.read_text()
        assert "requests" in pyproject_content, "Old dependencies should still be tracked"

    def test_update_git_node_preserves_old_when_clone_fails(self, test_env):
        """Test that failed git node update preserves old node.

        Given: Git node at commit abc123 is installed
        When: Update to commit def456 fails during git clone
        Then: Old commit abc123 is still installed and functional
        """
        # ARRANGE: Install initial commit
        node_info_v1 = NodeInfo(
            name="test-git-node",
            repository="https://github.com/example/test-git-node",
            source="git",
            version="abc123def456abc123def456abc123def456abc123"  # Full commit hash
        )

        cache_path_v1 = test_env.workspace_paths.cache / "custom_nodes" / "store" / "git-hash-v1" / "content"
        cache_path_v1.mkdir(parents=True, exist_ok=True)
        (cache_path_v1 / "__init__.py").write_text("# commit abc123")

        with patch.object(test_env.node_manager.node_lookup, 'get_node') as mock_get_node, \
             patch.object(test_env.node_manager.node_lookup, 'download_to_cache') as mock_download, \
             patch.object(test_env.node_manager.node_lookup, 'scan_requirements') as mock_scan:

            mock_get_node.return_value = node_info_v1
            mock_download.return_value = cache_path_v1
            mock_scan.return_value = []

            test_env.node_manager.add_node("https://github.com/example/test-git-node@abc123def456abc123def456abc123def456abc123", no_test=True)

        # Verify initial commit is installed
        nodes = test_env.pyproject.nodes.get_existing()
        assert "test-git-node" in nodes
        assert nodes["test-git-node"].version.startswith("abc123")

        node_path = test_env.custom_nodes_path / "test-git-node"
        assert node_path.exists()
        assert (node_path / "__init__.py").read_text() == "# commit abc123"

        # Setup mocks for failed update
        repo_info_latest = GitHubRepoInfo(
            owner="example",
            name="test-git-node",
            default_branch="main",
            clone_url="https://github.com/example/test-git-node",
            latest_commit="def456789012def456789012def456789012def456"
        )

        with patch.object(test_env.node_manager.node_lookup.github_client, 'get_repository_info') as mock_github_get, \
             patch.object(test_env.node_manager.node_lookup, 'download_to_cache') as mock_download:

            mock_github_get.return_value = repo_info_latest
            # Simulate clone failure
            mock_download.return_value = None

            # ACT: Attempt update (should fail but preserve old node)
            strategy = AutoConfirmStrategy()
            with pytest.raises(CDEnvironmentError) as exc_info:
                test_env.node_manager.update_node("test-git-node", confirmation_strategy=strategy, no_test=True)

            assert "Failed to download" in str(exc_info.value)

        # ASSERT: Old node should still be present
        nodes = test_env.pyproject.nodes.get_existing()
        assert "test-git-node" in nodes, "Node should still be tracked"
        assert nodes["test-git-node"].version.startswith("abc123"), "Old commit should be preserved"

        assert node_path.exists(), "Old node directory should exist"
        assert (node_path / "__init__.py").read_text() == "# commit abc123", "Old content should be unchanged"

    def test_update_preserves_old_when_dependency_conflict_detected(self, test_env):
        """Test that update with dependency conflicts preserves old node.

        Given: Node v1.0.0 is installed with requests==2.28.0
        When: Update to v2.0.0 has conflicts (requires requests==3.0.0 conflicting with another package)
        Then: Old v1.0.0 is still installed, update is aborted
        """
        # ARRANGE: Install v1.0.0
        node_info_v1 = NodeInfo(
            name="test-node",
            registry_id="test-node",
            source="registry",
            version="1.0.0",
            download_url="https://example.com/v1.0.0.zip"
        )

        cache_path_v1 = test_env.workspace_paths.cache / "custom_nodes" / "store" / "hash-v1" / "content"
        cache_path_v1.mkdir(parents=True, exist_ok=True)
        (cache_path_v1 / "__init__.py").write_text("# v1.0.0")
        (cache_path_v1 / "requirements.txt").write_text("requests==2.28.0")

        with patch.object(test_env.node_manager.node_lookup, 'get_node') as mock_get_node, \
             patch.object(test_env.node_manager.node_lookup, 'download_to_cache') as mock_download, \
             patch.object(test_env.node_manager.node_lookup, 'scan_requirements') as mock_scan:

            mock_get_node.return_value = node_info_v1
            mock_download.return_value = cache_path_v1
            mock_scan.return_value = ["requests==2.28.0"]

            test_env.node_manager.add_node("test-node@1.0.0", no_test=True)

        # Verify v1.0.0 is installed
        node_path = test_env.custom_nodes_path / "test-node"
        assert node_path.exists()

        # Setup for update with conflicting dependencies
        registry_node_v2 = RegistryNodeInfo(
            id="test-node",
            name="test-node",
            description="Test node",
            repository="https://github.com/example/test-node",
            latest_version=RegistryNodeVersion(
                changelog="",
                dependencies=[],
                deprecated=False,
                id="test-node-v2.0.0",
                version="2.0.0",
                download_url="https://example.com/v2.0.0.zip"
            )
        )

        cache_path_v2 = test_env.workspace_paths.cache / "custom_nodes" / "store" / "hash-v2" / "content"
        cache_path_v2.mkdir(parents=True, exist_ok=True)
        (cache_path_v2 / "__init__.py").write_text("# v2.0.0")
        (cache_path_v2 / "requirements.txt").write_text("requests==3.0.0")

        with patch.object(test_env.node_manager.node_lookup.registry_client, 'get_node') as mock_registry_get, \
             patch.object(test_env.node_manager.node_lookup.registry_client, 'install_node') as mock_install, \
             patch.object(test_env.node_manager.node_lookup, 'download_to_cache') as mock_download, \
             patch.object(test_env.node_manager.node_lookup, 'scan_requirements') as mock_scan, \
             patch.object(test_env.node_manager.resolution_tester, 'test_resolution') as mock_test_resolution:

            mock_registry_get.return_value = registry_node_v2
            mock_install.return_value = registry_node_v2.latest_version
            mock_download.return_value = cache_path_v2
            mock_scan.return_value = ["requests==3.0.0"]

            # Simulate dependency conflict
            mock_test_resolution.return_value = ResolutionResult(
                success=False,
                conflicts=["requests: 2.28.0 (current) conflicts with 3.0.0 (required)"]
            )

            # ACT: Attempt update with no_test=False to trigger resolution testing
            strategy = AutoConfirmStrategy()
            with pytest.raises(CDEnvironmentError) as exc_info:
                test_env.node_manager.update_node("test-node", confirmation_strategy=strategy, no_test=False)

            assert "conflict" in str(exc_info.value).lower()

        # ASSERT: Old node should be preserved
        nodes = test_env.pyproject.nodes.get_existing()
        assert "test-node" in nodes, "Node should still be tracked"
        assert nodes["test-node"].version == "1.0.0", "Old version should be preserved"

        assert node_path.exists(), "Old node should still exist"
        assert (node_path / "__init__.py").read_text() == "# v1.0.0", "Old content should be unchanged"
