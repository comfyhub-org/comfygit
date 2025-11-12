"""Tests for NodeLookupService cache-first behavior.

TDD tests to verify that NodeLookupService:
1. Checks local node mappings cache BEFORE hitting registry API
2. Falls back to API only when package not in cache
3. Respects prefer_registry_cache config setting
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest

from comfygit_core.models.node_mapping import GlobalNodePackage, GlobalNodePackageVersion
from comfygit_core.models.shared import NodeInfo
from comfygit_core.repositories.node_mappings_repository import NodeMappingsRepository
from comfygit_core.services.node_lookup_service import NodeLookupService


class TestNodeLookupCacheFirst:
    """Test cache-first lookup behavior."""

    @pytest.fixture
    def mock_mappings_data(self):
        """Create mock mappings JSON data."""
        return {
            "version": "2025.01.01",
            "generated_at": "2025-01-01T00:00:00",
            "stats": {
                "packages": 1,
                "signatures": 1,
                "total_nodes": 1,
                "augmented": True,
                "augmentation_date": "2025-01-01T00:00:00",
                "nodes_from_manager": 0,
                "manager_packages": 0
            },
            "mappings": {},
            "packages": {
                "test-package-id": {
                    "id": "test-package-id",
                    "display_name": "Test Package",
                    "author": "test-author",
                    "description": "Test description",
                    "repository": "https://github.com/test/repo",
                    "downloads": 100,
                    "github_stars": 50,
                    "rating": None,
                    "license": "MIT",
                    "category": "test",
                    "icon": None,
                    "tags": [],
                    "status": "active",
                    "created_at": "2025-01-01T00:00:00",
                    "source": None,
                    "versions": {
                        "1.0.0": {
                            "version": "1.0.0",
                            "changelog": "Initial release",
                            "release_date": "2025-01-01T00:00:00",
                            "dependencies": [],
                            "deprecated": False,
                            "download_url": "https://cdn.comfy.org/test-package-id/1.0.0/node.zip",
                            "status": "active",
                            "supported_accelerators": None,
                            "supported_comfyui_version": None,
                            "supported_os": None
                        }
                    }
                }
            }
        }

    @pytest.fixture
    def cache_dir(self):
        """Create a temporary cache directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def mappings_repo(self, mock_mappings_data):
        """Create a NodeMappingsRepository with test data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mappings_path = Path(tmpdir) / "mappings.json"
            mappings_path.write_text(json.dumps(mock_mappings_data))

            # Mock data manager to avoid RegistryDataManager dependency
            mock_data_manager = Mock()
            mock_data_manager.get_mappings_path.return_value = mappings_path

            repo = NodeMappingsRepository(data_manager=mock_data_manager)
            yield repo

    def test_find_node_checks_cache_before_api_when_enabled(self, mappings_repo, cache_dir):
        """SHOULD check local cache before hitting registry API when prefer_registry_cache=True."""
        # ARRANGE
        mock_registry_client = MagicMock()
        mock_workspace_config_repo = Mock()
        mock_workspace_config_repo.get_prefer_registry_cache.return_value = True

        # Create service with cache enabled
        service = NodeLookupService(
            cache_path=cache_dir,
            node_mappings_repository=mappings_repo,
            workspace_config_repository=mock_workspace_config_repo
        )
        service.registry_client = mock_registry_client

        # ACT
        result = service.find_node("test-package-id")

        # ASSERT
        # Should return NodeInfo from cache
        assert result is not None
        assert result.name == "Test Package"
        assert result.registry_id == "test-package-id"
        assert result.version == "1.0.0"
        assert result.download_url == "https://cdn.comfy.org/test-package-id/1.0.0/node.zip"
        assert result.source == "registry"

        # Should NOT have called the registry API
        mock_registry_client.get_node.assert_not_called()

    def test_find_node_falls_back_to_api_when_not_in_cache(self, mappings_repo, cache_dir):
        """SHOULD fall back to API when package not in local cache."""
        # ARRANGE
        mock_registry_client = MagicMock()
        mock_registry_node = Mock()
        mock_registry_node.id = "new-package-id"
        mock_registry_node.latest_version = Mock()
        mock_registry_node.latest_version.version = "2.0.0"
        mock_registry_client.get_node.return_value = mock_registry_node

        mock_workspace_config_repo = Mock()
        mock_workspace_config_repo.get_prefer_registry_cache.return_value = True

        service = NodeLookupService(
            
            cache_path=cache_dir,
            node_mappings_repository=mappings_repo,
            workspace_config_repository=mock_workspace_config_repo
        )
        service.registry_client = mock_registry_client

        # ACT
        result = service.find_node("new-package-id")

        # ASSERT
        # Should have called API since not in cache
        mock_registry_client.get_node.assert_called_once_with("new-package-id")
        assert result is not None
        assert result.registry_id == "new-package-id"

    def test_find_node_uses_api_when_cache_disabled(self, mappings_repo, cache_dir):
        """SHOULD use API directly when prefer_registry_cache=False."""
        # ARRANGE
        mock_registry_client = MagicMock()
        mock_registry_node = Mock()
        mock_registry_node.id = "test-package-id"
        mock_registry_node.latest_version = Mock()
        mock_registry_node.latest_version.version = "1.0.0"
        mock_registry_client.get_node.return_value = mock_registry_node

        mock_workspace_config_repo = Mock()
        mock_workspace_config_repo.get_prefer_registry_cache.return_value = False

        service = NodeLookupService(
            
            cache_path=cache_dir,
            node_mappings_repository=mappings_repo,
            workspace_config_repository=mock_workspace_config_repo
        )
        service.registry_client = mock_registry_client

        # ACT
        result = service.find_node("test-package-id")

        # ASSERT
        # Should have called API even though package is in cache
        mock_registry_client.get_node.assert_called_once_with("test-package-id")

    def test_find_node_handles_version_request_from_cache(self, mappings_repo, cache_dir):
        """SHOULD handle version-specific requests from cache (e.g., 'package@1.0.0')."""
        # ARRANGE
        mock_workspace_config_repo = Mock()
        mock_workspace_config_repo.get_prefer_registry_cache.return_value = True

        service = NodeLookupService(
            
            cache_path=cache_dir,
            node_mappings_repository=mappings_repo,
            workspace_config_repository=mock_workspace_config_repo
        )

        # ACT
        result = service.find_node("test-package-id@1.0.0")

        # ASSERT
        assert result is not None
        assert result.version == "1.0.0"
        assert result.registry_id == "test-package-id"


class TestNodeInfoFromGlobalPackage:
    """Test NodeInfo.from_global_package() classmethod."""

    def test_from_global_package_basic(self):
        """SHOULD create NodeInfo from GlobalNodePackage."""
        # ARRANGE
        version_data = GlobalNodePackageVersion(
            version="1.0.0",
            changelog="Initial",
            release_date="2025-01-01",
            dependencies=None,
            deprecated=False,
            download_url="https://cdn.comfy.org/pkg/1.0.0/node.zip",
            status="active",
            supported_accelerators=None,
            supported_comfyui_version=None,
            supported_os=None
        )

        package = GlobalNodePackage(
            id="test-pkg",
            display_name="Test Package",
            author="author",
            description="desc",
            repository="https://github.com/test/repo",
            downloads=100,
            github_stars=50,
            rating=None,
            license="MIT",
            category="test",
            versions={"1.0.0": version_data}
        )

        # ACT
        node_info = NodeInfo.from_global_package(package, version="1.0.0")

        # ASSERT
        assert node_info.name == "Test Package"
        assert node_info.registry_id == "test-pkg"
        assert node_info.repository == "https://github.com/test/repo"
        assert node_info.version == "1.0.0"
        assert node_info.download_url == "https://cdn.comfy.org/pkg/1.0.0/node.zip"
        assert node_info.source == "registry"

    def test_from_global_package_defaults_to_latest_version(self):
        """SHOULD default to latest version when no version specified."""
        # ARRANGE
        version_data = GlobalNodePackageVersion(
            version="2.0.0",
            changelog="Latest",
            release_date="2025-01-02",
            dependencies=None,
            deprecated=False,
            download_url="https://cdn.comfy.org/pkg/2.0.0/node.zip",
            status="active",
            supported_accelerators=None,
            supported_comfyui_version=None,
            supported_os=None
        )

        package = GlobalNodePackage(
            id="test-pkg",
            display_name="Test Package",
            author="author",
            description="desc",
            repository="https://github.com/test/repo",
            downloads=100,
            github_stars=50,
            rating=None,
            license="MIT",
            category="test",
            versions={"2.0.0": version_data}
        )

        # ACT
        node_info = NodeInfo.from_global_package(package)

        # ASSERT
        assert node_info.version == "2.0.0"


class TestWorkspaceConfigCachePreference:
    """Test workspace config methods for cache preference."""

    def test_get_prefer_registry_cache_default_true(self):
        """SHOULD default to True for prefer_registry_cache."""
        # ARRANGE
        from comfygit_core.repositories.workspace_config_repository import WorkspaceConfigRepository

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "workspace.json"
            repo = WorkspaceConfigRepository(config_file=config_path)

            # ACT
            result = repo.get_prefer_registry_cache()

            # ASSERT
            assert result is True

    def test_set_prefer_registry_cache(self):
        """SHOULD persist prefer_registry_cache setting."""
        # ARRANGE
        from comfygit_core.repositories.workspace_config_repository import WorkspaceConfigRepository

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "workspace.json"
            repo = WorkspaceConfigRepository(config_file=config_path)

            # ACT
            repo.set_prefer_registry_cache(False)
            result = repo.get_prefer_registry_cache()

            # ASSERT
            assert result is False

            # Verify it persists
            repo2 = WorkspaceConfigRepository(config_file=config_path)
            assert repo2.get_prefer_registry_cache() is False
