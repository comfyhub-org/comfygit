"""Test that status provides proper abstraction - no pyproject.load() in display layer.

This test validates that WorkflowAnalysisStatus contains all information needed
for display without requiring the CLI to access raw pyproject.toml data.

Abstraction Violation:
- CLI should NOT call env.pyproject.load() to compute display values
- CLI should NOT parse TOML structure with .get('tool', {}).get('comfygit', {})
- CLI should receive complete, ready-to-display data from core

Correct Abstraction:
- WorkflowAnalysisStatus should contain uninstalled_nodes list
- WorkflowAnalysisStatus should contain uninstalled_count property
- CLI only iterates and prints - NO business logic
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from conftest import simulate_comfyui_save_workflow


class TestStatusAbstraction:
    """Test that status data models provide complete abstraction for display."""

    def test_workflow_analysis_status_contains_uninstalled_info(self, test_env):
        """
        WorkflowAnalysisStatus should contain uninstalled node information.

        CLI should be able to display status by ONLY accessing properties on
        WorkflowAnalysisStatus, without any pyproject.load() calls.
        """
        # ARRANGE: Create workflow with uninstalled nodes
        workflow_data = {
            "nodes": [
                {"id": "1", "type": "CustomNode1", "widgets_values": []},
                {"id": "2", "type": "CustomNode2", "widgets_values": []}
            ],
            "links": []
        }
        simulate_comfyui_save_workflow(test_env, "test_workflow", workflow_data)

        # Simulate resolution: 3 nodes needed, only 1 installed
        config = test_env.pyproject.load()
        if 'workflows' not in config['tool']['comfygit']:
            config['tool']['comfygit']['workflows'] = {}

        config['tool']['comfygit']['workflows']['test_workflow'] = {
            'path': 'workflows/test_workflow.json',
            'nodes': ['node-a', 'node-b', 'node-c']  # 3 needed
        }

        # Only install node-a
        if 'nodes' not in config['tool']['comfygit']:
            config['tool']['comfygit']['nodes'] = {}
        config['tool']['comfygit']['nodes']['node-a'] = {
            'name': 'Node A',
            'source': 'git',
            'repository': 'https://github.com/test/node-a'
        }

        test_env.pyproject.save(config)

        # ACT: Get workflow status (what CLI calls)
        workflow_status = test_env.workflow_manager.get_workflow_status()

        # ASSERT: WorkflowAnalysisStatus should provide all display info
        test_workflow = next(
            (wf for wf in workflow_status.analyzed_workflows if wf.name == "test_workflow"),
            None
        )

        assert test_workflow is not None, "Workflow should be analyzed"

        # CLI should be able to access these WITHOUT calling pyproject.load()
        assert hasattr(test_workflow, 'uninstalled_nodes'), \
            "WorkflowAnalysisStatus should have 'uninstalled_nodes' attribute"

        # Should contain the 2 uninstalled nodes
        assert len(test_workflow.uninstalled_nodes) == 2, \
            f"Expected 2 uninstalled nodes, got {len(test_workflow.uninstalled_nodes)}"

        assert 'node-b' in test_workflow.uninstalled_nodes, \
            "node-b should be in uninstalled list"
        assert 'node-c' in test_workflow.uninstalled_nodes, \
            "node-c should be in uninstalled list"

        # Should have convenience property for count
        assert hasattr(test_workflow, 'uninstalled_count'), \
            "WorkflowAnalysisStatus should have 'uninstalled_count' property"

        assert test_workflow.uninstalled_count == 2, \
            f"Expected uninstalled_count=2, got {test_workflow.uninstalled_count}"

    def test_cli_display_without_pyproject_access(self, test_env):
        """
        Verify CLI can build complete status display using ONLY model properties.

        This simulates what the CLI _print_workflow_issues() method should do:
        access only WorkflowAnalysisStatus properties, no pyproject.load().
        """
        # ARRANGE: Setup scenario
        workflow_data = {
            "nodes": [{"id": "1", "type": "TestNode", "widgets_values": []}],
            "links": []
        }
        simulate_comfyui_save_workflow(test_env, "my_workflow", workflow_data)

        config = test_env.pyproject.load()
        if 'workflows' not in config['tool']['comfygit']:
            config['tool']['comfygit']['workflows'] = {}

        config['tool']['comfygit']['workflows']['my_workflow'] = {
            'path': 'workflows/my_workflow.json',
            'nodes': ['package-a', 'package-b']
        }
        test_env.pyproject.save(config)

        # ACT: Get status
        workflow_status = test_env.workflow_manager.get_workflow_status()
        wf = next(
            (w for w in workflow_status.analyzed_workflows if w.name == "my_workflow"),
            None
        )

        # SIMULATE CLI DISPLAY: Should work with ONLY model access
        parts = []

        # ✅ Good: Access model property
        if wf.uninstalled_count > 0:
            parts.append(f"{wf.uninstalled_count} packages needed for installation")

        # ✅ Good: Access resolution property
        if wf.resolution.nodes_unresolved:
            parts.append(f"{len(wf.resolution.nodes_unresolved)} nodes couldn't be resolved")

        if wf.resolution.models_unresolved:
            parts.append(f"{len(wf.resolution.models_unresolved)} models not found")

        if wf.resolution.models_ambiguous:
            parts.append(f"{len(wf.resolution.models_ambiguous)} ambiguous models")

        # VERIFY: Display parts were created successfully
        assert len(parts) > 0, "Should have generated display parts"
        assert "2 packages needed for installation" in parts[0], \
            f"Expected installation message, got: {parts[0]}"

    def test_multiple_workflows_status_abstraction(self, test_env):
        """Test abstraction works correctly with multiple workflows."""
        # ARRANGE: Create 2 workflows with different installation states
        for i, (name, nodes_needed, nodes_installed) in enumerate([
            ("workflow_a", ['node-1', 'node-2'], ['node-1']),  # 1 uninstalled
            ("workflow_b", ['node-3', 'node-4', 'node-5'], [])  # 3 uninstalled
        ]):
            workflow_data = {
                "nodes": [{"id": str(i), "type": f"Node{i}", "widgets_values": []}],
                "links": []
            }
            simulate_comfyui_save_workflow(test_env, name, workflow_data)

            config = test_env.pyproject.load()
            if 'workflows' not in config['tool']['comfygit']:
                config['tool']['comfygit']['workflows'] = {}

            config['tool']['comfygit']['workflows'][name] = {
                'path': f'workflows/{name}.json',
                'nodes': nodes_needed
            }

            # Install only specified nodes
            if 'nodes' not in config['tool']['comfygit']:
                config['tool']['comfygit']['nodes'] = {}
            for node_id in nodes_installed:
                config['tool']['comfygit']['nodes'][node_id] = {
                    'name': node_id,
                    'source': 'git',
                    'repository': f'https://github.com/test/{node_id}'
                }

            test_env.pyproject.save(config)

        # ACT: Get status
        workflow_status = test_env.workflow_manager.get_workflow_status()

        # ASSERT: Each workflow should have correct uninstalled info
        workflow_a = next((w for w in workflow_status.analyzed_workflows if w.name == "workflow_a"), None)
        workflow_b = next((w for w in workflow_status.analyzed_workflows if w.name == "workflow_b"), None)

        assert workflow_a is not None and workflow_b is not None

        # CLI can check status for each workflow without pyproject access
        assert workflow_a.uninstalled_count == 1, \
            f"workflow_a should have 1 uninstalled, got {workflow_a.uninstalled_count}"
        assert workflow_b.uninstalled_count == 3, \
            f"workflow_b should have 3 uninstalled, got {workflow_b.uninstalled_count}"

        # Verify specific nodes
        assert 'node-2' in workflow_a.uninstalled_nodes
        assert set(workflow_b.uninstalled_nodes) == {'node-3', 'node-4', 'node-5'}
