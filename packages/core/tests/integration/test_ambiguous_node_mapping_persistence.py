"""Integration test for ambiguous node mapping persistence bug.

Tests that when a user selects from an ambiguous list (e.g., multiple matches
from GlobalNodeResolver), the choice is properly saved to node_mappings.

Bug: User selects "1" from ambiguous list, but mapping is not saved because
match_type remains "fuzzy" instead of being changed to "user_confirmed".
"""

import pytest
import json
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from conftest import simulate_comfyui_save_workflow


class TestAmbiguousNodeMappingPersistence:
    """Test that ambiguous node selections persist to node_mappings."""

    def test_ambiguous_selection_saves_to_node_mappings(self, test_env):
        """When user selects from ambiguous matches, mapping should be saved.

        This tests the real-world scenario:
        1. Node 'Switch any [Crystools]' has multiple matches in global table
        2. GlobalNodeResolver returns list with match_type="fuzzy" (or "type_only")
        3. User selects option "1" from the ambiguous list
        4. The selection should be saved to node_mappings for future use

        Bug: Currently the selection is NOT saved because match_type stays "fuzzy"
        instead of being updated to "user_confirmed".
        """
        # ARRANGE: Create workflow with a node that will match ambiguously
        workflow_data = {
            "nodes": [
                {
                    "id": "1",
                    "type": "Switch any [Crystools]",  # Real-world example
                    "pos": [100, 100],
                    "size": [200, 100],
                    "flags": {},
                    "order": 0,
                    "mode": 0,
                    "inputs": [],
                    "outputs": [],
                    "properties": {},  # No properties - will use global table
                    "widgets_values": []
                }
            ],
            "links": [],
            "groups": [],
            "config": {},
            "extra": {},
            "version": 0.4
        }

        # Set up global mappings with MULTIPLE matches for this node (v2.0 schema)
        mappings_path = test_env.workspace_paths.cache / "custom_nodes" / "node_mappings.json"
        with open(mappings_path, 'r') as f:
            mappings = json.load(f)

        # Add two packages that could match
        mappings["packages"]["ComfyUI-Crystools"] = {
            "id": "ComfyUI-Crystools",
            "display_name": "ComfyUI-Crystools",
            "description": "With this suit, you can see the resources monitor...",
            "versions": {}
        }

        mappings["packages"]["ComfyUI-WBLESS"] = {
            "id": "ComfyUI-WBLESS",
            "display_name": "ComfyUI-WBLESS",
            "description": "Nodes: Set Global Variable, Get Global Variable...",
            "versions": {}
        }

        # Create multi-package mapping (v2.0 schema: array of packages)
        # This simulates what GlobalNodeResolver would find
        mappings["mappings"]["Switch any [Crystools]::_"] = [
            {
                "package_id": "ComfyUI-Crystools",
                "versions": [],
                "rank": 1
            },
            {
                "package_id": "ComfyUI-WBLESS",
                "versions": [],
                "rank": 2
            }
        ]

        with open(mappings_path, 'w') as f:
            json.dump(mappings, f)

        simulate_comfyui_save_workflow(test_env, "test_ambiguous", workflow_data)

        # Disable auto-select so we get ambiguous results
        config = test_env.pyproject.load()
        config['tool']['comfydock']['auto_select_ambiguous'] = False
        test_env.pyproject.save(config)

        # ACT: Analyze and resolve - this will find multiple matches
        analysis = test_env.workflow_manager.analyze_workflow("test_ambiguous")
        resolution = test_env.workflow_manager.resolve_workflow(analysis)

        # Should have ambiguous matches (auto-select disabled)
        assert len(resolution.nodes_ambiguous) > 0, \
            "Should have ambiguous node matches from global table"

        # Find the ambiguous node
        ambiguous_node_packages = None
        for packages in resolution.nodes_ambiguous:
            if packages[0].node_type == "Switch any [Crystools]":
                ambiguous_node_packages = packages
                break

        assert ambiguous_node_packages is not None, \
            "Should find 'Switch any [Crystools]' in ambiguous list"

        assert len(ambiguous_node_packages) >= 2, \
            f"Should have multiple matches. Got: {len(ambiguous_node_packages)}"

        # Simulate what InteractiveNodeStrategy does when user selects from ambiguous list
        # The fix makes _resolve_ambiguous() call _create_resolved_from_match()
        # which wraps the selection with match_type="user_confirmed"
        from comfydock_cli.strategies.interactive import InteractiveNodeStrategy

        strategy = InteractiveNodeStrategy()
        original_selected = ambiguous_node_packages[0]

        # Before the fix: InteractiveNodeStrategy would return `possible[idx]` directly
        # After the fix: It calls _create_resolved_from_match() to wrap with correct match_type
        selected_by_user = strategy._create_resolved_from_match(
            "Switch any [Crystools]",
            original_selected
        )

        # VERIFY: The wrapped selection should now have match_type="user_confirmed"
        assert selected_by_user.match_type == "user_confirmed", \
            f"After wrapping, match_type should be 'user_confirmed', got: {selected_by_user.match_type}"

        # Now simulate applying the resolution with the properly wrapped package
        from comfydock_core.models.workflow import ResolutionResult

        fixed_resolution = ResolutionResult(
            nodes_resolved=[selected_by_user],  # User's selection (wrapped)
            nodes_unresolved=[],
            nodes_ambiguous=[],
            models_resolved={},
            models_unresolved=[],
            models_ambiguous=[]
        )

        # ACT: Apply the resolution (this should save to node_mappings)
        test_env.workflow_manager.apply_resolution(
            resolution=fixed_resolution,
            workflow_name="test_ambiguous",
            model_refs=[]
        )

        # ASSERT: Check that node_mappings was updated
        config = test_env.pyproject.load()
        node_mappings = config.get('tool', {}).get('comfydock', {}).get('node_mappings', {})

        # THIS IS THE BUG: The mapping is NOT saved because match_type is "fuzzy"
        # not "user_confirmed", so it doesn't pass the user_intervention_types check
        assert "Switch any [Crystools]" in node_mappings, \
            f"BUG: Node mapping should be saved! Current mappings: {list(node_mappings.keys())}"

        assert node_mappings["Switch any [Crystools]"] == selected_by_user.package_id, \
            f"Mapping should point to user's selection: {selected_by_user.package_id}"

    def test_ambiguous_selection_with_user_confirmed_match_type(self, test_env):
        """When match_type is properly set to 'user_confirmed', mapping IS saved.

        This is the CONTROL test showing what SHOULD happen when the match_type
        is correctly set to "user_confirmed" by the interactive strategy.
        """
        # ARRANGE: Same setup as above
        workflow_data = {
            "nodes": [
                {
                    "id": "1",
                    "type": "Test Node Type",
                    "pos": [100, 100],
                    "size": [200, 100],
                    "flags": {},
                    "order": 0,
                    "mode": 0,
                    "inputs": [],
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

        # Set up global mappings
        mappings_path = test_env.workspace_paths.cache / "custom_nodes" / "node_mappings.json"
        with open(mappings_path, 'r') as f:
            mappings = json.load(f)

        mappings["packages"]["test-package"] = {
            "id": "test-package",
            "display_name": "Test Package",
            "versions": {}
        }

        with open(mappings_path, 'w') as f:
            json.dump(mappings, f)

        simulate_comfyui_save_workflow(test_env, "test_confirmed", workflow_data)

        # ACT: Create resolution with user_confirmed match_type (the FIX)
        from comfydock_core.models.workflow import ResolvedNodePackage, ResolutionResult

        user_selected = ResolvedNodePackage(
            package_id="test-package",
            package_data=None,
            node_type="Test Node Type",
            versions=[],
            match_type="user_confirmed",  # THE FIX: Proper match_type
            match_confidence=1.0
        )

        resolution = ResolutionResult(
            nodes_resolved=[user_selected],
            nodes_unresolved=[],
            nodes_ambiguous=[],
            models_resolved={},
            models_unresolved=[],
            models_ambiguous=[]
        )

        # Apply resolution
        test_env.workflow_manager.apply_resolution(
            resolution=resolution,
            workflow_name="test_confirmed",
            model_refs=[]
        )

        # ASSERT: With correct match_type, mapping SHOULD be saved
        config = test_env.pyproject.load()
        node_mappings = config.get('tool', {}).get('comfydock', {}).get('node_mappings', {})

        assert "Test Node Type" in node_mappings, \
            "With 'user_confirmed' match_type, mapping should be saved"

        assert node_mappings["Test Node Type"] == "test-package"
