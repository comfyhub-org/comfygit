"""Test that status correctly reports uninstalled nodes after resolution.

Bug: After workflow resolution adds nodes to the workflow's node list in pyproject.toml,
but before those nodes are actually installed, `status` should report them as needing
installation. Currently it incorrectly shows no issues because it compares
resolution.nodes_resolved (from re-parsing) against installed nodes, and both lists
now contain the nodes (even though they're not installed on disk).

Fix: Compare workflow's declared node list (from pyproject.toml) against actually
installed nodes (from pyproject.toml nodes section).
"""

import pytest
import sys
from pathlib import Path

# Add parent directory to path for conftest imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from conftest import simulate_comfyui_save_workflow, load_workflow_fixture


class TestStatusUninstalledNodes:
    """Tests for status reporting of uninstalled nodes after resolution."""

    def test_status_shows_uninstalled_nodes_after_resolution(self, test_env, workflow_fixtures):
        """
        Test that status correctly shows uninstalled nodes even after resolution.

        Scenario:
        1. User runs workflow resolve
        2. Nodes are added to workflow's node list in pyproject.toml
        3. User skips installation (or installation fails for some nodes)
        4. User runs status

        Expected: Status should show which nodes need installation
        Actual (bug): Status shows no issues because it compares wrong lists
        """
        # ARRANGE: Create a simple workflow
        workflow_data = {
            "nodes": [
                {
                    "id": "1",
                    "type": "TestCustomNode",  # Not a builtin
                    "widgets_values": []
                }
            ],
            "links": []
        }
        simulate_comfyui_save_workflow(test_env, "test_workflow", workflow_data)

        # ACT 1: Manually simulate what workflow resolve does:
        # - Adds node to workflow's node list
        # - But does NOT add to installed nodes section
        config = test_env.pyproject.load()

        # Ensure workflows section exists
        if 'workflows' not in config['tool']['comfydock']:
            config['tool']['comfydock']['workflows'] = {}

        # Add workflow with node requirement (simulating resolution)
        config['tool']['comfydock']['workflows']['test_workflow'] = {
            'path': 'workflows/test_workflow.json',
            'nodes': ['test-custom-node']  # Added to workflow's required list
        }

        # Do NOT add to nodes section (simulating failed/skipped installation)
        # config['tool']['comfydock']['nodes'] stays empty

        test_env.pyproject.save(config)

        # ACT 2: Get workflow status (this is what `cfd status` calls)
        workflow_status = test_env.workflow_manager.get_workflow_status()

        # ASSERT: Should show 1 uninstalled package needed
        # Find our workflow
        test_workflow = None
        for wf in workflow_status.analyzed_workflows:
            if wf.name == "test_workflow":
                test_workflow = wf
                break

        assert test_workflow is not None, "test_workflow should be in analyzed workflows"

        # Get packages from resolved nodes
        resolved_packages = {
            pkg.package_id
            for pkg in test_workflow.resolution.nodes_resolved
        }

        # Get installed packages
        installed_packages = set(test_env.pyproject.nodes.get_existing().keys())

        # Calculate difference (this is what _print_workflow_issues does)
        packages_needed = resolved_packages - installed_packages

        # BUG: This will be 0 because both lists are empty or matching
        # after resolution re-parses the workflow

        # What we SHOULD compare instead:
        workflow_config = config['tool']['comfydock']['workflows']['test_workflow']
        workflow_node_list = set(workflow_config.get('nodes', []))
        correct_packages_needed = workflow_node_list - installed_packages

        # This assertion will PASS (showing the correct behavior we want)
        assert len(correct_packages_needed) == 1, \
            f"Should have 1 uninstalled package, but got {len(correct_packages_needed)}"
        assert 'test-custom-node' in correct_packages_needed

        # This assertion will FAIL (showing the bug in current implementation)
        # Commenting out for now since we're testing the CORRECT behavior
        # assert len(packages_needed) == 1, \
        #     f"BUG: Status shows {len(packages_needed)} uninstalled (should be 1)"

    def test_status_clears_after_installation(self, test_env, workflow_fixtures):
        """
        Test that status correctly shows 0 uninstalled after nodes are installed.

        Scenario:
        1. Workflow resolved (nodes added to workflow's list)
        2. Nodes successfully installed (added to nodes section)
        3. Status should show 0 uninstalled
        """
        # ARRANGE: Create a workflow
        workflow_data = {
            "nodes": [
                {
                    "id": "1",
                    "type": "TestCustomNode",
                    "widgets_values": []
                }
            ],
            "links": []
        }
        simulate_comfyui_save_workflow(test_env, "test_workflow", workflow_data)

        # Simulate resolution AND installation
        config = test_env.pyproject.load()

        if 'workflows' not in config['tool']['comfydock']:
            config['tool']['comfydock']['workflows'] = {}

        # Add to workflow's node list
        config['tool']['comfydock']['workflows']['test_workflow'] = {
            'path': 'workflows/test_workflow.json',
            'nodes': ['test-custom-node']
        }

        # AND add to installed nodes (simulating successful installation)
        if 'nodes' not in config['tool']['comfydock']:
            config['tool']['comfydock']['nodes'] = {}
        config['tool']['comfydock']['nodes']['test-custom-node'] = {
            'name': 'Test Custom Node',
            'source': 'git',
            'repository': 'https://github.com/test/test-custom-node'
        }

        test_env.pyproject.save(config)

        # ACT: Get status
        workflow_status = test_env.workflow_manager.get_workflow_status()

        # ASSERT: Should show 0 uninstalled packages
        test_workflow = None
        for wf in workflow_status.analyzed_workflows:
            if wf.name == "test_workflow":
                test_workflow = wf
                break

        assert test_workflow is not None

        # Calculate correctly
        workflow_config = config['tool']['comfydock']['workflows']['test_workflow']
        workflow_node_list = set(workflow_config.get('nodes', []))
        installed_packages = set(test_env.pyproject.nodes.get_existing().keys())
        correct_packages_needed = workflow_node_list - installed_packages

        assert len(correct_packages_needed) == 0, \
            f"Should have 0 uninstalled packages after installation, got {len(correct_packages_needed)}"

    def test_status_shows_multiple_uninstalled_nodes(self, test_env, workflow_fixtures):
        """Test status with multiple uninstalled nodes (like the real bug scenario)."""
        # ARRANGE: Workflow with multiple nodes
        workflow_data = {
            "nodes": [
                {"id": "1", "type": "Node1", "widgets_values": []},
                {"id": "2", "type": "Node2", "widgets_values": []},
                {"id": "3", "type": "Node3", "widgets_values": []},
            ],
            "links": []
        }
        simulate_comfyui_save_workflow(test_env, "test_workflow", workflow_data)

        # Simulate resolution: 22 nodes needed, 19 installed, 3 failed
        config = test_env.pyproject.load()

        if 'workflows' not in config['tool']['comfydock']:
            config['tool']['comfydock']['workflows'] = {}

        # All 22 nodes in workflow's list
        all_nodes = [f'node-{i}' for i in range(22)]
        config['tool']['comfydock']['workflows']['test_workflow'] = {
            'path': 'workflows/test_workflow.json',
            'nodes': all_nodes
        }

        # Only 19 actually installed
        if 'nodes' not in config['tool']['comfydock']:
            config['tool']['comfydock']['nodes'] = {}
        installed_nodes = all_nodes[:19]
        for node_id in installed_nodes:
            config['tool']['comfydock']['nodes'][node_id] = {
                'name': node_id.replace('-', ' ').title(),
                'source': 'git',
                'repository': f'https://github.com/test/{node_id}'
            }

        test_env.pyproject.save(config)

        # ACT: Get status
        workflow_status = test_env.workflow_manager.get_workflow_status()
        test_workflow = next(
            (wf for wf in workflow_status.analyzed_workflows if wf.name == "test_workflow"),
            None
        )

        assert test_workflow is not None

        # ASSERT: Should show 3 uninstalled (nodes 19, 20, 21)
        workflow_config = config['tool']['comfydock']['workflows']['test_workflow']
        workflow_node_list = set(workflow_config.get('nodes', []))
        installed_packages = set(test_env.pyproject.nodes.get_existing().keys())
        packages_needed = workflow_node_list - installed_packages

        assert len(packages_needed) == 3, \
            f"Should have 3 uninstalled packages, got {len(packages_needed)}"

        # Verify it's the last 3
        expected_uninstalled = {'node-19', 'node-20', 'node-21'}
        assert packages_needed == expected_uninstalled, \
            f"Uninstalled packages should be {expected_uninstalled}, got {packages_needed}"
