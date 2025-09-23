# managers/node_manager.py
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ..logging.logging_config import get_logger
from ..managers.pyproject_manager import PyprojectManager
from ..managers.resolution_tester import ResolutionTester
from ..managers.uv_project_manager import UVProjectManager
from ..models.exceptions import (
    CDEnvironmentError,
    CDNodeConflictError,
    CDNodeNotFoundError,
)
from ..models.shared import NodePackage
from ..services.global_node_resolver import GlobalNodeResolver
from ..services.node_registry import NodeInfo, NodeRegistry

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

    def add_node(self, identifier: str, is_local: bool = False, is_development: bool = False, no_test: bool = False) -> NodeInfo:
        """Add a custom node to the environment.

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
            if self.global_resolver:
                if resolved := self.global_resolver.resolve_github_url(identifier):
                    registry_id, package_data = resolved
                    logger.info(f"Resolved GitHub URL to registry ID: {registry_id}")

                    # Check if already installed by registry ID
                    if self._is_node_installed_by_registry_id(registry_id):
                        existing_info = self._get_existing_node_by_registry_id(registry_id)
                        print(f"✅ Node already installed: {existing_info.get('name', registry_id)} v{existing_info.get('version', 'unknown')}")
                        response = input("Use existing version? (y/N): ").lower().strip()
                        if response == 'y':
                            return NodeInfo(
                                name=existing_info.get('name', registry_id),
                                registry_id=registry_id,
                                version=existing_info.get('version'),
                                repository=existing_info.get('repository'),
                                source=existing_info.get('source', 'unknown')
                            )
        else:
            registry_id = identifier

        # Get complete node package from NodeRegistry
        node_package = self.node_registry.prepare_node(identifier, is_local)

        # Enhance with dual-source information if available
        if github_url and registry_id:
            node_package.node_info.registry_id = registry_id
            node_package.node_info.repository = github_url
            logger.info(f"Enhanced node info with dual sources: registry_id={registry_id}, github_url={github_url}")

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

    def _is_node_installed_by_registry_id(self, registry_id: str) -> bool:
        """Check if a node is already installed by registry ID."""
        existing_nodes = self.pyproject.nodes.get_existing()
        for node_info in existing_nodes.values():
            if hasattr(node_info, 'registry_id') and node_info.registry_id == registry_id:
                return True
        return False

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

        # Add as development node
        self.pyproject.nodes.add_development(identifier, identifier)

        print(f"✓ Added development node '{identifier}' for tracking")

        # Return a simple NodeInfo
        return NodeInfo(
            name=identifier,
            version='dev',
            source='development'
        )

