# managers/node_manager.py
from __future__ import annotations

from pathlib import Path
import shutil
from typing import TYPE_CHECKING

from ..logging.logging_config import get_logger
from ..managers.pyproject_manager import PyprojectManager
from ..validation.resolution_tester import ResolutionTester
from ..managers.uv_project_manager import UVProjectManager
from ..models.exceptions import (
    CDEnvironmentError,
    CDNodeConflictError,
    CDNodeNotFoundError,
    NodeAction,
    NodeConflictContext,
)
from ..models.shared import NodePackage, UpdateResult, NodeRemovalResult
from ..resolvers.global_node_resolver import GlobalNodeResolver
from ..services.node_lookup_service import NodeLookupService
from ..models.shared import NodeInfo
from ..strategies.confirmation import ConfirmationStrategy, AutoConfirmStrategy
from ..utils.dependency_parser import parse_dependency_string

if TYPE_CHECKING:
    from ..services.registry_data_manager import RegistryDataManager

logger = get_logger(__name__)


class NodeManager:
    """Manages all node operations for an environment."""

    def __init__(
        self,
        pyproject: PyprojectManager,
        uv: UVProjectManager,
        node_lookup: NodeLookupService,
        resolution_tester: ResolutionTester,
        custom_nodes_path: Path,
        registry_data_manager: RegistryDataManager
    ):
        self.pyproject = pyproject
        self.uv = uv
        self.node_lookup = node_lookup
        self.resolution_tester = resolution_tester
        self.custom_nodes_path = custom_nodes_path
        self.registry_data_manager = registry_data_manager

        # Initialize global resolver for GitHub URL → Registry ID mapping
        node_mapper_path = self.registry_data_manager.get_mappings_path()
        self.global_resolver = GlobalNodeResolver(node_mapper_path)

    def _find_node_by_name(self, name: str) -> tuple[str, NodeInfo] | None:
        """Find a node by name across all identifiers (case-insensitive).

        Returns:
            Tuple of (identifier, node_info) if found, None otherwise
        """
        existing_nodes = self.pyproject.nodes.get_existing()
        name_lower = name.lower()
        for identifier, node_info in existing_nodes.items():
            if node_info.name.lower() == name_lower:
                return identifier, node_info
        return None

    def add_node_package(self, node_package: NodePackage) -> None:
        """Add a complete node package with requirements and source tracking.

        This is the low-level method for adding pre-prepared node packages.
        """
        # Check for duplicates by name (regardless of identifier)
        existing = self._find_node_by_name(node_package.name)
        if existing:
            existing_id, existing_node = existing
            node_type = "development" if existing_node.version == 'dev' else "regular"

            context = NodeConflictContext(
                conflict_type='already_tracked',
                node_name=node_package.name,
                existing_identifier=existing_id,
                is_development=(existing_node.version == 'dev'),
                suggested_actions=[
                    NodeAction(
                        action_type='remove_node',
                        node_identifier=existing_id,
                        description=f"Remove existing {node_type} node"
                    )
                ]
            )

            raise CDNodeConflictError(
                f"Node '{node_package.name}' already exists as {node_type} node (identifier: '{existing_id}')",
                context=context
            )

        # Snapshot sources before processing
        existing_sources = self.pyproject.uv_config.get_source_names()

        # Generate collision-resistant group name for UV dependencies
        group_name = self.pyproject.nodes.generate_group_name(
            node_package.node_info, node_package.identifier
        )

        # Add requirements if any
        if node_package.requirements:
            self.uv.add_requirements_with_sources(
                node_package.requirements, group=group_name, no_sync=True, raw=True
            )

        # Detect new sources after processing
        current_sources = self.pyproject.uv_config.get_source_names()
        new_sources = current_sources - existing_sources

        # Update node with detected sources
        if new_sources:
            node_package.node_info.dependency_sources = sorted(new_sources)

        # Store node configuration
        self.pyproject.nodes.add(node_package.node_info, node_package.identifier)

    def add_node(
        self,
        identifier: str,
        is_local: bool = False,
        is_development: bool = False,
        no_test: bool = False,
        force: bool = False,
    ) -> NodeInfo:
        """Add a custom node to the environment.

        Args:
            identifier: Registry ID or GitHub URL of the node
            is_local: If the node is installed locally
            is_development: If the node is a development node
            no_test: Skip testing the node

        Raises:
            CDNodeNotFoundError: If node not found
            CDNodeConflictError: If node has dependency conflicts
            CDEnvironmentError: If node with same name already exists
        """
        logger.info(f"Adding node: {identifier}")

        # Handle development nodes
        if is_development:
            return self._add_development_node(identifier)

        # Check for existing installation by registry ID (if GitHub URL provided)
        registry_id = None
        github_url = None

        if self._is_github_url(identifier):
            github_url = identifier
            # Try to resolve GitHub URL to registry ID
            if resolved := self.global_resolver.resolve_github_url(identifier):
                registry_id = resolved.id
                logger.info(f"Resolved GitHub URL to registry ID: {registry_id}")

                # Check if already installed by registry ID, if so use existing info
                if existing_info := self._get_existing_node_by_registry_id(registry_id):
                    return NodeInfo(
                        name=existing_info.get('name', registry_id),
                        registry_id=registry_id,
                        version=existing_info.get('version'),
                        repository=existing_info.get('repository'),
                        source=existing_info.get('source', 'unknown')
                    )
            else:
                # TODO: Do we require all nodes to be published on the Registry? Even if they're on Github?
                logger.warning(f"Could not resolve GitHub URL to registry ID: {identifier}")
                raise CDNodeNotFoundError(identifier)
        else:
            # Check for existing installation by registry ID
            registry_id = identifier

        # Get node info from lookup service
        node_info = self.node_lookup.get_node(identifier)

        # Enhance with dual-source information if available
        if github_url and registry_id:
            node_info.registry_id = registry_id
            node_info.repository = github_url
            logger.info(f"Enhanced node info with dual sources: registry_id={registry_id}, github_url={github_url}")

        # Check for filesystem conflicts before proceeding
        if not force:
            has_conflict, conflict_msg, conflict_context = self._check_filesystem_conflict(
                node_info.name,
                expected_repo_url=node_info.repository
            )
            if has_conflict:
                raise CDNodeConflictError(conflict_msg, context=conflict_context)

        # Check for .disabled version of this node and clean it up
        disabled_path = self.custom_nodes_path / f"{node_info.name}.disabled"
        if disabled_path.exists():
            logger.info(f"Removing old disabled version of {node_info.name}")
            shutil.rmtree(disabled_path)

        # Download to cache and copy to custom_nodes
        cache_path = self.node_lookup.download_to_cache(node_info)
        if not cache_path:
            raise CDEnvironmentError(f"Failed to download node '{node_info.name}'")

        # Copy from cache to custom_nodes
        target_path = self.custom_nodes_path / node_info.name
        shutil.copytree(cache_path, target_path, dirs_exist_ok=True)
        logger.info(f"Installed node '{node_info.name}' to {target_path}")

        # Scan requirements from installed directory
        requirements = self.node_lookup.scan_requirements(target_path)

        # Create node package
        node_package = NodePackage(node_info=node_info, requirements=requirements)

        # Add to pyproject with all complexity handled internally
        try:
            self.add_node_package(node_package)
        except Exception as e:
            # Re-raise as CDEnvironmentError for consistency
            if "already exists" in str(e):
                raise CDEnvironmentError(str(e))
            raise

        # Test resolution if requested (extraction happens later after sync)
        if not no_test:
            resolution_result = self.resolution_tester.test_resolution(self.pyproject.path)
            if not resolution_result.success:
                raise CDNodeConflictError(
                    f"Node '{node_package.name}' has dependency conflicts: "
                    f"{self.resolution_tester.format_conflicts(resolution_result)}"
                )

        # Sync Python environment to install new dependencies (matches remove behavior)
        self.uv.sync_project(all_groups=True)

        logger.info(f"Successfully added node '{node_package.name}'")
        return node_package.node_info

    def remove_node(self, identifier: str):
        """Remove a custom node by identifier or name (case-insensitive).

        Handles filesystem changes imperatively based on node type:
        - Development nodes: Renamed to .disabled suffix (preserved)
        - Registry/Git nodes: Deleted from filesystem (cached globally)

        Returns:
            NodeRemovalResult: Details about the removal

        Raises:
            CDNodeNotFoundError: If node not found
        """
        existing_nodes = self.pyproject.nodes.get_existing()
        identifier_lower = identifier.lower()

        # Try case-insensitive identifier lookup
        actual_identifier = None
        removed_node = None

        for key, node in existing_nodes.items():
            if key.lower() == identifier_lower:
                actual_identifier = key
                removed_node = node
                break

        if not actual_identifier:
            # Try name-based lookup as fallback
            found = self._find_node_by_name(identifier)
            if found:
                actual_identifier, removed_node = found
            else:
                raise CDNodeNotFoundError(f"Node '{identifier}' not found in environment")

        # At this point both must be set
        assert actual_identifier is not None
        assert removed_node is not None

        # Determine node type and filesystem action
        is_development = removed_node.source == 'development'
        node_path = self.custom_nodes_path / removed_node.name

        # Handle filesystem imperatively
        filesystem_action = "none"
        if node_path.exists():
            if is_development:
                # Preserve development node with .disabled suffix
                disabled_path = self.custom_nodes_path / f"{removed_node.name}.disabled"

                # Handle existing .disabled directory (backup with timestamp BEFORE .disabled)
                if disabled_path.exists():
                    import time
                    backup_path = self.custom_nodes_path / f"{removed_node.name}.{int(time.time())}.disabled"
                    shutil.move(disabled_path, backup_path)
                    logger.info(f"Backed up old .disabled to {backup_path.name}")

                shutil.move(node_path, disabled_path)
                filesystem_action = "disabled"
                logger.info(f"Disabled development node: {removed_node.name}")
            else:
                # Delete registry/git node (cached globally, can re-download)
                shutil.rmtree(node_path)
                filesystem_action = "deleted"
                logger.info(f"Removed {removed_node.name} (cached, can reinstall)")

        # Remove from pyproject.toml
        removed = self.pyproject.nodes.remove(actual_identifier)
        if not removed:
            raise CDNodeNotFoundError(f"Node '{identifier}' not found in environment")

        # Clean up orphaned UV sources for registry/git nodes
        if not is_development:
            removed_sources = removed_node.dependency_sources or []
            self.pyproject.uv_config.cleanup_orphaned_sources(removed_sources)

        # Sync Python environment to remove orphaned packages (matches add behavior)
        self.uv.sync_project(all_groups=True)

        logger.info(f"Removed node '{actual_identifier}' from tracking")

        return NodeRemovalResult(
            identifier=actual_identifier,
            name=removed_node.name,
            source=removed_node.source,
            filesystem_action=filesystem_action
        )

    def sync_nodes_to_filesystem(self):
        """Sync custom nodes directory to match expected state from pyproject.toml.

        Strategy:
        - Install missing registry/git nodes
        - Warn about extra nodes (user should add with --dev or remove manually)

        Note: This is for manual sync, not rollback. Rollback has its own reconciliation.
        """
        import shutil

        logger.info("Syncing custom nodes to filesystem...")

        # Ensure directory exists
        self.custom_nodes_path.mkdir(exist_ok=True)

        # Get expected nodes from pyproject.toml
        expected_nodes = self.pyproject.nodes.get_existing()

        # Get existing active nodes (not .disabled)
        existing_nodes = {
            d.name: d for d in self.custom_nodes_path.iterdir()
            if d.is_dir() and not d.name.endswith('.disabled')
        }

        expected_names = {info.name for info in expected_nodes.values()}
        untracked = set(existing_nodes.keys()) - expected_names

        # Warn about extra nodes (don't auto-delete during manual sync)
        for node_name in untracked:
            logger.warning(f"Untracked node found: {node_name}")
            logger.warning(f"  Run 'comfydock node add {node_name} --dev' to track it")

        # Install missing registry/git nodes
        for node_info in expected_nodes.values():
            # Skip development nodes - they're already on disk
            if node_info.source == 'development':
                node_path = self.custom_nodes_path / node_info.name
                if not node_path.exists():
                    logger.warning(f"Dev node '{node_info.name}' expected but missing from filesystem")
                continue

            node_path = self.custom_nodes_path / node_info.name
            if not node_path.exists():
                logger.info(f"Installing missing node: {node_info.name}")
                try:
                    # Download to cache
                    cache_path = self.node_lookup.download_to_cache(node_info)
                    if cache_path:
                        shutil.copytree(cache_path, node_path, dirs_exist_ok=True)
                        logger.info(f"Successfully installed node: {node_info.name}")
                    else:
                        logger.warning(f"Could not download node '{node_info.name}'")
                except Exception as e:
                    logger.warning(f"Could not download node '{node_info.name}': {e}")

        logger.info("Finished syncing custom nodes")

    def reconcile_nodes_for_rollback(self, old_nodes: dict[str, NodeInfo], new_nodes: dict[str, NodeInfo]):
        """Reconcile filesystem nodes after rollback with full context.

        Args:
            old_nodes: Nodes that were in pyproject before rollback
            new_nodes: Nodes that are in pyproject after rollback
        """
        import shutil
        import time

        # Nodes that were removed (in old, not in new)
        removed_node_names = set(old_nodes.keys()) - set(new_nodes.keys())

        for identifier in removed_node_names:
            old_node_info = old_nodes[identifier]
            node_path = self.custom_nodes_path / old_node_info.name

            if not node_path.exists():
                continue  # Already gone

            # We KNOW what type it was from old_nodes - no guessing needed!
            if old_node_info.source == 'development':
                # Dev node - preserve with .disabled suffix
                disabled_path = self.custom_nodes_path / f"{old_node_info.name}.disabled"

                # Handle existing .disabled directory (backup with timestamp)
                if disabled_path.exists():
                    backup_path = self.custom_nodes_path / f"{old_node_info.name}.{int(time.time())}.disabled"
                    shutil.move(disabled_path, backup_path)
                    logger.info(f"Backed up old .disabled to {backup_path.name}")

                shutil.move(node_path, disabled_path)
                logger.info(f"Disabled dev node '{old_node_info.name}' (rollback)")
            else:
                # Registry/git node - delete it (cached globally, can reinstall)
                shutil.rmtree(node_path)
                logger.info(f"Removed '{old_node_info.name}' (rollback, cached)")

        # Nodes that were added (in new, not in old)
        added_node_identifiers = set(new_nodes.keys()) - set(old_nodes.keys())

        for identifier in added_node_identifiers:
            new_node_info = new_nodes[identifier]
            node_path = self.custom_nodes_path / new_node_info.name

            if node_path.exists():
                continue  # Already present

            # Install the node (skip dev nodes - user manages those)
            if new_node_info.source != 'development':
                logger.info(f"Installing '{new_node_info.name}' (rollback)")
                try:
                    cache_path = self.node_lookup.download_to_cache(new_node_info)
                    if cache_path:
                        shutil.copytree(cache_path, node_path, dirs_exist_ok=True)
                        logger.info(f"Successfully installed '{new_node_info.name}'")
                    else:
                        logger.warning(f"Could not download '{new_node_info.name}'")
                except Exception as e:
                    logger.warning(f"Failed to install '{new_node_info.name}': {e}")

    def _is_github_url(self, identifier: str) -> bool:
        """Check if identifier is a GitHub URL."""
        return identifier.startswith(('https://github.com/', 'git@github.com:', 'ssh://git@github.com/'))

    def _get_existing_node_by_registry_id(self, registry_id: str) -> dict:
        """Get existing node configuration by registry ID."""
        existing_nodes = self.pyproject.nodes.get_existing()
        for node_info in existing_nodes.values():
            if hasattr(node_info, 'registry_id') and node_info.registry_id == registry_id:
                return {
                    'name': node_info.name,
                    'registry_id': node_info.registry_id,
                    'version': node_info.version,
                    'repository': node_info.repository,
                    'source': node_info.source
                }
        return {}

    def _check_filesystem_conflict(
        self,
        node_name: str,
        expected_repo_url: str | None = None
    ) -> tuple[bool, str, NodeConflictContext | None]:
        """Check if node directory exists and might conflict.

        Args:
            node_name: Name of the node directory
            expected_repo_url: Expected repository URL (for comparison)

        Returns:
            (has_conflict, conflict_message, context)
        """
        node_path = self.custom_nodes_path / node_name

        if not node_path.exists():
            return False, "", None

        # Check if it's a git repo
        git_dir = node_path / '.git'
        if not git_dir.exists():
            context = NodeConflictContext(
                conflict_type='directory_exists_non_git',
                node_name=node_name,
                filesystem_path=str(node_path),
                suggested_actions=[
                    NodeAction(
                        action_type='add_node_dev',
                        node_name=node_name,
                        description="Track existing directory as development node"
                    ),
                    NodeAction(
                        action_type='add_node_force',
                        node_identifier='<identifier>',
                        description="Force replace existing directory"
                    )
                ]
            )
            msg = f"Directory '{node_name}' already exists in custom_nodes/"
            return True, msg, context

        # Get remote URL
        from ..utils.git import git_remote_get_url
        local_remote = git_remote_get_url(node_path)

        if not local_remote:
            context = NodeConflictContext(
                conflict_type='directory_exists_no_remote',
                node_name=node_name,
                filesystem_path=str(node_path),
                suggested_actions=[
                    NodeAction(
                        action_type='add_node_dev',
                        node_name=node_name,
                        description="Track local git repository as development node"
                    ),
                    NodeAction(
                        action_type='add_node_force',
                        node_identifier='<identifier>',
                        description="Replace with registry version"
                    )
                ]
            )
            msg = f"Git repository '{node_name}' exists locally (no remote)"
            return True, msg, context

        # Compare URLs if we have expected URL
        if expected_repo_url:
            if self._same_repository(local_remote, expected_repo_url):
                context = NodeConflictContext(
                    conflict_type='same_repo_exists',
                    node_name=node_name,
                    local_remote_url=local_remote,
                    expected_remote_url=expected_repo_url,
                    suggested_actions=[
                        NodeAction(
                            action_type='add_node_dev',
                            node_name=node_name,
                            description="Track existing git clone as development node"
                        ),
                        NodeAction(
                            action_type='add_node_force',
                            node_identifier='<identifier>',
                            description="Re-download from registry (replaces local)"
                        )
                    ]
                )
                msg = f"Git clone of '{node_name}' already exists"
                return True, msg, context
            else:
                context = NodeConflictContext(
                    conflict_type='different_repo_exists',
                    node_name=node_name,
                    local_remote_url=local_remote,
                    expected_remote_url=expected_repo_url,
                    suggested_actions=[
                        NodeAction(
                            action_type='rename_directory',
                            directory_name=node_name,
                            new_name=f"{node_name}-fork",
                            description="Rename your fork to avoid conflict"
                        ),
                        NodeAction(
                            action_type='add_node_force',
                            node_identifier='<identifier>',
                            description="Replace with registry version (deletes yours)"
                        )
                    ]
                )
                msg = f"Repository conflict for '{node_name}'"
                return True, msg, context

        # Have git repo but no expected URL to compare
        context = NodeConflictContext(
            conflict_type='directory_exists_no_remote',
            node_name=node_name,
            local_remote_url=local_remote,
            suggested_actions=[
                NodeAction(
                    action_type='add_node_dev',
                    node_name=node_name,
                    description="Track as development node"
                ),
                NodeAction(
                    action_type='add_node_force',
                    node_identifier='<identifier>',
                    description="Force replace"
                )
            ]
        )
        msg = f"Git repository '{node_name}' already exists"
        return True, msg, context

    @staticmethod
    def _same_repository(url1: str, url2: str) -> bool:
        """Check if two git URLs refer to the same repository.

        Normalizes various URL formats for comparison.
        """
        import re

        def normalize(url: str) -> str:
            # Remove .git suffix
            url = url.rstrip('/')
            if url.endswith('.git'):
                url = url[:-4]

            # Convert to https format for comparison
            url = re.sub(r'^git@([^:]+):', r'https://\1/', url)
            url = re.sub(r'^ssh://git@([^/]+)/', r'https://\1/', url)

            return url.lower().rstrip('/')

        return normalize(url1) == normalize(url2)

    def _add_development_node(self, identifier: str) -> NodeInfo:
        """Add a development node - downloads if needed, then tracks."""
        # Try to find existing directory (case-insensitive)
        node_path = None
        node_name: str | None = None

        # Check if identifier is a simple name (not URL)
        if not self._is_github_url(identifier):
            # Look for existing directory
            for item in self.custom_nodes_path.iterdir():
                if item.is_dir() and item.name.lower() == identifier.lower():
                    node_path = item
                    node_name = item.name
                    logger.info(f"Found existing node directory: {node_name}")
                    break

        # If not found locally, download it
        if not node_path:
            logger.info(f"Node not found locally, downloading: {identifier}")

            # Get node info from lookup service
            try:
                node_info = self.node_lookup.get_node(identifier)
            except CDNodeNotFoundError:
                # Not in registry either - provide helpful error
                if self._is_github_url(identifier):
                    raise CDNodeNotFoundError(
                        f"Cannot download from GitHub URL: {identifier}\n"
                        f"Ensure the URL is accessible and correctly formatted"
                    )
                else:
                    raise CDNodeNotFoundError(
                        f"Node '{identifier}' not found in registry or filesystem.\n"
                        f"Provide a GitHub URL or ensure the directory exists in custom_nodes/"
                    )

            node_name = node_info.name
            node_path = self.custom_nodes_path / node_name

            # Download to cache and copy to filesystem 
            logger.info(f"Downloading node '{node_name}' to {node_path}")
            cache_path = self.node_lookup.download_to_cache(node_info)
            if not cache_path:
                raise CDEnvironmentError(f"Failed to download node '{node_name}'")
            shutil.copytree(cache_path, node_path, dirs_exist_ok=True)

        # At this point node_name and node_path must be set
        assert node_name is not None, "node_name should be set by now"
        assert node_path is not None, "node_path should be set by now"

        # Check for duplicate tracking
        existing = self._find_node_by_name(node_name)
        if existing:
            existing_id, existing_node = existing
            if existing_node.version == 'dev':
                logger.info(f"Development node '{node_name}' already tracked")
                return existing_node
            else:
                context = NodeConflictContext(
                    conflict_type='already_tracked',
                    node_name=node_name,
                    existing_identifier=existing_id,
                    is_development=False,
                    suggested_actions=[
                        NodeAction(
                            action_type='remove_node',
                            node_identifier=existing_id,
                            description="Remove existing regular node first"
                        )
                    ]
                )
                raise CDNodeConflictError(
                    f"Node '{node_name}' already tracked as regular node (identifier: '{existing_id}')",
                    context=context
                )

        # Scan for requirements
        requirements = self.node_lookup.scan_requirements(node_path)

        # Create as development node
        node_info = NodeInfo(name=node_name, version='dev', source='development')
        node_package = NodePackage(node_info=node_info, requirements=requirements)

        # Add to pyproject
        self.add_node_package(node_package)

        logger.info(f"Successfully added development node: {node_name}")
        return node_info

    def update_node(
        self,
        identifier: str,
        confirmation_strategy: ConfirmationStrategy | None = None,
        no_test: bool = False
    ) -> UpdateResult:
        """Update a node based on its source type.

        Args:
            identifier: Node identifier or name
            confirmation_strategy: Strategy for confirming updates (None = auto-confirm)
            no_test: Skip resolution testing (dev nodes only)

        Returns:
            UpdateResult with details of what changed

        Raises:
            CDNodeNotFoundError: If node not found
            CDEnvironmentError: If node cannot be updated
        """
        # Default to auto-confirm if no strategy provided
        if confirmation_strategy is None:
            confirmation_strategy = AutoConfirmStrategy()

        # Get current node info
        nodes = self.pyproject.nodes.get_existing()
        node_info = None
        actual_identifier = None

        # Try direct identifier lookup first
        if identifier in nodes:
            node_info = nodes[identifier]
            actual_identifier = identifier
        else:
            # Try name-based lookup
            found = self._find_node_by_name(identifier)
            if found:
                actual_identifier, node_info = found

        if not node_info or not actual_identifier:
            raise CDNodeNotFoundError(f"Node '{identifier}' not found")

        # Dispatch based on source type
        if node_info.source == 'development':
            return self._update_development_node(actual_identifier, node_info, no_test)
        elif node_info.source == 'registry':
            return self._update_registry_node(actual_identifier, node_info, confirmation_strategy, no_test)
        elif node_info.source == 'git':
            return self._update_git_node(actual_identifier, node_info, confirmation_strategy, no_test)
        else:
            raise CDEnvironmentError(f"Unknown node source: {node_info.source}")

    def _update_development_node(self, identifier: str, node_info: NodeInfo, no_test: bool) -> UpdateResult:
        """Update dev node by re-scanning requirements."""
        result = UpdateResult(node_name=node_info.name, source='development')

        # Scan current requirements
        node_path = self.custom_nodes_path / node_info.name
        if not node_path.exists():
            raise CDNodeNotFoundError(f"Dev node directory not found: {node_path}")

        current_reqs = self.node_lookup.scan_requirements(node_path)

        # Get stored requirements from dependency group
        group_name = self.pyproject.nodes.generate_group_name(node_info, identifier)
        stored_groups = self.pyproject.dependencies.get_groups()
        stored_reqs = stored_groups.get(group_name, [])

        # Normalize for comparison (compare package names only)
        current_names = {parse_dependency_string(r)[0] for r in current_reqs}
        stored_names = {parse_dependency_string(r)[0] for r in stored_reqs}

        added = current_names - stored_names
        removed = stored_names - current_names

        if not added and not removed:
            result.message = "No requirement changes detected"
            return result

        # Update requirements
        existing_sources = self.pyproject.uv_config.get_source_names()

        if current_reqs:
            self.uv.add_requirements_with_sources(
                current_reqs, group=group_name, no_sync=True, raw=True
            )
        else:
            # No requirements - remove group
            self.pyproject.dependencies.remove_group(group_name)

        # Detect new sources
        new_sources = self.pyproject.uv_config.get_source_names() - existing_sources
        if new_sources:
            node_info.dependency_sources = sorted(new_sources)
            self.pyproject.nodes.add(node_info, identifier)

        # Test resolution if requested
        if not no_test:
            resolution_result = self.resolution_tester.test_resolution(self.pyproject.path)
            if not resolution_result.success:
                raise CDNodeConflictError(
                    f"Updated requirements for '{node_info.name}' have conflicts: "
                    f"{self.resolution_tester.format_conflicts(resolution_result)}"
                )

        result.requirements_added = list(added)
        result.requirements_removed = list(removed)
        result.changed = True
        result.message = f"Updated requirements: +{len(added)} -{len(removed)}"

        # Sync Python environment to apply requirement changes (matches add/remove behavior)
        self.uv.sync_project(all_groups=True)

        logger.info(f"Updated dev node '{node_info.name}': {result.message}")
        return result

    def _update_registry_node(
        self,
        identifier: str,
        node_info: NodeInfo,
        confirmation_strategy: ConfirmationStrategy,
        no_test: bool
    ) -> UpdateResult:
        """Update registry node to latest version."""
        result = UpdateResult(node_name=node_info.name, source='registry')

        if not node_info.registry_id:
            raise CDEnvironmentError(f"Node '{node_info.name}' has no registry_id")

        # Query registry for latest version
        try:
            registry_node = self.node_lookup.registry_client.get_node(node_info.registry_id)
        except Exception as e:
            result.message = f"Failed to check for updates: {e}"
            return result

        if not registry_node or not registry_node.latest_version:
            result.message = "No updates available (registry unavailable)"
            return result

        latest_version = registry_node.latest_version.version
        current_version = node_info.version or "unknown"

        if latest_version == current_version:
            result.message = f"Already at latest version ({current_version})"
            return result

        # Confirm update using strategy
        if not confirmation_strategy.confirm_update(node_info.name, current_version, latest_version):
            result.message = "Update cancelled by user"
            return result

        # Remove old node
        self.remove_node(identifier)

        # Add new version
        self.add_node(node_info.registry_id, no_test=no_test)

        result.old_version = current_version
        result.new_version = latest_version
        result.changed = True
        result.message = f"Updated from {current_version} → {latest_version}"

        logger.info(f"Updated registry node '{node_info.name}': {result.message}")
        return result

    def _update_git_node(
        self,
        identifier: str,
        node_info: NodeInfo,
        confirmation_strategy: ConfirmationStrategy,
        no_test: bool
    ) -> UpdateResult:
        """Update git node to latest commit."""
        result = UpdateResult(node_name=node_info.name, source='git')

        if not node_info.repository:
            raise CDEnvironmentError(f"Node '{node_info.name}' has no repository URL")

        # Query GitHub for latest commit
        try:
            repo_info = self.node_lookup.github_client.get_repository_info(node_info.repository)
        except Exception as e:
            result.message = f"Failed to check for updates: {e}"
            return result

        if not repo_info:
            result.message = "Failed to get repository information"
            return result

        latest_commit = repo_info.latest_commit
        current_commit = node_info.version or "unknown"

        # Format for display
        current_display = current_commit[:8] if current_commit != "unknown" else "unknown"
        latest_display = latest_commit[:8] if latest_commit else "unknown"

        if latest_commit == current_commit:
            result.message = f"Already at latest commit ({current_display})"
            return result

        # Confirm update using strategy (pass formatted versions for display)
        if not confirmation_strategy.confirm_update(node_info.name, current_display, latest_display):
            result.message = "Update cancelled by user"
            return result

        # Remove old node
        self.remove_node(identifier)

        # Add new version
        self.add_node(node_info.repository, no_test=no_test)

        result.old_version = current_display
        result.new_version = latest_display
        result.changed = True
        result.message = f"Updated to latest commit ({latest_display})"

        logger.info(f"Updated git node '{node_info.name}': {result.message}")
        return result

    def check_development_node_drift(self) -> dict[str, tuple[set[str], set[str]]]:
        """Check if dev nodes have requirements drift.

        Returns:
            Dict mapping node_name -> (added_deps, removed_deps)
        """
        drift = {}
        nodes = self.pyproject.nodes.get_existing()

        for identifier, node_info in nodes.items():
            if node_info.source != 'development':
                continue

            node_path = self.custom_nodes_path / node_info.name
            if not node_path.exists():
                continue

            # Scan current requirements
            current_reqs = self.node_lookup.scan_requirements(node_path)

            # Get stored requirements from dependency group
            group_name = self.pyproject.nodes.generate_group_name(node_info, identifier)
            stored_groups = self.pyproject.dependencies.get_groups()
            stored_reqs = stored_groups.get(group_name, [])

            # Compare package names
            current_names = {parse_dependency_string(r)[0] for r in current_reqs}
            stored_names = {parse_dependency_string(r)[0] for r in stored_reqs}

            added = current_names - stored_names
            removed = stored_names - current_names

            if added or removed:
                drift[node_info.name] = (added, removed)

        return drift
