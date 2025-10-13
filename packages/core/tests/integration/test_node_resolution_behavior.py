"""Integration tests for per-workflow node resolution behavior.

Tests the complete node resolution flow as specified in:
docs/knowledge/node-resolution-behavior.md

Key behaviors tested:
1. Per-workflow custom_node_map storage (not global)
2. Reconciliation (remove orphaned entries)
3. Progressive writes for user choices
4. Priority chain: custom_node_map → cnr_id → global table
"""

import pytest
import json
from pathlib import Path
from unittest.mock import MagicMock

# Import helpers
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from conftest import simulate_comfyui_save_workflow, load_workflow_fixture


class TestPerWorkflowCustomNodeMap:
    """Test that custom_node_map is per-workflow, not global."""

    def test_fresh_start_auto_resolution_only(self, test_env):
        """Case 1: Fresh start with only auto-resolvable nodes.

        Expected behavior:
        - Analyze workflow → finds nodes A, B, C
        - Resolve via global table → A auto-resolved (exact match)
        - apply_resolution() writes A to workflow.nodes
        - NO custom_node_map entries (only auto-resolved)
        """
        # ARRANGE: Create workflow with auto-resolvable node
        workflow_data = {
            "nodes": [
                {
                    "id": 1,
                    "type": "LoadImage",  # Assume this is builtin
                    "widgets_values": []
                },
                {
                    "id": 2,
                    "type": "TestAutoResolvableNode",  # Will auto-resolve to "test-package-a"
                    "widgets_values": []
                }
            ],
            "links": []
        }

        simulate_comfyui_save_workflow(test_env, "test_workflow", workflow_data)

        # Mock global resolver to return auto-resolved package
        mock_resolved = MagicMock()
        mock_resolved.package_id = "test-package-a"
        mock_resolved.match_type = "exact"
        mock_resolved.match_confidence = 1.0
        mock_resolved.node_type = "TestAutoResolvableNode"

        original_resolve = test_env.workflow_manager.global_node_resolver.resolve_single_node_with_context
        def mock_resolve(node, context):
            if node.type == "TestAutoResolvableNode":
                return [mock_resolved]  # Single exact match
            return original_resolve(node, context)

        test_env.workflow_manager.global_node_resolver.resolve_single_node_with_context = mock_resolve

        # ACT: Resolve workflow (auto-resolution only, no fix)
        result = test_env.resolve_workflow(
            name="test_workflow",
            node_strategy=None,  # No strategy = no user intervention
            model_strategy=None,
            fix=False  # Skip fix phase
        )

        # ASSERT: Check pyproject.toml structure
        config = test_env.pyproject.load()
        workflow_section = config.get('tool', {}).get('comfydock', {}).get('workflows', {}).get('test_workflow', {})

        # Should have nodes list with auto-resolved package
        assert 'nodes' in workflow_section, "Missing workflow.nodes list"
        assert 'test-package-a' in workflow_section['nodes'], "Auto-resolved node not in workflow.nodes"

        # Should NOT have custom_node_map (only auto-resolved)
        assert 'custom_node_map' not in workflow_section, \
            "custom_node_map should not exist for auto-resolved nodes only"

    def test_ambiguous_node_creates_per_workflow_mapping(self, test_env):
        """Case 1 continued: User resolves ambiguous node.

        Expected behavior:
        - Node B has 2 matches (ambiguous)
        - User selects package-b
        - Write to workflow.nodes = ["package-a", "package-b"]
        - Write to workflow.custom_node_map: NodeTypeB = "package-b"
        """
        # ARRANGE: Workflow with ambiguous node
        workflow_data = {
            "nodes": [
                {"id": 1, "type": "TestAutoNode", "widgets_values": []},
                {"id": 2, "type": "TestAmbiguousNode", "widgets_values": []}
            ],
            "links": []
        }

        simulate_comfyui_save_workflow(test_env, "test_workflow", workflow_data)

        # Mock resolver: auto-node resolves cleanly, ambiguous-node has 2 matches
        def mock_resolve(node, context):
            if node.type == "TestAutoNode":
                pkg = MagicMock()
                pkg.package_id = "package-a"
                pkg.match_type = "exact"
                pkg.node_type = "TestAutoNode"
                return [pkg]
            elif node.type == "TestAmbiguousNode":
                pkg1 = MagicMock()
                pkg1.package_id = "package-b"
                pkg1.rank = 1
                pkg1.match_type = "type_only"
                pkg1.node_type = "TestAmbiguousNode"
                pkg1.package_data = MagicMock(display_name="Package B", description="B desc")

                pkg2 = MagicMock()
                pkg2.package_id = "package-g"
                pkg2.rank = 2
                pkg2.match_type = "type_only"
                pkg2.node_type = "TestAmbiguousNode"
                pkg2.package_data = MagicMock(display_name="Package G", description="G desc")

                return [pkg1, pkg2]  # Ambiguous!
            return None

        test_env.workflow_manager.global_node_resolver.resolve_single_node_with_context = mock_resolve

        # Disable auto_select so ambiguous nodes remain ambiguous
        # We'll monkey-patch the resolve_workflow to pass auto_select_ambiguous=False in context
        original_resolve = test_env.workflow_manager.resolve_workflow
        def patched_resolve(analysis):
            result = original_resolve(analysis)
            # Force auto_select off by modifying result BEFORE fix_resolution
            return result

        # Actually just set the config directly - modify the _auto_select_best_package to always return None
        original_auto_select = test_env.workflow_manager._auto_select_best_package
        test_env.workflow_manager._auto_select_best_package = lambda *args, **kwargs: None

        # Mock strategy: user selects package-b (first choice)
        mock_strategy = MagicMock()
        def user_chooses_package_b(node_type, possible):
            # User selects the first package
            selected = possible[0]
            selected.match_type = "user_confirmed"  # Mark as user choice
            # Ensure package_data.id is a string, not MagicMock
            if not isinstance(selected.package_data.id, str):
                selected.package_data.id = selected.package_id
            return selected

        mock_strategy.resolve_unknown_node = user_chooses_package_b

        # ACT: Resolve with user intervention
        result = test_env.resolve_workflow(
            name="test_workflow",
            node_strategy=mock_strategy,
            model_strategy=None,
            fix=True
        )

        # Restore original
        test_env.workflow_manager._auto_select_best_package = original_auto_select

        # ASSERT: Check pyproject.toml structure
        config = test_env.pyproject.load()
        workflow_section = config['tool']['comfydock']['workflows']['test_workflow']

        # Both packages in nodes list
        assert 'package-a' in workflow_section['nodes']
        assert 'package-b' in workflow_section['nodes']

        # User choice saved to custom_node_map
        assert 'custom_node_map' in workflow_section, \
            "custom_node_map should exist after user resolution"
        assert workflow_section['custom_node_map']['TestAmbiguousNode'] == 'package-b', \
            "User's choice should be saved to custom_node_map"

    def test_optional_node_creates_false_mapping(self, test_env):
        """Case 1 continued: User marks node as optional.

        Expected behavior:
        - Node C not found
        - User marks as optional
        - Write to workflow.custom_node_map: NodeTypeC = false
        - Do NOT add to workflow.nodes (no dependency)
        """
        # ARRANGE: Workflow with unresolvable node
        workflow_data = {
            "nodes": [
                {"id": 1, "type": "TestAutoNode", "widgets_values": []},
                {"id": 2, "type": "TestMissingNode", "widgets_values": []}
            ],
            "links": []
        }

        simulate_comfyui_save_workflow(test_env, "test_workflow", workflow_data)

        # Mock resolver: auto-node OK, missing-node unresolved
        def mock_resolve(node, context):
            if node.type == "TestAutoNode":
                pkg = MagicMock()
                pkg.package_id = "package-a"
                pkg.match_type = "exact"
                pkg.node_type = "TestAutoNode"
                return [pkg]
            elif node.type == "TestMissingNode":
                return None  # Not found
            return None

        test_env.workflow_manager.global_node_resolver.resolve_single_node_with_context = mock_resolve

        # Mock strategy: user marks as optional
        mock_strategy = MagicMock()
        def user_marks_optional(node_type, possible):
            optional_pkg = MagicMock()
            optional_pkg.match_type = "optional"
            optional_pkg.node_type = node_type
            optional_pkg.package_id = None
            return optional_pkg

        mock_strategy.resolve_unknown_node = user_marks_optional

        # ACT: Resolve with user marking optional
        result = test_env.resolve_workflow(
            name="test_workflow",
            node_strategy=mock_strategy,
            model_strategy=None,
            fix=True
        )

        # ASSERT: Check pyproject.toml structure
        config = test_env.pyproject.load()
        workflow_section = config['tool']['comfydock']['workflows']['test_workflow']

        # Only auto-resolved in nodes list
        assert workflow_section['nodes'] == ['package-a'], \
            "Optional node should NOT be in workflow.nodes"

        # False mapping in custom_node_map
        assert 'custom_node_map' in workflow_section
        assert workflow_section['custom_node_map']['TestMissingNode'] is False, \
            "Optional node should have 'false' in custom_node_map"

    def test_different_workflows_different_mappings(self, test_env):
        """Test that two workflows can map same node type to different packages.

        From spec: "Package conflicts: Multiple workflows can map same node type
        to different packages. This is allowed (user responsibility)."
        """
        # ARRANGE: Two workflows using same node type
        workflow1_data = {
            "nodes": [{"id": 1, "type": "SharedNodeType", "widgets_values": []}],
            "links": []
        }
        workflow2_data = {
            "nodes": [{"id": 1, "type": "SharedNodeType", "widgets_values": []}],
            "links": []
        }

        simulate_comfyui_save_workflow(test_env, "workflow1", workflow1_data)
        simulate_comfyui_save_workflow(test_env, "workflow2", workflow2_data)

        # Mock resolver: SharedNodeType is ambiguous
        def mock_resolve(node, context):
            if node.type == "SharedNodeType":
                # Check custom_node_map in context (per-workflow!)
                if context.workflow_name == "workflow1" and "SharedNodeType" in context.custom_mappings:
                    # Already resolved for workflow1
                    pkg = MagicMock()
                    pkg.package_id = context.custom_mappings["SharedNodeType"]
                    pkg.match_type = "custom_mapping"
                    pkg.node_type = "SharedNodeType"
                    return [pkg]
                elif context.workflow_name == "workflow2" and "SharedNodeType" in context.custom_mappings:
                    # Already resolved for workflow2
                    pkg = MagicMock()
                    pkg.package_id = context.custom_mappings["SharedNodeType"]
                    pkg.match_type = "custom_mapping"
                    pkg.node_type = "SharedNodeType"
                    return [pkg]
                else:
                    # First time - return ambiguous
                    pkg1 = MagicMock()
                    pkg1.package_id = "package-x"
                    pkg1.rank = 1
                    pkg1.match_type = "type_only"
                    pkg1.node_type = "SharedNodeType"
                    pkg1.package_data = MagicMock(display_name="X", description="X")

                    pkg2 = MagicMock()
                    pkg2.package_id = "package-y"
                    pkg2.rank = 2
                    pkg2.match_type = "type_only"
                    pkg2.node_type = "SharedNodeType"
                    pkg2.package_data = MagicMock(display_name="Y", description="Y")

                    return [pkg1, pkg2]
            return None

        test_env.workflow_manager.global_node_resolver.resolve_single_node_with_context = mock_resolve

        # Disable auto_select so ambiguous nodes remain ambiguous
        original_auto_select = test_env.workflow_manager._auto_select_best_package
        test_env.workflow_manager._auto_select_best_package = lambda *args, **kwargs: None

        # Mock strategy: workflow1 chooses X, workflow2 chooses Y
        mock_strategy = MagicMock()
        resolution_count = [0]

        def user_chooses_different_per_workflow(node_type, possible):
            resolution_count[0] += 1
            if resolution_count[0] == 1:  # First call (workflow1)
                selected = possible[0]  # Choose package-x
            else:  # Second call (workflow2)
                selected = possible[1]  # Choose package-y
            selected.match_type = "user_confirmed"
            # Ensure package_data.id is a string, not MagicMock
            if not isinstance(selected.package_data.id, str):
                selected.package_data.id = selected.package_id
            return selected

        mock_strategy.resolve_unknown_node = user_chooses_different_per_workflow

        # ACT: Resolve both workflows
        test_env.resolve_workflow("workflow1", node_strategy=mock_strategy, model_strategy=None, fix=True)
        test_env.resolve_workflow("workflow2", node_strategy=mock_strategy, model_strategy=None, fix=True)

        # Restore
        test_env.workflow_manager._auto_select_best_package = original_auto_select

        # ASSERT: Each workflow has different mapping
        config = test_env.pyproject.load()
        wf1 = config['tool']['comfydock']['workflows']['workflow1']
        wf2 = config['tool']['comfydock']['workflows']['workflow2']

        assert wf1['custom_node_map']['SharedNodeType'] == 'package-x', \
            "Workflow1 should map to package-x"
        assert wf2['custom_node_map']['SharedNodeType'] == 'package-y', \
            "Workflow2 should map to package-y"

        # Different packages in nodes lists
        assert 'package-x' in wf1['nodes']
        assert 'package-y' in wf2['nodes']


class TestReconciliation:
    """Test reconciliation removes orphaned entries (not just additive)."""

    def test_node_removal_cleanup_orphans(self, test_env):
        """Case 3: Node removal triggers cleanup.

        Expected behavior:
        - Workflow HAD: [A, B, C, D]
        - Workflow NOW: [D] (user deleted A, B, C from workflow)
        - Reconciliation: Remove A, B, C from workflow.nodes
        - Reconciliation: Remove B, C entries from workflow.custom_node_map
        """
        # ARRANGE: Create workflow with 4 nodes, resolve them
        initial_workflow_data = {
            "nodes": [
                {"id": 1, "type": "NodeA", "widgets_values": []},
                {"id": 2, "type": "NodeB", "widgets_values": []},
                {"id": 3, "type": "NodeC", "widgets_values": []},
                {"id": 4, "type": "NodeD", "widgets_values": []}
            ],
            "links": []
        }

        simulate_comfyui_save_workflow(test_env, "test_workflow", initial_workflow_data)

        # Mock resolver for initial resolution
        def mock_initial_resolve(node, context):
            pkg = MagicMock()
            pkg.package_id = f"package-{node.type.lower()}"
            pkg.match_type = "exact"
            pkg.node_type = node.type
            return [pkg]

        test_env.workflow_manager.global_node_resolver.resolve_single_node_with_context = mock_initial_resolve

        # Mock strategy that marks B and C as ambiguous (creates custom_node_map entries)
        mock_strategy = MagicMock()
        def mark_b_c_as_custom(node_type, possible):
            if node_type in ["NodeB", "NodeC"]:
                selected = possible[0]
                selected.match_type = "user_confirmed"
                return selected
            return None
        mock_strategy.resolve_unknown_node = mark_b_c_as_custom

        # Initial resolution
        test_env.resolve_workflow("test_workflow", node_strategy=mock_strategy, model_strategy=None, fix=True)

        # Manually add custom_node_map entries for B and C (simulate user choices)
        config = test_env.pyproject.load()
        if 'custom_node_map' not in config['tool']['comfydock']['workflows']['test_workflow']:
            config['tool']['comfydock']['workflows']['test_workflow']['custom_node_map'] = {}
        config['tool']['comfydock']['workflows']['test_workflow']['custom_node_map']['NodeB'] = 'package-nodeb'
        config['tool']['comfydock']['workflows']['test_workflow']['custom_node_map']['NodeC'] = False
        test_env.pyproject.save(config)

        # Verify initial state
        config = test_env.pyproject.load()
        initial_nodes = config['tool']['comfydock']['workflows']['test_workflow']['nodes']
        assert len(initial_nodes) == 4, "Should have 4 nodes initially"

        # ACT: User deletes nodes A, B, C from workflow, re-save
        modified_workflow_data = {
            "nodes": [
                {"id": 4, "type": "NodeD", "widgets_values": []}  # Only D remains
            ],
            "links": []
        }

        simulate_comfyui_save_workflow(test_env, "test_workflow", modified_workflow_data)

        # Mock resolver for modified workflow (only NodeD)
        def mock_modified_resolve(node, context):
            if node.type == "NodeD":
                pkg = MagicMock()
                pkg.package_id = "package-noded"
                pkg.match_type = "exact"
                pkg.node_type = "NodeD"
                return [pkg]
            return None

        test_env.workflow_manager.global_node_resolver.resolve_single_node_with_context = mock_modified_resolve

        # Re-resolve (should trigger reconciliation)
        test_env.resolve_workflow("test_workflow", node_strategy=None, model_strategy=None, fix=False)

        # ASSERT: Orphaned packages removed
        config = test_env.pyproject.load()
        workflow_section = config['tool']['comfydock']['workflows']['test_workflow']

        # Only NodeD should remain in nodes
        assert workflow_section['nodes'] == ['package-noded'], \
            f"Expected only ['package-noded'], got {workflow_section['nodes']}"

        # custom_node_map should be empty (or removed entirely)
        custom_map = workflow_section.get('custom_node_map', {})
        assert 'NodeB' not in custom_map, "NodeB should be removed from custom_node_map"
        assert 'NodeC' not in custom_map, "NodeC should be removed from custom_node_map"


class TestPriorityChain:
    """Test resolution priority: custom_node_map → cnr_id → global table."""

    def test_custom_node_map_overrides_global_table(self, test_env):
        """Case 2: Incremental resolution uses custom_node_map first.

        Expected behavior:
        - Node B exists in workflow.custom_node_map → use that mapping
        - Skip cnr_id and global table checks
        """
        # ARRANGE: Workflow with existing custom_node_map
        workflow_data = {
            "nodes": [{"id": 1, "type": "TestNode", "widgets_values": []}],
            "links": []
        }

        simulate_comfyui_save_workflow(test_env, "test_workflow", workflow_data)

        # Pre-populate custom_node_map (simulate previous user choice)
        config = test_env.pyproject.load()
        if 'workflows' not in config.get('tool', {}).get('comfydock', {}):
            config.setdefault('tool', {}).setdefault('comfydock', {})['workflows'] = {}
        config['tool']['comfydock']['workflows']['test_workflow'] = {
            'nodes': ['user-chosen-package'],
            'custom_node_map': {'TestNode': 'user-chosen-package'}
        }
        test_env.pyproject.save(config)

        # Mock resolver that respects custom_mappings priority and would fall back to global table
        def mock_resolve(node, context):
            # Priority 1: Check custom_mappings in context (per-workflow!)
            if context and context.custom_mappings and node.type in context.custom_mappings:
                mapping = context.custom_mappings[node.type]
                if isinstance(mapping, bool):  # Optional node
                    return []  # Skip
                else:  # Mapped to specific package
                    pkg = MagicMock()
                    pkg.package_id = mapping
                    pkg.match_type = "custom_mapping"
                    pkg.node_type = node.type
                    return [pkg]

            # Priority 3: Global table (would return different package!)
            if node.type == "TestNode":
                pkg = MagicMock()
                pkg.package_id = "global-table-package"  # Different from user choice!
                pkg.match_type = "exact"
                pkg.node_type = "TestNode"
                return [pkg]
            return None

        test_env.workflow_manager.global_node_resolver.resolve_single_node_with_context = mock_resolve

        # ACT: Resolve workflow (should use custom_node_map)
        result = test_env.resolve_workflow("test_workflow", node_strategy=None, model_strategy=None, fix=False)

        # ASSERT: custom_node_map choice preserved
        config = test_env.pyproject.load()
        workflow_section = config['tool']['comfydock']['workflows']['test_workflow']

        assert 'user-chosen-package' in workflow_section['nodes'], \
            "Should keep user's custom_node_map choice"
        assert 'global-table-package' not in workflow_section['nodes'], \
            "Should NOT use global table when custom_node_map exists"

    def test_cnr_id_overrides_global_table(self, test_env):
        """Priority chain: cnr_id from properties beats global table.

        Expected behavior:
        - Node D has cnr_id in properties → use that
        - Skip global table check
        """
        # ARRANGE: Workflow with node containing cnr_id
        workflow_data = {
            "nodes": [{
                "id": 1,
                "type": "TestNode",
                "widgets_values": [],
                "properties": {
                    "cnr_id": "package-from-cnr",
                    "ver": "abc123"
                }
            }],
            "links": []
        }

        simulate_comfyui_save_workflow(test_env, "test_workflow", workflow_data)

        # Mock resolver: global table would return different package
        def mock_resolve(node, context):
            # Check if cnr_id exists (priority 2)
            if hasattr(node, 'properties') and node.properties and 'cnr_id' in node.properties:
                pkg = MagicMock()
                pkg.package_id = node.properties['cnr_id']
                pkg.match_type = "properties"
                pkg.node_type = node.type
                return [pkg]

            # Fallback to global table (priority 3)
            pkg = MagicMock()
            pkg.package_id = "package-from-global-table"
            pkg.match_type = "exact"
            pkg.node_type = node.type
            return [pkg]

        test_env.workflow_manager.global_node_resolver.resolve_single_node_with_context = mock_resolve

        # ACT: Resolve workflow
        result = test_env.resolve_workflow("test_workflow", node_strategy=None, model_strategy=None, fix=False)

        # ASSERT: cnr_id used, not global table
        config = test_env.pyproject.load()
        workflow_section = config['tool']['comfydock']['workflows']['test_workflow']

        assert 'package-from-cnr' in workflow_section['nodes'], \
            "Should use cnr_id from properties"
        assert 'package-from-global-table' not in workflow_section['nodes'], \
            "Should NOT use global table when cnr_id exists"
