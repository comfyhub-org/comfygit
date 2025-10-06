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

        # Clean up empty sections before saving
        self._cleanup_empty_sections(config)

        try:
            # Ensure parent directory exists
            self.path.parent.mkdir(parents=True, exist_ok=True)

            with open(self.path, 'w') as f:
                tomlkit.dump(config, f)
        except OSError as e:
            raise CDPyprojectError(f"Failed to write pyproject.toml to {self.path}: {e}")

        logger.debug(f"Saved pyproject.toml to {self.path}")
        
    def reset_lazy_handlers(self):
        self._dependencies = None
        self._nodes = None
        self._uv_config = None
        self._workflows = None
        self._models = None

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

    def is_development(self, identifier: str) -> bool:
        """Check if a node is a development node."""
        nodes = self.get_existing()
        node = nodes.get(identifier)
        return node and hasattr(node, 'version') and node.version == 'dev'

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

    def add_workflow(self, name: str) -> None:
        """Add a new workflow to the pyproject.toml."""
        config = self.load()
        self.ensure_section(config, 'tool', 'comfydock', 'workflows')
        config['tool']['comfydock']['workflows'][name] = tomlkit.table()
        logger.info(f"Added new workflow: {name}")
        self.save(config)

    def apply_resolution(
        self,
        workflow_name: str,
        models: list,
        model_refs: list,
        node_packs: set[str] | None = None,
    ) -> None:
        """Apply workflow resolution atomically - adds models and sets mappings in one save.

        Args:
            workflow_name: Name of workflow
            models: List of ModelWithLocation objects
            model_refs: List of WorkflowNodeWidgetRef objects
            node_packs: List of node pack identifiers used by workflow

        Raises:
            CDPyprojectError: If save fails
        """
        if not models and not node_packs:
            logger.debug("No models or node packs to apply for workflow resolution")
            return

        # Build fresh mappings (encapsulated in this handler)
        fresh_mappings = self._build_model_mappings(models, model_refs) if models else {}

        # Add models via ModelHandler
        for model in models:
            self.manager.models.add_model(
                model_hash=model.hash,
                filename=model.filename,
                file_size=model.file_size,
                relative_path=model.relative_path,
                category="required",
            )

        # Set workflow mappings
        self.set_model_resolutions(workflow_name, fresh_mappings)

        # Set node pack references
        if node_packs:
            self.set_node_packs(workflow_name, node_packs)

        logger.info(f"Applied {len(models)} model(s) and {len(node_packs or [])} node pack(s) for workflow '{workflow_name}'")

    def _build_model_mappings(self, models: list, model_refs: list) -> dict:
        """Build mapping structure from models and refs.

        Encapsulates the schema: hash -> {nodes: [{node_id, widget_idx}]}

        Args:
            models: List of ModelWithLocation objects
            model_refs: List of WorkflowNodeWidgetRef objects

        Returns:
            Mapping dict with hash as key
        """
        mappings = {}
        for i, model in enumerate(models):
            if i < len(model_refs):
                ref = model_refs[i]
                if model.hash not in mappings:
                    mappings[model.hash] = {"nodes": []}
                mappings[model.hash]["nodes"].append({
                    "node_id": str(ref.node_id),
                    "widget_idx": int(ref.widget_index)
                })
        return mappings

    def set_model_resolutions(self, name: str, model_resolutions: dict) -> None:
        """Set model resolutions for a workflow using PRD schema.

        Args:
            name: Workflow name
            model_resolutions: Dict mapping hash to node locations
                Format: {
                    "abc123hash...": {
                        "nodes": [{"node_id": "4", "widget_idx": 0}]
                    }
                }
        """
        config = self.load()
        self.ensure_section(config, 'tool', 'comfydock', 'workflows', name)

        # Set workflow path
        config['tool']['comfydock']['workflows'][name]['path'] = f"workflows/{name}.json"

        # Create models table with hash as key (PRD schema)
        models_table = tomlkit.inline_table()

        for model_hash, resolution_data in model_resolutions.items():
            # Create inline table for this hash's data
            hash_entry = tomlkit.inline_table()

            # Nodes as array of inline tables
            nodes_list = []
            for node_ref in resolution_data.get('nodes', []):
                node_inline = tomlkit.inline_table()
                node_inline['node_id'] = str(node_ref['node_id'])
                node_inline['widget_idx'] = int(node_ref['widget_idx'])
                nodes_list.append(node_inline)

            hash_entry['nodes'] = nodes_list
            models_table[model_hash] = hash_entry

        config['tool']['comfydock']['workflows'][name]['models'] = models_table
        self.save(config)
        logger.info(f"Set model resolutions for workflow: {name}")

    def get_model_resolutions(self, name: str) -> dict:
        """Get model resolutions for a specific workflow."""
        try:
            config = self.load()
            workflow_data = config.get('tool', {}).get('comfydock', {}).get('workflows', {}).get(name, {})
            return workflow_data.get('models', {})
        except Exception:
            return {}

    def get_all_with_resolutions(self) -> dict:
        """Get all workflows that have model resolutions."""
        try:
            config = self.load()
            return config.get('tool', {}).get('comfydock', {}).get('workflows', {})
        except Exception:
            return {}

    def set_node_packs(self, name: str, node_pack_ids: set[str]) -> None:
        """Set node pack references for a workflow.

        Args:
            name: Workflow name
            node_pack_ids: List of node pack identifiers (e.g., ["comfyui-akatz-nodes"])
        """
        config = self.load()
        self.ensure_section(config, 'tool', 'comfydock', 'workflows', name)
        config['tool']['comfydock']['workflows'][name]['nodes'] = sorted(node_pack_ids)
        self.save(config)
        logger.info(f"Set {len(node_pack_ids)} node pack(s) for workflow: {name}")

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


class ModelHandler(BaseHandler):
    """Handles model configuration in pyproject.toml."""

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
        
        Raises:
            CDPyprojectError: If no configuration to save or write fails
        """
        config = self.load()

        # Lazy section creation - only when adding a model
        self.ensure_section(config, "tool", "comfydock", "models", category)

        # Use inline table for compact formatting
        model_entry = tomlkit.inline_table()
        model_entry["filename"] = filename
        model_entry["size"] = file_size
        for key, value in metadata.items():
            model_entry[key] = value

        config["tool"]["comfydock"]["models"][category][model_hash] = model_entry

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
        models = config.get("tool", {}).get("comfydock", {}).get("models", {})

        if category:
            # Remove from specific category
            if model_hash in models.get(category, {}):
                del models[category][model_hash]
                self.save(config)
                logger.info(f"Removed model from {category}: {model_hash[:8]}...")
                return True
        else:
            # Remove from any category
            for cat in ['required', 'optional']:
                if model_hash in models.get(cat, {}):
                    del models[cat][model_hash]
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
        return config.get("tool", {}).get("comfydock", {}).get("models", {})

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

    def cleanup_orphans(self) -> int:
        """Remove models from models.required that no workflow references.

        This is a cross-cutting operation that understands the relationship
        between workflows and models sections in pyproject.toml.

        Returns:
            Number of orphaned models removed
        """
        config = self.load()

        # Collect referenced hashes from all workflows
        referenced = set()
        workflows = config.get('tool', {}).get('comfydock', {}).get('workflows', {})
        for workflow_data in workflows.values():
            referenced.update(workflow_data.get('models', {}).keys())

        # Find orphans in required models
        models = config.get('tool', {}).get('comfydock', {}).get('models', {})
        orphaned = []
        for hash_val in list(models.get('required', {}).keys()):
            if hash_val not in referenced:
                del models['required'][hash_val]
                orphaned.append(hash_val)

        if orphaned:
            self.save(config)
            logger.info(f"Cleaned up {len(orphaned)} orphaned model(s)")

        return len(orphaned)
