"""Integration test for progressive node resolution in fix_resolution.

Tests that fix_resolution writes node packages to workflow.nodes progressively.
"""

import json
from conftest import simulate_comfyui_save_workflow
from comfydock_core.models.node_mapping import GlobalNodePackage
from comfydock_core.models.protocols import NodeResolutionStrategy
from comfydock_core.models.workflow import ResolvedNodePackage


def test_fix_resolution_writes_nodes_progressively(test_env):
    """Test that fix_resolution writes each resolved node to workflow.nodes immediately."""
    
    # Create workflow with unknown custom nodes
    workflow_data = {
        "nodes": [
            {"id": 1, "type": "UnknownNode1", "widgets_values": [], "pos": [0, 0]},
            {"id": 2, "type": "UnknownNode2", "widgets_values": [], "pos": [0, 100]}
        ],
        "links": []
    }
    simulate_comfyui_save_workflow(test_env, "test_workflow", workflow_data)

    class SimpleStrategy(NodeResolutionStrategy):
        def resolve_unknown_node(self, node_type: str, possible):
            pkg = GlobalNodePackage(
                id=f"pkg-{node_type.lower()}",
                display_name=node_type,
                description="Test",
                author="test",
                repository="https://github.com/test/pkg",
                downloads=None,
                github_stars=None,
                rating=None,
                license=None,
                category=None,
                tags=None,
                status=None,
                created_at=None,
                versions=None
            )
            return ResolvedNodePackage(
                node_type=node_type,
                package_data=pkg,
                versions=[],
                match_type="user_confirmed",
                match_confidence=1.0
            )

    # Analyze and resolve
    analysis = test_env.workflow_manager.analyze_workflow("test_workflow")
    result = test_env.workflow_manager.resolve_workflow(analysis)
    test_env.workflow_manager.apply_resolution(result)

    # Fix with strategy
    fixed_result = test_env.workflow_manager.fix_resolution(
        result,
        node_strategy=SimpleStrategy(),
        model_strategy=None
    )

    # Verify nodes in workflow.nodes
    workflow_nodes = test_env.pyproject.workflows.get_node_packs("test_workflow")
    for resolved in fixed_result.nodes_resolved:
        if resolved.package_data and resolved.match_type != 'optional':
            assert resolved.package_data.id in workflow_nodes, \
                f"Node {resolved.package_data.id} should be written to workflow.nodes"


def test_optional_nodes_not_in_workflow_nodes(test_env):
    """Test that optional nodes don't get added to workflow.nodes."""
    
    workflow_data = {
        "nodes": [{"id": 1, "type": "OptionalNode", "widgets_values": [], "pos": [0, 0]}],
        "links": []
    }
    simulate_comfyui_save_workflow(test_env, "optional_test", workflow_data)

    class OptionalStrategy(NodeResolutionStrategy):
        def resolve_unknown_node(self, node_type: str, possible):
            return ResolvedNodePackage(
                node_type=node_type,
                package_data=None,
                versions=[],
                match_type="optional",
                match_confidence=1.0
            )

    # Analyze and resolve
    analysis = test_env.workflow_manager.analyze_workflow("optional_test")
    result = test_env.workflow_manager.resolve_workflow(analysis)
    test_env.workflow_manager.apply_resolution(result)

    initial_nodes = set(test_env.pyproject.workflows.get_node_packs("optional_test"))

    # Fix with optional strategy
    if result.nodes_unresolved:
        test_env.workflow_manager.fix_resolution(
            result,
            node_strategy=OptionalStrategy(),
            model_strategy=None
        )

        # Verify workflow.nodes unchanged
        final_nodes = set(test_env.pyproject.workflows.get_node_packs("optional_test"))
        assert final_nodes == initial_nodes, \
            "Optional nodes should not be added to workflow.nodes"


def test_deduplication_in_workflow_nodes(test_env):
    """Test that duplicate node package IDs are deduplicated in workflow.nodes."""
    
    workflow_data = {
        "nodes": [
            {"id": 1, "type": "Node1", "widgets_values": [], "pos": [0, 0]},
            {"id": 2, "type": "Node2", "widgets_values": [], "pos": [0, 100]}
        ],
        "links": []
    }
    simulate_comfyui_save_workflow(test_env, "dedup_test", workflow_data)

    test_pkg_id = "shared-package"
    
    class DuplicateStrategy(NodeResolutionStrategy):
        def resolve_unknown_node(self, node_type: str, possible):
            pkg = GlobalNodePackage(
                id=test_pkg_id,  # Same for all
                display_name="Shared",
                description="Test",
                author="test",
                repository="https://github.com/test/pkg",
                downloads=None,
                github_stars=None,
                rating=None,
                license=None,
                category=None,
                tags=None,
                status=None,
                created_at=None,
                versions=None
            )
            return ResolvedNodePackage(
                node_type=node_type,
                package_data=pkg,
                versions=[],
                match_type="user_confirmed",
                match_confidence=1.0
            )

    # Analyze and resolve
    analysis = test_env.workflow_manager.analyze_workflow("dedup_test")
    result = test_env.workflow_manager.resolve_workflow(analysis)
    test_env.workflow_manager.apply_resolution(result)

    # Fix with duplicate strategy
    test_env.workflow_manager.fix_resolution(
        result,
        node_strategy=DuplicateStrategy(),
        model_strategy=None
    )

    # Verify only ONE instance
    workflow_nodes = list(test_env.workflow_manager.get_node_packs("dedup_test"))
    count = workflow_nodes.count(test_pkg_id)
    assert count == 1, f"Package should appear once, found {count} times"
