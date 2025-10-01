# managers/node_manager.py
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ..logging.logging_config import get_logger
from ..managers.pyproject_manager import PyprojectManager
from ..validation.resolution_tester import ResolutionTester
from ..managers.uv_project_manager import UVProjectManager
from ..models.exceptions import (
    CDEnvironmentError,
    CDNodeConflictError,
    CDNodeNotFoundError,
)
from ..models.shared import NodePackage, UpdateResult
from ..resolvers.global_node_resolver import GlobalNodeResolver
from ..services.node_registry import NodeInfo, NodeRegistry
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
        node_registry: NodeRegistry,
        resolution_tester: ResolutionTester,
        custom_nodes_path: Path,
        registry_data_manager: RegistryDataManager
    ):
        self.pyproject = pyproject
        self.uv = uv
        self.node_registry = node_registry
        self.resolution_tester = resolution_tester
        self.custom_nodes_path = custom_nodes_path
        self.registry_data_manager = registry_data_manager

        # Initialize global resolver for GitHub URL → Registry ID mapping
        node_mapper_path = self.registry_data_manager.get_mappings_path()
        self.global_resolver = GlobalNodeResolver(node_mapper_path)

    def _find_node_by_name(self, name: str) -> tuple[str, NodeInfo] | None:
        """Find a node by name across all identifiers.

        Returns:
            Tuple of (identifier, node_info) if found, None otherwise
        """
        existing_nodes = self.pyproject.nodes.get_existing()
        for identifier, node_info in existing_nodes.items():
            if node_info.name == name:
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
            raise CDEnvironmentError(
                f"Node '{node_package.name}' already exists as {node_type} node (identifier: '{existing_id}'). "
                f"Remove it first: comfydock node remove {existing_id}"
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

        # Get complete node package from NodeRegistry
        node_package = self.node_registry.prepare_node(identifier, is_local)

        # Enhance with dual-source information if available
        if github_url and registry_id:
            node_package.node_info.registry_id = registry_id
            node_package.node_info.repository = github_url
            logger.info(f"Enhanced node info with dual sources: registry_id={registry_id}, github_url={github_url}")

        # Check for .disabled version of this node and clean it up
        disabled_path = self.custom_nodes_path / f"{node_package.name}.disabled"
        if disabled_path.exists():
            import shutil
            logger.info(f"Removing old disabled version of {node_package.name}")
            shutil.rmtree(disabled_path)

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

        logger.info(f"Successfully added node '{node_package.name}'")
        return node_package.node_info

    def remove_node(self, identifier: str):
        """Remove a custom node by identifier or name.

        Raises:
            CDNodeNotFoundError: If node not found
        """
        # First try direct identifier lookup
        existing_nodes = self.pyproject.nodes.get_existing()
        if identifier in existing_nodes:
            actual_identifier = identifier
            removed_node = existing_nodes[identifier]
        else:
            # Try name-based lookup as fallback
            found = self._find_node_by_name(identifier)
            if found:
                actual_identifier, removed_node = found
            else:
                raise CDNodeNotFoundError(f"Node '{identifier}' not found in environment")

        # Check if it's a development node
        is_development = removed_node.version == 'dev'

        # Remove the node
        removed = self.pyproject.nodes.remove(actual_identifier)

        if not removed:
            raise CDNodeNotFoundError(f"Node '{identifier}' not found in environment")

        if is_development:
            logger.info(f"Removed development node '{actual_identifier}' from tracking")
            print(f"ℹ️ Development node '{removed_node.name}' removed from tracking (files preserved)")
        else:
            # Clean up orphaned sources for registry nodes
            removed_sources = removed_node.dependency_sources or []
            self.pyproject.uv_config.cleanup_orphaned_sources(removed_sources)
            logger.info(f"Removed node '{actual_identifier}' from environment")

    def sync_nodes_to_filesystem(self):
        """Sync custom nodes directory to match expected state from pyproject.toml."""
        # Get expected nodes from pyproject.toml
        pyproject_config = self.pyproject.load()
        expected_nodes = self.node_registry.parse_expected_nodes(pyproject_config)

        # Always sync to filesystem, even with empty dict (to remove unwanted nodes)
        self.node_registry.sync_nodes_to_filesystem(expected_nodes, self.custom_nodes_path)

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

    def _add_development_node(self, identifier: str) -> NodeInfo:
        """Add a development node by discovering it in the custom_nodes directory."""
        # Look for existing directory
        node_path = self.custom_nodes_path / identifier

        if not node_path.exists() or not node_path.is_dir():
            # Try case-insensitive search
            for item in self.custom_nodes_path.iterdir():
                if item.is_dir() and item.name.lower() == identifier.lower():
                    node_path = item
                    identifier = item.name  # Use actual directory name
                    break
            else:
                raise CDNodeNotFoundError(
                    f"Development node directory '{identifier}' not found in {self.custom_nodes_path}"
                )

        # Check for duplicate by name (dev and regular nodes can have different identifiers)
        existing = self._find_node_by_name(identifier)
        if existing:
            existing_id, existing_node = existing
            if existing_node.version == 'dev':
                print(f"⚠️ Development node '{identifier}' is already tracked")
                return existing_node
            else:
                raise CDEnvironmentError(
                    f"Node '{identifier}' already exists as regular node (identifier: '{existing_id}'). "
                    f"Remove it first: comfydock node remove {existing_id}"
                )

        # Scan for requirements on initial add
        deps = self.node_registry.scanner.scan_node(node_path)
        requirements = deps.requirements or []

        # Create NodePackage to use existing add flow
        node_info = NodeInfo(name=identifier, version='dev', source='development')
        node_package = NodePackage(node_info=node_info, requirements=requirements)

        # Add to pyproject (handles requirements + sources)
        self.add_node_package(node_package)

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

        deps = self.node_registry.scanner.scan_node(node_path)
        current_reqs = deps.requirements or []

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
            registry_node = self.node_registry.registry_client.get_node(node_info.registry_id)
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
            repo_info = self.node_registry.github_client.get_repository_info(node_info.repository)
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
        latest_display = latest_commit[:8]

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
            deps = self.node_registry.scanner.scan_node(node_path)
            current_reqs = deps.requirements or []

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
