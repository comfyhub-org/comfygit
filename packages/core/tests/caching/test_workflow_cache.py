"""Unit tests for WorkflowCacheRepository.

Tests workflow analysis caching including:
- Cache hit/miss behavior
- Content-based invalidation
- mtime + size fast path
- Hash fallback path
- Session cache isolation
- Multi-environment isolation
- Cache persistence
"""
import json
import time
from pathlib import Path
import pytest

from comfygit_core.caching.workflow_cache import WorkflowCacheRepository
from comfygit_core.models.workflow import WorkflowDependencies, WorkflowNode


@pytest.fixture
def cache_db(tmp_path):
    """Create temporary cache database."""
    db_path = tmp_path / "test_workflows.db"
    return WorkflowCacheRepository(db_path)


@pytest.fixture
def sample_workflow_file(tmp_path):
    """Create a sample workflow JSON file."""
    workflow_path = tmp_path / "test_workflow.json"
    workflow_data = {
        "nodes": [
            {
                "id": 1,
                "type": "CheckpointLoaderSimple",
                "widgets_values": ["model.safetensors"]
            },
            {
                "id": 2,
                "type": "KSampler",
                "widgets_values": [123, "fixed", 20, 8.0]
            }
        ],
        "extra": {
            "ds": {"scale": 1.0, "offset": [0, 0]}  # UI state - should be normalized
        }
    }
    with open(workflow_path, 'w') as f:
        json.dump(workflow_data, f)
    return workflow_path


@pytest.fixture
def sample_dependencies():
    """Create sample WorkflowDependencies object."""
    return WorkflowDependencies(
        workflow_name="test_workflow",
        builtin_nodes=[
            WorkflowNode(
                id="1",
                type="CheckpointLoaderSimple"
            ),
            WorkflowNode(
                id="2",
                type="KSampler"
            )
        ],
        non_builtin_nodes=[],
        found_models=[]
    )


class TestCacheMissReturnsNone:
    """Test that cache queries for non-existent workflows return None."""

    def test_cache_miss_returns_none(self, cache_db, sample_workflow_file):
        """Query cache for non-existent workflow should return None."""
        result = cache_db.get(
            env_name="test-env",
            workflow_name="nonexistent",
            workflow_path=sample_workflow_file
        )

        assert result is None


class TestCacheHitAfterSet:
    """Test that cached data is returned after being set."""

    def test_cache_hit_after_set_and_session_cache_populated(self, cache_db, sample_workflow_file, sample_dependencies):
        """Set workflow analysis in cache - should return cached data and populate session cache."""
        # Set cache
        cache_db.set(
            env_name="test-env",
            workflow_name="test_workflow",
            workflow_path=sample_workflow_file,
            dependencies=sample_dependencies
        )

        # Query cache - should return cached analysis
        result = cache_db.get(
            env_name="test-env",
            workflow_name="test_workflow",
            workflow_path=sample_workflow_file
        )

        assert result is not None
        assert result.dependencies is not None
        assert len(result.dependencies.builtin_nodes) == 2
        assert result.dependencies.builtin_nodes[0].type == "CheckpointLoaderSimple"
        assert result.dependencies.builtin_nodes[1].type == "KSampler"

        # Session cache key should exist
        session_key = "test-env:test_workflow"
        assert session_key in cache_db._session_cache
        assert cache_db._session_cache[session_key] is not None


class TestCacheInvalidationOnContentChange:
    """Test that cache is invalidated when workflow content changes."""

    def test_cache_invalidation_on_content_change(
        self,
        cache_db,
        sample_workflow_file,
        sample_dependencies
    ):
        """Modify workflow content - cache should miss."""
        # Cache workflow
        cache_db.set(
            env_name="test-env",
            workflow_name="test_workflow",
            workflow_path=sample_workflow_file,
            dependencies=sample_dependencies
        )

        # Verify cache hit
        result = cache_db.get(
            env_name="test-env",
            workflow_name="test_workflow",
            workflow_path=sample_workflow_file
        )
        assert result is not None

        # Modify workflow content (add a node)
        with open(sample_workflow_file, 'r') as f:
            workflow = json.load(f)

        workflow["nodes"].append({
            "id": 3,
            "type": "SaveImage",
            "widgets_values": []
        })

        with open(sample_workflow_file, 'w') as f:
            json.dump(workflow, f)

        # Clear session cache to force SQLite lookup
        cache_db._session_cache.clear()

        # Query again - should miss (content changed)
        result = cache_db.get(
            env_name="test-env",
            workflow_name="test_workflow",
            workflow_path=sample_workflow_file
        )

        assert result is None


class TestCacheHitOnMtimeMatch:
    """Test fast path using mtime + size matching."""

    def test_cache_hit_on_mtime_match(
        self,
        cache_db,
        sample_workflow_file,
        sample_dependencies
    ):
        """Query without file changes should use fast mtime path."""
        # Cache workflow
        cache_db.set(
            env_name="test-env",
            workflow_name="test_workflow",
            workflow_path=sample_workflow_file,
            dependencies=sample_dependencies
        )

        # Clear session cache to force SQLite lookup
        cache_db._session_cache.clear()

        # Query again - should hit via mtime fast path
        start_time = time.perf_counter()
        result = cache_db.get(
            env_name="test-env",
            workflow_name="test_workflow",
            workflow_path=sample_workflow_file
        )
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        assert result is not None
        assert result.dependencies is not None
        # Fast path should be very quick (< 10ms for test overhead)
        assert elapsed_ms < 10


class TestCacheHitAfterTouchOnly:
    """Test that hash fallback works when only mtime changes."""

    def test_cache_hit_after_touch_only(
        self,
        cache_db,
        sample_workflow_file,
        sample_dependencies
    ):
        """Touch file (change mtime, same content) - cache should hit via hash fallback."""
        # Cache workflow
        cache_db.set(
            env_name="test-env",
            workflow_name="test_workflow",
            workflow_path=sample_workflow_file,
            dependencies=sample_dependencies
        )

        # Touch file to change mtime
        time.sleep(0.01)  # Ensure mtime changes
        sample_workflow_file.touch()

        # Clear session cache to force SQLite lookup
        cache_db._session_cache.clear()

        # Query again - should hit via hash fallback
        result = cache_db.get(
            env_name="test-env",
            workflow_name="test_workflow",
            workflow_path=sample_workflow_file
        )

        assert result is not None
        assert result.dependencies is not None
        assert len(result.dependencies.builtin_nodes) == 2


class TestSessionCacheIsolation:
    """Test that session caches are isolated between instances."""

    def test_session_cache_isolation(
        self,
        tmp_path,
        sample_workflow_file,
        sample_dependencies
    ):
        """Session cache should be instance-specific, SQLite shared."""
        db_path = tmp_path / "shared.db"

        # Create two cache instances
        cache_a = WorkflowCacheRepository(db_path)
        cache_b = WorkflowCacheRepository(db_path)

        # Set in cache A
        cache_a.set(
            env_name="test-env",
            workflow_name="test_workflow",
            workflow_path=sample_workflow_file,
            dependencies=sample_dependencies
        )

        # Query in cache B - should hit SQLite, not session cache
        result_b = cache_b.get(
            env_name="test-env",
            workflow_name="test_workflow",
            workflow_path=sample_workflow_file
        )

        # Should get data from SQLite
        assert result_b is not None

        # Verify B's session cache was populated
        session_key = "test-env:test_workflow"
        assert session_key in cache_b._session_cache

        # Verify A and B have independent session caches
        assert cache_a._session_cache is not cache_b._session_cache


class TestMultiEnvironmentIsolation:
    """Test that different environments have isolated cache entries."""

    def test_multi_environment_isolation(
        self,
        cache_db,
        tmp_path,
        sample_dependencies
    ):
        """Same workflow name in different environments should have independent cache."""
        # Create two workflow files with different content
        workflow1 = tmp_path / "workflow1.json"
        workflow2 = tmp_path / "workflow2.json"

        workflow1.write_text(json.dumps({
            "nodes": [{"id": 1, "type": "NodeA"}]
        }))
        workflow2.write_text(json.dumps({
            "nodes": [{"id": 1, "type": "NodeB"}]
        }))

        deps1 = WorkflowDependencies(
            workflow_name="my_workflow",
            non_builtin_nodes=[WorkflowNode(id="1", type="NodeA")],
            builtin_nodes=[],
            found_models=[]
        )
        deps2 = WorkflowDependencies(
            workflow_name="my_workflow",
            non_builtin_nodes=[WorkflowNode(id="1", type="NodeB")],
            builtin_nodes=[],
            found_models=[]
        )

        # Cache same workflow name in different environments
        cache_db.set("env1", "my_workflow", workflow1, deps1)
        cache_db.set("env2", "my_workflow", workflow2, deps2)

        # Clear session cache
        cache_db._session_cache.clear()

        # Query each environment
        result1 = cache_db.get("env1", "my_workflow", workflow1)
        result2 = cache_db.get("env2", "my_workflow", workflow2)

        # Should get correct data for each environment
        assert result1 is not None
        assert result2 is not None
        assert result1.dependencies.non_builtin_nodes[0].type == "NodeA"
        assert result2.dependencies.non_builtin_nodes[0].type == "NodeB"


class TestCacheSurvivesRestart:
    """Test that cache persists across repository instances."""

    def test_cache_survives_restart(
        self,
        tmp_path,
        sample_workflow_file,
        sample_dependencies
    ):
        """Cache should persist when creating new repository instance."""
        db_path = tmp_path / "persistent.db"

        # Create cache instance A and set data
        cache_a = WorkflowCacheRepository(db_path)
        cache_a.set(
            env_name="test-env",
            workflow_name="test_workflow",
            workflow_path=sample_workflow_file,
            dependencies=sample_dependencies
        )

        # Destroy instance A
        del cache_a

        # Create new instance B with same db_path
        cache_b = WorkflowCacheRepository(db_path)

        # Query in instance B
        result = cache_b.get(
            env_name="test-env",
            workflow_name="test_workflow",
            workflow_path=sample_workflow_file
        )

        # Should get persisted data
        assert result is not None
        assert result.dependencies is not None
        assert len(result.dependencies.builtin_nodes) == 2


class TestInvalidation:
    """Test cache invalidation - selective and environment-wide."""

    def test_invalidate_specific_workflow_and_entire_environment(
        self,
        cache_db,
        tmp_path,
        sample_dependencies
    ):
        """Test both selective and environment-wide cache invalidation."""
        # Create workflows in two environments
        workflow1 = tmp_path / "workflow1.json"
        workflow2 = tmp_path / "workflow2.json"
        workflow3 = tmp_path / "workflow3.json"

        for wf in [workflow1, workflow2, workflow3]:
            wf.write_text(json.dumps({"nodes": []}))

        # Cache workflows in env1 and env2
        cache_db.set("env1", "workflow1", workflow1, sample_dependencies)
        cache_db.set("env1", "workflow2", workflow2, sample_dependencies)
        cache_db.set("env2", "workflow1", workflow1, sample_dependencies)

        # Test selective invalidation: invalidate workflow2 in env1
        cache_db.invalidate("env1", "workflow2")
        cache_db._session_cache.clear()

        result1 = cache_db.get("env1", "workflow1", workflow1)
        result2 = cache_db.get("env1", "workflow2", workflow2)

        assert result1 is not None  # workflow1 still cached
        assert result2 is None       # workflow2 invalidated

        # Test environment-wide invalidation: clear all of env1
        cache_db.invalidate("env1")
        cache_db._session_cache.clear()

        result_env1_wf1 = cache_db.get("env1", "workflow1", workflow1)
        result_env2_wf1 = cache_db.get("env2", "workflow1", workflow1)

        assert result_env1_wf1 is None          # env1 cleared
        assert result_env2_wf1 is not None      # env2 unaffected
        assert result_env2_wf1.dependencies is not None  # has data
