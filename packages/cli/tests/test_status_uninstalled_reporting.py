"""CLI test for status reporting of uninstalled nodes.

Tests the _print_workflow_issues() method to ensure it correctly reports
uninstalled packages after resolution.
"""

import pytest
import sys
import io
from pathlib import Path

# Add paths for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "core" / "tests"))
from conftest import simulate_comfyui_save_workflow

from comfygit_cli.env_commands import EnvironmentCommands
from comfygit_core.models.workflow import WorkflowAnalysisStatus


class TestStatusUninstalledReporting:
    """Test that CLI status correctly reports uninstalled nodes."""

    def test_print_workflow_issues_shows_uninstalled_after_resolution(self, test_env):
        """
        Test _print_workflow_issues() reports uninstalled nodes correctly.

        This is the exact bug scenario:
        - Workflow resolution adds nodes to workflow's node list
        - Some nodes fail to install
        - _print_workflow_issues() should show them as needed
        """
        # ARRANGE: Create workflow and simulate resolution
        workflow_data = {
            "nodes": [
                {"id": "1", "type": "TestNode", "widgets_values": []}
            ],
            "links": []
        }
        simulate_comfyui_save_workflow(test_env, "test_workflow", workflow_data)

        # Simulate resolution: added to workflow list but not installed
        config = test_env.pyproject.load()
        if 'workflows' not in config['tool']['comfygit']:
            config['tool']['comfygit']['workflows'] = {}

        config['tool']['comfygit']['workflows']['test_workflow'] = {
            'path': 'workflows/test_workflow.json',
            'nodes': ['node-1', 'node-2', 'node-3']  # 3 nodes needed
        }

        # Only install 2 nodes
        if 'nodes' not in config['tool']['comfygit']:
            config['tool']['comfygit']['nodes'] = {}

        config['tool']['comfygit']['nodes']['node-1'] = {
            'name': 'Node 1',
            'source': 'git',
            'repository': 'https://github.com/test/node-1'
        }
        config['tool']['comfygit']['nodes']['node-2'] = {
            'name': 'Node 2',
            'source': 'git',
            'repository': 'https://github.com/test/node-2'
        }
        # node-3 NOT installed (simulating install failure)

        test_env.pyproject.save(config)

        # Get workflow status
        workflow_status = test_env.workflow_manager.get_workflow_status()
        test_workflow = next(
            (wf for wf in workflow_status.analyzed_workflows if wf.name == "test_workflow"),
            None
        )

        assert test_workflow is not None

        # ACT: Call _print_workflow_issues (what status command does)
        env_commands = EnvironmentCommands()

        # Capture output
        captured_output = io.StringIO()
        sys.stdout = captured_output

        try:
            env_commands._print_workflow_issues(test_workflow)
        finally:
            sys.stdout = sys.__stdout__

        output = captured_output.getvalue()

        # ASSERT: Should report 1 package needed
        assert "1 packages needed for installation" in output or "1 package" in output, \
            f"Output should show 1 package needed, got: {output}"

    def test_print_workflow_issues_shows_zero_after_installation(self, test_env):
        """Test _print_workflow_issues() shows nothing when all nodes installed."""
        # ARRANGE: Workflow with all nodes installed
        workflow_data = {
            "nodes": [
                {"id": "1", "type": "TestNode", "widgets_values": []}
            ],
            "links": []
        }
        simulate_comfyui_save_workflow(test_env, "test_workflow", workflow_data)

        config = test_env.pyproject.load()
        if 'workflows' not in config['tool']['comfygit']:
            config['tool']['comfygit']['workflows'] = {}
        if 'nodes' not in config['tool']['comfygit']:
            config['tool']['comfygit']['nodes'] = {}

        # Same nodes in both lists (all installed)
        config['tool']['comfygit']['workflows']['test_workflow'] = {
            'path': 'workflows/test_workflow.json',
            'nodes': ['node-1', 'node-2']
        }

        for node_id in ['node-1', 'node-2']:
            config['tool']['comfygit']['nodes'][node_id] = {
                'name': node_id.replace('-', ' ').title(),
                'source': 'git',
                'repository': f'https://github.com/test/{node_id}'
            }

        test_env.pyproject.save(config)

        # Get workflow status
        workflow_status = test_env.workflow_manager.get_workflow_status()
        test_workflow = next(
            (wf for wf in workflow_status.analyzed_workflows if wf.name == "test_workflow"),
            None
        )

        assert test_workflow is not None

        # ACT: Call _print_workflow_issues
        env_commands = EnvironmentCommands()
        captured_output = io.StringIO()
        sys.stdout = captured_output

        try:
            env_commands._print_workflow_issues(test_workflow)
        finally:
            sys.stdout = sys.__stdout__

        output = captured_output.getvalue()

        # ASSERT: Should not mention packages needed
        assert "packages needed" not in output, \
            f"Output should not show packages needed when all installed, got: {output}"
