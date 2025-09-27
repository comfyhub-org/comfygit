"""Tests for workflow_dependency_parser.py."""
import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from comfydock_core.analyzers.workflow_dependency_parser import (
    WorkflowDependencies,
    WorkflowDependencyParser,
)


@pytest.fixture
def mock_model_index():
    """Mock model index manager."""
    mock = Mock()
    mock.get_all_models.return_value = [
        Mock(
            relative_path="checkpoints/v1-5-pruned-emaonly-fp16.safetensors",
            hash="abc123",
        ),
        Mock(
            relative_path="SD1.5/photon_v1.safetensors",
            hash="def456",
        ),
    ]
    return mock


@pytest.fixture
def mock_model_config():
    """Mock model config."""
    mock = Mock()
    mock.is_model_loader_node.return_value = True
    mock.get_widget_index_for_node.return_value = 0
    mock.reconstruct_model_path.return_value = ["SD1.5/photon_v1.safetensors"]
    return mock


@pytest.fixture
def test1_workflow_data():
    """Real workflow data from test1.json."""
    return {
        "id": "7d55d57f-f917-4fbc-903e-5507e5e6822e",
        "nodes": [
            {
                "id": 4,
                "type": "CheckpointLoaderSimple",
                "pos": [26, 474],
                "size": [315, 98],
                "flags": {},
                "order": 3,
                "mode": 0,
                "inputs": [
                    {
                        "localized_name": "ckpt_name",
                        "name": "ckpt_name",
                        "type": "COMBO",
                        "widget": {"name": "ckpt_name"},
                        "link": None,
                    }
                ],
                "outputs": [
                    {
                        "localized_name": "MODEL",
                        "name": "MODEL",
                        "type": "MODEL",
                        "slot_index": 0,
                        "links": [1],
                    }
                ],
                "properties": {"Node name for S&R": "CheckpointLoaderSimple"},
                "widgets_values": ["SD1.5/photon_v1.safetensors"],
            },
            {
                "id": 6,
                "type": "CLIPTextEncode",
                "pos": [415, 186],
                "size": [422.84503173828125, 164.31304931640625],
                "flags": {},
                "order": 5,
                "mode": 0,
                "inputs": [
                    {"localized_name": "clip", "name": "clip", "type": "CLIP", "link": 3}
                ],
                "outputs": [
                    {
                        "localized_name": "CONDITIONING",
                        "name": "CONDITIONING",
                        "type": "CONDITIONING",
                        "slot_index": 0,
                        "links": [4],
                    }
                ],
                "properties": {"Node name for S&R": "CLIPTextEncode"},
                "widgets_values": [
                    "beautiful scenery nature glass bottle landscape, , purple galaxy bottle,"
                ],
            },
            {
                "id": 10,
                "type": "IntegerInput",
                "pos": [963.3480834960938, 608.9468383789062],
                "size": [270, 58],
                "flags": {},
                "order": 1,
                "mode": 0,
                "inputs": [
                    {
                        "localized_name": "value",
                        "name": "value",
                        "type": "INT",
                        "widget": {"name": "value"},
                        "link": None,
                    }
                ],
                "outputs": [
                    {"localized_name": "INT", "name": "INT", "type": "INT", "links": [10]}
                ],
                "properties": {"Node name for S&R": "IntegerInput"},
                "widgets_values": [0],
            },
        ],
    }


@pytest.fixture
def depthflow_workflow_data():
    """Real workflow data from depthflow_basic_test.json."""
    return {
        "id": "63f48656-87e3-4031-a8ea-2105e3e1a376",
        "nodes": [
            {
                "id": 3,
                "type": "LoadImage",
                "pos": [811.641357421875, 242.5341796875],
                "size": [274.080078125, 314],
                "flags": {},
                "order": 0,
                "mode": 0,
                "inputs": [
                    {
                        "localized_name": "image",
                        "name": "image",
                        "type": "COMBO",
                        "widget": {"name": "image"},
                        "link": None,
                    }
                ],
                "outputs": [
                    {
                        "localized_name": "IMAGE",
                        "name": "IMAGE",
                        "type": "IMAGE",
                        "links": [2],
                    }
                ],
                "properties": {"Node name for S&R": "LoadImage"},
                "widgets_values": ["example.png", "image"],
            },
            {
                "id": 5,
                "type": "DepthflowMotionPresetCircle",
                "pos": [1188.53466796875, 845.6396484375],
                "size": [315.1978454589844, 370],
                "flags": {},
                "order": 2,
                "mode": 0,
                "inputs": [
                    {
                        "localized_name": "strength",
                        "name": "strength",
                        "type": "FLOAT",
                        "widget": {"name": "strength"},
                        "link": None,
                    }
                ],
                "outputs": [
                    {
                        "localized_name": "DEPTHFLOW_MOTION",
                        "name": "DEPTHFLOW_MOTION",
                        "type": "DEPTHFLOW_MOTION",
                        "links": [4],
                    }
                ],
                "properties": {"Node name for S&R": "DepthflowMotionPresetCircle"},
                "widgets_values": [1, 0, "intensity", "relative", 1, False, True, 0, 0, 0, 1, 1, 0, 0.3],
            },
            {
                "id": 1,
                "type": "Depthflow",
                "pos": [1202.3155517578125, 458.0935363769531],
                "size": [270, 310],
                "flags": {},
                "order": 3,
                "mode": 0,
                "inputs": [
                    {
                        "localized_name": "image",
                        "name": "image",
                        "type": "IMAGE",
                        "link": 2,
                    }
                ],
                "outputs": [
                    {
                        "localized_name": "IMAGE",
                        "name": "IMAGE",
                        "type": "IMAGE",
                        "links": [1, 6],
                    }
                ],
                "properties": {"Node name for S&R": "Depthflow"},
                "widgets_values": [1, 30, 30, 30, 50, 1, 0, "mirror", 5],
            },
        ],
    }


class TestWorkflowDependencies:
    def test_workflow_dependencies_initialization(self):
        """Test WorkflowDependencies dataclass initialization."""
        deps = WorkflowDependencies()
        assert deps.resolved_models == []
        assert deps.found_models == []
        assert deps.builtin_nodes == []
        assert deps.missing_nodes == []
        assert deps.python_dependencies == []

    def test_total_models_property(self):
        """Test total_models property calculation."""
        mock_model = Mock(hash="abc123")
        deps = WorkflowDependencies(
            resolved_models=[mock_model],
            found_models=[{"relative_path": "missing.safetensors"}],
        )
        assert deps.total_models == 2

    def test_model_hashes_property(self):
        """Test model_hashes property extraction."""
        mock_model1 = Mock(hash="abc123")
        mock_model2 = Mock(hash="def456")
        deps = WorkflowDependencies(resolved_models=[mock_model1, mock_model2])
        assert deps.model_hashes == ["abc123", "def456"]


class TestWorkflowDependencyParser:
    @patch("comfydock_core.utils.workflow_dependency_parser.WorkflowRepository")
    @patch("comfydock_core.utils.workflow_dependency_parser.NodeClassifier")
    def test_initialization(self, mock_node_classifier, mock_workflow_repo, mock_model_index, mock_model_config):
        """Test WorkflowDependencyParser initialization."""
        mock_workflow = Mock()
        mock_workflow_repo.return_value.load.return_value = mock_workflow
        mock_workflow_repo.return_value.load_raw_text.return_value = "workflow text"

        workflow_path = Path("/test/workflow.json")
        parser = WorkflowDependencyParser(workflow_path, mock_model_index, mock_model_config)

        assert parser.workflow == mock_workflow
        assert parser.workflow_text == "workflow text"
        assert parser.model_index == mock_model_index
        assert parser.model_config == mock_model_config

    @patch("comfydock_core.utils.workflow_dependency_parser.WorkflowRepository")
    @patch("comfydock_core.utils.workflow_dependency_parser.NodeClassifier")
    def test_analyze_dependencies_with_real_workflow_data(
        self, mock_node_classifier, mock_workflow_repo, mock_model_index, mock_model_config, test1_workflow_data
    ):
        """Test analyze_dependencies with real workflow data from test1.json."""
        # Setup mocks
        mock_workflow = Mock()
        mock_workflow.nodes = {str(node["id"]): Mock(**node) for node in test1_workflow_data["nodes"]}
        mock_workflow_repo.return_value.load.return_value = mock_workflow
        mock_workflow_repo.return_value.load_raw_text.return_value = json.dumps(test1_workflow_data)

        # Mock node classifier results
        mock_classification = Mock()
        mock_classification.builtin_nodes = [Mock(type="CLIPTextEncode"), Mock(type="CheckpointLoaderSimple")]
        mock_classification.custom_nodes = [Mock(type="IntegerInput")]
        mock_node_classifier.return_value.classify_nodes.return_value = mock_classification

        # Configure model config for CheckpointLoaderSimple
        def is_model_loader_side_effect(node_type):
            return node_type == "CheckpointLoaderSimple"

        mock_model_config.is_model_loader_node.side_effect = is_model_loader_side_effect

        # Create parser and analyze
        workflow_path = Path("/test/workflow.json")
        parser = WorkflowDependencyParser(workflow_path, mock_model_index, mock_model_config)
        result = parser.analyze_dependencies()

        # Verify results
        assert isinstance(result, WorkflowDependencies)
        assert len(result.builtin_nodes) == 2
        assert len(result.missing_nodes) == 1
        assert result.builtin_nodes[0].type == "CLIPTextEncode"
        assert result.missing_nodes[0].type == "IntegerInput"

    @patch("comfydock_core.utils.workflow_dependency_parser.WorkflowRepository")
    @patch("comfydock_core.utils.workflow_dependency_parser.NodeClassifier")
    def test_analyze_dependencies_with_depthflow_workflow(
        self, mock_node_classifier, mock_workflow_repo, mock_model_index, mock_model_config, depthflow_workflow_data
    ):
        """Test analyze_dependencies with real depthflow workflow data."""
        # Setup mocks
        mock_workflow = Mock()
        mock_workflow.nodes = {str(node["id"]): Mock(**node) for node in depthflow_workflow_data["nodes"]}
        mock_workflow_repo.return_value.load.return_value = mock_workflow
        mock_workflow_repo.return_value.load_raw_text.return_value = json.dumps(depthflow_workflow_data)

        # Mock node classifier results - all custom nodes for depthflow
        mock_classification = Mock()
        mock_classification.builtin_nodes = [Mock(type="LoadImage")]
        mock_classification.custom_nodes = [
            Mock(type="DepthflowMotionPresetCircle"),
            Mock(type="Depthflow"),
        ]
        mock_node_classifier.return_value.classify_nodes.return_value = mock_classification

        # Configure model config - LoadImage is not a model loader in this context
        mock_model_config.is_model_loader_node.return_value = False

        # Create parser and analyze
        workflow_path = Path("/test/workflow.json")
        parser = WorkflowDependencyParser(workflow_path, mock_model_index, mock_model_config)
        result = parser.analyze_dependencies()

        # Verify results
        assert isinstance(result, WorkflowDependencies)
        assert len(result.builtin_nodes) == 1
        assert len(result.missing_nodes) == 2
        assert result.builtin_nodes[0].type == "LoadImage"

    @patch("comfydock_core.utils.workflow_dependency_parser.WorkflowRepository")
    @patch("comfydock_core.utils.workflow_dependency_parser.NodeClassifier")
    def test_analyze_dependencies_with_empty_workflow(
        self, mock_node_classifier, mock_workflow_repo, mock_model_index, mock_model_config
    ):
        """Test analyze_dependencies with empty workflow."""
        # Setup mocks
        mock_workflow = Mock()
        mock_workflow.nodes = {}
        mock_workflow_repo.return_value.load.return_value = mock_workflow
        mock_workflow_repo.return_value.load_raw_text.return_value = "{}"

        # Create parser and analyze
        workflow_path = Path("/test/workflow.json")
        parser = WorkflowDependencyParser(workflow_path, mock_model_index, mock_model_config)
        result = parser.analyze_dependencies()

        # Verify empty results
        assert isinstance(result, WorkflowDependencies)
        assert len(result.resolved_models) == 0
        assert len(result.found_models) == 0
        assert len(result.builtin_nodes) == 0
        assert len(result.missing_nodes) == 0

    @patch("comfydock_core.utils.workflow_dependency_parser.WorkflowRepository")
    @patch("comfydock_core.utils.workflow_dependency_parser.NodeClassifier")
    def test_analyze_dependencies_handles_exceptions(
        self, mock_node_classifier, mock_workflow_repo, mock_model_index, mock_model_config
    ):
        """Test analyze_dependencies handles exceptions gracefully."""
        # Setup mocks - load succeeds but node classifier raises exception
        mock_workflow = Mock()
        mock_workflow.nodes = {"1": Mock(type="TestNode")}
        mock_workflow_repo.return_value.load.return_value = mock_workflow
        mock_workflow_repo.return_value.load_raw_text.return_value = "{}"

        # Make node classifier raise an exception
        mock_node_classifier.return_value.classify_nodes.side_effect = Exception("Classification error")

        # Create parser and analyze
        workflow_path = Path("/test/workflow.json")
        parser = WorkflowDependencyParser(workflow_path, mock_model_index, mock_model_config)
        result = parser.analyze_dependencies()

        # Should return empty dependencies on error
        assert isinstance(result, WorkflowDependencies)
        assert len(result.resolved_models) == 0
        assert len(result.found_models) == 0

    @patch("comfydock_core.utils.workflow_dependency_parser.WorkflowRepository")
    @patch("comfydock_core.utils.workflow_dependency_parser.NodeClassifier")
    def test_missing_model_detection(
        self, mock_node_classifier, mock_workflow_repo, mock_model_index, mock_model_config
    ):
        """Test that missing models are properly identified and tracked."""
        # Setup workflow with CheckpointLoaderSimple
        workflow_data = {
            "nodes": [
                {
                    "id": 1,
                    "type": "CheckpointLoaderSimple",
                    "widgets_values": ["missing_model.safetensors"],
                }
            ]
        }

        mock_workflow = Mock()
        mock_workflow.nodes = {"1": Mock(type="CheckpointLoaderSimple", widgets_values=["missing_model.safetensors"])}
        mock_workflow_repo.return_value.load.return_value = mock_workflow
        mock_workflow_repo.return_value.load_raw_text.return_value = json.dumps(workflow_data)

        # Mock empty model index (no models found)
        mock_model_index.get_all_models.return_value = []

        # Mock node classifier
        mock_classification = Mock()
        mock_classification.builtin_nodes = [Mock(type="CheckpointLoaderSimple")]
        mock_classification.custom_nodes = []
        mock_node_classifier.return_value.classify_nodes.return_value = mock_classification

        # Configure model config
        mock_model_config.is_model_loader_node.return_value = True
        mock_model_config.get_widget_index_for_node.return_value = 0
        mock_model_config.reconstruct_model_path.return_value = [
            "checkpoints/missing_model.safetensors",
            "models/checkpoints/missing_model.safetensors"
        ]

        # Create parser and analyze
        workflow_path = Path("/test/workflow.json")
        parser = WorkflowDependencyParser(workflow_path, mock_model_index, mock_model_config)
        result = parser.analyze_dependencies()

        # Verify missing models are tracked
        assert len(result.resolved_models) == 0
        assert len(result.found_models) == 1
        assert result.found_models[0]["relative_path"] == "CheckpointLoaderSimple:missing_model.safetensors"
        assert "checkpoints/missing_model.safetensors" in result.found_models[0]["attempted_paths"]

    @patch("comfydock_core.utils.workflow_dependency_parser.WorkflowRepository")
    @patch("comfydock_core.utils.workflow_dependency_parser.NodeClassifier")
    def test_duplicate_model_hash_prevention(
        self, mock_node_classifier, mock_workflow_repo, mock_model_index, mock_model_config
    ):
        """Test that same model referenced multiple times only appears once in resolved_models."""
        # Setup workflow with multiple nodes referencing same model
        workflow_data = {
            "nodes": [
                {
                    "id": 1,
                    "type": "CheckpointLoaderSimple",
                    "widgets_values": ["sd15.safetensors"],
                },
                {
                    "id": 2,
                    "type": "CheckpointLoaderSimple",
                    "widgets_values": ["sd15.safetensors"],  # Same model
                },
                {
                    "id": 3,
                    "type": "VAELoader",
                    "widgets_values": ["vae.safetensors"],  # Different model
                }
            ]
        }

        mock_workflow = Mock()
        mock_workflow.nodes = {
            "1": Mock(type="CheckpointLoaderSimple", widgets_values=["sd15.safetensors"]),
            "2": Mock(type="CheckpointLoaderSimple", widgets_values=["sd15.safetensors"]),
            "3": Mock(type="VAELoader", widgets_values=["vae.safetensors"])
        }
        mock_workflow_repo.return_value.load.return_value = mock_workflow
        mock_workflow_repo.return_value.load_raw_text.return_value = json.dumps(workflow_data)

        # Mock model index with models
        mock_sd_model = Mock(relative_path="checkpoints/sd15.safetensors", hash="hash_sd15")
        mock_vae_model = Mock(relative_path="vae/vae.safetensors", hash="hash_vae")
        mock_model_index.get_all_models.return_value = [mock_sd_model, mock_vae_model]

        # Mock node classifier
        mock_classification = Mock()
        mock_classification.builtin_nodes = [
            Mock(type="CheckpointLoaderSimple"),
            Mock(type="VAELoader")
        ]
        mock_classification.custom_nodes = []
        mock_node_classifier.return_value.classify_nodes.return_value = mock_classification

        # Configure model config
        def is_model_loader_side_effect(node_type):
            return node_type in ["CheckpointLoaderSimple", "VAELoader"]

        mock_model_config.is_model_loader_node.side_effect = is_model_loader_side_effect
        mock_model_config.get_widget_index_for_node.return_value = 0

        def reconstruct_path_side_effect(node_type, widget_value):
            if node_type == "CheckpointLoaderSimple":
                return ["checkpoints/" + widget_value]
            elif node_type == "VAELoader":
                return ["vae/" + widget_value]
            return []

        mock_model_config.reconstruct_model_path.side_effect = reconstruct_path_side_effect

        # Create parser and analyze
        workflow_path = Path("/test/workflow.json")
        parser = WorkflowDependencyParser(workflow_path, mock_model_index, mock_model_config)
        result = parser.analyze_dependencies()

        # Verify duplicate prevention - sd15 should only appear once
        assert len(result.resolved_models) == 2
        assert len(result.found_models) == 0

        # Check that we have exactly one of each model hash
        hashes = [model.hash for model in result.resolved_models]
        assert hashes.count("hash_sd15") == 1
        assert hashes.count("hash_vae") == 1

    @patch("comfydock_core.utils.workflow_dependency_parser.WorkflowRepository")
    @patch("comfydock_core.utils.workflow_dependency_parser.NodeClassifier")
    def test_alternative_path_resolution(
        self, mock_node_classifier, mock_workflow_repo, mock_model_index, mock_model_config
    ):
        """Test that alternative paths are tried when primary path fails."""
        workflow_data = {
            "nodes": [
                {
                    "id": 1,
                    "type": "CheckpointLoaderSimple",
                    "widgets_values": ["model.safetensors"],
                }
            ]
        }

        mock_workflow = Mock()
        mock_workflow.nodes = {"1": Mock(type="CheckpointLoaderSimple", widgets_values=["model.safetensors"])}
        mock_workflow_repo.return_value.load.return_value = mock_workflow
        mock_workflow_repo.return_value.load_raw_text.return_value = json.dumps(workflow_data)

        # Model exists only at the second alternative path
        mock_model = Mock(relative_path="models/checkpoints/model.safetensors", hash="hash_model")
        mock_model_index.get_all_models.return_value = [mock_model]

        # Mock node classifier
        mock_classification = Mock()
        mock_classification.builtin_nodes = [Mock(type="CheckpointLoaderSimple")]
        mock_classification.custom_nodes = []
        mock_node_classifier.return_value.classify_nodes.return_value = mock_classification

        # Configure model config to return multiple paths
        mock_model_config.is_model_loader_node.return_value = True
        mock_model_config.get_widget_index_for_node.return_value = 0
        mock_model_config.reconstruct_model_path.return_value = [
            "checkpoints/model.safetensors",  # First path doesn't exist
            "models/checkpoints/model.safetensors"  # Second path exists
        ]

        # Create parser and analyze
        workflow_path = Path("/test/workflow.json")
        parser = WorkflowDependencyParser(workflow_path, mock_model_index, mock_model_config)
        result = parser.analyze_dependencies()

        # Verify model was resolved using the alternative path
        assert len(result.resolved_models) == 1
        assert len(result.found_models) == 0
        assert result.resolved_models[0].hash == "hash_model"
        assert result.resolved_models[0].relative_path == "models/checkpoints/model.safetensors"

    @patch("comfydock_core.utils.workflow_dependency_parser.WorkflowRepository")
    @patch("comfydock_core.utils.workflow_dependency_parser.NodeClassifier")
    def test_direct_model_references_in_non_loader_nodes(
        self, mock_node_classifier, mock_workflow_repo, mock_model_index, mock_model_config
    ):
        """Test that direct model references in non-loader nodes are detected."""
        workflow_data = {
            "nodes": [
                {
                    "id": 1,
                    "type": "CustomNode",
                    "widgets_values": [
                        "some_setting",
                        "embeddings/clip_model.safetensors",  # Direct model path reference
                        42
                    ],
                },
                {
                    "id": 2,
                    "type": "AnotherCustomNode",
                    "widgets_values": [
                        "loras/style_lora.safetensors"  # Another direct model path
                    ],
                }
            ]
        }

        mock_workflow = Mock()
        mock_workflow.nodes = {
            "1": Mock(type="CustomNode", widgets_values=["some_setting", "embeddings/clip_model.safetensors", 42]),
            "2": Mock(type="AnotherCustomNode", widgets_values=["loras/style_lora.safetensors"])
        }
        mock_workflow_repo.return_value.load.return_value = mock_workflow
        mock_workflow_repo.return_value.load_raw_text.return_value = json.dumps(workflow_data)

        # Mock model index with models
        mock_clip = Mock(relative_path="embeddings/clip_model.safetensors", hash="hash_clip")
        mock_lora = Mock(relative_path="loras/style_lora.safetensors", hash="hash_lora")
        mock_model_index.get_all_models.return_value = [mock_clip, mock_lora]

        # Mock node classifier
        mock_classification = Mock()
        mock_classification.builtin_nodes = []
        mock_classification.custom_nodes = [Mock(type="CustomNode"), Mock(type="AnotherCustomNode")]
        mock_node_classifier.return_value.classify_nodes.return_value = mock_classification

        # Configure model config - these are NOT model loaders
        mock_model_config.is_model_loader_node.return_value = False

        # Create parser and analyze
        workflow_path = Path("/test/workflow.json")
        parser = WorkflowDependencyParser(workflow_path, mock_model_index, mock_model_config)
        result = parser.analyze_dependencies()

        # Verify direct model references were detected
        assert len(result.resolved_models) == 2
        assert len(result.found_models) == 0

        # Check both models were found
        hashes = [model.hash for model in result.resolved_models]
        assert "hash_clip" in hashes
        assert "hash_lora" in hashes

    @patch("comfydock_core.utils.workflow_dependency_parser.WorkflowRepository")
    @patch("comfydock_core.utils.workflow_dependency_parser.NodeClassifier")
    def test_widget_index_edge_cases(
        self, mock_node_classifier, mock_workflow_repo, mock_model_index, mock_model_config
    ):
        """Test edge cases with widget indices - out of bounds and non-string values."""
        workflow_data = {
            "nodes": [
                {
                    "id": 1,
                    "type": "CheckpointLoaderSimple",
                    "widgets_values": [],  # Empty widgets list
                },
                {
                    "id": 2,
                    "type": "VAELoader",
                    "widgets_values": [123, None, {"key": "value"}],  # Non-string values
                },
                {
                    "id": 3,
                    "type": "LoraLoader",
                    "widgets_values": ["valid_lora.safetensors"],  # Valid case for comparison
                }
            ]
        }

        mock_workflow = Mock()
        mock_workflow.nodes = {
            "1": Mock(type="CheckpointLoaderSimple", widgets_values=[]),
            "2": Mock(type="VAELoader", widgets_values=[123, None, {"key": "value"}]),
            "3": Mock(type="LoraLoader", widgets_values=["valid_lora.safetensors"])
        }
        mock_workflow_repo.return_value.load.return_value = mock_workflow
        mock_workflow_repo.return_value.load_raw_text.return_value = json.dumps(workflow_data)

        # Mock model index with one valid model
        mock_lora = Mock(relative_path="loras/valid_lora.safetensors", hash="hash_lora")
        mock_model_index.get_all_models.return_value = [mock_lora]

        # Mock node classifier
        mock_classification = Mock()
        mock_classification.builtin_nodes = [
            Mock(type="CheckpointLoaderSimple"),
            Mock(type="VAELoader"),
            Mock(type="LoraLoader")
        ]
        mock_classification.custom_nodes = []
        mock_node_classifier.return_value.classify_nodes.return_value = mock_classification

        # Configure model config
        def is_model_loader_side_effect(node_type):
            return node_type in ["CheckpointLoaderSimple", "VAELoader", "LoraLoader"]

        mock_model_config.is_model_loader_node.side_effect = is_model_loader_side_effect

        def get_widget_index_side_effect(node_type):
            # Return different indices for different nodes
            if node_type == "VAELoader":
                return 10  # Out of bounds index
            return 0  # Normal index

        mock_model_config.get_widget_index_for_node.side_effect = get_widget_index_side_effect

        def reconstruct_path_side_effect(node_type, widget_value):
            if node_type == "LoraLoader":
                return ["loras/" + widget_value]
            return []

        mock_model_config.reconstruct_model_path.side_effect = reconstruct_path_side_effect

        # Create parser and analyze
        workflow_path = Path("/test/workflow.json")
        parser = WorkflowDependencyParser(workflow_path, mock_model_index, mock_model_config)
        result = parser.analyze_dependencies()

        # Verify only the valid lora was resolved
        assert len(result.resolved_models) == 1
        assert result.resolved_models[0].hash == "hash_lora"

        # Empty widgets and out-of-bounds index should not crash or add missing models
        # Non-string values should be ignored
        assert len(result.found_models) == 0
