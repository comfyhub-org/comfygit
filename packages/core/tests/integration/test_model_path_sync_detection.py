"""Integration test for model path sync detection.

Tests that status correctly detects when model paths in workflow JSON differ
from resolved model paths, warning users to run 'resolve' to fix them.
"""

import sys
from pathlib import Path

# Import helpers
sys.path.insert(0, str(Path(__file__).parent.parent))
from conftest import simulate_comfyui_save_workflow
from helpers.model_index_builder import ModelIndexBuilder
from helpers.workflow_builder import WorkflowBuilder


class TestModelPathSyncDetection:
    """Test detection of model paths needing synchronization."""

    def test_detects_mismatched_model_paths_in_status(self, test_env, test_workspace):
        """Test that status flags workflows with model paths that don't match resolved paths.

        Scenario:
        1. User creates workflow in ComfyUI with wrong path: "models--SD1.5/model.safetensors"
        2. Model actually exists at: "checkpoints/SD1.5/model.safetensors"
        3. Status resolves model successfully (found by filename)
        4. But status should WARN that path needs syncing
        5. After running resolve, path should be fixed and warning should disappear

        This test SHOULD FAIL initially because:
        - ResolvedModel doesn't have needs_path_sync field yet
        - WorkflowAnalysisStatus doesn't track path sync issues
        - resolve_workflow doesn't detect path mismatches
        """
        # ARRANGE: Create model in index
        model_builder = ModelIndexBuilder(test_workspace)
        model_builder.add_model(
            filename="model.safetensors",
            relative_path="checkpoints/SD1.5",  # Correct path in index
            category="checkpoints"
        )
        model_builder.index_all()

        # Create workflow with WRONG path
        workflow = (
            WorkflowBuilder()
            .add_checkpoint_loader("models--SD1.5/model.safetensors")  # Wrong!
            .build()
        )
        simulate_comfyui_save_workflow(test_env, "test_workflow", workflow)

        # ACT: Get workflow status (read-only, no fixes)
        workflow_status = test_env.workflow_manager.get_workflow_status()

        # Find our workflow
        test_wf = next(
            (wf for wf in workflow_status.analyzed_workflows if wf.name == "test_workflow"),
            None
        )

        assert test_wf is not None, "test_workflow should exist in status"

        # ASSERT Phase 1: Model resolved but path differs
        # This should FAIL because needs_path_sync field doesn't exist yet
        assert len(test_wf.resolution.models_resolved) == 1, \
            "Model should resolve by filename match"

        resolved_model = test_wf.resolution.models_resolved[0]

        # FAIL POINT 1: ResolvedModel doesn't have needs_path_sync attribute yet
        assert hasattr(resolved_model, 'needs_path_sync'), \
            "ResolvedModel should have needs_path_sync field"

        assert resolved_model.needs_path_sync is True, \
            "Should flag that workflow path (models--SD1.5/model.safetensors) differs from resolved path (SD1.5/model.safetensors)"

        # FAIL POINT 2: WorkflowAnalysisStatus doesn't have path sync properties yet
        assert hasattr(test_wf, 'models_needing_path_sync_count'), \
            "WorkflowAnalysisStatus should track models needing path sync"

        assert test_wf.models_needing_path_sync_count == 1, \
            "Should count 1 model needing path sync"

        assert hasattr(test_wf, 'has_path_sync_issues'), \
            "WorkflowAnalysisStatus should have has_path_sync_issues property"

        assert test_wf.has_path_sync_issues is True, \
            "Should indicate workflow has path sync issues"

        # ASSERT Phase 2: After resolve, path should be fixed
        from comfygit_core.strategies.auto import AutoModelStrategy

        test_env.resolve_workflow(
            name="test_workflow",
            model_strategy=AutoModelStrategy()
        )

        # Re-check status after resolve
        workflow_status = test_env.workflow_manager.get_workflow_status()
        test_wf = next(
            (wf for wf in workflow_status.analyzed_workflows if wf.name == "test_workflow"),
            None
        )

        # After resolve, path should match
        resolved_model = test_wf.resolution.models_resolved[0]
        assert resolved_model.needs_path_sync is False, \
            "After resolve, path should be synced"

        assert test_wf.models_needing_path_sync_count == 0, \
            "No models should need path sync after resolve"

        assert test_wf.has_path_sync_issues is False, \
            "No path sync issues after resolve"

    def test_ignores_custom_nodes_for_path_sync(self, test_env, test_workspace):
        """Test that custom nodes don't trigger path sync warnings.

        Custom nodes manage their own model paths - we don't know what format
        they expect, so we shouldn't flag them as needing sync.
        """
        # ARRANGE: Create model
        model_builder = ModelIndexBuilder(test_workspace)
        model_builder.add_model(
            filename="custom_model.safetensors",
            relative_path="checkpoints",
            category="checkpoints"
        )
        model_builder.index_all()

        # Create workflow with custom node that has model-like path
        workflow = (
            WorkflowBuilder()
            .add_custom_node("CustomModelLoader", ["wrong/path/custom_model.safetensors"])
            .build()
        )
        simulate_comfyui_save_workflow(test_env, "custom_workflow", workflow)

        # ACT: Get status
        workflow_status = test_env.workflow_manager.get_workflow_status()
        test_wf = next(
            (wf for wf in workflow_status.analyzed_workflows if wf.name == "custom_workflow"),
            None
        )

        # ASSERT: Custom nodes should not be flagged for path sync
        # (even if they happen to have model-like paths)
        if len(test_wf.resolution.models_resolved) > 0:
            # If it resolved, it shouldn't flag as needing sync (custom nodes manage own paths)
            assert test_wf.models_needing_path_sync_count == 0, \
                "Custom nodes should not be flagged for path sync"

    def test_only_flags_builtin_nodes_with_path_mismatch(self, test_env, test_workspace):
        """Test that only builtin nodes with actual path mismatches are flagged.

        Scenarios:
        - Builtin node with correct path → no flag
        - Builtin node with wrong path → flagged
        - Unresolved model → not flagged (can't sync if not resolved)
        """
        # ARRANGE: Create models
        model_builder = ModelIndexBuilder(test_workspace)
        model_builder.add_model(
            filename="correct.safetensors",
            relative_path="checkpoints",
            category="checkpoints"
        )
        model_builder.add_model(
            filename="wrong.safetensors",
            relative_path="checkpoints/subdir",
            category="checkpoints"
        )
        model_builder.index_all()

        # Create workflow with:
        # 1. Correct path (should NOT flag)
        # 2. Wrong path (should flag)
        # 3. Missing model (should NOT flag - can't sync if not resolved)
        workflow = (
            WorkflowBuilder()
            .add_checkpoint_loader("correct.safetensors")  # Correct!
            .add_checkpoint_loader("bad/path/wrong.safetensors")  # Wrong!
            .add_checkpoint_loader("nonexistent.safetensors")  # Missing!
            .build()
        )
        simulate_comfyui_save_workflow(test_env, "mixed_workflow", workflow)

        # ACT: Get status
        workflow_status = test_env.workflow_manager.get_workflow_status()
        test_wf = next(
            (wf for wf in workflow_status.analyzed_workflows if wf.name == "mixed_workflow"),
            None
        )

        # ASSERT: Only the wrong path should be flagged
        assert test_wf.models_needing_path_sync_count == 1, \
            "Only 1 model (wrong.safetensors) should need path sync"

        # Verify which model is flagged
        flagged_models = [
            m for m in test_wf.resolution.models_resolved
            if m.needs_path_sync
        ]

        assert len(flagged_models) == 1, "Should have exactly 1 flagged model"
        assert "wrong.safetensors" in flagged_models[0].reference.widget_value, \
            "wrong.safetensors should be the flagged model"

    def test_duplicate_models_with_same_hash_should_not_need_sync(self, test_env, test_workspace):
        """Test that duplicate models (same hash, different paths) don't trigger false path sync warnings.

        Bug scenario:
        1. Same model file exists at two paths (duplicates or hard links)
           - models/loras/Wan21_CausVid_14B_T2V_lora_rank_1.safetensors
           - models/loras/WAN/Wan21_CausVid_14B_T2V_lora_rank32.safetensors
        2. Both files have IDENTICAL hash (they're the same file)
        3. Workflow references one of the paths
        4. Model index finds both locations
        5. System should NOT flag as needing sync because current path is valid

        This test documents the bug where the system:
        - Always picks first location from index
        - Does string path comparison instead of hash validation
        - Incorrectly suggests "syncing" to a different path for the same file
        """
        # ARRANGE: Create same model at TWO different paths (simulate duplicates)
        import shutil

        # Create first model file
        workspace_models_path = test_workspace.paths.root / "models"
        loras_path = workspace_models_path / "loras"
        loras_path.mkdir(parents=True, exist_ok=True)
        source_path = loras_path / "lora_rank_1.safetensors"

        # Write content (use real content that will hash consistently)
        test_content = b"TEST_LORA_MODEL" * 1000  # Consistent content
        source_path.write_bytes(test_content)

        # Index the first file
        test_workspace.sync_model_directory()

        # Get the actual hash from the repository
        results_before = test_env.model_repository.find_by_filename("lora_rank_1.safetensors")
        assert len(results_before) == 1, "Should find the original file"
        model_hash = results_before[0].hash

        # Copy the SAME file to a subdirectory with DIFFERENT filename
        # This matches the real scenario where the same model has different names
        subdir_path = loras_path / "WAN"
        subdir_path.mkdir(parents=True, exist_ok=True)
        dest_path = subdir_path / "Wan21_CausVid_14B_T2V_lora_rank32.safetensors"
        shutil.copy2(source_path, dest_path)

        # Re-index to pick up the duplicate
        test_workspace.sync_model_directory()

        # Verify both files have same hash
        results = test_env.model_repository.find_model_by_hash(model_hash)
        assert len(results) == 2, f"Should find 2 locations with same hash {model_hash}, found {len(results)}"

        # Create workflow using the original path
        # Workflow was SAVED by user with this path
        workflow = (
            WorkflowBuilder()
            .add_lora_loader("lora_rank_1.safetensors")
            .build()
        )
        simulate_comfyui_save_workflow(test_env, "duplicate_test", workflow)

        # ACT 1: Run RESOLVE to update the workflow with resolved paths
        # This is where the bug occurs - it picks first location
        from comfygit_core.strategies.auto import AutoModelStrategy
        test_env.resolve_workflow(
            name="duplicate_test",
            model_strategy=AutoModelStrategy()
        )

        # ACT 2: Get workflow status AFTER resolve
        # This should show the resolved path
        workflow_status = test_env.workflow_manager.get_workflow_status()
        test_wf = next(
            (wf for wf in workflow_status.analyzed_workflows if wf.name == "duplicate_test"),
            None
        )

        # ASSERT: Check what path was chosen
        assert test_wf is not None
        assert len(test_wf.resolution.models_resolved) == 1, \
            "Model should be resolved"

        resolved_model = test_wf.resolution.models_resolved[0]

        # ASSERT: needs_path_sync should be FALSE
        # The workflow path points to a valid file with the correct hash
        # Even though the "resolved" path is different, both have the SAME hash
        assert resolved_model.needs_path_sync is False, \
            f"BUG: needs_path_sync={resolved_model.needs_path_sync} but both paths have same hash {model_hash}!\n" \
            f"  Workflow path: {resolved_model.reference.widget_value}\n" \
            f"  Resolved path: {resolved_model.resolved_model.relative_path}\n" \
            f"  These are duplicates - no sync needed!"

        assert test_wf.models_needing_path_sync_count == 0, \
            f"Should have 0 models needing sync, found {test_wf.models_needing_path_sync_count}"
