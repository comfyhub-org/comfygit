"""Integration tests for progressive workflow resolution writes.

Tests the incremental write behavior where each user decision is saved
immediately to pyproject.toml and workflow JSON, enabling Ctrl+C safety
and auto-resume.

Key Requirements:
1. Each model resolution writes immediately (not batched)
2. Each node resolution writes immediately (not batched)
3. Ctrl+C preserves partial progress
4. Re-running resolution auto-skips already-resolved items
5. Workflow JSON updated incrementally
"""
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from conftest import simulate_comfyui_save_workflow
from comfydock_core.models.protocols import ModelResolutionStrategy


class TestProgressiveResolutionWrites:
    """Tests for incremental write behavior during resolution."""

    def test_model_resolution_writes_immediately_to_pyproject(
        self,
        test_env,
        test_models
    ):
        """
        Test that each model resolution writes to pyproject.toml immediately.

        CURRENT BEHAVIOR (should FAIL):
        - All models collected in memory
        - Single write at the end

        DESIRED BEHAVIOR:
        - Each model written as soon as user resolves it
        - Partial progress saved even if process interrupted
        """
        # ARRANGE: Workflow with 3 missing models
        workflow_data = {
            "id": "progressive-test-001",
            "nodes": [
                {
                    "id": 4,
                    "type": "CheckpointLoaderSimple",
                    "pos": [0, 0],
                    "widgets_values": ["missing_checkpoint.safetensors"]
                },
                {
                    "id": 5,
                    "type": "LoraLoader",
                    "pos": [100, 0],
                    "widgets_values": ["missing_lora1.safetensors", 1.0, 1.0]
                },
                {
                    "id": 6,
                    "type": "LoraLoader",
                    "pos": [200, 0],
                    "widgets_values": ["missing_lora2.safetensors", 1.0, 1.0]
                }
            ],
            "links": []
        }

        simulate_comfyui_save_workflow(test_env, "progressive_test", workflow_data)

        # ACT: Resolve models one by one, checking pyproject after each
        workflow_status = test_env.workflow_manager.get_workflow_status()
        workflow_analysis = workflow_status.analyzed_workflows[0]

        # Strategy that tracks how many times pyproject was read
        pyproject_reads = []
        original_load = test_env.pyproject.load

        def tracked_load():
            result = original_load()
            # Count how many models are in pyproject at each read
            models_count = len(result.get("tool", {}).get("comfydock", {}).get("models", {}).get("required", {}))
            pyproject_reads.append(models_count)
            return result

        test_env.pyproject.load = tracked_load

        class ProgressiveModelStrategy(ModelResolutionStrategy):
            """Strategy that resolves models one by one and verifies incremental writes."""

            def __init__(self, repo, pyproject):
                self.repo = repo
                self.pyproject = pyproject
                self.resolution_count = 0

            def resolve_ambiguous_model(self, ref, candidates):
                return candidates[0] if candidates else None

            def handle_missing_model(self, ref):
                # Resolve to sd15_v1 for all models
                model = self.repo.find_by_filename("sd15_v1.safetensors")
                if model:
                    self.resolution_count += 1
                    return ("select", model[0].relative_path)
                return None

        strategy = ProgressiveModelStrategy(test_env.model_repository, test_env.pyproject)

        # Call fix_resolution with workflow_name (enables progressive mode)
        resolution = test_env.workflow_manager.fix_resolution(
            workflow_analysis.resolution,
            model_strategy=strategy,
            workflow_name="progressive_test"  # THIS enables incremental writes
        )

        # ASSERT: Pyproject should have been updated DURING fix_resolution
        # Current behavior: All writes happen in apply_resolution (after fix_resolution)
        # Desired behavior: Writes happen inside fix_resolution loop

        # Check that pyproject has all 3 models NOW (before apply_resolution)
        config = test_env.pyproject.load()
        models_required = config.get("tool", {}).get("comfydock", {}).get("models", {}).get("required", {})

        # All 3 workflow nodes resolve to the same model file, so there's only 1 hash
        assert len(models_required) == 1, \
            f"Expected 1 model hash (all resolve to same file), got {len(models_required)}"

        # But workflow mappings should have 3 node locations
        workflow_mappings = config.get("tool", {}).get("comfydock", {}).get("workflows", {}).get("progressive_test", {}).get("models", {})
        assert len(workflow_mappings) > 0, "Workflow mappings should exist"

        # Get the single model's node list
        model_hash = list(models_required.keys())[0]
        node_locations = workflow_mappings.get(model_hash, {}).get("nodes", [])

        assert len(node_locations) == 3, \
            f"Expected 3 node locations written incrementally, got {len(node_locations)}"

    def test_workflow_json_updated_incrementally(
        self,
        test_env,
        test_models
    ):
        """
        Test that workflow JSON is updated after each model resolution.

        CURRENT BEHAVIOR (should FAIL):
        - Workflow JSON updated once at the end

        DESIRED BEHAVIOR:
        - Workflow JSON updated after each model resolution
        - User sees progress in real-time
        """
        # ARRANGE: Workflow with 2 missing models
        workflow_data = {
            "id": "incremental-json-test",
            "nodes": [
                {
                    "id": 4,
                    "type": "CheckpointLoaderSimple",
                    "pos": [0, 0],
                    "widgets_values": ["missing1.safetensors"]
                },
                {
                    "id": 5,
                    "type": "LoraLoader",
                    "pos": [100, 0],
                    "widgets_values": ["missing2.safetensors", 1.0, 1.0]
                }
            ],
            "links": []
        }

        simulate_comfyui_save_workflow(test_env, "incremental_json", workflow_data)
        workflow_path = test_env.comfyui_path / "user/default/workflows/incremental_json.json"

        # ACT: Resolve models with instrumented strategy
        workflow_status = test_env.workflow_manager.get_workflow_status()
        workflow_analysis = workflow_status.analyzed_workflows[0]

        class IncrementalCheckStrategy(ModelResolutionStrategy):
            """Strategy that checks workflow JSON after each resolution."""

            def __init__(self, repo, workflow_path):
                self.repo = repo
                self.workflow_path = workflow_path
                self.resolved_count = 0

            def resolve_ambiguous_model(self, ref, candidates):
                return candidates[0] if candidates else None

            def handle_missing_model(self, ref):
                # Resolve model
                model = self.repo.find_by_filename("sd15_v1.safetensors")
                if model:
                    self.resolved_count += 1

                    # CRITICAL CHECK: Read workflow JSON NOW
                    # In progressive mode, it should already be updated
                    with open(self.workflow_path) as f:
                        current_workflow = json.load(f)

                    # Count how many nodes have resolved paths (not "missing*.safetensors")
                    resolved_nodes = 0
                    for node in current_workflow["nodes"]:
                        if "widgets_values" in node and node["widgets_values"]:
                            value = node["widgets_values"][0]
                            if "sd15_v1" in value:
                                resolved_nodes += 1

                    # EXPECTED TO FAIL: Currently resolved_nodes will be 0
                    # because workflow JSON isn't updated until apply_resolution
                    # We expect it to equal self.resolved_count (incremental updates)
                    # For now, just store it for later assertion
                    self.last_check_resolved_count = resolved_nodes

                    return ("select", model[0].relative_path)
                return None

        strategy = IncrementalCheckStrategy(test_env.model_repository, workflow_path)

        resolution = test_env.workflow_manager.fix_resolution(
            workflow_analysis.resolution,
            model_strategy=strategy,
            workflow_name="incremental_json"
        )

        # ASSERT: Workflow JSON should have been updated during fix_resolution
        # EXPECTED TO FAIL: last_check_resolved_count will be 0 (no incremental updates)
        assert hasattr(strategy, 'last_check_resolved_count'), \
            "Strategy should have checked workflow state"
        assert strategy.last_check_resolved_count > 0, \
            "Workflow JSON should be updated incrementally (currently happens in batch)"

    def test_ctrl_c_preserves_partial_progress(
        self,
        test_env,
        test_models
    ):
        """
        Test that Ctrl+C during resolution preserves partial work.

        CURRENT BEHAVIOR (should FAIL):
        - KeyboardInterrupt loses all progress
        - User must start over completely

        DESIRED BEHAVIOR:
        - Already-resolved models saved to pyproject
        - Already-resolved models written to workflow JSON
        - Re-running resolution skips completed items
        """
        # ARRANGE: Workflow with 3 missing models
        workflow_data = {
            "id": "ctrl-c-test",
            "nodes": [
                {
                    "id": 4,
                    "type": "CheckpointLoaderSimple",
                    "pos": [0, 0],
                    "widgets_values": ["model1.safetensors"]
                },
                {
                    "id": 5,
                    "type": "LoraLoader",
                    "pos": [100, 0],
                    "widgets_values": ["model2.safetensors", 1.0, 1.0]
                },
                {
                    "id": 6,
                    "type": "LoraLoader",
                    "pos": [200, 0],
                    "widgets_values": ["model3.safetensors", 1.0, 1.0]
                }
            ],
            "links": []
        }

        simulate_comfyui_save_workflow(test_env, "ctrl_c_test", workflow_data)

        # ACT: Resolve 2 models, then simulate Ctrl+C on 3rd
        workflow_status = test_env.workflow_manager.get_workflow_status()
        workflow_analysis = workflow_status.analyzed_workflows[0]

        class CtrlCAfterTwoStrategy(ModelResolutionStrategy):
            """Simulates user hitting Ctrl+C after resolving 2 models."""

            def __init__(self, repo):
                self.repo = repo
                self.call_count = 0

            def resolve_ambiguous_model(self, ref, candidates):
                return candidates[0] if candidates else None

            def handle_missing_model(self, ref):
                self.call_count += 1

                if self.call_count <= 2:
                    # Resolve first 2 models
                    model = self.repo.find_by_filename("sd15_v1.safetensors")
                    if model:
                        return ("select", model[0].relative_path)
                else:
                    # Simulate Ctrl+C on 3rd model
                    raise KeyboardInterrupt("User cancelled")

                return None

        strategy = CtrlCAfterTwoStrategy(test_env.model_repository)

        # KeyboardInterrupt is caught and handled gracefully (doesn't propagate)
        # This is DESIRED behavior - partial work is saved, loop exits cleanly
        resolution = test_env.workflow_manager.fix_resolution(
            workflow_analysis.resolution,
            model_strategy=strategy,
            workflow_name="ctrl_c_test"
        )

        # ASSERT: Pyproject should have 2 models saved (partial progress)
        config = test_env.pyproject.load()
        models_required = config.get("tool", {}).get("comfydock", {}).get("models", {}).get("required", {})

        # All models resolve to same file, so 1 hash
        assert len(models_required) == 1, "Model should be in pyproject"

        # But workflow mappings should have 2 node locations (models 1 and 2)
        workflow_mappings = config.get("tool", {}).get("comfydock", {}).get("workflows", {}).get("ctrl_c_test", {}).get("models", {})
        model_hash = list(models_required.keys())[0]
        node_locations = workflow_mappings.get(model_hash, {}).get("nodes", [])

        assert len(node_locations) == 2, \
            f"Expected 2 node locations saved before Ctrl+C, got {len(node_locations)}. " \
            "Progressive writes should preserve partial work."

    def test_cli_path_preserves_progress_on_ctrl_c(
        self,
        test_env,
        test_models
    ):
        """
        Test that environment.resolve_workflow() (CLI path) preserves partial progress.

        CRITICAL BUG: environment.resolve_workflow() calls apply_resolution() after
        fix_resolution(), which WIPES OUT progressive writes.

        This test reproduces the exact user bug:
        1. User runs 'comfydock workflow resolve "VideoUtils_v2_2 (1) (2)"'
        2. User answers first question (JWIntegerDiv → manual entry)
        3. User hits Ctrl+C on second question (SetNode)
        4. User runs resolve again → ASKED SAME QUESTIONS (bug!)

        Expected: Partial progress saved, re-run skips resolved items
        Actual: apply_resolution() wipes progressive writes on return
        """
        # ARRANGE: Workflow with 3 missing models (like user's VideoUtils workflow)
        workflow_data = {
            "id": "cli-ctrl-c-test",
            "nodes": [
                {
                    "id": 4,
                    "type": "CheckpointLoaderSimple",
                    "pos": [0, 0],
                    "widgets_values": ["model1.safetensors"]
                },
                {
                    "id": 5,
                    "type": "LoraLoader",
                    "pos": [100, 0],
                    "widgets_values": ["model2.safetensors", 1.0, 1.0]
                },
                {
                    "id": 6,
                    "type": "LoraLoader",
                    "pos": [200, 0],
                    "widgets_values": ["model3.safetensors", 1.0, 1.0]
                }
            ],
            "links": []
        }

        simulate_comfyui_save_workflow(test_env, "cli_ctrl_c", workflow_data)

        # ACT: Resolve via CLI path (environment.resolve_workflow) with Ctrl+C after 2 models
        class CtrlCAfterTwoStrategy(ModelResolutionStrategy):
            """Simulates user hitting Ctrl+C after resolving 2 models."""

            def __init__(self, repo):
                self.repo = repo
                self.call_count = 0

            def resolve_ambiguous_model(self, ref, candidates):
                return candidates[0] if candidates else None

            def handle_missing_model(self, ref):
                self.call_count += 1

                if self.call_count <= 2:
                    # Resolve first 2 models
                    model = self.repo.find_by_filename("sd15_v1.safetensors")
                    if model:
                        return ("select", model[0].relative_path)
                else:
                    # Simulate Ctrl+C on 3rd model
                    raise KeyboardInterrupt("User cancelled")

                return None

        strategy = CtrlCAfterTwoStrategy(test_env.model_repository)

        # Call environment.resolve_workflow() (THIS IS THE CLI PATH!)
        # This internally calls:
        # 1. fix_resolution() with workflow_name → progressive writes ✅
        # 2. apply_resolution() after return → WIPES WRITES ❌
        try:
            result = test_env.resolve_workflow(
                name="cli_ctrl_c",
                model_strategy=strategy,
                fix=True
            )
        except KeyboardInterrupt:
            # KeyboardInterrupt is caught inside fix_resolution, shouldn't propagate
            pass

        # ASSERT: Pyproject should have 2 models saved (partial progress)
        # With the fix, progressive writes are preserved even though apply_resolution is called
        config = test_env.pyproject.load()
        models_required = config.get("tool", {}).get("comfydock", {}).get("models", {}).get("required", {})

        # All models resolve to same file, so 1 hash
        assert len(models_required) == 1, \
            f"Expected 1 model in pyproject after Ctrl+C, got {len(models_required)}. " \
            "Progressive writes should be preserved!"

        # But workflow mappings should have 2 node locations (models 1 and 2)
        workflow_mappings = config.get("tool", {}).get("comfydock", {}).get("workflows", {}).get("cli_ctrl_c", {}).get("models", {})
        model_hash = list(models_required.keys())[0]
        node_locations = workflow_mappings.get(model_hash, {}).get("nodes", [])

        # The fix: nodes_only flag prevents apply_resolution() from wiping progressive writes
        assert len(node_locations) == 2, \
            f"Expected 2 node locations saved before Ctrl+C, got {len(node_locations)}. " \
            "Progressive writes should be preserved!"

    @pytest.mark.skip(reason="Auto-resume caching is a separate feature - not part of progressive writes")
    def test_resume_skips_already_resolved_models(
        self,
        test_env,
        test_models
    ):
        """
        Test that re-running resolution skips already-resolved items.

        NOTE: This tests auto-resume caching (Phase 2), which is a SEPARATE feature
        from progressive writes (Phase 3). Progressive writes enable Ctrl+C safety,
        while auto-resume enables skipping already-cached resolutions on re-run.

        CURRENT STATUS: Not yet implemented (separate task)

        DESIRED BEHAVIOR:
        - Already-resolved models auto-skipped via pyproject cache
        - Only unresolved models prompt user
        """
        # ARRANGE: Pre-populate pyproject with 1 resolved model
        workflow_data = {
            "id": "resume-test",
            "nodes": [
                {
                    "id": 4,
                    "type": "CheckpointLoaderSimple",
                    "pos": [0, 0],
                    "widgets_values": ["model_already_resolved.safetensors"]
                },
                {
                    "id": 5,
                    "type": "LoraLoader",
                    "pos": [100, 0],
                    "widgets_values": ["model_still_missing.safetensors", 1.0, 1.0]
                }
            ],
            "links": []
        }

        simulate_comfyui_save_workflow(test_env, "resume_test", workflow_data)

        # Pre-resolve the checkpoint model manually
        indexed_model = test_env.model_repository.find_by_filename("sd15_v1.safetensors")[0]
        test_env.pyproject.models.add_model(
            model_hash=indexed_model.hash,
            filename=indexed_model.filename,
            file_size=indexed_model.file_size,
            relative_path=indexed_model.relative_path,
            category="required"
        )

        # Add workflow mapping for the resolved model
        test_env.pyproject.workflows.set_model_resolutions(
            name="resume_test",
            model_resolutions={
                indexed_model.hash: {
                    "nodes": [{"node_id": "4", "widget_idx": 0}]
                }
            }
        )

        # ACT: Run resolution again - should only ask about the lora
        workflow_status = test_env.workflow_manager.get_workflow_status()
        workflow_analysis = workflow_status.analyzed_workflows[0]

        class CountPromptsStrategy(ModelResolutionStrategy):
            """Counts how many models user is prompted for."""

            def __init__(self, repo):
                self.repo = repo
                self.prompt_count = 0

            def resolve_ambiguous_model(self, ref, candidates):
                self.prompt_count += 1
                return candidates[0] if candidates else None

            def handle_missing_model(self, ref):
                self.prompt_count += 1
                model = self.repo.find_by_filename("sd15_v1.safetensors")
                if model:
                    return ("select", model[0].relative_path)
                return None

        strategy = CountPromptsStrategy(test_env.model_repository)

        resolution = test_env.workflow_manager.fix_resolution(
            workflow_analysis.resolution,
            model_strategy=strategy,
            workflow_name="resume_test"
        )

        # ASSERT: Auto-skip happens in resolve_workflow (Phase 2), not fix_resolution (Phase 3)
        # So we expect BOTH models to still be in models_unresolved when fix_resolution is called
        # The checkpoint was auto-resolved in Phase 2 and moved to models_resolved
        # So fix_resolution only sees the lora as unresolved

        # Check: The resolution result should show checkpoint already resolved
        assert len(workflow_analysis.resolution.models_resolved) >= 1, \
            "Checkpoint should be auto-resolved from pyproject cache"

        # Only lora should be unresolved
        assert len(workflow_analysis.resolution.models_unresolved) == 1, \
            "Only lora should be unresolved"

        # fix_resolution should only prompt for the unresolved lora
        assert strategy.prompt_count == 1, \
            f"Expected 1 prompt (lora only), got {strategy.prompt_count}. " \
            "Auto-resume works via Phase 2 caching, not progressive writes."
