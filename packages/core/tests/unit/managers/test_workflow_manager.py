"""Tests for WorkflowManager normalization logic."""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch
from comfydock_core.managers.workflow_manager import WorkflowManager


@pytest.fixture
def workflow_manager():
    """Create a minimal WorkflowManager for testing normalization."""
    with patch('comfydock_core.managers.workflow_manager.GlobalNodeResolver'):
        with patch('comfydock_core.managers.workflow_manager.ModelResolver'):
            manager = WorkflowManager(
                comfyui_path=Path("/tmp/comfyui"),
                cec_path=Path("/tmp/cec"),
                pyproject=Mock(),
                model_repository=Mock(),
                registry_data_manager=Mock()
            )
            return manager


def test_normalize_workflow_removes_volatile_fields(workflow_manager):
    """Test that workflow normalization removes volatile metadata fields."""

    workflow = {
        "id": "test-workflow",
        "revision": 5,
        "nodes": [],
        "links": [],
        "extra": {
            "ds": {"scale": 1.0, "offset": [0, 0]},
            "frontendVersion": "1.25.11",
            "someOtherField": "preserved"
        }
    }

    normalized = workflow_manager._normalize_workflow_for_comparison(workflow)

    # Check volatile fields removed
    assert "revision" not in normalized
    assert "ds" not in normalized.get("extra", {})
    assert "frontendVersion" not in normalized.get("extra", {})

    # Check other fields preserved
    assert normalized["id"] == "test-workflow"
    assert normalized["extra"]["someOtherField"] == "preserved"


def test_normalize_workflow_handles_randomize_seeds(workflow_manager):
    """Test that auto-generated seeds with 'randomize' mode are normalized."""

    workflow = {
        "nodes": [
            {
                "id": "3",
                "type": "KSampler",
                "widgets_values": [609167611557182, "randomize", 20, 8, "euler", "normal", 1],
                "api_widget_values": [609167611557182, "randomize", 20, 8, "euler", "normal", 1]
            }
        ]
    }

    normalized = workflow_manager._normalize_workflow_for_comparison(workflow)

    # Seed should be normalized to 0 when control is "randomize"
    assert normalized["nodes"][0]["widgets_values"][0] == 0
    assert normalized["nodes"][0]["api_widget_values"][0] == 0

    # Other values should be preserved
    assert normalized["nodes"][0]["widgets_values"][2] == 20  # steps
    assert normalized["nodes"][0]["widgets_values"][3] == 8  # cfg


def test_normalize_workflow_preserves_fixed_seeds(workflow_manager):
    """Test that user-set fixed seeds are NOT normalized."""

    workflow = {
        "nodes": [
            {
                "id": "3",
                "type": "KSampler",
                "widgets_values": [12345, "fixed", 20, 8, "euler", "normal", 1],
                "api_widget_values": [12345, "fixed", 20, 8, "euler", "normal", 1]
            }
        ]
    }

    normalized = workflow_manager._normalize_workflow_for_comparison(workflow)

    # Fixed seed should be preserved
    assert normalized["nodes"][0]["widgets_values"][0] == 12345
    assert normalized["nodes"][0]["api_widget_values"][0] == 12345


def test_workflows_differ_detects_real_changes():
    """Test that _workflows_differ detects actual workflow changes."""
    # This would require more setup with actual files
    # Skipping for now as it's integration-level
    pass


class TestStripBaseDirectoryForNode:
    """Test path stripping logic for ComfyUI node loaders.

    Note: Path stripping is still needed even with symlinks!
    See: docs/context/comfyui-node-loader-base-directories.md
    """

    def test_strip_checkpoint_loader_simple(self, workflow_manager):
        """CheckpointLoaderSimple expects path without 'checkpoints/' prefix."""
        node_type = "CheckpointLoaderSimple"
        relative_path = "checkpoints/SD1.5/helloyoung25d_V15jvae.safetensors"

        result = workflow_manager._strip_base_directory_for_node(node_type, relative_path)

        assert result == "SD1.5/helloyoung25d_V15jvae.safetensors"

    def test_strip_lora_loader(self, workflow_manager):
        """LoraLoader expects path without 'loras/' prefix."""
        node_type = "LoraLoader"
        relative_path = "loras/realistic/detail_tweaker.safetensors"

        result = workflow_manager._strip_base_directory_for_node(node_type, relative_path)

        assert result == "realistic/detail_tweaker.safetensors"

    def test_strip_vae_loader(self, workflow_manager):
        """VAELoader expects path without 'vae/' prefix."""
        node_type = "VAELoader"
        relative_path = "vae/vae-ft-mse-840000.safetensors"

        result = workflow_manager._strip_base_directory_for_node(node_type, relative_path)

        assert result == "vae-ft-mse-840000.safetensors"

    def test_strip_controlnet_loader(self, workflow_manager):
        """ControlNetLoader expects path without 'controlnet/' prefix."""
        node_type = "ControlNetLoader"
        relative_path = "controlnet/depth/control_v11f1p_sd15_depth.pth"

        result = workflow_manager._strip_base_directory_for_node(node_type, relative_path)

        assert result == "depth/control_v11f1p_sd15_depth.pth"

    def test_multiple_base_dirs_uses_first_match(self, workflow_manager):
        """Nodes with multiple base dirs (like CheckpointLoader) strip first match."""
        node_type = "CheckpointLoader"  # Can load from checkpoints or configs
        relative_path = "checkpoints/model.safetensors"

        result = workflow_manager._strip_base_directory_for_node(node_type, relative_path)

        assert result == "model.safetensors"

    def test_no_matching_prefix_returns_unchanged(self, workflow_manager):
        """If path doesn't start with expected base, return as-is."""
        node_type = "CheckpointLoaderSimple"
        relative_path = "custom_folder/model.safetensors"

        result = workflow_manager._strip_base_directory_for_node(node_type, relative_path)

        assert result == "custom_folder/model.safetensors"

    def test_unknown_node_type_returns_unchanged(self, workflow_manager):
        """Unknown node types return path unchanged."""
        node_type = "CustomUnknownNode"
        relative_path = "checkpoints/model.safetensors"

        result = workflow_manager._strip_base_directory_for_node(node_type, relative_path)

        assert result == "checkpoints/model.safetensors"

    def test_path_already_stripped_returns_unchanged(self, workflow_manager):
        """If path is already without base prefix, return as-is."""
        node_type = "CheckpointLoaderSimple"
        relative_path = "SD1.5/model.safetensors"

        result = workflow_manager._strip_base_directory_for_node(node_type, relative_path)

        assert result == "SD1.5/model.safetensors"

    def test_nested_subdirectories_preserved(self, workflow_manager):
        """Nested paths after base are preserved."""
        node_type = "CheckpointLoaderSimple"
        relative_path = "checkpoints/SD1.5/special/subfolder/model.safetensors"

        result = workflow_manager._strip_base_directory_for_node(node_type, relative_path)

        assert result == "SD1.5/special/subfolder/model.safetensors"

    def test_filename_only_without_base(self, workflow_manager):
        """Filename without any directory returns as-is."""
        node_type = "CheckpointLoaderSimple"
        relative_path = "model.safetensors"

        result = workflow_manager._strip_base_directory_for_node(node_type, relative_path)

        assert result == "model.safetensors"

    def test_upscale_model_loader(self, workflow_manager):
        """UpscaleModelLoader expects path without 'upscale_models/' prefix."""
        node_type = "UpscaleModelLoader"
        relative_path = "upscale_models/4x-UltraSharp.pth"

        result = workflow_manager._strip_base_directory_for_node(node_type, relative_path)

        assert result == "4x-UltraSharp.pth"