"""Parse git changes in pyproject.toml files to extract what was modified."""

from pathlib import Path
from typing import Any

import tomlkit

from ..logging.logging_config import get_logger
from ..models.environment import GitStatus
from ..utils.dependency_parser import compare_dependency_sets, extract_all_dependencies
from ..utils.git import git_show

logger = get_logger(__name__)


class GitChangeParser:
    """Parse git changes to pyproject.toml to identify what was modified."""

    def __init__(self, repo_path: Path):
        """Initialize the parser.

        Args:
            repo_path: Path to git repository (.cec directory)
        """
        self.repo_path = repo_path

    def parse_changes(self, current_config: dict) -> dict[str, Any]:
        """Parse git changes comparing HEAD to current.

        Args:
            current_config: Current pyproject.toml configuration

        Returns:
            Dict with changes categorized by type
        """
        changes = {
            'nodes_added': [],
            'nodes_removed': [],
            'dependencies_added': [],
            'dependencies_removed': [],
            'dependencies_updated': [],
            'constraints_added': [],
            'constraints_removed': [],
        }

        try:
            # Get the last committed version
            committed_content = git_show(
                self.repo_path,
                "HEAD",
                Path("pyproject.toml"),
                is_text=True
            )

            if not committed_content:
                return changes

            committed_config = tomlkit.loads(committed_content)

            # Compare each category
            self._compare_nodes(committed_config, current_config, changes)
            self._compare_dependencies(committed_config, current_config, changes)
            self._compare_constraints(committed_config, current_config, changes)

        except (ValueError, OSError) as e:
            # No previous commit or file doesn't exist in HEAD
            logger.debug(f"Could not get previous pyproject.toml: {e}")
            # This is fine - might be the first commit

        return changes


    def update_git_status(self, status: GitStatus, current_config: dict) -> None:
        """Update a GitStatus object with parsed changes.

        Args:
            status: GitStatus object to update
            current_config: Current pyproject.toml configuration
        """
        changes = self.parse_changes(current_config)

        status.nodes_added = changes['nodes_added']
        status.nodes_removed = changes['nodes_removed']
        status.dependencies_added = changes['dependencies_added']
        status.dependencies_removed = changes['dependencies_removed']
        status.dependencies_updated = changes['dependencies_updated']
        status.constraints_added = changes['constraints_added']
        status.constraints_removed = changes['constraints_removed']

    def _compare_nodes(self, old_config: dict, new_config: dict, changes: dict) -> None:
        """Compare custom nodes between configs."""
        old_nodes = old_config.get('tool', {}).get('comfygit', {}).get('nodes', {})
        new_nodes = new_config.get('tool', {}).get('comfygit', {}).get('nodes', {})

        # Flatten old nodes (handle legacy 'development' section)
        old_flat = self._flatten_nodes(old_nodes)
        new_flat = self._flatten_nodes(new_nodes)

        old_keys = set(old_flat.keys())
        new_keys = set(new_flat.keys())

        for key in new_keys - old_keys:
            node_data = new_flat[key]
            node_name = node_data.get('name', key)
            is_development = node_data.get('version') == 'dev'
            changes['nodes_added'].append({
                'name': node_name,
                'is_development': is_development
            })

        for key in old_keys - new_keys:
            node_data = old_flat[key]
            node_name = node_data.get('name', key)
            is_development = node_data.get('version') == 'dev'
            changes['nodes_removed'].append({
                'name': node_name,
                'is_development': is_development
            })

    def _flatten_nodes(self, nodes_config: dict) -> dict:
        """Flatten nodes, handling legacy 'development' section."""
        flat = {}
        for key, value in nodes_config.items():
            if key == 'development' and isinstance(value, dict):
                # Legacy development section - flatten it
                for dev_key, dev_value in value.items():
                    if isinstance(dev_value, dict):
                        flat[dev_key] = dev_value
            elif isinstance(value, dict) and 'name' in value:
                # Regular node
                flat[key] = value
        return flat

    def _compare_dependencies(self, old_config: dict, new_config: dict, changes: dict) -> None:
        """Compare Python dependencies using existing utilities."""
        old_deps = extract_all_dependencies(old_config)
        new_deps = extract_all_dependencies(new_config)

        dep_changes = compare_dependency_sets(old_deps, new_deps)
        changes['dependencies_added'] = dep_changes.get('added', [])
        changes['dependencies_removed'] = dep_changes.get('removed', [])
        changes['dependencies_updated'] = dep_changes.get('updated', [])

    def _compare_constraints(self, old_config: dict, new_config: dict, changes: dict) -> None:
        """Compare UV constraint dependencies."""
        old_constraints = old_config.get('tool', {}).get('uv', {}).get('constraint-dependencies', [])
        new_constraints = new_config.get('tool', {}).get('uv', {}).get('constraint-dependencies', [])

        old_set = set(old_constraints)
        new_set = set(new_constraints)

        changes['constraints_added'] = list(new_set - old_set)
        changes['constraints_removed'] = list(old_set - new_set)

    # Workflow tracking comparison removed - all workflows are auto-managed

