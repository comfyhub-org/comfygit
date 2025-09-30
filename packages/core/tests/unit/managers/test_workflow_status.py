"""Tests for enhanced WorkflowManager status system."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from comfydock_core.models.workflow import (
    WorkflowSyncStatus,
    WorkflowAnalysisStatus,
    DetailedWorkflowStatus,
)


class TestWorkflowSyncStatus:
    """Test WorkflowSyncStatus dataclass."""

    def test_has_changes_with_new_workflows(self):
        """Test has_changes property with new workflows."""
        status = WorkflowSyncStatus(new=["workflow1"], modified=[], deleted=[], synced=[])
        assert status.has_changes is True

    def test_has_changes_with_modified_workflows(self):
        """Test has_changes property with modified workflows."""
        status = WorkflowSyncStatus(new=[], modified=["workflow1"], deleted=[], synced=[])
        assert status.has_changes is True

    def test_has_changes_with_deleted_workflows(self):
        """Test has_changes property with deleted workflows."""
        status = WorkflowSyncStatus(new=[], modified=[], deleted=["workflow1"], synced=[])
        assert status.has_changes is True

    def test_has_changes_with_only_synced(self):
        """Test has_changes property with only synced workflows."""
        status = WorkflowSyncStatus(new=[], modified=[], deleted=[], synced=["workflow1"])
        assert status.has_changes is False

    def test_total_count(self):
        """Test total_count property."""
        status = WorkflowSyncStatus(
            new=["wf1", "wf2"],
            modified=["wf3"],
            deleted=["wf4"],
            synced=["wf5", "wf6"]
        )
        assert status.total_count == 6


class TestDetailedWorkflowStatus:
    """Test DetailedWorkflowStatus dataclass."""

    def test_total_issues_with_no_issues(self):
        """Test total_issues when no workflows have issues."""
        from comfydock_core.models.workflow import (
            WorkflowDependencies,
            ResolutionResult,
        )

        sync_status = WorkflowSyncStatus(synced=["wf1"])
        analysis = WorkflowAnalysisStatus(
            name="wf1",
            sync_state="synced",
            dependencies=WorkflowDependencies(workflow_name="wf1"),
            resolution=ResolutionResult()  # No issues
        )

        status = DetailedWorkflowStatus(
            sync_status=sync_status,
            analyzed_workflows=[analysis]
        )

        assert status.total_issues == 0
        assert status.is_commit_safe is True

    def test_total_issues_with_unresolved_models(self):
        """Test total_issues with unresolved models."""
        from comfydock_core.models.workflow import (
            WorkflowDependencies,
            ResolutionResult,
            WorkflowNodeWidgetRef,
        )

        sync_status = WorkflowSyncStatus(modified=["wf1"])

        model_ref = WorkflowNodeWidgetRef(
            node_id="3",
            node_type="CheckpointLoaderSimple",
            widget_index=0,
            widget_value="model.safetensors"
        )

        analysis = WorkflowAnalysisStatus(
            name="wf1",
            sync_state="modified",
            dependencies=WorkflowDependencies(workflow_name="wf1"),
            resolution=ResolutionResult(models_unresolved=[model_ref])
        )

        status = DetailedWorkflowStatus(
            sync_status=sync_status,
            analyzed_workflows=[analysis]
        )

        assert status.total_issues == 1
        assert status.total_unresolved_models == 1
        assert status.is_commit_safe is False

    def test_get_suggested_actions_with_model_issues(self):
        """Test suggested actions generation with model issues."""
        from comfydock_core.models.workflow import (
            WorkflowDependencies,
            ResolutionResult,
            WorkflowNodeWidgetRef,
        )

        sync_status = WorkflowSyncStatus(modified=["wf1"])

        model_ref = WorkflowNodeWidgetRef(
            node_id="3",
            node_type="CheckpointLoaderSimple",
            widget_index=0,
            widget_value="model.safetensors"
        )

        analysis = WorkflowAnalysisStatus(
            name="wf1",
            sync_state="modified",
            dependencies=WorkflowDependencies(workflow_name="wf1"),
            resolution=ResolutionResult(models_unresolved=[model_ref])
        )

        status = DetailedWorkflowStatus(
            sync_status=sync_status,
            analyzed_workflows=[analysis]
        )

        actions = status.get_suggested_actions()
        assert len(actions) > 0
        assert any("model" in action.lower() for action in actions)

    def test_get_suggested_actions_ready_to_commit(self):
        """Test suggested actions when ready to commit."""
        from comfydock_core.models.workflow import (
            WorkflowDependencies,
            ResolutionResult,
        )

        sync_status = WorkflowSyncStatus(modified=["wf1"])

        analysis = WorkflowAnalysisStatus(
            name="wf1",
            sync_state="modified",
            dependencies=WorkflowDependencies(workflow_name="wf1"),
            resolution=ResolutionResult()  # No issues
        )

        status = DetailedWorkflowStatus(
            sync_status=sync_status,
            analyzed_workflows=[analysis]
        )

        actions = status.get_suggested_actions()
        assert any("commit" in action.lower() for action in actions)