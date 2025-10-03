"""Integration tests reproducing workflow commit bugs.

These tests reproduce the exact bugs found during manual testing:
1. Workflows are never copied to .cec during commit
2. Workflows only appear in status if they have issues
3. is_synced doesn't consider workflow changes
"""
import json
import pytest
import subprocess
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from conftest import (
    simulate_comfyui_save_workflow,
    load_workflow_fixture,
)

class TestWorkflowCommitFlow:
    """E2E tests for complete workflow commit cycle."""

    def test_workflow_copied_to_cec_during_commit(
        self,
        test_env,
        workflow_fixtures,
        test_models
    ):
        """
        BUG #1: Workflows are never copied to .cec during commit.

        Reproduces:
        1. User saves workflow in ComfyUI
        2. User runs commit
        3. Commit says "success"
        4. But .cec/workflows/ is empty!

        This test WILL FAIL until bug is fixed.
        """
        # Setup: Load workflow fixture with valid model
        workflow_data = load_workflow_fixture(workflow_fixtures, "simple_txt2img")

        # Action 1: Simulate user saving workflow in ComfyUI
        simulate_comfyui_save_workflow(test_env, "test_workflow", workflow_data)

        # Action 2: Commit
        workflow_status = test_env.workflow_manager.get_workflow_status()
        test_env.execute_commit(
            workflow_status=workflow_status,
            message="Add workflow",
            node_strategy=None,
            model_strategy=None
        )

        # Assertion: Workflow should be in .cec/workflows/
        cec_workflow = test_env.cec_path / "workflows" / "test_workflow.json"
        assert cec_workflow.exists(), \
            "BUG: Workflow was not copied to .cec during commit"

        # Verify content matches
        with open(cec_workflow) as f:
            committed_content = json.load(f)

        assert committed_content == workflow_data, \
            "Committed workflow should match original"

    def test_workflow_appears_in_status_without_issues(
        self,
        test_env,
        workflow_fixtures,
        test_models
    ):
        """
        BUG #2: Workflows only appear in status if they have issues.

        Reproduces:
        1. User saves workflow with valid model
        2. User runs status
        3. Workflow is not shown! (because is_synced=True)

        This test WILL FAIL until bug is fixed.
        """
        # Setup: Workflow with valid model (no issues)
        workflow_data = load_workflow_fixture(workflow_fixtures, "simple_txt2img")

        # Action: Simulate user saving workflow
        simulate_comfyui_save_workflow(test_env, "test_workflow", workflow_data)

        # Get status
        status = test_env.status()

        # Assertion: Workflow should appear even without issues
        assert "test_workflow" in status.workflow.sync_status.new, \
            f"BUG: Workflow should appear in status even when it has no issues. " \
            f"Found: {status.workflow.sync_status.new}"

        # Assertion: Status should not be "synced" when new workflow exists
        assert not status.is_synced, \
            "BUG: is_synced should be False when new workflow exists"

    def test_git_commit_includes_workflow_files(
        self,
        test_env,
        workflow_fixtures,
        test_models
    ):
        """Verify that git commit actually versions workflow files."""
        # Setup
        workflow_data = load_workflow_fixture(workflow_fixtures, "simple_txt2img")
        simulate_comfyui_save_workflow(test_env, "test_workflow", workflow_data)

        # Commit
        workflow_status = test_env.workflow_manager.get_workflow_status()
        test_env.execute_commit(
            workflow_status=workflow_status,
            message="Add workflow",
            node_strategy=None,
            model_strategy=None
        )

        # Check git status - should be clean (everything committed)
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=test_env.cec_path,
            capture_output=True,
            text=True
        )

        assert result.stdout.strip() == "", \
            f"Git should have no uncommitted changes after commit. Found: {result.stdout}"

        # Verify workflow is in git
        result = subprocess.run(
            ["git", "ls-files", "workflows/test_workflow.json"],
            cwd=test_env.cec_path,
            capture_output=True,
            text=True
        )

        assert "workflows/test_workflow.json" in result.stdout, \
            "Workflow should be tracked by git"

    def test_workflow_lifecycle_with_state_transitions(
        self,
        test_env,
        workflow_fixtures,
        test_models
    ):
        """Test complete workflow lifecycle with state verification at each step."""
        # STATE 1: Clean environment
        status = test_env.status()
        assert status.is_synced, "Should start synced"
        assert status.workflow.sync_status.total_count == 0, "Should have no workflows"

        # ACTION 1: User saves new workflow
        workflow_data = load_workflow_fixture(workflow_fixtures, "simple_txt2img")
        simulate_comfyui_save_workflow(test_env, "my_workflow", workflow_data)

        # STATE 2: New workflow detected
        status = test_env.status()
        assert not status.is_synced, "Should be out of sync after new workflow"
        assert "my_workflow" in status.workflow.sync_status.new, \
            f"Workflow should be in 'new'. Found: {status.workflow.sync_status.new}"
        assert status.workflow.sync_status.total_count == 1

        # ACTION 2: Commit
        workflow_status = test_env.workflow_manager.get_workflow_status()
        test_env.execute_commit(
            workflow_status=workflow_status,
            message="Add workflow",
            node_strategy=None,
            model_strategy=None
        )

        # STATE 3: Workflow committed
        status = test_env.status()
        assert status.is_synced, "Should be in sync after commit"
        assert "my_workflow" in status.workflow.sync_status.synced, \
            f"Workflow should be synced. Found synced={status.workflow.sync_status.synced}"
        assert (test_env.cec_path / "workflows" / "my_workflow.json").exists(), \
            "Workflow should exist in .cec"

        # ACTION 3: User modifies workflow in ComfyUI
        modified_workflow = workflow_data.copy()
        modified_workflow["nodes"][1]["widgets_values"] = ["different prompt"]
        simulate_comfyui_save_workflow(test_env, "my_workflow", modified_workflow)

        # STATE 4: Modified workflow detected
        status = test_env.status()
        assert not status.is_synced, "Should be out of sync after modification"
        assert "my_workflow" in status.workflow.sync_status.modified, \
            f"Workflow should be modified. Found: {status.workflow.sync_status.modified}"

        # ACTION 4: Commit changes
        workflow_status = test_env.workflow_manager.get_workflow_status()
        test_env.execute_commit(
            workflow_status=workflow_status,
            message="Update workflow",
            node_strategy=None,
            model_strategy=None
        )

        # STATE 5: Changes committed
        status = test_env.status()
        assert status.is_synced

        # Verify .cec has updated content
        with open(test_env.cec_path / "workflows" / "my_workflow.json") as f:
            committed = json.load(f)

        assert committed["nodes"][1]["widgets_values"] == ["different prompt"], \
            "Committed workflow should have updated content"

class TestWorkflowModelResolution:
    """Tests for model dependency resolution."""

    def test_missing_model_detected(
        self,
        test_env,
        workflow_fixtures,
        test_models
    ):
        """Workflow with missing model should be detected in analysis."""
        # Use fixture with model that doesn't exist
        workflow_data = load_workflow_fixture(workflow_fixtures, "with_missing_model")
        simulate_comfyui_save_workflow(test_env, "test", workflow_data)

        # Analyze
        status = test_env.status()

        # Should have unresolved models
        assert status.workflow.total_issues > 0, \
            "Workflow with missing model should have issues"

        workflow_status = status.workflow.workflows_with_issues[0]
        assert len(workflow_status.resolution.models_unresolved) > 0, \
            "Should have unresolved models"

        # Model should be identified correctly
        unresolved = workflow_status.resolution.models_unresolved[0]
        assert "v1-5-pruned-emaonly-fp16.safetensors" in unresolved.widget_value, \
            f"Should identify missing model. Found: {unresolved.widget_value}"

class TestWorkflowRollback:
    """Tests for workflow versioning and rollback."""

    def test_rollback_restores_workflow_content(
        self,
        test_env,
        workflow_fixtures,
        test_models
    ):
        """Rollback should restore exact workflow content from previous version."""
        # V1: Save initial version
        v1_workflow = load_workflow_fixture(workflow_fixtures, "simple_txt2img")
        simulate_comfyui_save_workflow(test_env, "test", v1_workflow)

        workflow_status = test_env.workflow_manager.get_workflow_status()
        test_env.execute_commit(
            workflow_status=workflow_status,
            message="v1",
            node_strategy=None,
            model_strategy=None
        )

        # V2: Modify and commit
        v2_workflow = v1_workflow.copy()
        v2_workflow["nodes"][1]["widgets_values"] = ["modified prompt v2"]
        simulate_comfyui_save_workflow(test_env, "test", v2_workflow)

        workflow_status = test_env.workflow_manager.get_workflow_status()
        test_env.execute_commit(
            workflow_status=workflow_status,
            message="v2",
            node_strategy=None,
            model_strategy=None
        )

        # Verify we're on v2
        comfyui_workflow_path = test_env.comfyui_path / "user" / "default" / "workflows" / "test.json"
        with open(comfyui_workflow_path) as f:
            current = json.load(f)
        assert current["nodes"][1]["widgets_values"] == ["modified prompt v2"]

        # Rollback to v1
        test_env.rollback("v1")

        # Verify v1 content restored
        with open(comfyui_workflow_path) as f:
            restored = json.load(f)

        assert restored["nodes"][1]["widgets_values"] == v1_workflow["nodes"][1]["widgets_values"], \
            "Rollback should restore exact v1 content"

    def test_commit_creates_retrievable_version(
        self,
        test_env,
        workflow_fixtures,
        test_models
    ):
        """Each commit should create a new version in git history."""
        # Get initial version count
        initial_versions = test_env.get_versions()
        initial_count = len(initial_versions)

        # Make change and commit
        workflow = load_workflow_fixture(workflow_fixtures, "simple_txt2img")
        simulate_comfyui_save_workflow(test_env, "test", workflow)

        workflow_status = test_env.workflow_manager.get_workflow_status()
        test_env.execute_commit(
            workflow_status=workflow_status,
            message="Add workflow",
            node_strategy=None,
            model_strategy=None
        )

        # Verify new version exists
        versions = test_env.get_versions()
        assert len(versions) == initial_count + 1, \
            f"Should have {initial_count + 1} versions. Found: {len(versions)}"
        assert versions[-1]['message'] == "Add workflow"
        assert versions[-1]['version'] == f"v{initial_count + 1}"
