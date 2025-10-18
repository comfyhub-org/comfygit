"""Integration tests for deferred model downloads feature.

Tests the complete flow of collecting download intents during interactive resolution
and executing batch downloads at the end.
"""
from pathlib import Path
from unittest.mock import Mock

import pytest

from comfydock_core.models.workflow import BatchDownloadCallbacks, ResolvedModel
from comfydock_core.strategies.auto import AutoModelStrategy
from conftest import simulate_comfyui_save_workflow
from helpers.model_index_builder import ModelIndexBuilder
from helpers.pyproject_assertions import PyprojectAssertions
from helpers.workflow_builder import WorkflowBuilder


class TestDeferredModelDownloads:
    """Test deferred model download functionality."""

    def test_download_intent_stored_in_pyproject(self, test_env):
        """Test that download intent is written to pyproject with sources and relative_path."""
        # ARRANGE - Create workflow with missing model
        workflow = (
            WorkflowBuilder()
            .add_checkpoint_loader("missing_model.safetensors")
            .build()
        )
        simulate_comfyui_save_workflow(test_env, "test", workflow)

        # Create mock strategy that returns download intent
        mock_strategy = Mock()
        target_path = Path("checkpoints/sdxl/missing_model.safetensors")
        download_url = "https://civitai.com/api/download/models/123456"

        mock_strategy.resolve_model = Mock(return_value=ResolvedModel(
            workflow="test",
            reference=Mock(
                node_id="1",
                node_type="CheckpointLoaderSimple",
                widget_index=0,
                widget_value="missing_model.safetensors"
            ),
            resolved_model=None,
            model_source=download_url,
            is_optional=False,
            match_type="download_intent",
            target_path=target_path
        ))

        # ACT - Resolve workflow with download intent
        result = test_env.resolve_workflow(
            name="test",
            model_strategy=mock_strategy,
            fix=True
        )

        # ASSERT - Download intent should be stored in pyproject
        assertions = PyprojectAssertions(test_env)

        # Verify workflow model has download intent fields
        workflow_models = test_env.pyproject.workflows.get_workflow_models("test")
        assert len(workflow_models) == 1, "Should have one workflow model"

        model = workflow_models[0]
        assert model.status == "unresolved", "Status should be unresolved (no hash yet)"
        assert model.sources == [download_url], "Should store download URL in sources"
        assert model.relative_path == str(target_path), "Should store target path"
        assert model.hash is None, "Hash should be None until downloaded"

    def test_download_intent_resume_after_interrupt(self, test_env):
        """Test that download intents are detected on resume and don't re-prompt."""
        # ARRANGE - Create workflow with download intent already in pyproject
        workflow = (
            WorkflowBuilder()
            .add_checkpoint_loader("model.safetensors")
            .build()
        )
        simulate_comfyui_save_workflow(test_env, "test", workflow)

        # Manually add download intent to pyproject (simulating previous interrupted session)
        from comfydock_core.models.manifest import ManifestWorkflowModel
        from comfydock_core.models.workflow import WorkflowNodeWidgetRef

        download_intent = ManifestWorkflowModel(
            filename="model.safetensors",
            category="checkpoints",
            criticality="flexible",
            status="unresolved",
            nodes=[WorkflowNodeWidgetRef(
                node_id="1",
                node_type="CheckpointLoaderSimple",
                widget_index=0,
                widget_value="model.safetensors"
            )],
            sources=["https://civitai.com/api/download/models/999"],
            relative_path="checkpoints/model.safetensors"
        )
        test_env.pyproject.workflows.add_workflow_model("test", download_intent)

        # Create mock strategy that should NOT be called (intent should be auto-resolved)
        mock_strategy = Mock()
        mock_strategy.resolve_model = Mock(side_effect=AssertionError("Should not prompt user"))

        # ACT - Resolve workflow again
        result = test_env.resolve_workflow(
            name="test",
            model_strategy=mock_strategy,
            fix=True
        )

        # ASSERT - Should detect existing download intent without calling strategy
        assert len(result.models_resolved) > 0, "Should have resolved models"

        # Find the download intent resolution
        download_intents = [m for m in result.models_resolved if m.match_type == "download_intent"]
        assert len(download_intents) == 1, "Should detect one download intent"
        assert download_intents[0].model_source == "https://civitai.com/api/download/models/999"

    def test_batch_download_execution_with_callbacks(self, test_env, test_workspace):
        """Test batch download execution calls all callbacks correctly."""
        # ARRANGE - Create model index builder
        builder = ModelIndexBuilder(test_workspace)

        # Create workflow with missing model
        workflow = (
            WorkflowBuilder()
            .add_checkpoint_loader("test_model.safetensors")
            .build()
        )
        simulate_comfyui_save_workflow(test_env, "test", workflow)

        # Create mock callbacks
        callbacks = BatchDownloadCallbacks(
            on_batch_start=Mock(),
            on_file_start=Mock(),
            on_file_progress=Mock(),
            on_file_complete=Mock(),
            on_batch_complete=Mock()
        )

        # Mock strategy that returns download intent
        mock_strategy = Mock()
        target_path = Path("checkpoints/test_model.safetensors")

        # Create a test file to "download" (simulating successful download)
        full_target_path = test_env.workspace_paths.models / target_path
        full_target_path.parent.mkdir(parents=True, exist_ok=True)
        full_target_path.write_bytes(b"fake model data")

        mock_strategy.resolve_model = Mock(return_value=ResolvedModel(
            workflow="test",
            reference=Mock(
                node_id="1",
                node_type="CheckpointLoaderSimple",
                widget_index=0,
                widget_value="test_model.safetensors"
            ),
            resolved_model=None,
            model_source="https://example.com/model.safetensors",
            is_optional=False,
            match_type="download_intent",
            target_path=target_path
        ))

        # ACT - Resolve with callbacks
        result = test_env.resolve_workflow(
            name="test",
            model_strategy=mock_strategy,
            fix=True,
            download_callbacks=callbacks
        )

        # ASSERT - All callbacks should be called
        callbacks.on_batch_start.assert_called_once_with(1)  # 1 file to download
        callbacks.on_file_start.assert_called_once()  # File started
        callbacks.on_file_complete.assert_called_once()  # File completed
        callbacks.on_batch_complete.assert_called_once()  # Batch done

    def test_batch_download_updates_hash_after_download(self, test_env):
        """Test that pyproject is updated with actual hash after download completes."""
        # This test will fail initially because batch download logic doesn't exist yet
        pytest.skip("TODO: Implement after batch download execution is in place")

    def test_multiple_download_intents_batch_execution(self, test_env):
        """Test multiple download intents are batched together."""
        # This test will fail initially
        pytest.skip("TODO: Implement after batch download execution is in place")

    def test_download_deduplication_by_url(self, test_env):
        """Test that same URL downloads once and reuses model across workflows."""
        # This test will fail initially
        pytest.skip("TODO: Implement after batch download execution is in place")


class TestModelResolutionContextChanges:
    """Test changes to ModelResolutionContext to support full ManifestWorkflowModel storage."""

    def test_context_stores_full_manifest_model(self, test_env, test_workspace):
        """Test that context.previous_resolutions stores full ManifestWorkflowModel."""
        # ARRANGE - Create workflow with resolved model
        builder = ModelIndexBuilder(test_workspace)
        builder.add_model("test.safetensors", "checkpoints", size_mb=4)
        builder.index_all()

        workflow = (
            WorkflowBuilder()
            .add_checkpoint_loader("test.safetensors")
            .build()
        )
        simulate_comfyui_save_workflow(test_env, "test", workflow)

        # Resolve once to populate pyproject
        result = test_env.resolve_workflow(
            name="test",
            model_strategy=AutoModelStrategy(),
            fix=True
        )

        # ACT - Resolve again to trigger context resolution
        # The second resolution should detect the previous resolution from pyproject
        result2 = test_env.resolve_workflow(
            name="test",
            model_strategy=AutoModelStrategy(),
            fix=True
        )

        # ASSERT - The second resolution should have detected the resolved model from context
        # This validates that context is being built with full ManifestWorkflowModel objects
        assert len(result2.models_resolved) > 0, "Should have resolved models from context"

        # Verify the model was resolved from workflow_context (not re-resolved)
        context_resolved = [m for m in result2.models_resolved if m.match_type == "workflow_context"]
        assert len(context_resolved) > 0, "Should have at least one model resolved from context"

        # Verify pyproject has the model data (validates full ManifestWorkflowModel was used)
        workflow_models = test_env.pyproject.workflows.get_workflow_models("test")
        assert len(workflow_models) > 0, "Should have workflow models in pyproject"
        assert workflow_models[0].hash is not None, "Model should have hash (resolved)"


class TestSchemaChanges:
    """Test schema changes to support download intents."""

    def test_manifest_workflow_model_has_relative_path(self):
        """Test ManifestWorkflowModel includes relative_path field."""
        from comfydock_core.models.manifest import ManifestWorkflowModel
        from comfydock_core.models.workflow import WorkflowNodeWidgetRef

        # ACT - Create ManifestWorkflowModel with relative_path
        model = ManifestWorkflowModel(
            filename="test.safetensors",
            category="checkpoints",
            criticality="flexible",
            status="unresolved",
            nodes=[WorkflowNodeWidgetRef(
                node_id="1",
                node_type="CheckpointLoaderSimple",
                widget_index=0,
                widget_value="test.safetensors"
            )],
            sources=["https://example.com/model"],
            relative_path="checkpoints/test.safetensors"
        )

        # ASSERT
        assert model.relative_path == "checkpoints/test.safetensors"

        # Test TOML serialization includes relative_path
        toml_dict = model.to_toml_dict()
        assert "relative_path" in toml_dict
        assert toml_dict["relative_path"] == "checkpoints/test.safetensors"

    def test_resolved_model_has_target_path(self):
        """Test ResolvedModel includes target_path field."""
        from comfydock_core.models.workflow import ResolvedModel, WorkflowNodeWidgetRef

        # ACT - Create ResolvedModel with target_path
        ref = WorkflowNodeWidgetRef(
            node_id="1",
            node_type="CheckpointLoaderSimple",
            widget_index=0,
            widget_value="model.safetensors"
        )

        resolved = ResolvedModel(
            workflow="test",
            reference=ref,
            resolved_model=None,
            model_source="https://example.com/model",
            is_optional=False,
            match_type="download_intent",
            target_path=Path("checkpoints/model.safetensors")
        )

        # ASSERT
        assert resolved.target_path == Path("checkpoints/model.safetensors")

    def test_resolution_result_has_download_intents_property(self):
        """Test ResolutionResult.has_download_intents property."""
        from comfydock_core.models.workflow import ResolutionResult, ResolvedModel, WorkflowNodeWidgetRef

        # ARRANGE - Create result with download intent
        ref = WorkflowNodeWidgetRef(
            node_id="1",
            node_type="CheckpointLoaderSimple",
            widget_index=0,
            widget_value="model.safetensors"
        )

        download_intent = ResolvedModel(
            workflow="test",
            reference=ref,
            resolved_model=None,
            model_source="https://example.com/model",
            is_optional=False,
            match_type="download_intent",
            target_path=Path("checkpoints/model.safetensors")
        )

        # ACT
        result_with_intent = ResolutionResult(
            workflow_name="test",
            models_resolved=[download_intent]
        )

        result_without_intent = ResolutionResult(
            workflow_name="test",
            models_resolved=[]
        )

        # ASSERT
        assert result_with_intent.has_download_intents is True
        assert result_without_intent.has_download_intents is False

    def test_batch_download_callbacks_dataclass(self):
        """Test BatchDownloadCallbacks dataclass exists with correct signature."""
        from comfydock_core.models.workflow import BatchDownloadCallbacks

        # ACT - Create callbacks with all fields
        callbacks = BatchDownloadCallbacks(
            on_batch_start=lambda count: None,
            on_file_start=lambda name, idx, total: None,
            on_file_progress=lambda downloaded, total: None,
            on_file_complete=lambda name, success, error: None,
            on_batch_complete=lambda success, total: None
        )

        # ASSERT - All fields exist
        assert hasattr(callbacks, 'on_batch_start')
        assert hasattr(callbacks, 'on_file_start')
        assert hasattr(callbacks, 'on_file_progress')
        assert hasattr(callbacks, 'on_file_complete')
        assert hasattr(callbacks, 'on_batch_complete')

        # All should be optional (can be None)
        callbacks_empty = BatchDownloadCallbacks()
        assert callbacks_empty.on_batch_start is None
        assert callbacks_empty.on_file_start is None
