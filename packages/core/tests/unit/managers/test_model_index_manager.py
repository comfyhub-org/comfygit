"""Unit tests for ModelIndexManager."""

import time
from comfydock_core.repositories.model_repository import ModelRepository


def test_add_and_find_models(tmp_path):
    """Test adding models and finding by hash and filename."""
    db_path = tmp_path / "test_models.db"
    base_path = tmp_path / "models"
    base_path.mkdir()
    index_mgr = ModelRepository(db_path)

    # Model info to use for testing (but we'll add directly to index)

    # Add models to index with locations
    model1_path = "checkpoints/test_model.safetensors"
    model2_path = "loras/another_model.ckpt"

    # Create actual files for testing
    (base_path / "checkpoints").mkdir()
    (base_path / "loras").mkdir()
    (base_path / model1_path).write_bytes(b"test" * 256000)  # Create dummy content
    (base_path / model2_path).write_bytes(b"test" * 512000)  # Create dummy content

    # Ensure models exist in the index
    index_mgr.ensure_model("abc123def456", 1024000, blake3_hash="abc123def456")
    index_mgr.ensure_model("xyz789uvw012", 2048000, blake3_hash="xyz789uvw012")

    # Add locations for the models
    index_mgr.add_location("abc123def456", model1_path, "test_model.safetensors", time.time())
    index_mgr.add_location("xyz789uvw012", model2_path, "another_model.ckpt", time.time())

    # Find by hash prefix
    results = index_mgr.find_model_by_hash("abc123")
    assert len(results) == 1
    assert results[0].hash == "abc123def456"
    assert results[0].filename == "test_model.safetensors"

    # Find by filename
    filename_results = index_mgr.find_by_filename("test_model")
    assert len(filename_results) == 1
    assert filename_results[0].hash == "abc123def456"

    # Get all models
    all_models = index_mgr.get_all_models()
    assert len(all_models) == 2


def test_models_by_path_and_stats(tmp_path):
    """Test filtering models by path pattern and getting statistics."""
    db_path = tmp_path / "test_types.db"
    index_mgr = ModelRepository(db_path)

    # Add models in different directories
    models_data = [
        ("hash1", "checkpoints/model1.safetensors", "model1.safetensors", 1000000),
        ("hash2", "checkpoints/model2.safetensors", "model2.safetensors", 1500000),
        ("hash3", "loras/lora1.safetensors", "lora1.safetensors", 500000),
        ("hash4", "vae/vae1.safetensors", "vae1.safetensors", 800000),
    ]

    for hash_val, rel_path, filename, size in models_data:
        index_mgr.ensure_model(hash_val, size, blake3_hash=hash_val)
        index_mgr.add_location(hash_val, rel_path, filename, time.time())

    # Get all models and filter by path
    all_locations = index_mgr.get_all_locations()

    checkpoint_models = [loc for loc in all_locations if "checkpoints/" in loc['relative_path']]
    assert len(checkpoint_models) == 2

    lora_models = [loc for loc in all_locations if "loras/" in loc['relative_path']]
    assert len(lora_models) == 1
    assert lora_models[0]['filename'] == "lora1.safetensors"

    vae_models = [loc for loc in all_locations if "vae/" in loc['relative_path']]
    assert len(vae_models) == 1

    # Get statistics
    stats = index_mgr.get_stats()
    assert stats['total_models'] == 4
    assert stats['total_locations'] == 4


def test_update_and_remove_models(tmp_path):
    """Test updating model locations and removing models."""
    db_path = tmp_path / "test_updates.db"
    index_mgr = ModelRepository(db_path)

    # Add a model
    original_path = "original/update_test.safetensors"
    index_mgr.ensure_model("update_test_hash", 1024, blake3_hash="update_test_hash")
    index_mgr.add_location("update_test_hash", original_path, "update_test.safetensors", time.time())

    # Verify it was added
    results = index_mgr.find_model_by_hash("update_test_hash")
    assert len(results) == 1
    assert results[0].relative_path == original_path

    # Update the path (add the model at a new location)
    new_path = "moved/update_test.safetensors"
    index_mgr.add_location("update_test_hash", new_path, "update_test.safetensors", time.time())

    # Verify we now have the model at the new location
    updated_results = index_mgr.find_model_by_hash("update_test_hash")
    # Should have both locations now
    assert any(r.relative_path == new_path for r in updated_results)

    # Remove the model location
    removed = index_mgr.remove_location(original_path)
    assert removed

    # Verify the location was removed
    location_results = index_mgr.get_all_locations()
    assert not any(loc['relative_path'] == original_path for loc in location_results)

    # Remove the remaining location
    index_mgr.remove_location(new_path)

    # Verify no locations remain (model still in database but no locations)
    removed_results = index_mgr.find_model_by_hash("update_test_hash")
    assert len(removed_results) == 0  # No locations means no results from find
