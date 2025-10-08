"""Test GitHub URL normalization to prevent duplicate node entries.

This test demonstrates the bug where manually entered GitHub URLs
are stored as-is instead of being normalized to registry IDs,
causing duplicate entries and version mismatches.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from conftest import load_workflow_fixture, simulate_comfyui_save_workflow


@pytest.fixture
def test_env_with_kjnodes_mapping(test_env):
    """Add KJNodes to the global mappings for testing normalization."""
    # Add KJNodes package to the mappings
    mappings_path = test_env.workspace_paths.cache / "custom_nodes/node_mappings.json"

    mappings_data = {
        "version": "test",
        "generated_at": "2025-01-01",
        "stats": {},
        "mappings": {
            "SetNode": {
                "package_id": "comfyui-kjnodes",
                "versions": [],
                "source": "registry"
            },
            "GetNode": {
                "package_id": "comfyui-kjnodes",
                "versions": [],
                "source": "registry"
            }
        },
        "packages": {
            "comfyui-kjnodes": {
                "id": "comfyui-kjnodes",
                "display_name": "ComfyUI-KJNodes",
                "repository": "https://github.com/kijai/ComfyUI-KJNodes.git",
                "description": "KJNodes for ComfyUI",
                "versions": {}
            }
        }
    }

    with open(mappings_path, 'w') as f:
        json.dump(mappings_data, f)

    # Reload the global node resolver with new mappings
    from comfydock_core.resolvers.global_node_resolver import GlobalNodeResolver
    test_env.workflow_manager.global_node_resolver = GlobalNodeResolver(mappings_path=mappings_path)

    return test_env


class TestGitHubURLNormalization:
    """Test that GitHub URLs are normalized to registry IDs during resolution."""

    def test_manual_github_url_normalized_to_registry_id(self, test_env_with_kjnodes_mapping, test_models, workflow_fixtures):
        """
        FAILING TEST: Demonstrates GitHub URL duplication bug.

        When user manually enters a GitHub URL for a node that exists in the registry,
        it should be normalized to the registry ID to prevent duplicates.

        Current behavior (BUG):
        - User enters: https://github.com/kijai/ComfyUI-KJNodes.git
        - System stores: https://github.com/kijai/ComfyUI-KJNodes.git
        - Later workflow references: comfyui-kjnodes
        - Result: Two entries for same package → conflicts

        Expected behavior:
        - User enters: https://github.com/kijai/ComfyUI-KJNodes.git
        - System normalizes to: comfyui-kjnodes (registry ID)
        - Result: Single consistent entry
        """
        from comfydock_core.models.workflow import ResolvedNodePackage
        from comfydock_core.strategies.auto import AutoModelStrategy

        # Use the fixture with KJNodes mappings
        test_env = test_env_with_kjnodes_mapping

        # Load workflow with KJNodes nodes (SetNode, GetNode)
        workflow = load_workflow_fixture(workflow_fixtures, "kjnodes_workflow")
        simulate_comfyui_save_workflow(test_env, "test_workflow", workflow)

        # Create a manual resolution strategy that simulates user entering GitHub URL
        class ManualGitHubURLStrategy:
            """Simulates user manually entering GitHub URL."""

            def resolve_unknown_node(self, node_type, possible):
                # Simulate user typing GitHub URL for KJNodes
                if "SetNode" in node_type or "GetNode" in node_type:
                    github_url = "https://github.com/kijai/ComfyUI-KJNodes.git"
                    return ResolvedNodePackage(
                        package_id=github_url,  # BUG: Should be normalized to registry ID
                        package_data=None,
                        node_type=node_type,
                        versions=[],
                        match_type="manual",
                        match_confidence=1.0
                    )
                return None

        # Resolve workflow with manual strategy
        workflow_status = test_env.workflow_manager.get_workflow_status()
        analysis = workflow_status.analyzed_workflows[0]

        resolution = test_env.workflow_manager.fix_resolution(
            analysis.resolution,
            node_strategy=ManualGitHubURLStrategy(),
            model_strategy=AutoModelStrategy()
        )

        # Apply resolution (saves to node_mappings and workflow)
        test_env.workflow_manager.apply_resolution(
            resolution,
            workflow_name="test_workflow",
            model_refs=analysis.dependencies.found_models
        )

        # Check node_mappings in pyproject.toml
        mappings = test_env.pyproject.node_mappings.get_all_mappings()

        # ASSERTION 1: GitHub URL should be normalized to registry ID
        # Current behavior: Stores GitHub URL directly
        # Expected behavior: Stores "comfyui-kjnodes"
        for node_type, package_id in mappings.items():
            if "SetNode" in node_type or "GetNode" in node_type:
                assert not package_id.startswith("https://"), \
                    f"GitHub URL should be normalized to registry ID, got: {package_id}"
                assert package_id == "comfyui-kjnodes", \
                    f"Expected registry ID 'comfyui-kjnodes', got: {package_id}"

        # ASSERTION 2: Workflow nodes list should not have duplicates
        config = test_env.pyproject.load()
        workflow_nodes = config.get('tool', {}).get('comfydock', {}).get('workflows', {}).get('test_workflow', {}).get('nodes', [])

        # Count occurrences of KJNodes (should be 1, not multiple)
        kjnodes_count = sum(1 for n in workflow_nodes if 'kjnodes' in n.lower() or 'ComfyUI-KJNodes' in n)

        assert kjnodes_count == 1, \
            f"Should have exactly 1 KJNodes entry, found {kjnodes_count}. Nodes: {workflow_nodes}"

    def test_empty_manual_input_skips_gracefully(self, test_env, test_models, workflow_fixtures):
        """
        Test that empty manual input is handled gracefully.

        When user presses enter without typing anything in manual mode,
        the system should skip the node and continue.
        """
        from comfydock_core.strategies.auto import AutoModelStrategy

        # Load workflow
        workflow = load_workflow_fixture(workflow_fixtures, "kjnodes_workflow")
        simulate_comfyui_save_workflow(test_env, "test_workflow", workflow)

        # Create strategy that simulates empty input
        class EmptyInputStrategy:
            """Simulates user pressing enter without input."""

            def resolve_unknown_node(self, node_type, possible):
                # Simulate empty input by returning None
                return None

        # Resolve workflow - should not crash
        workflow_status = test_env.workflow_manager.get_workflow_status()
        analysis = workflow_status.analyzed_workflows[0]

        resolution = test_env.workflow_manager.fix_resolution(
            analysis.resolution,
            node_strategy=EmptyInputStrategy(),
            model_strategy=AutoModelStrategy()
        )

        # Should complete without error
        assert resolution is not None

        # Unresolved nodes should remain unresolved (not crash or create invalid entries)
        assert len(resolution.nodes_unresolved) > 0, \
            "Empty input should leave nodes unresolved, not create invalid entries"

    def test_registry_id_preserved_when_entered_directly(self, test_env, test_models, workflow_fixtures):
        """
        Test that registry IDs entered directly are preserved.

        When user enters a registry ID (not a GitHub URL), it should
        be stored as-is without modification.
        """
        from comfydock_core.models.workflow import ResolvedNodePackage
        from comfydock_core.strategies.auto import AutoModelStrategy

        workflow = load_workflow_fixture(workflow_fixtures, "kjnodes_workflow")
        simulate_comfyui_save_workflow(test_env, "test_workflow", workflow)

        class RegistryIDStrategy:
            """Simulates user entering registry ID directly."""

            def resolve_unknown_node(self, node_type, possible):
                if "SetNode" in node_type or "GetNode" in node_type:
                    return ResolvedNodePackage(
                        package_id="comfyui-kjnodes",  # Registry ID, not GitHub URL
                        package_data=None,
                        node_type=node_type,
                        versions=[],
                        match_type="manual",
                        match_confidence=1.0
                    )
                return None

        workflow_status = test_env.workflow_manager.get_workflow_status()
        analysis = workflow_status.analyzed_workflows[0]

        resolution = test_env.workflow_manager.fix_resolution(
            analysis.resolution,
            node_strategy=RegistryIDStrategy(),
            model_strategy=AutoModelStrategy()
        )

        test_env.workflow_manager.apply_resolution(
            resolution,
            workflow_name="test_workflow",
            model_refs=analysis.dependencies.found_models
        )

        # Check that registry ID is preserved
        mappings = test_env.pyproject.node_mappings.get_all_mappings()

        for node_type, package_id in mappings.items():
            if "SetNode" in node_type or "GetNode" in node_type:
                assert package_id == "comfyui-kjnodes", \
                    f"Registry ID should be preserved, got: {package_id}"
