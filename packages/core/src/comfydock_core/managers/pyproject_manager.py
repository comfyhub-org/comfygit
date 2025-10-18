"""PyprojectManager - Handles all pyproject.toml file operations.

This module provides a clean, reusable interface for managing pyproject.toml files,
especially for UV-based Python projects.
"""
from __future__ import annotations

import hashlib
import re
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING

import tomlkit
from tomlkit.exceptions import TOMLKitError

from comfydock_core.models.manifest import ManifestWorkflowModel, ManifestModel

from ..logging.logging_config import get_logger
from ..models.exceptions import CDPyprojectError, CDPyprojectInvalidError, CDPyprojectNotFoundError

if TYPE_CHECKING:
    from ..models.shared import NodeInfo

from ..utils.dependency_parser import parse_dependency_string

logger = get_logger(__name__)


class PyprojectManager:
    """Manages pyproject.toml file operations for Python projects."""

    def __init__(self, pyproject_path: Path):
        """Initialize the PyprojectManager.

        Args:
            pyproject_path: Path to the pyproject.toml file
        """
        self.path = pyproject_path

    @cached_property
    def dependencies(self) -> DependencyHandler:
        """Get dependency handler."""
        return DependencyHandler(self)

    @cached_property
    def nodes(self) -> NodeHandler:
        """Get node handler."""
        return NodeHandler(self)

    @cached_property
    def uv_config(self) -> UVConfigHandler:
        """Get UV configuration handler."""
        return UVConfigHandler(self)

    @cached_property
    def workflows(self) -> WorkflowHandler:
        """Get workflow handler."""
        return WorkflowHandler(self)

    @cached_property
    def models(self) -> ModelHandler:
        """Get model handler."""
        return ModelHandler(self)

    # ===== Core Operations =====

    def exists(self) -> bool:
        """Check if the pyproject.toml file exists."""
        return self.path.exists()

    def load(self) -> dict:
        """Load the pyproject.toml file.
        
        Args:
            force_reload: Force reload from disk even if cached
            
        Returns:
            The loaded configuration dictionary
            
        Raises:
            CDPyprojectNotFoundError: If the file doesn't exist
            CDPyprojectInvalidError: If the file is empty or invalid
        """
        if not self.exists():
            raise CDPyprojectNotFoundError(f"pyproject.toml not found at {self.path}")

        try:
            with open(self.path) as f:
                config = tomlkit.load(f)
        except (OSError, TOMLKitError) as e:
            raise CDPyprojectInvalidError(f"Failed to parse pyproject.toml at {self.path}: {e}")

        if not config:
            raise CDPyprojectInvalidError(f"pyproject.toml is empty at {self.path}")

        return config


    def save(self, config: dict | None = None) -> None:
        """Save the configuration to pyproject.toml.

        Args:
            config: Configuration to save (uses cache if not provided)

        Raises:
            CDPyprojectError: If no configuration to save or write fails
        """
        if config is None:
            raise CDPyprojectError("No configuration to save")

        # Clean up empty sections before saving
        self._cleanup_empty_sections(config)

        # Ensure proper spacing between major sections
        self._ensure_section_spacing(config)

        try:
            # Ensure parent directory exists
            self.path.parent.mkdir(parents=True, exist_ok=True)

            with open(self.path, 'w') as f:
                tomlkit.dump(config, f)
        except OSError as e:
            raise CDPyprojectError(f"Failed to write pyproject.toml to {self.path}: {e}")

        logger.debug(f"Saved pyproject.toml to {self.path}")

    def reset_lazy_handlers(self):
        """Clear cached properties to force re-initialization."""
        for attr in ('dependencies', 'nodes', 'uv_config', 'workflows', 'models', 'node_mappings'):
            if attr in self.__dict__:
                del self.__dict__[attr]

    def _cleanup_empty_sections(self, config: dict) -> None:
        """Recursively remove empty sections from config."""
        def _clean_dict(d: dict) -> bool:
            """Recursively clean dict, return True if dict became empty."""
            keys_to_remove = []
            for key, value in list(d.items()):
                if isinstance(value, dict):
                    if _clean_dict(value) or not value:
                        keys_to_remove.append(key)
            for key in keys_to_remove:
                del d[key]
            return not d

        _clean_dict(config)

    def _ensure_section_spacing(self, config: dict) -> None:
        """Ensure proper spacing between major sections in tool.comfydock.

        This adds visual separation between:
        - [tool.comfydock] metadata and workflows
        - workflows section and models section
        """
        if 'tool' not in config or 'comfydock' not in config['tool']:
            return

        comfydock = config['tool']['comfydock']

        # Track which sections exist
        has_metadata = any(k in comfydock for k in ['comfyui_version', 'python_version', 'manifest_state'])
        has_nodes = 'nodes' in comfydock
        has_workflows = 'workflows' in comfydock
        has_models = 'models' in comfydock

        # Only rebuild if we have workflows or models (need spacing)
        if not (has_workflows or has_models):
            return

        # Deep copy sections to strip any accumulated whitespace
        def deep_copy_table(obj):
            """Recursively copy tomlkit objects, preserving special types."""
            if isinstance(obj, dict):
                # Determine if inline table or regular table
                is_inline = hasattr(obj, '__class__') and 'InlineTable' in obj.__class__.__name__
                new_dict = tomlkit.inline_table() if is_inline else tomlkit.table()
                for k, v in obj.items():
                    # Skip whitespace items (empty keys)
                    if k == '':
                        continue
                    new_dict[k] = deep_copy_table(v)
                return new_dict
            elif isinstance(obj, list):
                # Check if this is a tomlkit array (preserve inline table items)
                is_tomlkit_array = hasattr(obj, '__class__') and 'Array' in obj.__class__.__name__
                if is_tomlkit_array:
                    new_array = tomlkit.array()
                    for item in obj:
                        # Preserve inline tables inside arrays
                        if hasattr(item, '__class__') and 'InlineTable' in item.__class__.__name__:
                            new_inline = tomlkit.inline_table()
                            for k, v in item.items():
                                new_inline[k] = deep_copy_table(v)
                            new_array.append(new_inline)
                        else:
                            new_array.append(deep_copy_table(item))
                    return new_array
                else:
                    return [deep_copy_table(item) for item in obj]
            else:
                return obj

        # Create a new table with sections in the correct order
        new_table = tomlkit.table()

        # Add metadata fields first
        for key in ['comfyui_version', 'python_version', 'manifest_state']:
            if key in comfydock:
                new_table[key] = comfydock[key]

        # Add nodes if it exists
        if has_nodes:
            new_table['nodes'] = deep_copy_table(comfydock['nodes'])

        # Add workflows with preceding newline if needed
        if has_workflows:
            if has_metadata or has_nodes:
                new_table.add(tomlkit.nl())
            new_table['workflows'] = deep_copy_table(comfydock['workflows'])

        # Add models with preceding newline if needed
        if has_models:
            if has_metadata or has_nodes or has_workflows:
                new_table.add(tomlkit.nl())
            new_table['models'] = deep_copy_table(comfydock['models'])

        # Replace the comfydock table
        config['tool']['comfydock'] = new_table

    def get_manifest_state(self) -> str:
        """Get the current manifest state.
        
        Returns:
            'local' or 'exportable'
        """
        config = self.load()
        if 'tool' in config and 'comfydock' in config['tool']:
            return config['tool']['comfydock'].get('manifest_state', 'local')
        return 'local'

    def set_manifest_state(self, state: str) -> None:
        """Set the manifest state.

        Args:
            state: 'local' or 'exportable'
        """
        if state not in ('local', 'exportable'):
            raise ValueError(f"Invalid manifest state: {state}")

        config = self.load()
        if 'tool' not in config:
            config['tool'] = {}
        if 'comfydock' not in config['tool']:
            config['tool']['comfydock'] = {}

        config['tool']['comfydock']['manifest_state'] = state
        self.save(config)
        logger.info(f"Set manifest state to: {state}")

    def snapshot(self) -> dict:
        """Create a deep copy of current pyproject.toml state for rollback.

        Returns:
            Deep copy of the entire config dictionary
        """
        import copy
        return copy.deepcopy(self.load())

    def restore(self, snapshot: dict) -> None:
        """Restore pyproject.toml from a snapshot.

        Args:
            snapshot: Previously captured state from snapshot()
        """
        self.save(snapshot)
        # Reset lazy handlers so they reload from restored state
        self.reset_lazy_handlers()
        logger.debug("Restored pyproject.toml from snapshot")


class BaseHandler:
    """Base handler providing common functionality."""

    def __init__(self, manager: PyprojectManager):
        self.manager = manager

    def load(self) -> dict:
        """Load configuration from manager."""
        return self.manager.load()

    def save(self, config: dict) -> None:
        """Save configuration through manager.
        
        Raises:
            CDPyprojectError
        """
        self.manager.save(config)

    def ensure_section(self, config: dict, *path: str) -> dict:
        """Ensure a nested section exists in config."""
        current = config
        for key in path:
            if key not in current:
                current[key] = tomlkit.table()
            current = current[key]
        return current

    def clean_empty_sections(self, config: dict, *path: str) -> None:
        """Clean up empty sections by removing them from bottom up."""
        if not path:
            return

        # Navigate to parent of the last key
        current = config
        for key in path[:-1]:
            if key not in current:
                return
            current = current[key]

        # Check if the final key exists and is empty
        final_key = path[-1]
        if final_key in current and not current[final_key]:
            del current[final_key]
            # Recursively clean parent if it becomes empty (except top-level sections)
            if len(path) > 2 and not current:
                self.clean_empty_sections(config, *path[:-1])


class DependencyHandler(BaseHandler):
    """Handles dependency groups and analysis."""

    def get_groups(self) -> dict[str, list[str]]:
        """Get all dependency groups."""
        try:
            config = self.load()
            return config.get('dependency-groups', {})
        except Exception:
            return {}

    def add_to_group(self, group: str, packages: list[str]) -> None:
        """Add packages to a dependency group."""
        config = self.load()

        if 'dependency-groups' not in config:
            config['dependency-groups'] = {}

        if group not in config['dependency-groups']:
            config['dependency-groups'][group] = []

        group_deps = config['dependency-groups'][group]
        added_count = 0

        for pkg in packages:
            if pkg not in group_deps:
                group_deps.append(pkg)
                added_count += 1

        logger.info(f"Added {added_count} packages to group '{group}'")
        self.save(config)

    def remove_group(self, group: str) -> None:
        """Remove a dependency group."""
        config = self.load()

        if 'dependency-groups' not in config:
            raise ValueError("No dependency groups found")

        if group not in config['dependency-groups']:
            raise ValueError(f"Group '{group}' not found")

        del config['dependency-groups'][group]
        logger.info(f"Removed dependency group: {group}")
        self.save(config)


class UVConfigHandler(BaseHandler):
    """Handles UV-specific configuration."""

    # System-level sources that should never be auto-removed
    PROTECTED_SOURCES = {'pytorch-cuda', 'pytorch-cpu', 'torch-cpu', 'torch-cuda'}

    def add_constraint(self, package: str) -> None:
        """Add a constraint dependency to [tool.uv]."""
        config = self.load()
        self.ensure_section(config, 'tool', 'uv')

        constraints = config['tool']['uv'].get('constraint-dependencies', [])

        # Extract package name for comparison
        pkg_name = self._extract_package_name(package)

        # Update existing or add new
        for i, existing in enumerate(constraints):
            if self._extract_package_name(existing) == pkg_name:
                logger.info(f"Updating constraint: {existing} -> {package}")
                constraints[i] = package
                break
        else:
            logger.info(f"Adding constraint: {package}")
            constraints.append(package)

        config['tool']['uv']['constraint-dependencies'] = constraints
        self.save(config)

    def remove_constraint(self, package_name: str) -> bool:
        """Remove a constraint dependency from [tool.uv]."""
        config = self.load()
        constraints = config.get('tool', {}).get('uv', {}).get('constraint-dependencies', [])

        if not constraints:
            return False

        # Find and remove constraint by package name
        for i, existing in enumerate(constraints):
            if self._extract_package_name(existing) == package_name.lower():
                removed = constraints.pop(i)
                logger.info(f"Removing constraint: {removed}")
                config['tool']['uv']['constraint-dependencies'] = constraints
                self.save(config)
                return True

        return False

    def add_index(self, name: str, url: str, explicit: bool = True) -> None:
        """Add an index to [[tool.uv.index]]."""
        config = self.load()
        self.ensure_section(config, 'tool', 'uv')
        indexes = config['tool']['uv'].get('index', [])

        if not isinstance(indexes, list):
            indexes = [indexes] if indexes else []

        # Update existing or add new
        for i, existing in enumerate(indexes):
            if existing.get('name') == name:
                logger.info(f"Updating index '{name}'")
                indexes[i] = {'name': name, 'url': url, 'explicit': explicit}
                break
        else:
            logger.info(f"Creating index '{name}'")
            indexes.append({'name': name, 'url': url, 'explicit': explicit})

        config['tool']['uv']['index'] = indexes
        self.save(config)

    def add_source(self, package_name: str, source: dict) -> None:
        """Add a source mapping to [tool.uv.sources]."""
        config = self.load()
        self.ensure_section(config, 'tool', 'uv')

        if 'sources' not in config['tool']['uv']:
            config['tool']['uv']['sources'] = {}

        config['tool']['uv']['sources'][package_name] = source
        logger.info(f"Added source for '{package_name}': {source}")
        self.save(config)

    def add_url_sources(self, package_name: str, urls_with_markers: list[dict], group: str | None = None) -> None:
        """Add URL sources with markers to [tool.uv.sources]."""
        config = self.load()
        self.ensure_section(config, 'tool', 'uv')

        if 'sources' not in config['tool']['uv']:
            config['tool']['uv']['sources'] = {}

        # Clean up markers
        cleaned_sources = []
        for source in urls_with_markers:
            cleaned_source = {'url': source['url']}
            if source.get('marker'):
                cleaned_marker = source['marker'].replace('\\"', '"').replace("\\'", "'")
                cleaned_source['marker'] = cleaned_marker
            cleaned_sources.append(cleaned_source)

        # Format sources
        if len(cleaned_sources) > 1:
            config['tool']['uv']['sources'][package_name] = cleaned_sources
        else:
            config['tool']['uv']['sources'][package_name] = cleaned_sources[0]

        # Add to dependency group if specified
        if group:
            self._add_to_dependency_group(config, group, package_name, urls_with_markers)

        self.save(config)

    def get_constraints(self) -> list[str]:
        """Get UV constraint dependencies."""
        try:
            config = self.load()
            return config.get('tool', {}).get('uv', {}).get('constraint-dependencies', [])
        except Exception:
            return []

    def get_indexes(self) -> list[dict]:
        """Get UV indexes."""
        try:
            config = self.load()
            indexes = config.get('tool', {}).get('uv', {}).get('index', [])
            return indexes if isinstance(indexes, list) else [indexes] if indexes else []
        except Exception:
            return []

    def get_sources(self) -> dict:
        """Get UV source mappings."""
        try:
            config = self.load()
            return config.get('tool', {}).get('uv', {}).get('sources', {})
        except Exception:
            return {}

    def get_source_names(self) -> set[str]:
        """Get all UV source package names."""
        return set(self.get_sources().keys())

    def cleanup_orphaned_sources(self, removed_node_sources: list[str]) -> None:
        """Remove sources that are no longer referenced by any nodes."""
        if not removed_node_sources:
            return

        config = self.load()

        # Get all remaining nodes and their sources
        remaining_sources = set()
        if hasattr(self.manager, 'nodes'):
            for node_info in self.manager.nodes.get_existing().values():
                if node_info.dependency_sources:
                    remaining_sources.update(node_info.dependency_sources)

        # Remove orphaned sources (not protected, not used by other nodes)
        sources_removed = False
        for source_name in removed_node_sources:
            if (source_name not in remaining_sources and
                not self._is_protected_source(source_name)):
                self._remove_source(config, source_name)
                sources_removed = True

        if sources_removed:
            self.save(config)

    def _is_protected_source(self, source_name: str) -> bool:
        """Check if source should never be auto-removed."""
        return any(protected in source_name.lower() for protected in self.PROTECTED_SOURCES)

    def _remove_source(self, config: dict, source_name: str) -> None:
        """Remove all source entries for a given package."""
        if 'tool' not in config or 'uv' not in config['tool']:
            return

        sources = config['tool']['uv'].get('sources', {})
        if source_name in sources:
            del sources[source_name]
            logger.info(f"Removed orphaned source: {source_name}")

    def _extract_package_name(self, package_spec: str) -> str:
        """Extract package name from a version specification."""
        name, _ = parse_dependency_string(package_spec)
        return name.lower()

    def _add_to_dependency_group(self, config: dict, group: str, package: str, sources: list[dict]) -> None:
        """Internal helper to add a package to a dependency group with markers."""
        if 'dependency-groups' not in config:
            config['dependency-groups'] = {}

        if group not in config['dependency-groups']:
            config['dependency-groups'][group] = []

        group_deps = config['dependency-groups'][group]

        # Check if package already exists
        pkg_name = self._extract_package_name(package)
        for dep in group_deps:
            if self._extract_package_name(dep) == pkg_name:
                return  # Already exists

        # Add with unique markers
        unique_markers = set()
        for source in sources:
            if source.get('marker'):
                unique_markers.add(source['marker'])

        if unique_markers:
            for marker in unique_markers:
                entry = f"{package} ; {marker}"
                if entry not in group_deps:
                    group_deps.append(entry)
                    logger.info(f"Added '{entry}' to group '{group}'")
        else:
            group_deps.append(package)
            logger.info(f"Added '{package}' to group '{group}'")


class NodeHandler(BaseHandler):
    """Handles custom node management."""

    def add(self, node_info: NodeInfo, node_identifier: str | None) -> None:
        """Add a custom node to the pyproject.toml."""
        config = self.load()
        identifier = node_identifier or (node_info.registry_id if node_info.registry_id else node_info.name)

        # Only create nodes section when actually adding a node
        self.ensure_section(config, 'tool', 'comfydock', 'nodes')

        # Build node data, excluding any None values (tomlkit requirement)
        filtered_data = {k: v for k, v in node_info.__dict__.copy().items() if v is not None}

        # Create a proper tomlkit table for better formatting
        node_table = tomlkit.table()
        for key, value in filtered_data.items():
            node_table[key] = value

        # Add node to configuration
        config['tool']['comfydock']['nodes'][identifier] = node_table

        logger.info(f"Added custom node: {identifier}")
        self.save(config)

    def add_development(self, name: str) -> None:
        """Add a development node (version='dev')."""
        from ..models.shared import NodeInfo
        node_info = NodeInfo(
            name=name,
            version='dev',
            source='development'
        )
        self.add(node_info, name)

    # def is_development(self, identifier: str) -> bool:
    #     """Check if a node is a development node."""
    #     nodes = self.get_existing()
    #     node = nodes.get(identifier)
    #     return node and hasattr(node, 'version') and node.version == 'dev'

    def get_existing(self) -> dict[str, NodeInfo]:
        """Get all existing custom nodes from pyproject.toml."""
        from ..models.shared import NodeInfo
        config = self.load()
        nodes_data = config.get('tool', {}).get('comfydock', {}).get('nodes', {})

        result = {}
        for identifier, node_data in nodes_data.items():
            result[identifier] = NodeInfo(
                name=node_data.get('name') or identifier,
                repository=node_data.get('repository'),
                registry_id=node_data.get('registry_id'),
                version=node_data.get('version'),
                source=node_data.get('source', 'unknown'),
                download_url=node_data.get('download_url'),
                dependency_sources=node_data.get('dependency_sources')
            )

        return result

    def remove(self, node_identifier: str) -> bool:
        """Remove a custom node and its associated dependency group."""
        config = self.load()
        removed = False

        # Get existing nodes to find the one to remove
        existing_nodes = self.get_existing()
        if node_identifier not in existing_nodes:
            return False

        node_info = existing_nodes[node_identifier]

        # Generate the hash-based group name that was used during add
        fallback_identifier = node_info.registry_id if node_info.registry_id else node_info.name
        group_name = self.generate_group_name(node_info, fallback_identifier)

        # Remove from dependency-groups using the hash-based group name
        if 'dependency-groups' in config and group_name in config['dependency-groups']:
            del config['dependency-groups'][group_name]
            removed = True
            logger.debug(f"Removed dependency group: {group_name}")

        # Remove from nodes using the original identifier
        if ('tool' in config and 'comfydock' in config['tool'] and
            'nodes' in config['tool']['comfydock'] and
            node_identifier in config['tool']['comfydock']['nodes']):
            del config['tool']['comfydock']['nodes'][node_identifier]
            removed = True
            logger.debug(f"Removed node info: {node_identifier}")

        if removed:
            # Clean up empty sections
            self.clean_empty_sections(config, 'tool', 'comfydock', 'nodes')
            self.save(config)
            logger.info(f"Removed custom node: {node_identifier}")

        return removed

    @staticmethod
    def generate_group_name(node_info: NodeInfo, fallback_identifier: str) -> str:
        """Generate a collision-resistant group name for a custom node."""
        # Use node name as base, fallback to identifier
        base_name = node_info.name or fallback_identifier

        # Normalize the base name (similar to what UV would do)
        normalized = re.sub(r'[^a-z0-9]+', '-', base_name.lower()).strip('-')

        # Generate hash from repository URL (most unique identifier) or fallback
        hash_source = node_info.repository or fallback_identifier
        hash_digest = hashlib.sha256(hash_source.encode()).hexdigest()[:8]

        return f"{normalized}-{hash_digest}"


# DevNodeHandler removed - development nodes now handled by NodeHandler with version='dev'


class WorkflowHandler(BaseHandler):
    """Handles workflow model resolutions and tracking."""
    
    def get_workflow(self, name: str) -> dict | None:
        """Get a workflow from pyproject.toml."""
        try:
            config = self.load()
            return config.get('tool', {}).get('comfydock', {}).get('workflows', {}).get(name, None)
        except Exception:
            logger.error(f"Failed to load config for workflow: {name}")
            return None

    def add_workflow(self, name: str) -> None:
        """Add a new workflow to the pyproject.toml."""
        config = self.load()
        self.ensure_section(config, 'tool', 'comfydock', 'workflows')
        config['tool']['comfydock']['workflows'][name] = tomlkit.table()
        config['tool']['comfydock']['workflows'][name]['path'] = f"workflows/{name}.json"
        logger.info(f"Added new workflow: {name}")
        self.save(config)

    def get_workflow_models(
        self,
        workflow_name: str
    ) -> list["ManifestWorkflowModel"]:
        """Get all models for a workflow.

        Args:
            workflow_name: Workflow name

        Returns:
            List of ManifestWorkflowModel objects (resolved and unresolved)
        """
        try:
            config = self.load()
            workflow_data = config.get('tool', {}).get('comfydock', {}).get('workflows', {}).get(workflow_name, {})
            models_data = workflow_data.get('models', [])

            return [ManifestWorkflowModel.from_toml_dict(m) for m in models_data]
        except Exception as e:
            logger.debug(f"Error loading workflow models for '{workflow_name}': {e}")
            return []

    def set_workflow_models(
        self,
        workflow_name: str,
        models: list["ManifestWorkflowModel"]
    ) -> None:
        """Set all models for a workflow (unified list).

        Args:
            workflow_name: Workflow name
            models: List of ManifestWorkflowModel objects (resolved and unresolved)
        """
        config = self.load()

        # Ensure sections exist
        self.ensure_section(config, 'tool', 'comfydock', 'workflows')

        # Ensure specific workflow exists
        if workflow_name not in config['tool']['comfydock']['workflows']:
            config['tool']['comfydock']['workflows'][workflow_name] = tomlkit.table()

        # Set workflow path
        if 'path' not in config['tool']['comfydock']['workflows'][workflow_name]:
            config['tool']['comfydock']['workflows'][workflow_name]['path'] = f"workflows/{workflow_name}.json"

        # Serialize to array of tables
        models_array = []
        for model in models:
            model_dict = model.to_toml_dict()
            # Convert to inline table for compact representation
            models_array.append(model_dict)

        config['tool']['comfydock']['workflows'][workflow_name]['models'] = models_array
        self.save(config)
        logger.debug(f"Set {len(models)} model(s) for workflow '{workflow_name}'")

    def add_workflow_model(
        self,
        workflow_name: str,
        model: "ManifestWorkflowModel"
    ) -> None:
        """Add or update a single model in workflow (progressive write).

        Args:
            workflow_name: Workflow name
            model: ManifestWorkflowModel to add or update

        Note:
            - If same node reference exists, replaces/upgrades that entry
            - If model with same hash exists, merges nodes
            - Otherwise, appends as new model
        """
        existing = self.get_workflow_models(workflow_name)

        # Build set of node references in new model
        new_refs = {(n.node_id, n.widget_index) for n in model.nodes}

        # Check for overlap with existing models
        updated = False
        for i, existing_model in enumerate(existing):
            existing_refs = {(n.node_id, n.widget_index) for n in existing_model.nodes}

            # If any node references overlap, this is a resolution of an existing entry
            if new_refs & existing_refs:
                if model.hash:
                    # Resolved version replaces unresolved
                    existing[i] = model
                    logger.debug(f"Replaced unresolved model '{existing_model.filename}' with resolved '{model.filename}'")
                else:
                    # Both unresolved - merge nodes and update mutable fields
                    non_overlapping = [n for n in model.nodes if (n.node_id, n.widget_index) not in existing_refs]
                    existing_model.nodes.extend(non_overlapping)
                    existing_model.criticality = model.criticality
                    existing_model.status = model.status
                    # Update download intent fields if present
                    if model.sources:
                        existing_model.sources = model.sources
                    if model.relative_path:
                        existing_model.relative_path = model.relative_path
                    logger.debug(f"Updated unresolved model '{existing_model.filename}' with {len(non_overlapping)} new ref(s)")
                updated = True
                break

            # Fallback: hash matching (for models resolved to same file from different nodes)
            elif model.hash and existing_model.hash == model.hash:
                non_overlapping = [n for n in model.nodes if (n.node_id, n.widget_index) not in existing_refs]
                existing_model.nodes.extend(non_overlapping)
                logger.debug(f"Merged {len(non_overlapping)} new node(s) into existing model '{model.filename}'")
                updated = True
                break

        if not updated:
            # Completely new model
            existing.append(model)
            logger.debug(f"Added new model '{model.filename}' to workflow '{workflow_name}'")

        self.set_workflow_models(workflow_name, existing)


    def get_all_with_resolutions(self) -> dict:
        """Get all workflows that have model resolutions."""
        try:
            config = self.load()
            return config.get('tool', {}).get('comfydock', {}).get('workflows', {})
        except Exception:
            return {}

    def set_node_packs(self, name: str, node_pack_ids: set[str] | None) -> None:
        """Set node pack references for a workflow.

        Args:
            name: Workflow name
            node_pack_ids: List of node pack identifiers (e.g., ["comfyui-akatz-nodes"]) | None which clears node packs
        """
        config = self.load()
        self.ensure_section(config, 'tool', 'comfydock', 'workflows', name)
        if not node_pack_ids:
            if 'nodes' in config['tool']['comfydock']['workflows'][name]:
                logger.info(f"Clearing node packs for workflow: {name}")
                del config['tool']['comfydock']['workflows'][name]['nodes']
        else:
            logger.info(f"Set {len(node_pack_ids)} node pack(s) for workflow: {name}")
            config['tool']['comfydock']['workflows'][name]['nodes'] = sorted(node_pack_ids)
        self.save(config)

    def clear_workflow_resolutions(self, name: str) -> bool:
        """Clear model resolutions for a workflow."""
        config = self.load()
        workflows = config.get('tool', {}).get('comfydock', {}).get('workflows', {})

        if name not in workflows:
            return False

        del workflows[name]
        # Clean up empty sections
        self.clean_empty_sections(config, 'tool', 'comfydock', 'workflows')
        self.save(config)
        logger.info(f"Cleared model resolutions for workflow: {name}")
        return True

    # === Per-workflow custom_node_map methods ===

    def get_custom_node_map(self, workflow_name: str) -> dict[str, str | bool]:
        """Get custom_node_map for a specific workflow.

        Args:
            workflow_name: Name of workflow

        Returns:
            Dict mapping node_type -> package_id (or false for optional)
        """
        try:
            config = self.load()
            workflow_data = config.get('tool', {}).get('comfydock', {}).get('workflows', {}).get(workflow_name, {})
            return workflow_data.get('custom_node_map', {})
        except Exception:
            return {}

    def set_custom_node_mapping(self, workflow_name: str, node_type: str, package_id: str | None) -> None:
        """Set a single custom_node_map entry for a workflow (progressive write).

        Args:
            workflow_name: Name of workflow
            node_type: Node type to map
            package_id: Package ID (or None for optional = false)
        """
        config = self.load()
        self.ensure_section(config, 'tool', 'comfydock', 'workflows', workflow_name)

        # Ensure custom_node_map exists
        if 'custom_node_map' not in config['tool']['comfydock']['workflows'][workflow_name]:
            config['tool']['comfydock']['workflows'][workflow_name]['custom_node_map'] = {}

        # Set mapping (false for optional, package_id string for resolved)
        if package_id is None:
            config['tool']['comfydock']['workflows'][workflow_name]['custom_node_map'][node_type] = False
        else:
            config['tool']['comfydock']['workflows'][workflow_name]['custom_node_map'][node_type] = package_id

        self.save(config)
        logger.debug(f"Set custom_node_map for workflow '{workflow_name}': {node_type} -> {package_id}")

    def remove_custom_node_mapping(self, workflow_name: str, node_type: str) -> bool:
        """Remove a single custom_node_map entry for a workflow.

        Args:
            workflow_name: Name of workflow
            node_type: Node type to remove

        Returns:
            True if removed, False if not found
        """
        config = self.load()
        workflow_data = config.get('tool', {}).get('comfydock', {}).get('workflows', {}).get(workflow_name, {})

        if 'custom_node_map' not in workflow_data or node_type not in workflow_data['custom_node_map']:
            return False

        del workflow_data['custom_node_map'][node_type]

        # Clean up empty custom_node_map
        if not workflow_data['custom_node_map']:
            del workflow_data['custom_node_map']

        self.save(config)
        logger.debug(f"Removed custom_node_map entry for workflow '{workflow_name}': {node_type}")
        return True


class ModelHandler(BaseHandler):
    """Handles global model manifest in pyproject.toml.

    Note: This stores ONLY resolved models with hashes for deduplication.
    Unresolved models are stored per-workflow only.
    """

    def add_model(self, model: "ManifestModel") -> None:
        """Add a model to the global manifest.

        Args:
            model: ManifestModel object with hash, filename, size, etc.

        Raises:
            CDPyprojectError: If save fails
        """
        config = self.load()

        # Ensure sections exist
        self.ensure_section(config, "tool", "comfydock", "models")

        # Serialize to inline table for compact representation
        model_dict = model.to_toml_dict()
        model_entry = tomlkit.inline_table()
        for key, value in model_dict.items():
            model_entry[key] = value

        config["tool"]["comfydock"]["models"][model.hash] = model_entry
        self.save(config)
        logger.debug(f"Added model: {model.filename} ({model.hash[:8]}...)")

    def get_all(self) -> list["ManifestModel"]:
        """Get all models in manifest.

        Returns:
            List of ManifestModel objects
        """
        try:
            config = self.load()
            models_data = config.get("tool", {}).get("comfydock", {}).get("models", {})

            return [
                ManifestModel.from_toml_dict(hash_key, data)
                for hash_key, data in models_data.items()
            ]
        except Exception as e:
            logger.debug(f"Error loading models: {e}")
            return []

    def get_by_hash(self, model_hash: str) -> "ManifestModel | None":
        """Get a specific model by hash.

        Args:
            model_hash: Model hash to look up

        Returns:
            ManifestModel if found, None otherwise
        """
        try:
            config = self.load()
            models_data = config.get("tool", {}).get("comfydock", {}).get("models", {})

            if model_hash in models_data:
                return ManifestModel.from_toml_dict(model_hash, models_data[model_hash])
            return None
        except Exception:
            return None

    def remove_model(self, model_hash: str) -> bool:
        """Remove a model from the manifest.

        Args:
            model_hash: Model hash to remove

        Returns:
            True if removed, False if not found
        """
        config = self.load()
        models = config.get("tool", {}).get("comfydock", {}).get("models", {})

        if model_hash in models:
            del models[model_hash]
            self.save(config)
            logger.debug(f"Removed model: {model_hash[:8]}...")
            return True

        return False

    def get_all_model_hashes(self) -> set[str]:
        """Get all model hashes in manifest.

        Returns:
            Set of all model hashes
        """
        config = self.load()
        models = config.get("tool", {}).get("comfydock", {}).get("models", {})
        return set(models.keys())

    def cleanup_orphans(self) -> None:
        """Remove models from global table that aren't referenced by any workflow.

        This should be called after all workflows have been processed to clean up
        models that were removed from all workflows.
        """
        # Collect all model hashes referenced by ANY workflow
        referenced_hashes = set()
        all_workflows = self.manager.workflows.get_all_with_resolutions()

        for workflow_name in all_workflows:
            workflow_models = self.manager.workflows.get_workflow_models(workflow_name)
            for model in workflow_models:
                # Only track resolved models (unresolved models aren't in global table)
                if model.hash and model.status == "resolved":
                    referenced_hashes.add(model.hash)

        # Get all hashes in global models table
        global_hashes = self.get_all_model_hashes()

        # Remove orphans (in global but not referenced)
        orphaned_hashes = global_hashes - referenced_hashes

        if orphaned_hashes:
            config = self.load()
            models_section = config.get("tool", {}).get("comfydock", {}).get("models", {})

            for model_hash in orphaned_hashes:
                if model_hash in models_section:
                    del models_section[model_hash]
                    logger.debug(f"Removed orphaned model: {model_hash[:8]}...")

            self.save(config)
            logger.info(f"Cleaned up {len(orphaned_hashes)} orphaned model(s)")

