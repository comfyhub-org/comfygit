"""NodeLookupService - Pure stateless service for finding nodes and analyzing requirements."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from comfygit_core.models.exceptions import CDNodeNotFoundError, CDRegistryError
from comfygit_core.models.shared import NodeInfo

from ..analyzers.custom_node_scanner import CustomNodeScanner
from ..caching import APICacheManager, CustomNodeCacheManager
from ..clients import ComfyRegistryClient, GitHubClient
from ..logging.logging_config import get_logger
from ..utils.git import is_git_url

if TYPE_CHECKING:
    from comfygit_core.repositories.node_mappings_repository import NodeMappingsRepository
    from comfygit_core.repositories.workspace_config_repository import WorkspaceConfigRepository

logger = get_logger(__name__)


class NodeLookupService:
    """Pure stateless service for finding nodes and analyzing their requirements.

    Responsibilities:
    - Registry lookup (cache-first, then API)
    - GitHub API calls (validating repos, getting commit info)
    - Requirement scanning (analyzing node directories)
    - Cache management (API responses, downloaded node archives)
    """

    def __init__(
        self,
        cache_path: Path,
        node_mappings_repository: NodeMappingsRepository | None = None,
        workspace_config_repository: WorkspaceConfigRepository | None = None,
    ):
        """Initialize the node lookup service.

        Args:
            cache_path: Required path to workspace cache directory
            node_mappings_repository: Repository for cached node mappings
            workspace_config_repository: Repository for workspace config (cache preference)
        """
        self.scanner = CustomNodeScanner()
        self.api_cache = APICacheManager(cache_base_path=cache_path)
        self.custom_node_cache = CustomNodeCacheManager(cache_base_path=cache_path)
        self.registry_client = ComfyRegistryClient(cache_manager=self.api_cache)
        self.github_client = GitHubClient(cache_manager=self.api_cache)
        self.node_mappings_repository = node_mappings_repository
        self.workspace_config_repository = workspace_config_repository

    def find_node(self, identifier: str) -> NodeInfo | None:
        """Find node info from cache, registry, or git URL.

        Cache-first strategy:
        1. If prefer_registry_cache=True and package in local cache → return from cache
        2. Otherwise → query live API

        Args:
            identifier: Registry ID, git URL, or name. Supports @version/@ref syntax:
                       - registry-id@1.0.0 (registry version)
                       - https://github.com/user/repo@v1.2.3 (git tag)
                       - https://github.com/user/repo@main (git branch)
                       - https://github.com/user/repo@abc123 (git commit)

        Returns:
            NodeInfo with metadata, or None if not found
        """
        # Parse version/ref from identifier (e.g., "package-id@1.2.3" or "https://...@branch")
        requested_version = None
        base_identifier = identifier

        if '@' in identifier:
            parts = identifier.rsplit('@', 1)  # rsplit to handle URLs with @
            base_identifier = parts[0]
            requested_version = parts[1]

        # Check if it's a git URL - these bypass cache
        if is_git_url(base_identifier):
            try:
                if repo_info := self.github_client.get_repository_info(base_identifier, ref=requested_version):
                    return NodeInfo(
                        name=repo_info.name,
                        repository=repo_info.clone_url,
                        source="git",
                        version=repo_info.latest_commit  # This will be the requested ref's commit
                    )
            except Exception as e:
                logger.warning(f"Invalid git URL: {e}")
                return None

        # Check if we should prefer cached mappings
        prefer_cache = True
        if self.workspace_config_repository:
            prefer_cache = self.workspace_config_repository.get_prefer_registry_cache()

        # Strategy: Cache first, then API
        if prefer_cache and self.node_mappings_repository:
            package = self.node_mappings_repository.get_package(base_identifier)
            if package:
                logger.debug(f"Found '{base_identifier}' in local cache")
                return NodeInfo.from_global_package(package, version=requested_version)
            else:
                logger.debug(f"'{base_identifier}' not in local cache, trying API...")

        # Fallback to registry API
        try:
            registry_node = self.registry_client.get_node(base_identifier)
            if registry_node:
                if requested_version:
                    version = requested_version
                    logger.debug(f"Using requested version: {version}")
                else:
                    version = registry_node.latest_version.version if registry_node.latest_version else None
                node_version = self.registry_client.install_node(registry_node.id, version)
                if node_version:
                    registry_node.latest_version = node_version
                return NodeInfo.from_registry_node(registry_node)
        except CDRegistryError as e:
            logger.warning(f"Cannot reach registry: {e}")

        logger.debug(f"Node '{base_identifier}' not found")
        return None

    def get_node(self, identifier: str) -> NodeInfo:
        """Get a node - raises if not found.

        Args:
            identifier: Registry ID, node name, or git URL

        Returns:
            NodeInfo with metadata

        Raises:
            CDNodeNotFoundError: If node not found in any source
        """
        node = self.find_node(identifier)
        if not node:
            # Build context-aware error based on what was tried
            if is_git_url(identifier):
                msg = f"Node '{identifier}' not found. GitHub repository is invalid or inaccessible."
            else:
                # Registry lookup was attempted
                prefer_cache = True
                if self.workspace_config_repository:
                    prefer_cache = self.workspace_config_repository.get_prefer_registry_cache()

                sources_tried = ["local cache", "registry API"] if prefer_cache else ["registry API"]
                msg = f"Node '{identifier}' not found in {' or '.join(sources_tried)}"

            raise CDNodeNotFoundError(msg)
        return node

    def scan_requirements(self, node_path: Path) -> list[str]:
        """Scan a node directory for Python requirements.

        Args:
            node_path: Path to node directory

        Returns:
            List of requirement strings (empty if none found)
        """
        deps = self.scanner.scan_node(node_path)
        if deps and deps.requirements:
            logger.info(f"Found {len(deps.requirements)} requirements in {node_path.name}")
            return deps.requirements
        logger.info(f"No requirements found in {node_path.name}")
        return []

    def download_to_cache(self, node_info: NodeInfo) -> Path | None:
        """Download a node to cache and return the cached path.

        Args:
            node_info: Node information

        Returns:
            Path to cached node directory, or None if download failed
        """
        import tempfile

        from ..utils.download import download_and_extract_archive
        from ..utils.git import git_clone

        # Check if already cached
        if cache_path := self.custom_node_cache.get_cached_path(node_info):
            logger.debug(f"Node '{node_info.name}' already in cache")
            return cache_path

        # Download to temp location
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir) / node_info.name

            try:
                if node_info.source == "registry":
                    if not node_info.download_url:
                        # Fallback: Clone from repository if download URL missing
                        if node_info.repository:
                            logger.info(
                                f"No CDN package for '{node_info.name}', "
                                f"falling back to git clone from {node_info.repository}"
                            )
                            # Update source to git for this installation
                            node_info.source = "git"
                            ref = node_info.version if node_info.version else None
                            git_clone(node_info.repository, temp_path, depth=1, ref=ref, timeout=30)
                        else:
                            logger.error(
                                f"Cannot download '{node_info.name}': "
                                f"no CDN package and no repository URL"
                            )
                            return None
                    else:
                        download_and_extract_archive(node_info.download_url, temp_path)
                elif node_info.source == "git":
                    if not node_info.repository:
                        logger.error(f"No repository URL for git node '{node_info.name}'")
                        return None
                    ref = node_info.version if node_info.version else None
                    git_clone(node_info.repository, temp_path, depth=1, ref=ref, timeout=30)
                else:
                    logger.error(f"Unsupported source: '{node_info.source}'")
                    return None

                # Cache it
                logger.info(f"Caching node '{node_info.name}'")
                return self.custom_node_cache.cache_node(node_info, temp_path)

            except Exception as e:
                logger.error(f"Failed to download node '{node_info.name}': {e}")
                return None

    def search_nodes(self, query: str, limit: int = 10) -> list[NodeInfo] | None:
        """Search for nodes in the registry.

        Args:
            query: Search term
            limit: Maximum results

        Returns:
            List of matching NodeInfo objects or None
        """
        try:
            nodes = self.registry_client.search_nodes(query)
            if nodes:
                return [NodeInfo.from_registry_node(node) for node in nodes[:limit]]
        except CDRegistryError as e:
            logger.warning(f"Failed to search registry: {e}")
        return None
