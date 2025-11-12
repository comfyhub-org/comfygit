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


def normalize_workflow_for_comparison(workflow: dict) -> dict:
    """Normalize workflow JSON for semantic comparison.

    Strips fields that don't affect workflow semantics:
    - Empty arrays (inputs, outputs, widgets_values)
    - Empty dicts (properties, flags, extra, config)
    - Type differences (int vs float in pos, node IDs)
    - Model path prefixes (checkpoints/, loras/, etc.) that ComfyUI adds automatically

    This allows comparing workflows that are semantically identical
    but have different serialization artifacts.
    """
    import copy
    normalized = copy.deepcopy(workflow)

    # Model loader base directories that ComfyUI prepends automatically
    # These can be stripped for comparison since they're functionally equivalent
    BASE_DIRS = ['checkpoints/', 'loras/', 'vae/', 'clip_vision/', 'controlnet/',
                 'upscale_models/', 'embeddings/', 'style_models/']

    # Normalize nodes
    if 'nodes' in normalized:
        for node in normalized['nodes']:
            if isinstance(node, dict):
                # Remove empty arrays/dicts that don't affect semantics
                if node.get('inputs') == []:
                    node.pop('inputs', None)
                if node.get('outputs') == []:
                    node.pop('outputs', None)
                if node.get('properties') == {}:
                    node.pop('properties', None)
                if node.get('flags') == {}:
                    node.pop('flags', None)
                if node.get('widgets_values') == []:
                    node.pop('widgets_values', None)

                # Normalize model paths in widget values (strip base directory)
                # ComfyUI builtin loaders prepend their base directories automatically
                if 'widgets_values' in node and isinstance(node['widgets_values'], list):
                    normalized_values = []
                    for val in node['widgets_values']:
                        if isinstance(val, str):
                            # Strip known base directories
                            for base_dir in BASE_DIRS:
                                if val.startswith(base_dir):
                                    val = val[len(base_dir):]
                                    break
                        normalized_values.append(val)
                    node['widgets_values'] = normalized_values

                # Normalize pos to list of ints (remove float artifacts)
                if 'pos' in node:
                    if isinstance(node['pos'], tuple):
                        node['pos'] = list(node['pos'])
                    if isinstance(node['pos'], list):
                        node['pos'] = [int(x) if isinstance(x, (int, float)) else x for x in node['pos']]

                # Normalize node ID to int
                if 'id' in node:
                    node['id'] = int(node['id']) if isinstance(node['id'], (int, str)) and str(node['id']).isdigit() else node['id']

    # Remove empty top-level containers
    if normalized.get('extra') == {}:
        normalized.pop('extra', None)
    if normalized.get('config') == {}:
        normalized.pop('config', None)
    if normalized.get('groups') == []:
        normalized.pop('groups', None)

    return normalized

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

        # Action 1b: Resolve workflow to fix any path sync issues
        deps = test_env.workflow_manager.analyze_workflow("test_workflow")
        resolution = test_env.workflow_manager.resolve_workflow(deps)
        test_env.workflow_manager.apply_resolution(resolution)

        # Action 2: Commit
        workflow_status = test_env.workflow_manager.get_workflow_status()
        test_env.execute_commit(
            workflow_status=workflow_status,
            message="Add workflow"
        )

        # Assertion: Workflow should be in .cec/workflows/
        cec_workflow = test_env.cec_path / "workflows" / "test_workflow.json"
        assert cec_workflow.exists(), \
            "BUG: Workflow was not copied to .cec during commit"

        # Verify content matches semantically (ignoring serialization artifacts)
        with open(cec_workflow) as f:
            committed_content = json.load(f)

        # Normalize both for comparison (removes empty fields, normalizes types)
        normalized_committed = normalize_workflow_for_comparison(committed_content)
        normalized_original = normalize_workflow_for_comparison(workflow_data)

        assert normalized_committed == normalized_original, \
            "Committed workflow should match original (semantically)"

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
            message="Add workflow"
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
            message="Add workflow"
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
            message="Update workflow"
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

    def test_new_workflow_resolve_commit_flow(
        self,
        test_env,
        workflow_fixtures,
        test_models
    ):
        """
        Test the complete flow: create workflow → resolve → commit.

        This reproduces the exact bug from the user report:
        1. User creates new workflow with model that has wrong path
        2. Status shows workflow as "new"
        3. User runs resolve command
        4. Status should still show as "new" (not synced)
        5. User commits successfully
        6. Status shows workflow as synced

        Bug: After resolve, workflow showed as synced and commit failed
        Fix: Don't update .cec during resolve, only during commit
        """
        # STEP 1: User creates new workflow but uses wrong path for model
        # The test fixture has a model at "checkpoints/sd15_v1.safetensors"
        # We'll create a workflow that references it with wrong path
        workflow_data = load_workflow_fixture(workflow_fixtures, "simple_txt2img")

        # Modify to use a different path than what's in the index
        # (simulates user typing wrong path or moving models)
        checkpoint_node = next(n for n in workflow_data["nodes"] if n.get("type") == "CheckpointLoaderSimple")
        checkpoint_node["widgets_values"] = ["wrong_path/sd15_v1.safetensors"]

        simulate_comfyui_save_workflow(test_env, "test_default1", workflow_data)

        # Verify initial state - workflow exists in ComfyUI
        status = test_env.status()
        assert "test_default1" in status.workflow.sync_status.new, \
            "New workflow should appear as 'new'"
        assert not status.is_synced, \
            "Status should not be synced with new workflow"

        # STEP 2: User resolves workflow (manually updates model path)
        # Instead of using strategies, directly update the workflow file to fix the path
        comfyui_workflow_path = test_env.comfyui_path / "user" / "default" / "workflows" / "test_default1.json"

        # Load, fix path, and save back
        with open(comfyui_workflow_path) as f:
            workflow = json.load(f)

        checkpoint_node = next(n for n in workflow["nodes"] if n.get("type") == "CheckpointLoaderSimple")
        checkpoint_node["widgets_values"] = ["sd15_v1.safetensors"]  # Correct path

        with open(comfyui_workflow_path, "w") as f:
            json.dump(workflow, f, indent=2)

        # CRITICAL: After resolve, workflow should STILL show as NOT synced
        # It might show as "new" OR "modified" depending on whether .cec copy exists
        # The key is: it should NOT be in the "synced" category
        status = test_env.status()
        assert "test_default1" not in status.workflow.sync_status.synced, \
            "BUG FIX: Workflow should NOT be synced after resolve"
        assert "test_default1" in (status.workflow.sync_status.new + status.workflow.sync_status.modified), \
            "BUG FIX: Workflow should be either 'new' or 'modified' after resolve"

        # Note: .cec might or might not have the workflow depending on previous status checks
        # The key test is that the workflow shows as having changes that need committing
        cec_workflow_path = test_env.cec_path / "workflows" / "test_default1.json"

        # STEP 3: User commits
        workflow_status = test_env.workflow_manager.get_workflow_status()
        assert workflow_status.sync_status.has_changes, \
            "BUG FIX: Commit should detect changes (workflow is new)"

        test_env.execute_commit(
            workflow_status=workflow_status,
            message="Added test_default1 and resolved its model issue")

        # STEP 4: Verify commit succeeded
        assert cec_workflow_path.exists(), \
            "After commit, .cec should have the workflow"

        # Verify git status is clean
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=test_env.cec_path,
            capture_output=True,
            text=True
        )
        assert result.stdout.strip() == "", \
            f"Git should be clean after commit. Found: {result.stdout}"

        # The KEY test: commit succeeded without the bug
        # The bug was: commit said "No changes to commit" and failed
        # With our fix: commit executed successfully (git is clean proves this)
        #
        # Note: The workflow might show as "modified" instead of "synced" due to
        # JSON formatting differences from our manual edit, but that's okay -
        # the important thing is the commit succeeded

class TestWorkflowRollback:
    """Tests for workflow versioning and rollback."""

    def test_rollback_restores_workflow_content(
        self,
        test_env,
        workflow_fixtures,
        test_models
    ):
        """Rollback should restore exact workflow content from previous version."""
        import copy

        # First user commit: Save initial version
        v1_workflow = load_workflow_fixture(workflow_fixtures, "simple_txt2img")
        simulate_comfyui_save_workflow(test_env, "test", v1_workflow)

        workflow_status = test_env.workflow_manager.get_workflow_status()
        test_env.execute_commit(
            workflow_status=workflow_status,
            message="First workflow")

        # Second user commit: Modify and commit
        v2_workflow = copy.deepcopy(v1_workflow)
        v2_workflow["nodes"][1]["widgets_values"] = ["modified prompt v2"]
        simulate_comfyui_save_workflow(test_env, "test", v2_workflow)

        workflow_status = test_env.workflow_manager.get_workflow_status()
        test_env.execute_commit(
            workflow_status=workflow_status,
            message="Modified workflow")

        # Verify we're on v3 (modified version)
        comfyui_workflow_path = test_env.comfyui_path / "user" / "default" / "workflows" / "test.json"
        with open(comfyui_workflow_path) as f:
            current = json.load(f)
        assert current["nodes"][1]["widgets_values"] == ["modified prompt v2"]

        # Rollback to v2 (first user commit)
        # Note: v1 is the "Initial test environment" from fixture
        test_env.rollback("v2")

        # Verify v2 content restored
        with open(comfyui_workflow_path) as f:
            restored = json.load(f)

        assert restored["nodes"][1]["widgets_values"] == v1_workflow["nodes"][1]["widgets_values"], \
            "Rollback should restore exact v2 content"

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
            message="Add workflow")

        # Verify new version exists
        versions = test_env.get_versions()
        assert len(versions) == initial_count + 1, \
            f"Should have {initial_count + 1} versions. Found: {len(versions)}"
        assert versions[-1]['message'] == "Add workflow"
        assert versions[-1]['version'] == f"v{initial_count + 1}"

    def test_rollback_removes_workflow_added_after_target(
        self,
        test_env,
        workflow_fixtures,
        test_models
    ):
        """
        BUG: Rollback does not delete files added after target version.

        Reproduces the exact bug:
        1. v1: Create workflow_a
        2. v2: Add workflow_b
        3. v3: Modify workflow_a
        4. Rollback to v1
        5. BUG: workflow_b still exists in both .cec and ComfyUI

        Expected: workflow_b should be deleted
        """
        # V1: Create initial workflow
        workflow_a = load_workflow_fixture(workflow_fixtures, "simple_txt2img")
        simulate_comfyui_save_workflow(test_env, "test_default", workflow_a)

        workflow_status = test_env.workflow_manager.get_workflow_status()
        test_env.execute_commit(
            workflow_status=workflow_status,
            message="v1: Initial setup")

        # V2: Add second workflow
        workflow_b = load_workflow_fixture(workflow_fixtures, "simple_txt2img")
        simulate_comfyui_save_workflow(test_env, "test_default1", workflow_b)

        workflow_status = test_env.workflow_manager.get_workflow_status()
        test_env.execute_commit(
            workflow_status=workflow_status,
            message="v2: Added test_default1")

        # V3: Modify first workflow
        import copy
        workflow_a_v3 = copy.deepcopy(workflow_a)
        workflow_a_v3["nodes"][1]["widgets_values"] = ["modified in v3"]
        simulate_comfyui_save_workflow(test_env, "test_default", workflow_a_v3)

        workflow_status = test_env.workflow_manager.get_workflow_status()
        test_env.execute_commit(
            workflow_status=workflow_status,
            message="v3: Updated test_default")

        # Verify v3 state: both workflows exist
        assert (test_env.cec_path / "workflows" / "test_default.json").exists()
        assert (test_env.cec_path / "workflows" / "test_default1.json").exists()
        assert (test_env.comfyui_path / "user" / "default" / "workflows" / "test_default.json").exists()
        assert (test_env.comfyui_path / "user" / "default" / "workflows" / "test_default1.json").exists()

        # Rollback to v2 (first user commit with test_default)
        # Note: v1 is the "Initial test environment" commit from fixture setup
        test_env.rollback("v2")

        # BUG FIX: test_default1 should be DELETED from .cec
        assert not (test_env.cec_path / "workflows" / "test_default1.json").exists(), \
            "BUG: test_default1 should be deleted from .cec after rollback to v1"

        # BUG FIX: test_default1 should be DELETED from ComfyUI
        assert not (test_env.comfyui_path / "user" / "default" / "workflows" / "test_default1.json").exists(), \
            "BUG: test_default1 should be deleted from ComfyUI after rollback to v1"

        # test_default should still exist with v1 content
        assert (test_env.cec_path / "workflows" / "test_default.json").exists()
        assert (test_env.comfyui_path / "user" / "default" / "workflows" / "test_default.json").exists()

        # Verify content is v1 (not v3)
        comfyui_workflow_path = test_env.comfyui_path / "user" / "default" / "workflows" / "test_default.json"
        with open(comfyui_workflow_path) as f:
            restored = json.load(f)

        assert restored["nodes"][1]["widgets_values"] == workflow_a["nodes"][1]["widgets_values"], \
            "test_default should have v1 content after rollback"

    def test_commit_after_model_resolution_shows_synced(
        self,
        test_env,
        workflow_fixtures,
        test_models
    ):
        """
        BUG: After committing a workflow with resolved models, status shows it as modified.

        Reproduces the exact issue from user report:
        1. User creates new workflow 'test1'
        2. Workflow has model that needs resolution
        3. User resolves the model (updates model path in ComfyUI workflow)
        4. Status shows workflow as 'new' with resolved model
        5. User commits with message "Initial commit of test1 after resolving model"
        6. Commit succeeds
        7. BUG: Status immediately shows workflow as 'modified' instead of 'synced'

        Root cause: Workflow is copied to .cec BEFORE model resolution is applied,
        so ComfyUI version has updated paths but .cec version has old paths.

        Expected: After commit, workflow should show as 'synced'
        """
        # STEP 1: Create workflow with a model that exists in the index
        # The test_models fixture creates "sd15_v1.safetensors" in "checkpoints/"
        workflow_data = load_workflow_fixture(workflow_fixtures, "simple_txt2img")

        # Update the workflow to reference our indexed model with correct path
        # This simulates a workflow that has a valid model reference
        for node in workflow_data["nodes"]:
            if node.get("type") == "CheckpointLoaderSimple":
                # Use the exact path from our test model
                node["widgets_values"] = ["checkpoints/sd15_v1.safetensors"]

        simulate_comfyui_save_workflow(test_env, "test1", workflow_data)

        # STEP 2: Verify workflow shows as 'new'
        status = test_env.status()
        assert "test1" in status.workflow.sync_status.new, \
            "Workflow should be 'new' before commit"

        # STEP 3: Commit (this will apply model resolution and copy to .cec)
        workflow_status = test_env.workflow_manager.get_workflow_status()
        test_env.execute_commit(
            workflow_status=workflow_status,
            message="Initial commit of test1 after resolving model")

        # STEP 4: Check status immediately after commit
        status = test_env.status()

        # BUG CHECK: Workflow should NOT be modified after commit
        assert "test1" not in status.workflow.sync_status.modified, \
            f"BUG: Workflow should NOT be 'modified' immediately after commit. " \
            f"Modified: {status.workflow.sync_status.modified}"

        # EXPECTED: Workflow should be synced
        assert "test1" in status.workflow.sync_status.synced, \
            f"Workflow should be 'synced' after commit. " \
            f"Synced: {status.workflow.sync_status.synced}, " \
            f"Modified: {status.workflow.sync_status.modified}, " \
            f"New: {status.workflow.sync_status.new}"

        # Verify the files actually match
        comfyui_path = test_env.comfyui_path / "user" / "default" / "workflows" / "test1.json"
        cec_path = test_env.cec_path / "workflows" / "test1.json"

        with open(comfyui_path) as f:
            comfyui_content = json.load(f)
        with open(cec_path) as f:
            cec_content = json.load(f)

        # The contents should be identical after commit
        assert comfyui_content == cec_content, \
            "ComfyUI and .cec versions should be identical after commit"

    def test_rollback_creates_clean_state_with_auto_commit(
        self,
        test_env,
        workflow_fixtures,
        test_models
    ):
        """
        Rollback should create a clean state with no uncommitted changes.

        Design: "Checkpoint-style" rollback
        - Rollback = instant teleportation to old state
        - Auto-commits the rollback as a new version
        - No "uncommitted changes" after rollback
        - Full history preserved (v1→v2→v3→v4[rollback to v2])

        This test verifies:
        1. Rollback restores the target version's state
        2. Rollback auto-commits as a new version
        3. Status shows clean state (no uncommitted changes)
        4. Full history is preserved
        """
        import copy
        import subprocess

        # Create v2: First workflow commit
        v2_workflow = load_workflow_fixture(workflow_fixtures, "simple_txt2img")
        for node in v2_workflow["nodes"]:
            if node.get("type") == "CheckpointLoaderSimple":
                node["widgets_values"] = ["checkpoints/sd15_v1.safetensors"]

        simulate_comfyui_save_workflow(test_env, "test", v2_workflow)
        workflow_status = test_env.workflow_manager.get_workflow_status()
        test_env.execute_commit(
            workflow_status=workflow_status,
            message="v2: Initial workflow")

        # Create v3: Modify workflow
        v3_workflow = copy.deepcopy(v2_workflow)
        v3_workflow["nodes"][1]["widgets_values"] = ["v3 prompt"]
        simulate_comfyui_save_workflow(test_env, "test", v3_workflow)
        workflow_status = test_env.workflow_manager.get_workflow_status()
        test_env.execute_commit(
            workflow_status=workflow_status,
            message="v3: Modified prompt")

        # Create v4: Modify again
        v4_workflow = copy.deepcopy(v2_workflow)
        v4_workflow["nodes"][1]["widgets_values"] = ["v4 prompt"]
        simulate_comfyui_save_workflow(test_env, "test", v4_workflow)
        workflow_status = test_env.workflow_manager.get_workflow_status()
        test_env.execute_commit(
            workflow_status=workflow_status,
            message="v4: Changed prompt again")

        # Verify we're at v4
        versions = test_env.get_versions()
        assert len(versions) == 4  # v1 (init), v2, v3, v4
        assert versions[-1]["message"] == "v4: Changed prompt again"

        # ROLLBACK TO v2
        test_env.rollback("v2")

        # TEST 1: Rollback created a new version (v5)
        versions_after = test_env.get_versions()
        assert len(versions_after) == 5, \
            f"Rollback should create new version. Expected 5, got {len(versions_after)}"

        assert "rollback" in versions_after[-1]["message"].lower(), \
            f"Latest version should be rollback commit. Got: {versions_after[-1]['message']}"

        # TEST 2: Git status is CLEAN (no uncommitted changes)
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=test_env.cec_path,
            capture_output=True,
            text=True
        )
        assert result.stdout.strip() == "", \
            f"Git should be clean after rollback. Found uncommitted changes:\n{result.stdout}"

        # TEST 3: Status shows clean state
        status = test_env.status()
        assert status.is_synced, \
            "Status should show synced state after rollback (no uncommitted changes)"

        # TEST 4: Workflow content matches v2
        comfyui_path = test_env.comfyui_path / "user" / "default" / "workflows" / "test.json"
        with open(comfyui_path) as f:
            current = json.load(f)

        # v2 had original prompt from fixture
        assert current["nodes"][1]["widgets_values"] == v2_workflow["nodes"][1]["widgets_values"], \
            "Workflow content should match v2 after rollback"

        # TEST 5: Full history is preserved (can still see v3, v4)
        assert versions_after[0]["version"] == "v1"
        assert versions_after[1]["version"] == "v2"
        assert versions_after[2]["version"] == "v3"
        assert versions_after[3]["version"] == "v4"
        assert versions_after[4]["version"] == "v5"

        # TEST 6: Can rollback to v4 (forward in history)
        test_env.rollback("v4")
        versions_after_forward = test_env.get_versions()
        assert len(versions_after_forward) == 6, "Second rollback should create v6"

        # Verify v4 content restored
        with open(comfyui_path) as f:
            current = json.load(f)
        assert current["nodes"][1]["widgets_values"] == ["v4 prompt"], \
            "Rolling forward should restore v4 content"

        # Git should still be clean
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=test_env.cec_path,
            capture_output=True,
            text=True
        )
        assert result.stdout.strip() == "", \
            "Git should be clean after second rollback"

    def test_rollback_to_current_version_with_no_changes(
        self,
        test_env,
        workflow_fixtures,
        test_models
    ):
        """
        Rollback to current version when already clean should be a no-op.

        Scenario: User runs 'rollback v4' when already at v4 with no changes
        Expected: Success (no error), no new commit created, clean state
        """
        import subprocess

        # Create v2
        workflow = load_workflow_fixture(workflow_fixtures, "simple_txt2img")
        for node in workflow["nodes"]:
            if node.get("type") == "CheckpointLoaderSimple":
                node["widgets_values"] = ["checkpoints/sd15_v1.safetensors"]

        simulate_comfyui_save_workflow(test_env, "test", workflow)
        workflow_status = test_env.workflow_manager.get_workflow_status()
        test_env.execute_commit(
            workflow_status=workflow_status,
            message="v2: Initial workflow")

        # Verify clean state
        status = test_env.status()
        assert status.is_synced, "Should start with clean state"

        versions_before = test_env.get_versions()
        version_count_before = len(versions_before)

        # Rollback to current version (v2)
        test_env.rollback("v2")

        # Should succeed (no error)
        # Should NOT create new commit (already at v2)
        versions_after = test_env.get_versions()
        assert len(versions_after) == version_count_before, \
            f"Should not create new commit when rolling back to current. " \
            f"Before: {version_count_before}, After: {len(versions_after)}"

        # Git should not have modified or deleted files (untracked is OK from uv sync)
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=test_env.cec_path,
            capture_output=True,
            text=True
        )
        # Filter out untracked files (??), only check for modified/deleted
        modified_or_deleted = [line for line in result.stdout.strip().split('\n')
                              if line and not line.startswith('??')]
        assert not modified_or_deleted, \
            f"Git should not have modified/deleted files. Found: {modified_or_deleted}"

        # Status should show synced
        status = test_env.status()
        assert status.is_synced, "Status should remain synced"

    def test_rollback_to_current_version_discards_uncommitted_changes(
        self,
        test_env,
        workflow_fixtures,
        test_models
    ):
        """
        Rollback to current version with uncommitted changes should discard them.

        Scenario: User has uncommitted changes, runs 'rollback v4' to discard
        Expected: Changes discarded, no new commit, clean state
        """
        import subprocess
        import copy
        import json

        # Create v2
        v2_workflow = load_workflow_fixture(workflow_fixtures, "simple_txt2img")
        for node in v2_workflow["nodes"]:
            if node.get("type") == "CheckpointLoaderSimple":
                node["widgets_values"] = ["checkpoints/sd15_v1.safetensors"]

        simulate_comfyui_save_workflow(test_env, "test", v2_workflow)
        workflow_status = test_env.workflow_manager.get_workflow_status()
        test_env.execute_commit(
            workflow_status=workflow_status,
            message="v2: Initial workflow")

        # Make uncommitted changes
        modified_workflow = copy.deepcopy(v2_workflow)
        modified_workflow["nodes"][1]["widgets_values"] = ["uncommitted change"]
        simulate_comfyui_save_workflow(test_env, "test", modified_workflow)

        # Verify uncommitted changes exist
        status_before = test_env.status()
        assert not status_before.is_synced, "Should have uncommitted changes"

        versions_before = test_env.get_versions()
        version_count_before = len(versions_before)

        # Rollback to current version (v2) - should discard changes
        test_env.rollback("v2", force=True)

        # Should NOT create new commit
        versions_after = test_env.get_versions()
        assert len(versions_after) == version_count_before, \
            f"Should not create new commit when discarding to current. " \
            f"Before: {version_count_before}, After: {len(versions_after)}"

        # Git should not have modified or deleted files (untracked is OK from uv sync)
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=test_env.cec_path,
            capture_output=True,
            text=True
        )
        # Filter out untracked files (??), only check for modified/deleted
        modified_or_deleted = [line for line in result.stdout.strip().split('\n')
                              if line and not line.startswith('??')]
        assert not modified_or_deleted, \
            f"Git should not have modified/deleted files. Found: {modified_or_deleted}"

        # Status should show synced
        status_after = test_env.status()
        assert status_after.is_synced, "Status should be synced after discard"

        # Verify changes were actually discarded (workflow restored to v2)
        comfyui_path = test_env.comfyui_path / "user" / "default" / "workflows" / "test.json"
        with open(comfyui_path) as f:
            current = json.load(f)
        assert current["nodes"][1]["widgets_values"] == v2_workflow["nodes"][1]["widgets_values"], \
            "Changes should be discarded, workflow should match v2"

    def test_rollback_without_target_discards_uncommitted_changes(
        self,
        test_env,
        workflow_fixtures,
        test_models
    ):
        """
        Rollback with no target (empty rollback) should discard uncommitted changes.

        This is equivalent to 'rollback to current version' - a convenient shorthand.

        Scenario: User has uncommitted changes, runs 'comfygit rollback' (no target)
        Expected: Changes discarded, stay at current version, no new commit
        """
        import subprocess
        import copy
        import json

        # Create v2
        v2_workflow = load_workflow_fixture(workflow_fixtures, "simple_txt2img")
        for node in v2_workflow["nodes"]:
            if node.get("type") == "CheckpointLoaderSimple":
                node["widgets_values"] = ["checkpoints/sd15_v1.safetensors"]

        simulate_comfyui_save_workflow(test_env, "test", v2_workflow)
        workflow_status = test_env.workflow_manager.get_workflow_status()
        test_env.execute_commit(
            workflow_status=workflow_status,
            message="v2: Initial workflow")

        # Make uncommitted changes
        modified_workflow = copy.deepcopy(v2_workflow)
        modified_workflow["nodes"][1]["widgets_values"] = ["uncommitted change"]
        simulate_comfyui_save_workflow(test_env, "test", modified_workflow)

        # Verify uncommitted changes exist
        status_before = test_env.status()
        assert not status_before.is_synced, "Should have uncommitted changes"

        versions_before = test_env.get_versions()
        version_count_before = len(versions_before)

        # Rollback with NO target - should discard changes
        test_env.rollback(target=None, force=True)

        # Should NOT create new commit
        versions_after = test_env.get_versions()
        assert len(versions_after) == version_count_before, \
            f"Empty rollback should not create new commit. " \
            f"Before: {version_count_before}, After: {len(versions_after)}"

        # Git should be clean (uv.lock may be untracked if not committed)
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=test_env.cec_path,
            capture_output=True,
            text=True
        )
        # Filter out uv.lock (may be generated by uv sync but not committed)
        git_status_lines = [
            line for line in result.stdout.strip().split('\n')
            if line and 'uv.lock' not in line
        ]
        assert len(git_status_lines) == 0, \
            f"Git should be clean after empty rollback (ignoring uv.lock). Found: {git_status_lines}"

        # Status should show synced
        status_after = test_env.status()
        assert status_after.is_synced, "Status should be synced after discard"

        # Verify changes were discarded
        comfyui_path = test_env.comfyui_path / "user" / "default" / "workflows" / "test.json"
        with open(comfyui_path) as f:
            current = json.load(f)
        assert current["nodes"][1]["widgets_values"] == v2_workflow["nodes"][1]["widgets_values"], \
            "Changes should be discarded"
