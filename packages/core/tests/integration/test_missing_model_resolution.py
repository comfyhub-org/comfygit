"""Integration tests for missing model resolution with content-addressable design.

Tests verify the fuzzy search and hash-based mapping system for resolving
missing model references without modifying workflow JSON files.

DESIGN: Content-addressable model resolution
- Workflow JSON files are NEVER modified during local resolution
- Models mapped via hash in pyproject.toml
- Fuzzy search against existing model index
- Original workflow references preserved for shareability

CURRENT STATUS: Most tests will fail - they document expected behavior.
Use TDD approach: make tests pass incrementally.
"""
import json
import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from conftest import (
    simulate_comfyui_save_workflow,
    load_workflow_fixture,
)


class TestFuzzySearchResolution:
    """Test fuzzy search for similar models in index."""

    @pytest.fixture
    def workflow_with_missing_checkpoint(self, test_env, test_models):
        """Workflow referencing 'sd15-missing.safetensors' (not in index)."""
        workflow_data = {
            "nodes": [
                {
                    "id": 1,
                    "type": "CheckpointLoaderSimple",
                    "widgets_values": ["sd15-missing.safetensors"],
                }
            ],
        }
        simulate_comfyui_save_workflow(test_env, "test_wf", workflow_data)
        return test_env

    def test_fuzzy_search_finds_similar_models(
        self,
        workflow_with_missing_checkpoint,
        test_models
    ):
        """
        WILL FAIL: Fuzzy search should find models with similar names.

        Workflow asks for: "sd15-missing.safetensors"
        Index has: "photon_v1.safetensors" (in SD1.5 category)

        Expected: fuzzy search returns photon_v1 as potential match
        """
        env = workflow_with_missing_checkpoint

        # Get workflow status - should show unresolved model
        workflow_status = env.workflow_manager.get_workflow_status()
        assert len(workflow_status.analyzed_workflows) == 1

        resolution = workflow_status.analyzed_workflows[0].resolution
        assert len(resolution.models_unresolved) == 1, \
            "Should have 1 unresolved model"

        missing_ref = resolution.models_unresolved[0]

        # Test fuzzy search functionality
        similar = env.workflow_manager.find_similar_models(
            missing_ref=missing_ref.widget_value,
            node_type=missing_ref.node_type,
            limit=5
        )

        # EXPECTED: Should find photon_v1 as a potential match
        assert len(similar) > 0, \
            "WILL FAIL: Fuzzy search should find similar models (not implemented)"

        # Check that photon is in results
        filenames = [m.model.filename for m in similar]
        assert "photon_v1.safetensors" in filenames, \
            "Should find photon_v1.safetensors as similar to sd15-missing"

    def test_user_selects_from_fuzzy_results(
        self,
        workflow_with_missing_checkpoint,
        test_models
    ):
        """
        WILL FAIL: User should be able to select from fuzzy results.

        Flow:
        1. System finds similar models via fuzzy search
        2. Strategy returns selected model
        3. Mapping saved to pyproject.toml
        4. Workflow JSON stays unchanged
        """
        env = workflow_with_missing_checkpoint

        # Mock strategy that selects first result
        class AutoSelectStrategy:
            def handle_missing_model(self, reference):
                # Simulate user selecting photon_v1
                return ("select", "SD1.5/photon_v1.safetensors")

            def resolve_ambiguous_model(self, reference, candidates):
                return None

        workflow_status = env.workflow_manager.get_workflow_status()
        resolution = workflow_status.analyzed_workflows[0].resolution

        # Fix resolution with auto-select strategy
        fixed = env.workflow_manager.fix_resolution(
            resolution=resolution,
            node_strategy=None,
            model_strategy=AutoSelectStrategy()
        )

        # EXPECTED: Model should be resolved
        assert len(fixed.models_unresolved) == 0, \
            "WILL FAIL: Model should be resolved after selection (not implemented)"

        # EXPECTED: Model added to resolved list
        assert len(fixed.models_resolved) > 0, \
            "Should have resolved models"

    def test_pyproject_mapping_created_after_selection(
        self,
        workflow_with_missing_checkpoint,
        test_models
    ):
        """
        WILL FAIL: Selecting a model should create pyproject.toml mapping.

        pyproject.toml should have:
        - Model in registry (keyed by hash)
        - Workflow mapping (original ref -> hash)

        Workflow JSON should be UNCHANGED.
        """
        env = workflow_with_missing_checkpoint

        class AutoSelectStrategy:
            def handle_missing_model(self, reference):
                return ("select", "SD1.5/photon_v1.safetensors")

            def resolve_ambiguous_model(self, reference, candidates):
                return None

        workflow_status = env.workflow_manager.get_workflow_status()
        resolution = workflow_status.analyzed_workflows[0].resolution

        # Fix resolution
        fixed = env.workflow_manager.fix_resolution(
            resolution=resolution,
            node_strategy=None,
            model_strategy=AutoSelectStrategy()
        )

        # Apply resolution to pyproject
        env.workflow_manager.apply_resolution(fixed)

        # Load pyproject.toml
        import tomllib
        pyproject_path = env.cec_path / "pyproject.toml"
        with open(pyproject_path, 'rb') as f:
            pyproject = tomllib.load(f)

        # EXPECTED: Model in registry
        models_required = pyproject.get("tool", {}).get("comfydock", {}).get("models", {}).get("required", {})
        assert len(models_required) > 0, \
            "WILL FAIL: Model should be in registry (not implemented)"

        # EXPECTED: Workflow has mapping
        workflow_models = pyproject.get("tool", {}).get("comfydock", {}).get("workflows", {}).get("test_wf", {}).get("models", {})
        assert "sd15-missing.safetensors" in workflow_models, \
            "WILL FAIL: Workflow should have model mapping (not implemented)"

        # Mapping should point to hash
        mapping = workflow_models["sd15-missing.safetensors"]
        assert "hash" in mapping, \
            "Mapping should include model hash"

        # EXPECTED: Workflow JSON unchanged
        workflow_path = env.comfyui_path / "user/default/workflows/test_wf.json"
        with open(workflow_path) as f:
            workflow_data = json.load(f)

        # Original reference should be preserved
        assert workflow_data["nodes"][0]["widgets_values"][0] == "sd15-missing.safetensors", \
            "Workflow JSON should be unchanged (preserves shareability)"


class TestManualPathResolution:
    """Test manual path entry from index."""

    @pytest.fixture
    def workflow_with_missing_model(self, test_env, test_models):
        """Simple workflow with missing model."""
        workflow_data = {
            "nodes": [
                {
                    "id": 1,
                    "type": "CheckpointLoaderSimple",
                    "widgets_values": ["missing.safetensors"],
                }
            ],
        }
        simulate_comfyui_save_workflow(test_env, "manual_test", workflow_data)
        return test_env

    def test_manual_path_finds_model_in_index(
        self,
        workflow_with_missing_model,
        test_models
    ):
        """
        WILL FAIL: User can manually enter path from index.

        User enters: "SD1.5/photon_v1.safetensors"
        System finds in index, creates mapping.
        """
        env = workflow_with_missing_model

        class ManualPathStrategy:
            def handle_missing_model(self, reference):
                # User manually enters path
                return ("select", "SD1.5/photon_v1.safetensors")

            def resolve_ambiguous_model(self, reference, candidates):
                return None

        workflow_status = env.workflow_manager.get_workflow_status()
        resolution = workflow_status.analyzed_workflows[0].resolution

        fixed = env.workflow_manager.fix_resolution(
            resolution=resolution,
            node_strategy=None,
            model_strategy=ManualPathStrategy()
        )

        # Should be resolved
        assert len(fixed.models_unresolved) == 0, \
            "WILL FAIL: Manual path should resolve model (not implemented)"

    def test_manual_path_not_in_index_stays_unresolved(
        self,
        workflow_with_missing_model,
        test_models
    ):
        """
        Path not in index should stay unresolved with helpful error.

        User enters: "not/in/index.safetensors"
        System can't find it, shows error, stays unresolved.
        """
        env = workflow_with_missing_model

        class InvalidPathStrategy:
            def handle_missing_model(self, reference):
                # User enters path not in index
                return ("select", "not/in/index.safetensors")

            def resolve_ambiguous_model(self, reference, candidates):
                return None

        workflow_status = env.workflow_manager.get_workflow_status()
        resolution = workflow_status.analyzed_workflows[0].resolution

        # This should handle gracefully (not crash)
        fixed = env.workflow_manager.fix_resolution(
            resolution=resolution,
            node_strategy=None,
            model_strategy=InvalidPathStrategy()
        )

        # Model should stay unresolved
        assert len(fixed.models_unresolved) > 0, \
            "Model not in index should stay unresolved"


class TestResolutionSkip:
    """Test skip/cancel behavior."""

    @pytest.fixture
    def workflow_with_missing_model(self, test_env, test_models):
        """Simple workflow with missing model."""
        workflow_data = {
            "nodes": [
                {
                    "id": 1,
                    "type": "CheckpointLoaderSimple",
                    "widgets_values": ["skip_me.safetensors"],
                }
            ],
        }
        simulate_comfyui_save_workflow(test_env, "skip_test", workflow_data)
        return test_env

    def test_skip_resolution(
        self,
        workflow_with_missing_model,
        test_models
    ):
        """
        User can skip resolution (returns None).

        Model stays unresolved, no pyproject changes.
        """
        env = workflow_with_missing_model

        class SkipStrategy:
            def handle_missing_model(self, reference):
                # User chooses to skip
                return None

            def resolve_ambiguous_model(self, reference, candidates):
                return None

        workflow_status = env.workflow_manager.get_workflow_status()
        resolution = workflow_status.analyzed_workflows[0].resolution

        fixed = env.workflow_manager.fix_resolution(
            resolution=resolution,
            node_strategy=None,
            model_strategy=SkipStrategy()
        )

        # Model should stay unresolved
        assert len(fixed.models_unresolved) == 1, \
            "Skipped model should stay unresolved"

        # No models should be resolved
        assert len(fixed.models_resolved) == 0, \
            "Skip should not resolve any models"


class TestResolutionPersistence:
    """Test that resolutions persist across status checks."""

    @pytest.fixture
    def workflow_with_missing_model(self, test_env, test_models):
        """Simple workflow with missing model."""
        workflow_data = {
            "nodes": [
                {
                    "id": 1,
                    "type": "CheckpointLoaderSimple",
                    "widgets_values": ["persist_test.safetensors"],
                }
            ],
        }
        simulate_comfyui_save_workflow(test_env, "persist_test", workflow_data)
        return test_env

    def test_resolution_survives_status_rerun(
        self,
        workflow_with_missing_model,
        test_models
    ):
        """
        WILL FAIL: After resolving and saving to pyproject, running status
        again should show model as resolved.

        This is critical - prevents infinite loop of re-prompting.
        """
        env = workflow_with_missing_model

        class AutoSelectStrategy:
            def handle_missing_model(self, reference):
                return ("select", "SD1.5/photon_v1.safetensors")

            def resolve_ambiguous_model(self, reference, candidates):
                return None

        # First status check - unresolved
        status1 = env.workflow_manager.get_workflow_status()
        resolution1 = status1.analyzed_workflows[0].resolution
        assert len(resolution1.models_unresolved) == 1

        # Fix and apply resolution
        fixed = env.workflow_manager.fix_resolution(
            resolution=resolution1,
            node_strategy=None,
            model_strategy=AutoSelectStrategy()
        )
        env.workflow_manager.apply_resolution(fixed)

        # Second status check - should be resolved now
        status2 = env.workflow_manager.get_workflow_status()
        resolution2 = status2.analyzed_workflows[0].resolution

        assert len(resolution2.models_unresolved) == 0, \
            "WILL FAIL: After saving to pyproject, model should be resolved (not implemented)"

        assert len(resolution2.models_resolved) > 0, \
            "Model should appear in resolved list"

    def test_model_deleted_after_resolution_detected(
        self,
        workflow_with_missing_model,
        test_models
    ):
        """
        WILL FAIL: If model file is deleted after resolution, next status
        check should detect it and mark as unresolved again.

        This ensures we never assume a mapping is valid without verifying.
        """
        env = workflow_with_missing_model

        class AutoSelectStrategy:
            def handle_missing_model(self, reference):
                return ("select", "SD1.5/photon_v1.safetensors")

            def resolve_ambiguous_model(self, reference, candidates):
                return None

        # Resolve model
        status1 = env.workflow_manager.get_workflow_status()
        fixed = env.workflow_manager.fix_resolution(
            resolution=status1.analyzed_workflows[0].resolution,
            node_strategy=None,
            model_strategy=AutoSelectStrategy()
        )
        env.workflow_manager.apply_resolution(fixed)

        # Verify resolved
        status2 = env.workflow_manager.get_workflow_status()
        assert len(status2.analyzed_workflows[0].resolution.models_unresolved) == 0

        # Delete the model file
        models_dir = env.workspace_config_manager.get_models_directory()
        model_path = models_dir / "SD1.5" / "photon_v1.safetensors"
        model_path.unlink()

        # Re-index (removes deleted model from index)
        env.workspace.sync_model_directory()

        # Check status again
        status3 = env.workflow_manager.get_workflow_status()

        # Should detect model is missing
        assert len(status3.analyzed_workflows[0].resolution.models_unresolved) > 0, \
            "WILL FAIL: Should detect model file deleted (not implemented)"


class TestPartialResolutions:
    """Test handling of partial resolutions (some resolved, some not)."""

    @pytest.fixture
    def workflow_with_multiple_missing_models(self, test_env, test_models):
        """Workflow with 3 missing models."""
        workflow_data = {
            "nodes": [
                {
                    "id": 1,
                    "type": "CheckpointLoaderSimple",
                    "widgets_values": ["model_a.safetensors"],
                },
                {
                    "id": 2,
                    "type": "LoraLoader",
                    "widgets_values": ["some_text", "model_b.safetensors"],
                },
                {
                    "id": 3,
                    "type": "VAELoader",
                    "widgets_values": ["model_c.safetensors"],
                },
            ],
        }
        simulate_comfyui_save_workflow(test_env, "partial_test", workflow_data)
        return test_env

    def test_partial_resolution_saves_individually(
        self,
        workflow_with_multiple_missing_models,
        test_models
    ):
        """
        WILL FAIL: Each resolved model should be saved immediately to pyproject.

        If user resolves 2 out of 3 models, those 2 should be in pyproject.
        If they run resolution again, only the 1 unresolved model should be prompted.
        """
        env = workflow_with_multiple_missing_models

        # Strategy that resolves first 2, skips third
        call_count = [0]

        class PartialStrategy:
            def handle_missing_model(self, reference):
                call_count[0] += 1
                if call_count[0] <= 2:
                    # Resolve first 2
                    return ("select", "SD1.5/photon_v1.safetensors")
                else:
                    # Skip third
                    return None

            def resolve_ambiguous_model(self, reference, candidates):
                return None

        status1 = env.workflow_manager.get_workflow_status()
        resolution1 = status1.analyzed_workflows[0].resolution

        # Should have 3 unresolved
        assert len(resolution1.models_unresolved) == 3

        # Fix with partial strategy
        fixed = env.workflow_manager.fix_resolution(
            resolution=resolution1,
            node_strategy=None,
            model_strategy=PartialStrategy()
        )
        env.workflow_manager.apply_resolution(fixed)

        # Check status again
        status2 = env.workflow_manager.get_workflow_status()
        resolution2 = status2.analyzed_workflows[0].resolution

        # Should have 1 unresolved (the skipped one)
        assert len(resolution2.models_unresolved) == 1, \
            "WILL FAIL: Partial resolutions should be saved (not implemented)"

        # Should have 2 resolved
        assert len(resolution2.models_resolved) == 2, \
            "Two models should be resolved"


class TestMultipleWorkflowsSameModel:
    """Test deduplication when multiple workflows reference same model."""

    def test_same_model_hash_stored_once(self, test_env, test_models):
        """
        WILL FAIL: Multiple workflows referencing same model (by content)
        should result in single entry in model registry, multiple workflow mappings.

        This tests content-addressable deduplication.
        """
        env = test_env

        # Create two workflows with different references to same model
        workflow_a = {
            "nodes": [
                {
                    "id": 1,
                    "type": "CheckpointLoaderSimple",
                    "widgets_values": ["ref_a.safetensors"],  # Different name
                }
            ],
        }
        workflow_b = {
            "nodes": [
                {
                    "id": 1,
                    "type": "CheckpointLoaderSimple",
                    "widgets_values": ["ref_b.safetensors"],  # Different name
                }
            ],
        }

        simulate_comfyui_save_workflow(env, "workflow_a", workflow_a)
        simulate_comfyui_save_workflow(env, "workflow_b", workflow_b)

        # Resolve both to same actual model
        class AutoSelectStrategy:
            def handle_missing_model(self, reference):
                # Both resolve to photon
                return ("select", "SD1.5/photon_v1.safetensors")

            def resolve_ambiguous_model(self, reference, candidates):
                return None

        status = env.workflow_manager.get_workflow_status()

        for analyzed in status.analyzed_workflows:
            fixed = env.workflow_manager.fix_resolution(
                resolution=analyzed.resolution,
                node_strategy=None,
                model_strategy=AutoSelectStrategy()
            )
            env.workflow_manager.apply_resolution(fixed)

        # Check pyproject
        import tomllib
        with open(env.cec_path / "pyproject.toml", 'rb') as f:
            pyproject = tomllib.load(f)

        # Should have 1 model in registry (deduplicated by hash)
        models_required = pyproject.get("tool", {}).get("comfydock", {}).get("models", {}).get("required", {})
        assert len(models_required) == 1, \
            "WILL FAIL: Same model should be stored once (not implemented)"

        # Should have 2 workflow mappings
        workflow_a_models = pyproject.get("tool", {}).get("comfydock", {}).get("workflows", {}).get("workflow_a", {}).get("models", {})
        workflow_b_models = pyproject.get("tool", {}).get("comfydock", {}).get("workflows", {}).get("workflow_b", {}).get("models", {})

        assert "ref_a.safetensors" in workflow_a_models, \
            "Workflow A should have its mapping"
        assert "ref_b.safetensors" in workflow_b_models, \
            "Workflow B should have its mapping"

        # Both should point to same hash
        hash_a = workflow_a_models["ref_a.safetensors"]["hash"]
        hash_b = workflow_b_models["ref_b.safetensors"]["hash"]
        assert hash_a == hash_b, \
            "Both workflows should reference same model hash"
