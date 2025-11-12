"""Tests for enhanced WorkflowManager status system."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from comfygit_core.models.workflow import (
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
        from comfygit_core.models.workflow import (
            WorkflowDependencies,
            ResolutionResult,
        )

        sync_status = WorkflowSyncStatus(synced=["wf1"])
        analysis = WorkflowAnalysisStatus(
            name="wf1",
            sync_state="synced",
            dependencies=WorkflowDependencies(workflow_name="wf1"),
            resolution=ResolutionResult(workflow_name="wf1")  # No issues
        )

        status = DetailedWorkflowStatus(
            sync_status=sync_status,
            analyzed_workflows=[analysis]
        )

        assert status.total_issues == 0
        assert status.is_commit_safe is True

    def test_total_issues_with_unresolved_models(self):
        """Test total_issues with unresolved models."""
        from comfygit_core.models.workflow import (
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
            resolution=ResolutionResult(workflow_name="wf1", models_unresolved=[model_ref])
        )

        status = DetailedWorkflowStatus(
            sync_status=sync_status,
            analyzed_workflows=[analysis]
        )

        assert status.total_issues == 1
        assert status.total_unresolved_models == 1
        assert status.is_commit_safe is False


class TestWorkflowAnalysisStatusDownloadIntents:
    """Test WorkflowAnalysisStatus download intent detection."""

    def test_has_issues_with_download_intents(self):
        """Test that has_issues returns True when download intents are present."""
        from comfygit_core.models.workflow import (
            WorkflowDependencies,
            ResolutionResult,
            ResolvedModel,
            WorkflowNodeWidgetRef,
        )
        from pathlib import Path

        sync_status = WorkflowSyncStatus(synced=["wf1"])

        model_ref = WorkflowNodeWidgetRef(
            node_id="4",
            node_type="CheckpointLoaderSimple",
            widget_index=0,
            widget_value="model.safetensors"
        )

        # Create resolved model with download_intent match_type
        download_intent = ResolvedModel(
            workflow="wf1",
            reference=model_ref,
            match_type="download_intent",
            resolved_model=None,
            model_source="https://example.com/model.safetensors",
            target_path=Path("checkpoints/model.safetensors"),
            is_optional=False,
            match_confidence=1.0
        )

        analysis = WorkflowAnalysisStatus(
            name="wf1",
            sync_state="synced",
            dependencies=WorkflowDependencies(workflow_name="wf1"),
            resolution=ResolutionResult(
                workflow_name="wf1",
                models_resolved=[download_intent]
            )
        )

        assert analysis.has_issues is True

    def test_has_issues_without_download_intents(self):
        """Test that has_issues returns False when no download intents."""
        from comfygit_core.models.workflow import (
            WorkflowDependencies,
            ResolutionResult,
        )

        analysis = WorkflowAnalysisStatus(
            name="wf1",
            sync_state="synced",
            dependencies=WorkflowDependencies(workflow_name="wf1"),
            resolution=ResolutionResult(workflow_name="wf1")
        )

        assert analysis.has_issues is False

    def test_download_intents_count(self):
        """Test download_intents_count property."""
        from comfygit_core.models.workflow import (
            WorkflowDependencies,
            ResolutionResult,
            ResolvedModel,
            WorkflowNodeWidgetRef,
        )
        from pathlib import Path

        ref1 = WorkflowNodeWidgetRef(
            node_id="4",
            node_type="CheckpointLoaderSimple",
            widget_index=0,
            widget_value="model1.safetensors"
        )

        ref2 = WorkflowNodeWidgetRef(
            node_id="10",
            node_type="LoraLoader",
            widget_index=0,
            widget_value="lora.safetensors"
        )

        download1 = ResolvedModel(
            workflow="wf1",
            reference=ref1,
            match_type="download_intent",
            model_source="https://example.com/model1.safetensors",
            target_path=Path("checkpoints/model1.safetensors")
        )

        download2 = ResolvedModel(
            workflow="wf1",
            reference=ref2,
            match_type="download_intent",
            model_source="https://example.com/lora.safetensors",
            target_path=Path("loras/lora.safetensors")
        )

        # Add a regular resolved model
        regular_model = ResolvedModel(
            workflow="wf1",
            reference=ref1,
            match_type="exact",
            resolved_model=None
        )

        analysis = WorkflowAnalysisStatus(
            name="wf1",
            sync_state="synced",
            dependencies=WorkflowDependencies(workflow_name="wf1"),
            resolution=ResolutionResult(
                workflow_name="wf1",
                models_resolved=[download1, download2, regular_model]
            )
        )

        assert analysis.download_intents_count == 2