"""
Integration tests for model source preservation bug.

BUG: When models are resolved from local index (which has source URLs),
the sources are NOT written to pyproject.toml. This breaks collaboration
because other devs can't download the models.

Expected behavior:
- Model has source in SQLite repository ✓
- Model is resolved from repository ✓
- Sources are written to pyproject.toml ✗ (BUG - currently writes empty sources=[])

These tests should FAIL until the fix is implemented.
"""

from helpers.model_index_builder import ModelIndexBuilder
from helpers.workflow_builder import WorkflowBuilder
from helpers.pyproject_assertions import PyprojectAssertions
from conftest import simulate_comfyui_save_workflow


class TestModelSourcePreservation:
    """Test that model sources flow from repository to pyproject during resolution."""

    def test_progressive_resolution_preserves_sources_from_repository(self, test_env, test_workspace):
        """
        BUG TEST: Progressive resolution should write sources to pyproject.

        Scenario:
        1. Download model with source URL (adds to repository with source)
        2. Use model in workflow
        3. Resolve workflow progressively
        4. EXPECTED: pyproject.toml should have source URLs from repository
        5. ACTUAL (BUG): pyproject.toml has sources=[]
        """
        # ARRANGE - Create model with source in repository
        builder = ModelIndexBuilder(test_workspace)
        builder.add_model(
            filename="test_lora.safetensors",
            relative_path="loras",
            size_mb=1,
            category="loras"
        )
        builder.index_all()

        # Get the ACTUAL hash from indexed model (not builder's deterministic hash)
        indexed_models = test_workspace.model_index_manager.get_all_models()
        indexed_model = next((m for m in indexed_models if m.filename == "test_lora.safetensors"), None)
        assert indexed_model is not None, "Model should be indexed"
        model_hash = indexed_model.hash

        # Add source to repository (simulates download with URL)
        test_url = "https://civitai.com/api/download/models/12345"
        test_workspace.model_index_manager.add_source(
            model_hash=model_hash,
            source_type="civitai",
            source_url=test_url
        )

        # Verify source is in repository
        sources = test_workspace.model_index_manager.get_sources(model_hash)
        assert len(sources) == 1
        assert sources[0]['url'] == test_url

        # Create workflow using this model
        workflow = (
            WorkflowBuilder()
            .add_lora_loader("test_lora.safetensors")
            .build()
        )
        simulate_comfyui_save_workflow(test_env, "test_workflow", workflow)

        # ACT - Resolve workflow (progressive mode - calls _write_single_model_resolution)
        deps = test_env.workflow_manager.analyze_workflow("test_workflow")
        resolution = test_env.workflow_manager.resolve_workflow(deps)

        # Apply resolution writes to pyproject
        test_env.workflow_manager.apply_resolution(resolution)

        # ASSERT - BUG: Sources should be in pyproject but are currently empty
        assertions = PyprojectAssertions(test_env)

        # Check workflow model has sources
        workflow_model = (
            assertions
            .has_workflow("test_workflow")
            .has_model_with_filename("test_lora.safetensors")
        )
        # This will FAIL until bug is fixed:
        assert test_url in workflow_model.config.get("sources", []), \
            f"BUG: Expected source '{test_url}' in workflow model, got {workflow_model.config.get('sources', [])}"

        # Check global model table has sources
        global_model = assertions.has_global_model(model_hash)
        # This will FAIL until bug is fixed:
        global_model.has_source(test_url)

    def test_bulk_resolution_preserves_sources_from_repository(self, test_env, test_workspace):
        """
        BUG TEST: Bulk resolution should write sources to pyproject.

        Scenario:
        1. Create multiple models with sources in repository
        2. Create workflow using these models
        3. Resolve workflow in bulk (apply_resolution path)
        4. EXPECTED: All model sources should be in pyproject
        5. ACTUAL (BUG): sources=[] for all models
        """
        # ARRANGE - Create two models with sources
        builder = ModelIndexBuilder(test_workspace)
        builder.add_model("checkpoint.safetensors", "checkpoints", size_mb=4, category="checkpoints")
        builder.add_model("lora.safetensors", "loras", size_mb=1, category="loras")
        builder.index_all()

        # Get actual hashes from indexed models
        indexed_models = test_workspace.model_index_manager.get_all_models()
        checkpoint_model = next((m for m in indexed_models if m.filename == "checkpoint.safetensors"), None)
        lora_model = next((m for m in indexed_models if m.filename == "lora.safetensors"), None)
        assert checkpoint_model is not None and lora_model is not None, "Models should be indexed"

        checkpoint_hash = checkpoint_model.hash
        lora_hash = lora_model.hash

        # Add sources to repository
        checkpoint_url = "https://civitai.com/api/download/models/1111"
        lora_url = "https://huggingface.co/models/test/lora.safetensors"

        test_workspace.model_index_manager.add_source(checkpoint_hash, "civitai", checkpoint_url)
        test_workspace.model_index_manager.add_source(lora_hash, "huggingface", lora_url)

        # Create workflow with both models
        workflow = (
            WorkflowBuilder()
            .add_checkpoint_loader("checkpoint.safetensors")
            .add_lora_loader("lora.safetensors")
            .build()
        )
        simulate_comfyui_save_workflow(test_env, "multi_model", workflow)

        # ACT - Resolve in bulk
        deps = test_env.workflow_manager.analyze_workflow("multi_model")
        resolution = test_env.workflow_manager.resolve_workflow(deps)
        test_env.workflow_manager.apply_resolution(resolution)

        # ASSERT - Both models should have sources (will FAIL)
        assertions = PyprojectAssertions(test_env)

        # Check checkpoint has source
        checkpoint_model = (
            assertions
            .has_workflow("multi_model")
            .has_model_with_filename("checkpoint.safetensors")
        )
        assert checkpoint_url in checkpoint_model.config.get("sources", []), \
            f"BUG: Checkpoint missing source. Got sources: {checkpoint_model.config.get('sources', [])}"

        # Check lora has source
        lora_model = (
            assertions
            .has_workflow("multi_model")
            .has_model_with_filename("lora.safetensors")
        )
        assert lora_url in lora_model.config.get("sources", []), \
            f"BUG: Lora missing source. Got sources: {lora_model.config.get('sources', [])}"

        # Check global models table
        assertions.has_global_model(checkpoint_hash).has_source(checkpoint_url)
        assertions.has_global_model(lora_hash).has_source(lora_url)

    def test_collaboration_scenario_fails_without_sources(self, test_env, test_workspace):
        """
        BUG TEST: Real-world collaboration scenario that fails.

        Dev A scenario:
        1. Dev A downloads model (has source in their repository)
        2. Dev A uses model in workflow
        3. Dev A commits workflow
        4. pyproject.toml is pushed to git

        Dev B scenario:
        5. Dev B pulls pyproject.toml
        6. Dev B runs repair/import
        7. EXPECTED: Models download using sources from pyproject
        8. ACTUAL (BUG): No sources in pyproject, can't download
        """
        # DEV A - Download and use model
        builder = ModelIndexBuilder(test_workspace)
        builder.add_model("shared_model.safetensors", "checkpoints", size_mb=2)
        builder.index_all()

        # Get the ACTUAL hash from the indexed model (not the builder's deterministic hash)
        indexed_models = test_workspace.model_index_manager.get_all_models()
        indexed_model = next((m for m in indexed_models if m.filename == "shared_model.safetensors"), None)
        assert indexed_model is not None, "Model should be indexed"
        model_hash = indexed_model.hash

        model_url = "https://civitai.com/api/download/models/9999"

        # Simulate download - adds source to repository
        test_workspace.model_index_manager.add_source(model_hash, "civitai", model_url)

        # Dev A creates workflow
        workflow = WorkflowBuilder().add_checkpoint_loader("shared_model.safetensors").build()
        simulate_comfyui_save_workflow(test_env, "shared_wf", workflow)

        # Dev A resolves and commits
        deps = test_env.workflow_manager.analyze_workflow("shared_wf")
        resolution = test_env.workflow_manager.resolve_workflow(deps)
        test_env.workflow_manager.apply_resolution(resolution)

        # Check what Dev A commits to pyproject.toml
        pyproject_config = test_env.pyproject.load()
        global_models = pyproject_config.get("tool", {}).get("comfydock", {}).get("models", {})

        # BUG: This model should have sources but doesn't
        assert model_hash in global_models, "Model should be in global table"
        committed_model = global_models[model_hash]

        # This assertion will FAIL - proving the bug
        committed_sources = committed_model.get("sources", [])
        assert model_url in committed_sources, \
            f"BUG: Model committed without source! Dev B won't be able to download it. " \
            f"Sources in pyproject: {committed_sources}, Expected: ['{model_url}']"
