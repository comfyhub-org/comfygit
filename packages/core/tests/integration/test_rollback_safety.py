"""Tests for rollback safety with uncommitted changes."""
import json
import pytest
from comfygit_core.models.exceptions import CDEnvironmentError


# Test strategies for rollback confirmation
class AlwaysConfirmStrategy:
    """Always confirm rollback (for testing --yes behavior)."""
    def confirm_destructive_rollback(self, git_changes: bool, workflow_changes: bool) -> bool:
        return True


class AlwaysDenyStrategy:
    """Always deny rollback (for testing cancellation)."""
    def confirm_destructive_rollback(self, git_changes: bool, workflow_changes: bool) -> bool:
        return False


class TestRollbackSafety:
    """Test that rollback protects uncommitted work."""

    def test_rollback_blocks_with_uncommitted_changes(self, test_env, test_models):
        """Rollback should error when there are uncommitted changes (no --force)."""
        # ARRANGE: Create v1
        workflow_path = test_env.comfyui_path / "user/default/workflows/test_wf.json"
        workflow_path.parent.mkdir(parents=True, exist_ok=True)
        workflow_path.write_text(json.dumps({"nodes": [], "links": [], "extra": {}}))
        test_env.workflow_manager.copy_all_workflows()
        test_env.commit("v1: Initial")

        # Create v2
        workflow_path.write_text(json.dumps({"nodes": [], "links": [], "extra": {"v2": True}}))
        test_env.workflow_manager.copy_all_workflows()
        test_env.commit("v2: Update")

        # Make uncommitted change in .cec/ (git tracked)
        cec_workflow_path = test_env.cec_path / "workflows/test_wf.json"
        with open(cec_workflow_path) as f:
            workflow = json.load(f)
        workflow["extra"]["uncommitted"] = True
        with open(cec_workflow_path, 'w') as f:
            json.dump(workflow, f)

        # ACT & ASSERT: Rollback should raise error
        with pytest.raises(CDEnvironmentError, match="uncommitted changes"):
            test_env.rollback("v1")

        # Verify data not lost
        with open(cec_workflow_path) as f:
            workflow = json.load(f)
        assert workflow["extra"]["uncommitted"] is True

    def test_rollback_with_force_discards_changes(self, test_env, test_models):
        """Rollback with force=True should discard uncommitted changes."""
        # ARRANGE: Create v1
        workflow_path = test_env.comfyui_path / "user/default/workflows/test_wf.json"
        workflow_path.parent.mkdir(parents=True, exist_ok=True)
        workflow_path.write_text(json.dumps({"nodes": [], "links": [], "extra": {}}))
        test_env.workflow_manager.copy_all_workflows()
        test_env.commit("v1: Initial")

        # Create v2
        workflow_path.write_text(json.dumps({"nodes": [], "links": [], "extra": {"v2": True}}))
        test_env.workflow_manager.copy_all_workflows()
        test_env.commit("v2: Update")

        # Make uncommitted change in .cec/ (git tracked)
        cec_workflow_path = test_env.cec_path / "workflows/test_wf.json"
        with open(cec_workflow_path) as f:
            workflow = json.load(f)
        workflow["extra"]["will_be_lost"] = True
        with open(cec_workflow_path, 'w') as f:
            json.dump(workflow, f)

        # ACT: Rollback with force
        test_env.rollback("v1", force=True)

        # ASSERT: Changes discarded, back to v1 state
        # Rollback restores workflows to ComfyUI, check there
        if workflow_path.exists():
            with open(workflow_path) as f:
                workflow = json.load(f)
            assert "will_be_lost" not in workflow.get("extra", {})
            assert "v2" not in workflow.get("extra", {})

    def test_rollback_without_uncommitted_changes_works(self, test_env, test_models):
        """Rollback works normally when no uncommitted changes."""
        # ARRANGE: Create v1 and v2
        workflow_path = test_env.comfyui_path / "user/default/workflows/test_wf.json"
        workflow_path.parent.mkdir(parents=True, exist_ok=True)
        workflow_path.write_text(json.dumps({"nodes": [], "links": [], "extra": {}}))
        test_env.workflow_manager.copy_all_workflows()
        test_env.commit("v1: Initial")

        workflow_path.write_text(json.dumps({"nodes": [], "links": [], "extra": {"v2": True}}))
        test_env.workflow_manager.copy_all_workflows()
        test_env.commit("v2: Update")

        # ACT: Rollback (no uncommitted changes, should succeed)
        test_env.rollback("v1")

        # ASSERT: Rollback completed without error (implicit pass if no exception)

    def test_rollback_blocks_with_modified_comfyui_workflows(self, test_env, test_models):
        """Rollback should detect and protect modified workflows in ComfyUI (not yet committed).

        This reproduces the exact issue from the user's scenario:
        - User has modified workflow in ComfyUI (shows as 'modified' in status)
        - User runs rollback to earlier version without strategy
        - Expected: should raise error about uncommitted changes
        """
        # ARRANGE: Create v1
        workflow_path = test_env.comfyui_path / "user/default/workflows/important_work.json"
        workflow_path.parent.mkdir(parents=True, exist_ok=True)
        workflow_path.write_text(json.dumps({"nodes": [], "links": [], "extra": {"version": "v1"}}))
        test_env.workflow_manager.copy_all_workflows()
        test_env.commit("v1: Initial workflow")

        # Create v2
        workflow_path.write_text(json.dumps({"nodes": [], "links": [], "extra": {"version": "v2"}}))
        test_env.workflow_manager.copy_all_workflows()
        test_env.commit("v2: Updated workflow")

        # Simulate user editing workflow in ComfyUI (uncommitted changes)
        workflow_path.write_text(json.dumps({
            "nodes": [{"type": "NewNode"}],
            "links": [],
            "extra": {"version": "v2-modified", "important_edits": True}
        }))

        # Verify status sees the modification
        status = test_env.status()
        assert status.workflow.sync_status.has_changes
        assert len(status.workflow.sync_status.modified) == 1

        # ACT & ASSERT: Rollback without strategy should raise error
        with pytest.raises(CDEnvironmentError, match="uncommitted|workflow"):
            test_env.rollback("v1")

        # Verify data not lost (rollback was blocked)
        with open(workflow_path) as f:
            workflow = json.load(f)
        assert workflow["extra"]["important_edits"] is True
        assert workflow["extra"]["version"] == "v2-modified"

    def test_rollback_with_workflow_changes_and_deny_strategy(self, test_env, test_models):
        """Rollback with deny strategy should block even when strategy is provided."""
        # ARRANGE: Create v1 and v2
        workflow_path = test_env.comfyui_path / "user/default/workflows/test_wf.json"
        workflow_path.parent.mkdir(parents=True, exist_ok=True)
        workflow_path.write_text(json.dumps({"nodes": [], "links": [], "extra": {"v": 1}}))
        test_env.workflow_manager.copy_all_workflows()
        test_env.commit("v1")

        workflow_path.write_text(json.dumps({"nodes": [], "links": [], "extra": {"v": 2}}))
        test_env.workflow_manager.copy_all_workflows()
        test_env.commit("v2")

        # Modify workflow
        workflow_path.write_text(json.dumps({"nodes": [], "links": [], "extra": {"v": 3}}))

        # ACT & ASSERT: Strategy denies, should raise cancelled error
        strategy = AlwaysDenyStrategy()
        with pytest.raises(CDEnvironmentError, match="cancelled"):
            test_env.rollback("v1", strategy=strategy)

        # Verify data not lost
        with open(workflow_path) as f:
            workflow = json.load(f)
        assert workflow["extra"]["v"] == 3

    def test_rollback_with_workflow_changes_and_confirm_strategy(self, test_env, test_models):
        """Rollback with confirm strategy should proceed despite uncommitted changes."""
        # ARRANGE: Create v1 with workflow
        workflow_path = test_env.comfyui_path / "user/default/workflows/test_wf.json"
        workflow_path.parent.mkdir(parents=True, exist_ok=True)
        workflow_path.write_text(json.dumps({"nodes": [], "links": [], "extra": {"v": 1}}))
        test_env.workflow_manager.copy_all_workflows()
        test_env.commit("v1")

        # Create v2 with updated workflow
        workflow_path.write_text(json.dumps({"nodes": [], "links": [], "extra": {"v": 2}}))
        test_env.workflow_manager.copy_all_workflows()
        test_env.commit("v2")

        # Modify workflow (uncommitted)
        workflow_path.write_text(json.dumps({"nodes": [], "links": [], "extra": {"v": 3}}))

        # ACT: Strategy confirms, rollback should proceed without error
        strategy = AlwaysConfirmStrategy()
        test_env.rollback("v1", strategy=strategy)

        # ASSERT: Rollback succeeded (implicit - no exception raised)
        # This proves the strategy pattern works - user confirmed, rollback proceeded
