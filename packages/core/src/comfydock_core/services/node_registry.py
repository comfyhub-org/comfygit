"""NodeRegistry - Stateless service for finding and analyzing nodes."""

import tempfile
from pathlib import Path

from comfydock_core.models.exceptions import CDNodeNotFoundError, CDRegistryError, ComfyDockError
from comfydock_core.models.shared import NodeInfo, NodePackage

from ..caching import APICacheManager, CustomNodeCacheManager
from ..logging.logging_config import get_logger
from ..analyzers.custom_node_scanner import CustomNodeScanner
from ..utils.download import download_and_extract_archive
from ..utils.git import git_clone
from ..clients import ComfyRegistryClient, GitHubClient

logger = get_logger(__name__)


class NodeRegistry:
    """
    Service for finding nodes and their requirements.
    """

    def __init__(self, workspace_path: Path | None = None, cache_path: Path | None = None):
        """Initialize the node registry service."""
        self.scanner = CustomNodeScanner()
        cache_path = cache_path or (workspace_path / "cache" if workspace_path else None)
        self.api_cache = APICacheManager(cache_base_path=cache_path)
        self.custom_node_cache = CustomNodeCacheManager(cache_base_path=cache_path)
        self.registry_client = ComfyRegistryClient(cache_manager=self.api_cache)
        self.github_client = GitHubClient(cache_manager=self.api_cache)

    def prepare_node(self, identifier: str, is_local: bool = False) -> NodePackage:
        """Prepare a complete node package with info and requirements.
        
        Args:
            identifier: Registry ID, node name, or git URL
            is_local: Whether the node is local
            
        Returns:
            NodePackage with node info and requirements
            
        Raises:
            CDNodeNotFoundError: If node not found
        """
        # Get node info
        node_info = self.get_node(identifier, is_local)

        # Get requirements
        requirements = self.get_node_requirements(node_info) or []

        return NodePackage(node_info=node_info, requirements=requirements)

    def get_node(self, identifier: str, is_local: bool = False) -> NodeInfo:
        """Get a node - raises if not found.
        
        Args:
            identifier: Registry ID, node name, or git URL
            is_local: Whether the node is local
        
        Returns:
            NodeInfo with metadata
            
        Raises:
            CDNodeNotFoundError: If node not found in any source
        """
        node = self.find_node(identifier, is_local)
        if not node:
            # Provide helpful error message
            msg = f"Node '{identifier}' not found"
            if identifier.startswith(('http://', 'https://')) and not identifier.endswith('.git'):
                msg += ". Did you mean to provide a git URL? (should end with .git)"
            elif '/' not in identifier:
                msg += " in registry. Try: 1) Full registry ID, 2) Git URL, or 3) Local path"
            raise CDNodeNotFoundError(msg)
        return node

    def find_node(self, identifier: str, is_local: bool = False) -> NodeInfo | None:
        """Find node info from registry or git URL.

        Args:
            identifier: Registry ID (optionally with @version), node name, or git URL
            is_local: Whether the node is local

        Returns:
            NodeInfo with metadata, or None if not found
        """
        # TODO: Check if it's a local path first

        # Parse version from identifier if present (e.g., "package-id@1.2.3")
        requested_version = None
        if '@' in identifier and not identifier.startswith(('https://', 'git@', 'ssh://')):
            parts = identifier.split('@', 1)
            identifier = parts[0]
            requested_version = parts[1]

        # Check if it's a git URL
        if identifier.startswith(('https://', 'git@', 'ssh://')):
            # Validate git URL
            try:
                if repo_info := self.github_client.get_repository_info(identifier):
                    # Use canonical clone URL for git operations, not the original identifier
                    return NodeInfo(
                        name=repo_info.name,
                        repository=repo_info.clone_url,
                        source="git",
                        version=repo_info.latest_commit
                    )
            except Exception as e:
                logger.warning(f"Invalid git URL: {e}")
                return None

        # Check registry
        try:
            registry_node = self.registry_client.get_node(identifier)
            if registry_node:
                logger.info(f"Found node '{registry_node.name}' in registry: {str(registry_node)}")
                # Use requested version if specified, otherwise use latest
                if requested_version:
                    version = requested_version
                    logger.info(f"Using requested version: {version}")
                else:
                    version = registry_node.latest_version.version if registry_node.latest_version else None
                node_version = self.registry_client.install_node(registry_node.id, version)
                if node_version:
                    registry_node.latest_version = node_version
                return NodeInfo.from_registry_node(registry_node)
        except CDRegistryError as e:
            logger.warning(f"Cannot reach registry: {e}")

        logger.debug(f"Node '{identifier}' not found")
        return None

    def download_node(self, node_info: NodeInfo, target_path: Path) -> None:
        """Download a node to the specified path.
        
        Args:
            node_info: Node information from get_node()
            target_path: Path where the node should be downloaded
            
        Returns:
            None if successful
            
        Raises:
            OSError: If downloading fails
            RuntimeError: If downloading fails
        """

        logger.info(f"Downloading node '{node_info.name}' to {target_path}...")

        # First check custom node cache
        logger.debug(f"Looking at node info: {str(node_info)}")
        cache_path = self.custom_node_cache.get_cached_path(node_info)
        logger.debug(f"Found cached path: {cache_path}")
        if cache_path:
            # Copy from cache to target path
            try:
                import shutil
                if cache_path.is_dir():
                    shutil.copytree(cache_path, target_path, dirs_exist_ok=True)
                else:
                    shutil.copy2(cache_path, target_path)
            except Exception as e:
                logger.warning(f"Failed to copy cached node: {e}")
                raise OSError(f"Failed to copy cached node: {e}")
            return

        # Download the node based on source type
        downloaded = False
        if node_info.source == "registry":
            url = node_info.download_url
            logger.debug(f"Downloading node '{node_info.name}' from URL: {url}")
            if not url:
                logger.warning(f"No download URL for node '{node_info.name}'")
                raise ComfyDockError(f"No download URL for node '{node_info.name}'")
            try:
                download_and_extract_archive(url, target_path)
                downloaded = True
            except Exception as e:
                logger.warning(f"Failed to download archive for '{node_info.name}'")
                raise ComfyDockError(f"Failed to download archive for '{node_info.name}': {e}")
        elif node_info.source == "git":
            if not node_info.repository:
                logger.warning(f"No repository URL for node '{node_info.name}'")
                return
            try:
                # Pass the version (commit hash) as ref if it's a commit hash
                ref = node_info.version if node_info.version else None
                git_clone(node_info.repository, target_path, depth=1, ref=ref, timeout=30)
                downloaded = True
            except Exception as e:
                logger.warning(f"Failed to clone repository for '{node_info.name}': {e}")
                raise ComfyDockError(f"Failed to clone repository for '{node_info.name}': {e}")
        else:
            logger.warning(f"Unsupported source: '{node_info.source}' for node '{node_info.name}'")
            return

        # Cache the node
        if downloaded:
            logger.debug(f"Caching downloaded node '{node_info.name}'")
            self.custom_node_cache.cache_node(node_info, target_path)

    @staticmethod
    def parse_expected_nodes(pyproject_config: dict) -> dict[str, NodeInfo]:
        """Parse expected nodes from pyproject.toml configuration.

        Args:
            pyproject_config: Loaded pyproject.toml configuration

        Returns:
            Dict of node_name -> NodeInfo for expected nodes
        """
        nodes_config = pyproject_config.get('tool', {}).get('comfydock', {}).get('nodes', {})

        if not nodes_config:
            return {}

        expected_nodes = {}

        # Parse all nodes (development nodes have version='dev')
        for node_identifier, node_data in nodes_config.items():
            node_info = NodeInfo.from_pyproject_config(nodes_config, node_identifier=node_identifier)
            if node_info:
                # Mark as development if version is 'dev'
                if node_info.version == 'dev':
                    node_info.source = 'development'
                expected_nodes[node_info.name] = node_info

        return expected_nodes

    def sync_nodes_to_filesystem(self, expected_nodes: dict[str, NodeInfo], custom_nodes_dir: Path) -> None:
        """Sync custom nodes directory to match expected state.

        Strategy: Delete registry/git nodes (cache ensures recovery), disable dev nodes (preserve user work).

        Args:
            expected_nodes: Dict of node_name -> NodeInfo for expected nodes
            custom_nodes_dir: Path to custom_nodes directory
        """
        import shutil

        logger.info(f"Syncing custom nodes to filesystem (expecting {len(expected_nodes)} nodes)")

        # Ensure directory exists
        custom_nodes_dir.mkdir(exist_ok=True)

        # Get existing active nodes (not .disabled)
        existing_nodes = {
            d.name: d for d in custom_nodes_dir.iterdir()
            if d.is_dir() and not d.name.endswith('.disabled')
        }

        # Nodes to remove (exist but not expected)
        to_remove = set(existing_nodes.keys()) - set(expected_nodes.keys())

        # Remove extra nodes with appropriate strategy
        for node_name in to_remove:
            node_path = existing_nodes[node_name]

            # Try to determine if it was a dev node by checking git history
            # If we can't determine, assume it's not dev (safe default - can re-download)
            is_dev_node = self._check_if_dev_node_from_history(node_name, custom_nodes_dir.parent)

            if is_dev_node:
                # Dev node - preserve with .disabled
                disabled_path = custom_nodes_dir / f"{node_name}.disabled"
                if disabled_path.exists():
                    # Backup existing .disabled
                    import time
                    backup_path = custom_nodes_dir / f"{node_name}.disabled.{int(time.time())}"
                    shutil.move(disabled_path, backup_path)
                    logger.info(f"Backed up old .disabled to {backup_path.name}")

                shutil.move(node_path, disabled_path)
                logger.info(f"Disabled dev node: {node_name}")
            else:
                # Registry/git node - delete (cache ensures we can recover)
                shutil.rmtree(node_path)
                logger.info(f"Removed {node_name} (cached, can reinstall)")

        # Install missing nodes (skip dev nodes - they should already exist)
        for node_name, node_info in expected_nodes.items():
            if not node_info:
                continue

            # Skip development nodes - they're already on disk
            if node_info.source == 'development':
                node_path = custom_nodes_dir / node_name
                if not node_path.exists():
                    logger.warning(f"Dev node '{node_name}' expected but missing from filesystem")
                continue

            node_path = custom_nodes_dir / node_name
            if not node_path.exists():
                logger.debug(f"Installing node: {node_name}")
                try:
                    self.download_node(node_info, node_path)
                    logger.debug(f"Successfully installed node: {node_name}")
                except Exception as e:
                    logger.warning(f"Could not download node '{node_name}': {e}")
            else:
                logger.debug(f"Node already exists: {node_name}")

        logger.debug("Finished syncing custom nodes")

    def _check_if_dev_node_from_history(self, node_name: str, cec_parent: Path) -> bool:
        """Check if a node was tracked as a dev node in the last commit.

        Args:
            node_name: Name of the node
            cec_parent: Parent directory of .cec (environment root)

        Returns:
            True if node was a dev node, False otherwise
        """
        try:
            from ..utils.git import git_show

            cec_path = cec_parent / ".cec"
            if not (cec_path / ".git").exists():
                return False

            # Get pyproject.toml from last commit
            pyproject_content = git_show(cec_path, "HEAD", Path("pyproject.toml"))

            # Parse TOML to check node source
            import tomllib
            config = tomllib.loads(pyproject_content)

            nodes = config.get('tool', {}).get('comfydock', {}).get('nodes', {})
            for identifier, node_data in nodes.items():
                if node_data.get('name') == node_name:
                    return node_data.get('source') == 'development'

            return False
        except Exception as e:
            logger.debug(f"Could not check git history for {node_name}: {e}")
            return False

    def get_node_requirements(self, node_info: NodeInfo) -> list[str] | None:
        """Get requirements for a node by downloading and scanning.
        
        Args:
            node_info: Node information from get_node()
        
        Returns:
            List of requirement strings
        """

        def _scan_node_for_deps(node_path: Path):
            # Scan for requirements
            logger.debug(f"helper: Scanning node '{node_info.name}' for requirements...")
            deps = self.scanner.scan_node(node_path)
            logger.debug(f"helper: Found {deps} requirements for '{node_info.name}'")
            if deps and deps.requirements:
                logger.info(f"Found {len(deps.requirements)} requirements for '{node_info.name}'")
                return deps.requirements
            else:
                logger.info(f"No requirements found for '{node_info.name}'")
                return []

        try:
            # First check custom node cache
            logger.debug(f"Looking at node info: {str(node_info)}")
            cache_path = self.custom_node_cache.get_cached_path(node_info)
            logger.debug(f"Found cached path: {cache_path}")
            if cache_path:
                return _scan_node_for_deps(cache_path)

            # Download to temporary directory for scanning
            with tempfile.TemporaryDirectory() as tmpdir:
                node_path = Path(tmpdir) / "node"

                logger.info(f"Scanning node '{node_info.name}' for requirements...")

                # Use the new download_node method
                self.download_node(node_info, node_path)

                return _scan_node_for_deps(node_path)

        except Exception as e:
            logger.warning(f"Could not scan requirements for '{node_info.name}': {e}")
            return None

    def search_nodes(self, query: str, limit: int = 10) -> list[NodeInfo] | None:
        """Search for nodes in the registry.
        
        Args:
            query: Search term
            limit: Maximum results
        
        Returns:
            List of matching NodeInfo objects or None
        """
        results = []

        # Search registry
        try:
            nodes = self.registry_client.search_nodes(query)
        except CDRegistryError as e:
            logger.warning(f"Failed to search registry: {e}")
            return None

        if nodes:
            for node_data in nodes[:limit]:
                results.append(NodeInfo.from_registry_node(node_data))
            return results

        return None
