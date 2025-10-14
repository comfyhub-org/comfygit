"""Tests for PyprojectManager TOML formatting."""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
import tomlkit

from comfydock_core.managers.pyproject_manager import PyprojectManager
from comfydock_core.models.shared import NodeInfo


@pytest.fixture
def temp_pyproject():
    """Create a temporary pyproject.toml for testing."""
    with TemporaryDirectory() as tmpdir:
        pyproject_path = Path(tmpdir) / "pyproject.toml"

        # Create a basic pyproject.toml structure
        initial_config = {
            "project": {
                "name": "test-project",
                "version": "0.1.0",
                "requires-python": ">=3.11",
                "dependencies": [],
            },
            "tool": {
                "comfydock": {
                    "comfyui_version": "v0.3.60",
                    "python_version": "3.11",
                }
            }
        }

        with open(pyproject_path, 'w') as f:
            tomlkit.dump(initial_config, f)

        yield pyproject_path


class TestModelHandlerFormatting:
    """Test that model operations produce clean TOML output."""

    def test_add_required_model_only(self, temp_pyproject):
        """Test adding only required models doesn't create optional section."""
        manager = PyprojectManager(temp_pyproject)

        # Add a required model
        manager.models.add_model(
            model_hash="abc123",
            filename="test_model.safetensors",
            file_size=1234567,
            category="required",
            relative_path="checkpoints/test_model.safetensors"
        )

        # Read the raw TOML output
        with open(temp_pyproject) as f:
            content = f.read()

        # Verify structure
        assert "[tool.comfydock.models.required]" in content
        assert "[tool.comfydock.models.optional]" not in content
        assert "abc123" in content

        # Verify inline table format (all on one line)
        lines = content.split('\n')
        model_line = [l for l in lines if 'abc123' in l][0]
        assert 'filename' in model_line
        assert 'size' in model_line
        assert 'relative_path' in model_line

    def test_add_optional_model_only(self, temp_pyproject):
        """Test adding only optional models doesn't create required section."""
        manager = PyprojectManager(temp_pyproject)

        # Add an optional model
        manager.models.add_model(
            model_hash="xyz789",
            filename="optional_model.safetensors",
            file_size=9876543,
            category="optional",
            relative_path="checkpoints/optional.safetensors"
        )

        # Read the raw TOML output
        with open(temp_pyproject) as f:
            content = f.read()

        # Verify structure
        assert "[tool.comfydock.models.optional]" in content
        assert "[tool.comfydock.models.required]" not in content

    def test_add_both_model_categories(self, temp_pyproject):
        """Test adding both required and optional models."""
        manager = PyprojectManager(temp_pyproject)

        # Add models to both categories
        manager.models.add_model(
            model_hash="req123",
            filename="required.safetensors",
            file_size=1000,
            category="required"
        )
        manager.models.add_model(
            model_hash="opt456",
            filename="optional.safetensors",
            file_size=2000,
            category="optional"
        )

        # Read the raw TOML output
        with open(temp_pyproject) as f:
            content = f.read()

        # Both sections should exist
        assert "[tool.comfydock.models.required]" in content
        assert "[tool.comfydock.models.optional]" in content

        # Models should be under the correct sections
        lines = content.split('\n')
        req_section_idx = next(i for i, l in enumerate(lines) if 'models.required]' in l)
        opt_section_idx = next(i for i, l in enumerate(lines) if 'models.optional]' in l)

        # Required model should come before optional section
        req_model_idx = next(i for i, l in enumerate(lines) if 'req123' in l)
        assert req_section_idx < req_model_idx < opt_section_idx

        # Optional model should come after optional section
        opt_model_idx = next(i for i, l in enumerate(lines) if 'opt456' in l)
        assert opt_section_idx < opt_model_idx

    def test_remove_all_models_cleans_sections(self, temp_pyproject):
        """Test removing all models cleans up empty sections."""
        manager = PyprojectManager(temp_pyproject)

        # Add models
        manager.models.add_model("hash1", "model1.safetensors", 1000, "required")
        manager.models.add_model("hash2", "model2.safetensors", 2000, "optional")

        # Remove all models
        manager.models.remove_model("hash1")
        manager.models.remove_model("hash2")

        # Read the raw TOML output
        with open(temp_pyproject) as f:
            content = f.read()

        # Model sections should not exist
        assert "[tool.comfydock.models" not in content


class TestNodeHandlerFormatting:
    """Test that node operations produce clean TOML output."""

    def test_add_node(self, temp_pyproject):
        """Test adding a node creates the nodes section."""
        manager = PyprojectManager(temp_pyproject)

        node_info = NodeInfo(
            name="test-node",
            version="1.0.0",
            source="registry",
            registry_id="test-node-id",
            repository="https://github.com/test/node"
        )

        manager.nodes.add(node_info, "test-node-id")

        # Read the raw TOML output
        with open(temp_pyproject) as f:
            content = f.read()

        # Verify nodes section exists
        assert "[tool.comfydock.nodes" in content
        assert "test-node-id" in content

    def test_remove_all_nodes_cleans_section(self, temp_pyproject):
        """Test removing all nodes cleans up empty section."""
        manager = PyprojectManager(temp_pyproject)

        # Add a node
        node_info = NodeInfo(
            name="test-node",
            version="1.0.0",
            source="registry"
        )
        manager.nodes.add(node_info, "test-node-id")

        # Remove the node
        manager.nodes.remove("test-node-id")

        # Read the raw TOML output
        with open(temp_pyproject) as f:
            content = f.read()

        # Nodes section should not exist
        assert "[tool.comfydock.nodes]" not in content


class TestWorkflowModelDeduplication:
    """Test that workflow model entries don't duplicate when resolving to different filenames."""

    def test_resolving_unresolved_to_different_filename_replaces(self, temp_pyproject):
        """Test that resolving a model to a different filename replaces the unresolved entry."""
        from comfydock_core.models.manifest import ManifestWorkflowModel
        from comfydock_core.models.workflow import WorkflowNodeWidgetRef

        manager = PyprojectManager(temp_pyproject)

        # Create unresolved model entry (what analyze_workflow creates)
        unresolved_ref = WorkflowNodeWidgetRef(
            node_id="4",
            node_type="CheckpointLoaderSimple",
            widget_index=0,
            widget_value="v1-5-pruned-emaonly-fp16.safetensors"
        )
        unresolved_model = ManifestWorkflowModel(
            filename="v1-5-pruned-emaonly-fp16.safetensors",
            category="checkpoints",
            criticality="flexible",
            status="unresolved",
            nodes=[unresolved_ref]
        )

        # Add unresolved model
        manager.workflows.add_workflow_model("test_workflow", unresolved_model)

        # Verify it was added
        models = manager.workflows.get_workflow_models("test_workflow")
        assert len(models) == 1
        assert models[0].filename == "v1-5-pruned-emaonly-fp16.safetensors"
        assert models[0].status == "unresolved"
        assert models[0].hash is None

        # Now resolve to a DIFFERENT filename (user selected fuzzy match)
        resolved_model = ManifestWorkflowModel(
            hash="abc123hash",
            filename="v1-5-pruned-emaonly.safetensors",  # Different!
            category="checkpoints",
            criticality="flexible",
            status="resolved",
            nodes=[unresolved_ref]  # Same node reference!
        )

        # Add resolved model (progressive write)
        manager.workflows.add_workflow_model("test_workflow", resolved_model)

        # Verify: should have REPLACED the unresolved entry, not created duplicate
        models = manager.workflows.get_workflow_models("test_workflow")
        assert len(models) == 1, "Should not duplicate when resolving to different filename"
        assert models[0].filename == "v1-5-pruned-emaonly.safetensors"
        assert models[0].status == "resolved"
        assert models[0].hash == "abc123hash"


class TestCleanupBehavior:
    """Test the cleanup behavior of empty sections."""

    def test_empty_sections_removed_on_save(self, temp_pyproject):
        """Test that empty sections are automatically removed on save."""
        # Manually create config with empty sections
        config = {
            "project": {"name": "test"},
            "tool": {
                "comfydock": {
                    "python_version": "3.11",
                    "nodes": {},  # Empty
                    "models": {
                        "required": {},  # Empty
                        "optional": {}   # Empty
                    }
                }
            }
        }

        manager = PyprojectManager(temp_pyproject)
        manager.save(config)

        # Read back
        with open(temp_pyproject) as f:
            content = f.read()

        # Empty sections should be removed
        assert "[tool.comfydock.nodes]" not in content
        assert "[tool.comfydock.models" not in content