"""PyprojectManager - Handles all pyproject.toml file operations.

This module provides a clean, reusable interface for managing pyproject.toml files,
especially for UV-based Python projects.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import TYPE_CHECKING

import tomlkit
from tomlkit.exceptions import TOMLKitError

from ..logging.logging_config import get_logger
from ..models.exceptions import CDPyprojectError, CDPyprojectInvalidError, CDPyprojectNotFoundError

if TYPE_CHECKING:
    from ..services.node_registry import NodeInfo

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

        # Lazy-initialized handlers
        self._dependencies: DependencyHandler | None = None
        self._nodes: NodeHandler | None = None
        self._uv_config: UVConfigHandler | None = None
        self._workflows: WorkflowHandler | None = None
        self._models: ModelHandler | None = None

    @property
    def dependencies(self) -> DependencyHandler:
        """Get dependency handler."""
        if self._dependencies is None:
            self._dependencies = DependencyHandler(self)
        return self._dependencies

    @property
    def nodes(self) -> NodeHandler:
        """Get node handler."""
        if self._nodes is None:
            self._nodes = NodeHandler(self)
        return self._nodes

    # dev_nodes removed - development nodes now handled by nodes handler with version='dev'

    @property
    def uv_config(self) -> UVConfigHandler:
        """Get UV configuration handler."""
        if self._uv_config is None:
            self._uv_config = UVConfigHandler(self)
        return self._uv_config

    @property
    def workflows(self) -> WorkflowHandler:
        """Get workflow handler."""
        if self._workflows is None:
            self._workflows = WorkflowHandler(self)
        return self._workflows

    @property
    def models(self) -> ModelHandler:
        """Get model handler."""
        if self._models is None:
            self._models = ModelHandler(self)
        return self._models

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

        try:
            # Ensure parent directory exists
            self.path.parent.mkdir(parents=True, exist_ok=True)

            with open(self.path, 'w') as f:
                tomlkit.dump(config, f)
        except OSError as e:
            raise CDPyprojectError(f"Failed to write pyproject.toml to {self.path}: {e}")

        logger.debug(f"Saved pyproject.toml to {self.path}")

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


class BaseHandler:
    """Base handler providing common functionality."""

    def __init__(self, manager: PyprojectManager):
        self.manager = manager

    def load(self) -> dict:
        """Load configuration from manager."""
        return self.manager.load()

    def save(self, config: dict) -> None:
        """Save configuration through manager."""
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

    def add_development(self, identifier: str, name: str) -> None:
        """Add a development node (version='dev')."""
        from ..models.shared import NodeInfo
        node_info = NodeInfo(
            name=name,
            version='dev',
            source='development'
        )
        self.add(node_info, identifier)

    def is_development(self, identifier: str) -> bool:
        """Check if a node is a development node."""
        nodes = self.get_existing()
        node = nodes.get(identifier)
        return node and hasattr(node, 'version') and node.version == 'dev'

    def get_existing(self) -> dict[str, NodeInfo]:
        """Get all existing custom nodes from pyproject.toml."""
        from ..services.node_registry import NodeInfo
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
    """Handles workflow management."""

    def add(self, name: str, workflow_info: dict) -> None:
        """Add a workflow to tracking in pyproject.toml."""
        config = self.load()
        self.ensure_section(config, 'tool', 'comfydock')

        if 'workflows' not in config['tool']['comfydock']:
            config['tool']['comfydock']['workflows'] = tomlkit.table()

        if 'tracked' not in config['tool']['comfydock']['workflows']:
            config['tool']['comfydock']['workflows']['tracked'] = tomlkit.table()

        # Create inline table for requires to keep everything grouped
        requires = workflow_info.get('requires', {})
        requires_table = tomlkit.inline_table()

        # Add each requires section, filtering out None values
        for key, value in requires.items():
            if value is None:
                continue

            if isinstance(value, list):
                # Filter out None values from lists
                filtered_value = [v for v in value if v is not None]
                if filtered_value:  # Only add non-empty lists
                    requires_table[key] = filtered_value
            elif isinstance(value, dict):
                # Skip private/debug keys that start with underscore
                # These are for debugging and shouldn't be saved to TOML
                if key.startswith('_'):
                    continue
                # For other dict values, create a proper nested table
                dict_table = tomlkit.table()
                for dict_key, dict_value in value.items():
                    if dict_key is not None and dict_value is not None:
                        # Ensure dict values are properly formatted
                        if isinstance(dict_value, list):
                            # Filter None from nested lists
                            filtered_dict_value = [v for v in dict_value if v is not None]
                            if filtered_dict_value:
                                dict_table[dict_key] = filtered_dict_value
                        else:
                            dict_table[dict_key] = dict_value
                if dict_table:  # Only add non-empty tables
                    requires_table[key] = dict_table
            else:
                # For other scalar values, wrap in list
                requires_table[key] = [value]

        # Create the workflow entry with None checks
        workflow_entry = tomlkit.table()

        # Ensure file path is not None
        file_path = workflow_info.get('file')
        if file_path is None:
            raise ValueError(f"Workflow file path cannot be None for workflow '{name}'")

        workflow_entry['file'] = file_path
        workflow_entry['requires'] = requires_table

        config['tool']['comfydock']['workflows']['tracked'][name] = workflow_entry


        self.save(config)
        logger.info(f"Added tracked workflow: {name}")

    def get_tracked(self) -> dict:
        """Get all tracked workflows from pyproject.toml."""
        try:
            config = self.load()
            return config.get('tool', {}).get('comfydock', {}).get('workflows', {}).get('tracked', {})
        except Exception:
            return {}

    def remove(self, name: str) -> bool:
        """Remove a tracked workflow from pyproject.toml."""
        config = self.load()
        workflows = config.get('tool', {}).get('comfydock', {}).get('workflows', {}).get('tracked', {})

        if name not in workflows:
            return False

        del workflows[name]
        # Clean up empty sections
        self.clean_empty_sections(config, 'tool', 'comfydock', 'workflows', 'tracked')
        self.clean_empty_sections(config, 'tool', 'comfydock', 'workflows')
        self.save(config)
        logger.info(f"Removed tracked workflow: {name}")
        return True


class ModelHandler(BaseHandler):
    """Handles model configuration in pyproject.toml."""

    def _ensure_structure(self, config: dict) -> None:
        """Ensure tool.comfydock.models exists with required sections."""
        if "tool" not in config:
            config["tool"] = tomlkit.table()
        if "comfydock" not in config["tool"]:
            config["tool"]["comfydock"] = tomlkit.table()
        if "models" not in config["tool"]["comfydock"]:
            models_table = tomlkit.table()
            models_table["required"] = tomlkit.table()
            models_table["optional"] = tomlkit.table()
            config["tool"]["comfydock"]["models"] = models_table
        else:
            # Ensure both sections exist even if models section exists
            models = config["tool"]["comfydock"]["models"]
            if "required" not in models:
                models["required"] = tomlkit.table()
            if "optional" not in models:
                models["optional"] = tomlkit.table()

    def add_model(
        self,
        model_hash: str,
        filename: str,
        file_size: int,
        category: str = "required",
        **metadata,
    ) -> None:
        """Add a model to the manifest.

        Args:
            model_hash: Model hash (short hash used as key)
            filename: Model filename
            file_size: File size in bytes
            category: 'required' or 'optional'
            **metadata: Additional metadata (blake3, sha256, sources, etc.)
        """
        config = self.load()
        self._ensure_structure(config)

        # Ensure the specific category exists
        if category not in config["tool"]["comfydock"]["models"]:
            config["tool"]["comfydock"]["models"][category] = tomlkit.table()

        models_section = config["tool"]["comfydock"]["models"][category]
        models_section[model_hash] = {
            "filename": filename,
            "size": file_size,
            **metadata,
        }

        self.save(config)
        logger.info(f"Added {category} model: {filename} ({model_hash[:8]}...)")

    def remove_model(self, model_hash: str, category: str | None = None) -> bool:
        """Remove a model from the manifest.
        
        Args:
            model_hash: Model hash to remove
            category: Specific category to remove from, or None to check both
            
        Returns:
            True if removed, False if not found
        """
        config = self.load()
        self._ensure_structure(config)

        models = config["tool"]["comfydock"]["models"]

        if category:
            # Remove from specific category
            if model_hash in models.get(category, {}):
                del models[category][model_hash]
                # Clean up empty sections
                self.clean_empty_sections(config, 'tool', 'comfydock', 'models', category)
                self.clean_empty_sections(config, 'tool', 'comfydock', 'models')
                self.save(config)
                logger.info(f"Removed model from {category}: {model_hash[:8]}...")
                return True
        else:
            # Remove from any category
            for cat in ['required', 'optional']:
                if model_hash in models.get(cat, {}):
                    del models[cat][model_hash]
                    # Clean up empty sections
                    self.clean_empty_sections(config, 'tool', 'comfydock', 'models', cat)
                    self.clean_empty_sections(config, 'tool', 'comfydock', 'models')
                    self.save(config)
                    logger.info(f"Removed model from {cat}: {model_hash[:8]}...")
                    return True

        return False

    def get_all(self) -> dict:
        """Get all models in manifest.
        
        Returns:
            Dictionary with 'required' and 'optional' sections
        """
        config = self.load()
        self._ensure_structure(config)
        return config["tool"]["comfydock"]["models"]

    def get_category(self, category: str) -> dict:
        """Get models from specific category.
        
        Args:
            category: 'required' or 'optional'
            
        Returns:
            Dictionary of models in that category
        """
        models = self.get_all()
        return models.get(category, {})

    def has_model(self, model_hash: str) -> str | None:
        """Check if model exists in manifest.
        
        Args:
            model_hash: Model hash to check
            
        Returns:
            Category name if found ('required' or 'optional'), None otherwise
        """
        models = self.get_all()

        if model_hash in models.get('required', {}):
            return 'required'
        elif model_hash in models.get('optional', {}):
            return 'optional'

        return None

    def update_model_metadata(self, model_hash: str, **metadata) -> bool:
        """Update metadata for existing model.
        
        Args:
            model_hash: Model hash to update
            **metadata: Metadata to add/update (blake3, sha256, etc.)
            
        Returns:
            True if updated, False if model not found
        """
        config = self.load()
        models = config.get("tool", {}).get("comfydock", {}).get("models", {})

        # Find which category the model is in
        for category in ['required', 'optional']:
            if model_hash in models.get(category, {}):
                models[category][model_hash].update(metadata)
                self.save(config)
                logger.debug(f"Updated metadata for model {model_hash[:8]}...")
                return True

        return False

    def get_all_model_hashes(self) -> set[str]:
        """Get all model hashes in manifest.
        
        Returns:
            Set of all model hashes across both categories
        """
        models = self.get_all()
        all_hashes = set()
        all_hashes.update(models.get('required', {}).keys())
        all_hashes.update(models.get('optional', {}).keys())
        return all_hashes

    def get_model_count(self) -> dict[str, int]:
        """Get count of models by category.
        
        Returns:
            Dictionary with counts for each category
        """
        models = self.get_all()
        return {
            'required': len(models.get('required', {})),
            'optional': len(models.get('optional', {})),
            'total': len(models.get('required', {})) + len(models.get('optional', {}))
        }
