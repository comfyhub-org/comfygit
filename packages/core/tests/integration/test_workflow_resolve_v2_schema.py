"""Integration tests for workflow resolution with v2.0 schema.

Tests the full workflow resolution pipeline with multi-package ranked mappings.
These tests verify that workflow_manager correctly:
1. Handles multiple packages from registry (auto-select based on installed/rank)
2. Distinguishes registry ambiguity from fuzzy search ambiguity
3. Respects auto_select_ambiguous configuration
"""

import json
import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from conftest import simulate_comfyui_save_workflow


class TestRegistryMultiPackageResolution:
    """Test resolution when registry returns multiple ranked packages."""

    def test_auto_select_installed_package_over_rank_1(self, test_env):
        """When rank 2 is installed but rank 1 isn't, auto-select rank 2.

        This is the key Q1 behavior: prioritize installed packages.
        """
        # ARRANGE: Set up mappings with multiple packages
        mappings_path = test_env.workspace_paths.cache / "custom_nodes" / "node_mappings.json"
        mappings_data = {
            "version": "2025.10.10",
            "mappings": {
                "CustomNode::abc123": [
                    {"package_id": "pkg-popular", "versions": ["1.0"], "rank": 1},
                    {"package_id": "pkg-installed", "versions": ["1.0"], "rank": 2},
                    {"package_id": "pkg-third", "versions": ["1.0"], "rank": 3}
                ]
            },
            "packages": {
                "pkg-popular": {
                    "id": "pkg-popular",
                    "display_name": "Popular Package",
                    "repository": "https://github.com/test/popular",
                    "downloads": 5000,
                    "versions": {}
                },
                "pkg-installed": {
                    "id": "pkg-installed",
                    "display_name": "Installed Package",
                    "repository": "https://github.com/test/installed",
                    "downloads": 1000,
                    "versions": {}
                },
                "pkg-third": {
                    "id": "pkg-third",
                    "display_name": "Third Package",
                    "repository": "https://github.com/test/third",
                    "downloads": 100,
                    "versions": {}
                }
            },
            "stats": {}
        }

        with open(mappings_path, 'w') as f:
            json.dump(mappings_data, f)

        # Simulate rank 2 package is already installed
        config = test_env.pyproject.load()
        config.setdefault('tool', {}).setdefault('comfydock', {}).setdefault('nodes', {})
        config['tool']['comfydock']['nodes']['pkg-installed'] = {
            'name': 'pkg-installed',
            'source': 'registry',
            'version': '1.0'
        }
        test_env.pyproject.save(config)

        # Create workflow using this node
        workflow_data = {
            "nodes": [
                {
                    "id": "1",
                    "type": "CustomNode",
                    "inputs": [{"name": "input1", "type": "STRING"}],
                    "outputs": [],
                    "properties": {},
                    "widgets_values": []
                }
            ],
            "links": [],
            "groups": [],
            "config": {},
            "extra": {},
            "version": 0.4
        }

        simulate_comfyui_save_workflow(test_env, "test_multi", workflow_data)

        # ACT: Resolve workflow
        analysis = test_env.workflow_manager.analyze_workflow("test_multi")
        resolution = test_env.workflow_manager.resolve_workflow(analysis)

        # ASSERT: Should auto-select installed package (rank 2), not rank 1
        assert len(resolution.nodes_resolved) == 1
        assert resolution.nodes_resolved[0].package_id == "pkg-installed"
        assert len(resolution.nodes_ambiguous) == 0  # Not ambiguous!

    def test_auto_select_rank_1_when_none_installed(self, test_env):
        """When no packages installed, auto-select rank 1."""
        # ARRANGE
        mappings_path = test_env.workspace_paths.cache / "custom_nodes" / "node_mappings.json"
        mappings_data = {
            "version": "2025.10.10",
            "mappings": {
                "CustomNode::abc123": [
                    {"package_id": "pkg-rank1", "versions": [], "rank": 1},
                    {"package_id": "pkg-rank2", "versions": [], "rank": 2}
                ]
            },
            "packages": {
                "pkg-rank1": {"id": "pkg-rank1", "display_name": "Rank 1", "versions": {}},
                "pkg-rank2": {"id": "pkg-rank2", "display_name": "Rank 2", "versions": {}}
            },
            "stats": {}
        }

        with open(mappings_path, 'w') as f:
            json.dump(mappings_data, f)

        # No installed packages
        workflow_data = {
            "nodes": [
                {
                    "id": "1",
                    "type": "CustomNode",
                    "inputs": [{"name": "input1", "type": "STRING"}],
                    "outputs": [],
                    "properties": {},
                    "widgets_values": []
                }
            ],
            "links": [],
            "version": 0.4
        }

        simulate_comfyui_save_workflow(test_env, "test_rank1", workflow_data)

        # ACT
        analysis = test_env.workflow_manager.analyze_workflow("test_rank1")
        resolution = test_env.workflow_manager.resolve_workflow(analysis)

        # ASSERT: Should auto-select rank 1
        assert len(resolution.nodes_resolved) == 1
        assert resolution.nodes_resolved[0].package_id == "pkg-rank1"
        assert resolution.nodes_resolved[0].rank == 1

    def test_multiple_installed_picks_highest_rank(self, test_env):
        """When multiple packages installed, pick the one with highest rank."""
        # ARRANGE
        mappings_path = test_env.workspace_paths.cache / "custom_nodes" / "node_mappings.json"
        mappings_data = {
            "version": "2025.10.10",
            "mappings": {
                "CustomNode::abc123": [
                    {"package_id": "pkg-rank1", "versions": [], "rank": 1},
                    {"package_id": "pkg-rank2", "versions": [], "rank": 2},
                    {"package_id": "pkg-rank3", "versions": [], "rank": 3}
                ]
            },
            "packages": {
                "pkg-rank1": {"id": "pkg-rank1", "versions": {}},
                "pkg-rank2": {"id": "pkg-rank2", "versions": {}},
                "pkg-rank3": {"id": "pkg-rank3", "versions": {}}
            },
            "stats": {}
        }

        with open(mappings_path, 'w') as f:
            json.dump(mappings_data, f)

        # Install rank 2 and rank 3 (not rank 1)
        config = test_env.pyproject.load()
        config['tool']['comfydock']['nodes']['pkg-rank2'] = {
            'name': 'pkg-rank2',
            'source': 'registry'
        }
        config['tool']['comfydock']['nodes']['pkg-rank3'] = {
            'name': 'pkg-rank3',
            'source': 'registry'
        }
        test_env.pyproject.save(config)

        workflow_data = {
            "nodes": [{"id": "1", "type": "CustomNode", "inputs": [], "outputs": []}],
            "links": [],
            "version": 0.4
        }

        simulate_comfyui_save_workflow(test_env, "test_best_installed", workflow_data)

        # ACT
        analysis = test_env.workflow_manager.analyze_workflow("test_best_installed")
        resolution = test_env.workflow_manager.resolve_workflow(analysis)

        # ASSERT: Should pick rank 2 (best installed)
        assert resolution.nodes_resolved[0].package_id == "pkg-rank2"


class TestAutoSelectConfiguration:
    """Test configurable auto-select behavior."""

    def test_auto_select_disabled_returns_all_packages(self, test_env):
        """With auto_select_ambiguous=False, all packages go to ambiguous list.

        This allows users to disable automatic selection and manually choose.
        """
        # ARRANGE
        mappings_path = test_env.workspace_paths.cache / "custom_nodes" / "node_mappings.json"
        mappings_data = {
            "version": "2025.10.10",
            "mappings": {
                "CustomNode::abc123": [
                    {"package_id": "pkg-1", "versions": [], "rank": 1},
                    {"package_id": "pkg-2", "versions": [], "rank": 2}
                ]
            },
            "packages": {
                "pkg-1": {"id": "pkg-1", "display_name": "Package 1", "versions": {}},
                "pkg-2": {"id": "pkg-2", "display_name": "Package 2", "versions": {}}
            },
            "stats": {}
        }

        with open(mappings_path, 'w') as f:
            json.dump(mappings_data, f)

        # Set configuration to disable auto-select
        config = test_env.pyproject.load()
        config['tool']['comfydock']['auto_select_ambiguous'] = False
        test_env.pyproject.save(config)

        workflow_data = {
            "nodes": [{"id": "1", "type": "CustomNode", "inputs": [], "outputs": []}],
            "links": [],
            "version": 0.4
        }

        simulate_comfyui_save_workflow(test_env, "test_no_auto", workflow_data)

        # ACT
        analysis = test_env.workflow_manager.analyze_workflow("test_no_auto")
        resolution = test_env.workflow_manager.resolve_workflow(analysis)

        # ASSERT: Should NOT auto-select, return all as ambiguous
        assert len(resolution.nodes_resolved) == 0
        assert len(resolution.nodes_ambiguous) == 1
        assert len(resolution.nodes_ambiguous[0]) == 2  # Both packages

    def test_auto_select_enabled_by_default(self, test_env):
        """Default behavior: auto-select is enabled."""
        # ARRANGE
        mappings_path = test_env.workspace_paths.cache / "custom_nodes" / "node_mappings.json"
        mappings_data = {
            "version": "2025.10.10",
            "mappings": {
                "CustomNode::abc": [
                    {"package_id": "pkg-1", "versions": [], "rank": 1},
                    {"package_id": "pkg-2", "versions": [], "rank": 2}
                ]
            },
            "packages": {
                "pkg-1": {"id": "pkg-1", "versions": {}},
                "pkg-2": {"id": "pkg-2", "versions": {}}
            },
            "stats": {}
        }

        with open(mappings_path, 'w') as f:
            json.dump(mappings_data, f)

        # NO config set = default enabled
        workflow_data = {
            "nodes": [{"id": "1", "type": "CustomNode", "inputs": [], "outputs": []}],
            "links": [],
            "version": 0.4
        }

        simulate_comfyui_save_workflow(test_env, "test_default", workflow_data)

        # ACT
        analysis = test_env.workflow_manager.analyze_workflow("test_default")
        resolution = test_env.workflow_manager.resolve_workflow(analysis)

        # ASSERT: Should auto-select (default behavior)
        assert len(resolution.nodes_resolved) == 1
        assert resolution.nodes_resolved[0].package_id == "pkg-1"  # rank 1


class TestRegistryVsFuzzySearchAmbiguity:
    """Test that registry ambiguity is handled differently from fuzzy search."""

    def test_registry_multi_package_not_treated_as_fuzzy(self, test_env):
        """Registry mappings with multiple packages should NOT go to ambiguous list."""
        # This tests the key distinction:
        # - Registry multiple packages (with ranks) → auto-select
        # - Fuzzy search multiple packages (no ranks) → ambiguous list

        # ARRANGE: Registry mapping with 2 packages
        mappings_path = test_env.workspace_paths.cache / "custom_nodes" / "node_mappings.json"
        mappings_data = {
            "version": "2025.10.10",
            "mappings": {
                "KnownNode::abc": [
                    {"package_id": "pkg-a", "versions": [], "rank": 1},
                    {"package_id": "pkg-b", "versions": [], "rank": 2}
                ]
            },
            "packages": {
                "pkg-a": {"id": "pkg-a", "versions": {}},
                "pkg-b": {"id": "pkg-b", "versions": {}}
            },
            "stats": {}
        }

        with open(mappings_path, 'w') as f:
            json.dump(mappings_data, f)

        workflow_data = {
            "nodes": [{"id": "1", "type": "KnownNode", "inputs": [], "outputs": []}],
            "links": [],
            "version": 0.4
        }

        simulate_comfyui_save_workflow(test_env, "test_registry_multi", workflow_data)

        # ACT
        analysis = test_env.workflow_manager.analyze_workflow("test_registry_multi")
        resolution = test_env.workflow_manager.resolve_workflow(analysis)

        # ASSERT: Registry multi-package should auto-resolve, NOT be ambiguous
        assert len(resolution.nodes_resolved) == 1
        assert len(resolution.nodes_ambiguous) == 0

    def test_fuzzy_search_goes_to_ambiguous_list(self, test_env):
        """Fuzzy search results (no exact mapping) should go to ambiguous list."""
        # This will need the node to NOT be in mappings, triggering search_packages()
        pytest.skip("Fuzzy search behavior unchanged - existing tests cover this")


class TestManagerPackageHandling:
    """Test Manager-only packages work correctly with ranking."""

    def test_manager_package_in_multi_package_mapping(self, test_env):
        """Manager packages can coexist with Registry packages in same mapping."""
        # ARRANGE
        mappings_path = test_env.workspace_paths.cache / "custom_nodes" / "node_mappings.json"
        mappings_data = {
            "version": "2025.10.10",
            "mappings": {
                "CustomNode::abc": [
                    {"package_id": "registry-pkg", "versions": ["1.0"], "rank": 1},
                    {"package_id": "manager_user_repo", "versions": [], "rank": 2, "source": "manager"}
                ]
            },
            "packages": {
                "registry-pkg": {
                    "id": "registry-pkg",
                    "display_name": "Registry Package",
                    "downloads": 1000,
                    "versions": {}
                },
                "manager_user_repo": {
                    "id": "manager_user_repo",
                    "display_name": "Manager Package",
                    "repository": "https://github.com/user/repo",
                    "downloads": 0,
                    "source": "manager",
                    "versions": {}
                }
            },
            "stats": {}
        }

        with open(mappings_path, 'w') as f:
            json.dump(mappings_data, f)

        workflow_data = {
            "nodes": [{"id": "1", "type": "CustomNode", "inputs": [], "outputs": []}],
            "links": [],
            "version": 0.4
        }

        simulate_comfyui_save_workflow(test_env, "test_manager", workflow_data)

        # ACT
        analysis = test_env.workflow_manager.analyze_workflow("test_manager")
        resolution = test_env.workflow_manager.resolve_workflow(analysis)

        # ASSERT: Should auto-select registry package (rank 1)
        assert len(resolution.nodes_resolved) == 1
        assert resolution.nodes_resolved[0].package_id == "registry-pkg"


class TestRankInformation:
    """Test that rank information flows through the resolution pipeline."""

    def test_rank_displayed_in_resolution_result(self, test_env):
        """Resolved packages should include rank for CLI display."""
        # ARRANGE
        mappings_path = test_env.workspace_paths.cache / "custom_nodes" / "node_mappings.json"
        mappings_data = {
            "version": "2025.10.10",
            "mappings": {
                "TestNode::abc": [
                    {"package_id": "pkg-1", "versions": [], "rank": 1},
                    {"package_id": "pkg-2", "versions": [], "rank": 2}
                ]
            },
            "packages": {
                "pkg-1": {"id": "pkg-1", "versions": {}},
                "pkg-2": {"id": "pkg-2", "versions": {}}
            },
            "stats": {}
        }

        with open(mappings_path, 'w') as f:
            json.dump(mappings_data, f)

        workflow_data = {
            "nodes": [{"id": "1", "type": "TestNode", "inputs": [], "outputs": []}],
            "links": [],
            "version": 0.4
        }

        simulate_comfyui_save_workflow(test_env, "test_rank_info", workflow_data)

        # ACT
        analysis = test_env.workflow_manager.analyze_workflow("test_rank_info")
        resolution = test_env.workflow_manager.resolve_workflow(analysis)

        # ASSERT: Rank should be accessible
        resolved_node = resolution.nodes_resolved[0]
        assert hasattr(resolved_node, 'rank')
        assert resolved_node.rank == 1

        # For Q3: CLI can display "rank 1 of 2" by checking total packages
        # (This would be done in CLI layer, not here)


class TestSinglePackageBehavior:
    """Test that single-package mappings behave like v1.0."""

    def test_single_package_cleanly_resolves(self, test_env):
        """Single package mapping should resolve without ambiguity."""
        # ARRANGE
        mappings_path = test_env.workspace_paths.cache / "custom_nodes" / "node_mappings.json"
        mappings_data = {
            "version": "2025.10.10",
            "mappings": {
                "SingleNode::abc": [
                    {"package_id": "only-pkg", "versions": ["1.0"], "rank": 1}
                ]
            },
            "packages": {
                "only-pkg": {"id": "only-pkg", "display_name": "Only Package", "versions": {}}
            },
            "stats": {}
        }

        with open(mappings_path, 'w') as f:
            json.dump(mappings_data, f)

        workflow_data = {
            "nodes": [{"id": "1", "type": "SingleNode", "inputs": [], "outputs": []}],
            "links": [],
            "version": 0.4
        }

        simulate_comfyui_save_workflow(test_env, "test_single", workflow_data)

        # ACT
        analysis = test_env.workflow_manager.analyze_workflow("test_single")
        resolution = test_env.workflow_manager.resolve_workflow(analysis)

        # ASSERT: Should resolve cleanly
        assert len(resolution.nodes_resolved) == 1
        assert resolution.nodes_resolved[0].package_id == "only-pkg"
        assert len(resolution.nodes_ambiguous) == 0
