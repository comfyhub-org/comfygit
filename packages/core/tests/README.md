# ComfyDock Core Testing Infrastructure

**Last Updated:** 2025-10-02

This document describes the testing architecture for comfydock-core. Use this as a reference when adding new tests or extending existing test infrastructure.

## Table of Contents

- [Overview](#overview)
- [Test Architecture](#test-architecture)
- [Fixture Reference](#fixture-reference)
- [Adding New Tests](#adding-new-tests)
- [Common Patterns](#common-patterns)
- [Best Practices](#best-practices)
- [Troubleshooting](#troubleshooting)

---

## Overview

### Goals

The test infrastructure provides:

1. **Fast execution** - Full integration test suite runs in ~7-8 seconds
2. **Isolation** - Each test gets a fresh workspace in tmpdir
3. **Realism** - Tests use actual file operations, not mocks
4. **Simplicity** - Minimal setup required for new tests

### Test Types

```
tests/
├── unit/           # Unit tests (fast, isolated, mocked dependencies)
├── integration/    # Integration tests (realistic, end-to-end workflows)
└── fixtures/       # Shared test data
```

**Current Focus:** Integration tests for workflow commit flow

---

## Test Architecture

### Design Philosophy

**Test Through Core API, Not CLI**

```python
# ✅ Good - Tests business logic directly
test_env.execute_commit(workflow_status, message="Add workflow")

# ❌ Bad - Tests CLI parsing/formatting
subprocess.run(["comfydock", "commit", "-m", "Add workflow"])
```

**Benefits:**
- Faster execution (no subprocess overhead)
- Better error messages (full stack traces)
- Can inspect internal state
- Tests actual business logic, not UI

### Fixture Hierarchy

```
test_workspace (workspace with config)
    └─> test_env (environment with ComfyUI structure)
            └─> test_models (indexed model files)
                    └─> YOUR TEST
```

Each level depends on the previous:
- `test_workspace`: Creates workspace with proper config
- `test_env`: Adds environment structure (no ComfyUI clone!)
- `test_models`: Creates and indexes stub model files

**Key Insight:** Fixtures are **function-scoped** - each test gets fresh instances.

---

## Fixture Reference

### Core Fixtures (in `conftest.py`)

#### `test_workspace`

**Purpose:** Creates isolated workspace with proper initialization

**Provides:**
- WorkspaceFactory-initialized workspace
- Configured models directory
- Required metadata files
- Clean git state

**Usage:**
```python
def test_something(test_workspace):
    # Workspace is ready to use
    assert test_workspace.paths.root.exists()

    # Can create environments
    env = test_workspace.create_environment("my-env")
```

**What It Does:**
1. Creates workspace in pytest tmpdir
2. Initializes workspace.json with proper schema
3. Creates and registers models directory
4. Sets up cache directories

**Path Structure:**
```
{tmp}/comfydock_workspace/
├── .metadata/
│   └── workspace.json          # Workspace config
├── environments/               # Where envs go
├── comfydock_cache/           # Model index, node mappings
└── models/                    # Test model files
```

---

#### `test_env`

**Purpose:** Creates minimal environment without cloning ComfyUI

**Depends on:** `test_workspace`

**Provides:**
- Environment instance ready for testing
- Minimal ComfyUI directory structure
- Git repository in `.cec/`
- Empty node mappings file

**Usage:**
```python
def test_something(test_env):
    # Environment is ready
    assert test_env.comfyui_path.exists()

    # Can use environment methods
    status = test_env.status()
    test_env.execute_commit(...)
```

**What It Does:**
1. Creates environment directory structure
2. Creates minimal ComfyUI folders (no clone!)
3. Initializes git repo in `.cec/`
4. Creates empty node mappings (prevents init errors)
5. Creates minimal pyproject.toml

**ComfyUI Structure Created:**
```
environments/test-env/
├── .cec/                          # Git-tracked config
│   ├── .git/                      # Git repo
│   ├── pyproject.toml             # UV project
│   └── workflows/                 # Committed workflows go here
└── ComfyUI/                       # Minimal ComfyUI structure
    ├── custom_nodes/
    └── user/default/workflows/    # Active workflows (simulated ComfyUI saves)
```

**Why No ComfyUI Clone?**
- Original plan: Clone real repo (~30-60s per test)
- Optimization: Create directory structure only
- Result: **10x faster** (7.6s vs 60s)

---

#### `test_models`

**Purpose:** Creates and indexes stub model files

**Depends on:** `test_workspace`

**Provides:**
- Dictionary of created model metadata
- Indexed models in workspace model repository

**Usage:**
```python
def test_something(test_env, test_models):
    # Models are created and indexed
    assert "photon_v1.safetensors" in test_models

    # Can get model info
    model = test_models["photon_v1.safetensors"]
    assert model["file_size"] == 4194336  # 4MB
```

**What It Does:**
1. Loads model specs from `fixtures/models/test_models.json`
2. Creates 4MB stub files with deterministic content
3. Generates simple hashes (sha256 of filename)
4. Indexes models via `workspace.sync_model_directory()`

**Model Structure:**
```python
{
    "photon_v1.safetensors": {
        "filename": "photon_v1.safetensors",
        "hash": "4dc3c04e98315041",  # Deterministic
        "file_size": 4194336,          # 4MB
        "relative_path": "SD1.5",
        "path": Path(".../models/SD1.5/photon_v1.safetensors")
    }
}
```

---

#### `workflow_fixtures` and `model_fixtures`

**Purpose:** Provide paths to fixture data directories

**Usage:**
```python
def test_something(workflow_fixtures, model_fixtures):
    # Load workflow JSON
    workflow_path = workflow_fixtures / "simple_txt2img.json"

    # Load model specs
    specs_path = model_fixtures / "test_models.json"
```

**Available Fixtures:**

**Workflows** (`fixtures/workflows/`):
- `simple_txt2img.json` - Valid workflow with existing model
- `with_missing_model.json` - Workflow with non-existent model

**Models** (`fixtures/models/`):
- `test_models.json` - Specifications for creating test models

---

### Helper Functions (in `conftest.py`)

#### `simulate_comfyui_save_workflow(env, name, workflow_data)`

**Purpose:** Mimics ComfyUI saving a workflow file

**Usage:**
```python
workflow_data = load_workflow_fixture(workflow_fixtures, "simple_txt2img")
simulate_comfyui_save_workflow(test_env, "my_workflow", workflow_data)

# Workflow now exists where ComfyUI would save it
path = test_env.comfyui_path / "user/default/workflows/my_workflow.json"
assert path.exists()
```

**What It Does:**
- Writes workflow JSON to ComfyUI's workflow directory
- Exactly mimics what real ComfyUI does (just file I/O)
- No mocking, no simulation - real file operations

---

#### `load_workflow_fixture(fixtures_dir, name)`

**Purpose:** Loads workflow JSON from fixtures

**Usage:**
```python
workflow = load_workflow_fixture(workflow_fixtures, "simple_txt2img")
# Returns: dict with workflow structure
```

**Returns:** Python dict of workflow JSON

---

## Adding New Tests

### Step 1: Choose Test Type

**Integration Test** - Use when testing:
- End-to-end workflows
- Multiple components working together
- File system operations
- Git operations
- Real environment state

**Unit Test** - Use when testing:
- Single function/class
- Pure logic (no I/O)
- Mocked dependencies

### Step 2: Create Test File

**For integration tests:**
```python
# tests/integration/test_my_feature.py

import pytest
import json
from pathlib import Path

# Import helpers if needed
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from conftest import simulate_comfyui_save_workflow, load_workflow_fixture

class TestMyFeature:
    """Tests for my new feature."""

    def test_basic_functionality(self, test_env, test_models):
        """Test description."""
        # Arrange
        workflow_data = load_workflow_fixture(
            test_env.workflow_fixtures,
            "simple_txt2img"
        )

        # Act
        simulate_comfyui_save_workflow(test_env, "test", workflow_data)
        status = test_env.status()

        # Assert
        assert "test" in status.workflow.sync_status.new
```

### Step 3: Use Appropriate Fixtures

**Choose fixtures based on what you need:**

```python
# Just workspace
def test_workspace_level(test_workspace):
    # Can create environments, scan models
    pass

# Workspace + environment
def test_env_level(test_env):
    # Can test commits, status, workflows
    pass

# Workspace + environment + models
def test_with_models(test_env, test_models):
    # Can test model resolution
    pass
```

### Step 4: Follow Test Structure

```python
def test_descriptive_name(self, test_env, test_models):
    """
    Clear description of what is being tested.

    Include:
    - What behavior is expected
    - Why this test exists
    - Any known issues/limitations
    """
    # ARRANGE - Set up test data
    workflow_data = load_workflow_fixture(...)
    simulate_comfyui_save_workflow(...)

    # ACT - Execute the operation
    result = test_env.some_operation()

    # ASSERT - Verify expected behavior
    assert result.some_property == expected_value, \
        "Clear failure message explaining what went wrong"
```

---

## Common Patterns

### Pattern 1: Test Workflow Lifecycle

```python
def test_workflow_lifecycle(self, test_env, workflow_fixtures, test_models):
    """Test complete workflow from save to commit."""
    # Load fixture
    workflow = load_workflow_fixture(workflow_fixtures, "simple_txt2img")

    # Simulate ComfyUI save
    simulate_comfyui_save_workflow(test_env, "my_workflow", workflow)

    # Check status
    status = test_env.status()
    assert "my_workflow" in status.workflow.sync_status.new

    # Commit
    workflow_status = test_env.workflow_manager.get_workflow_status()
    test_env.execute_commit(workflow_status, message="Add workflow")

    # Verify committed
    cec_workflow = test_env.cec_path / "workflows/my_workflow.json"
    assert cec_workflow.exists()
```

### Pattern 2: Test State Transitions

```python
def test_state_transitions(self, test_env, workflow_fixtures, test_models):
    """Test state changes at each step."""
    # STATE 1: Initial
    status = test_env.status()
    assert status.is_synced

    # ACTION 1: Save workflow
    workflow = load_workflow_fixture(workflow_fixtures, "simple_txt2img")
    simulate_comfyui_save_workflow(test_env, "test", workflow)

    # STATE 2: After save
    status = test_env.status()
    assert not status.is_synced
    assert "test" in status.workflow.sync_status.new

    # ACTION 2: Commit
    workflow_status = test_env.workflow_manager.get_workflow_status()
    test_env.execute_commit(workflow_status, message="Commit")

    # STATE 3: After commit
    status = test_env.status()
    assert status.is_synced
    assert "test" in status.workflow.sync_status.synced
```

### Pattern 3: Test Error Conditions

```python
def test_handles_missing_model(self, test_env, workflow_fixtures, test_models):
    """Test workflow with missing model is detected."""
    # Load workflow with missing model
    workflow = load_workflow_fixture(workflow_fixtures, "with_missing_model")
    simulate_comfyui_save_workflow(test_env, "test", workflow)

    # Check status detects issue
    status = test_env.status()
    assert status.workflow.total_issues > 0

    # Check specific error
    workflow_status = status.workflow.workflows_with_issues[0]
    assert len(workflow_status.resolution.models_unresolved) > 0
```

### Pattern 4: Test Git Operations

```python
def test_git_tracking(self, test_env, workflow_fixtures, test_models):
    """Test files are tracked in git."""
    import subprocess

    workflow = load_workflow_fixture(workflow_fixtures, "simple_txt2img")
    simulate_comfyui_save_workflow(test_env, "test", workflow)

    workflow_status = test_env.workflow_manager.get_workflow_status()
    test_env.execute_commit(workflow_status, message="Add workflow")

    # Check git status
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=test_env.cec_path,
        capture_output=True,
        text=True
    )

    # Should be clean (everything committed)
    assert result.stdout.strip() == ""

    # Check file is tracked
    result = subprocess.run(
        ["git", "ls-files", "workflows/test.json"],
        cwd=test_env.cec_path,
        capture_output=True,
        text=True
    )

    assert "workflows/test.json" in result.stdout
```

---

## Best Practices

### DO ✅

**1. Use Fixtures for Common Setup**
```python
# Good - Reuse test_env fixture
def test_something(self, test_env):
    status = test_env.status()
```

**2. Assert with Clear Messages**
```python
# Good - Clear failure message
assert cec_workflow.exists(), \
    f"Workflow should be in .cec after commit. Path: {cec_workflow}"
```

**3. Test One Thing Per Test**
```python
# Good - Focused test
def test_workflow_copied_during_commit(self, test_env):
    # Test only workflow copying
    pass

def test_workflow_appears_in_status(self, test_env):
    # Test only status display
    pass
```

**4. Document Expected Failures**
```python
def test_known_bug(self, test_env):
    """
    BUG #123: This should fail until bug is fixed.

    Expected: Workflow should be copied
    Actual: Workflow not copied (bug)
    """
```

**5. Use Descriptive Variable Names**
```python
# Good
workflow_data = load_workflow_fixture(...)
cec_workflow_path = test_env.cec_path / "workflows/test.json"

# Bad
data = load_workflow_fixture(...)
path = test_env.cec_path / "workflows/test.json"
```

---

### DON'T ❌

**1. Don't Create Duplicate Fixtures**
```python
# Bad - Reinventing test_env
@pytest.fixture
def my_special_env(tmp_path):
    workspace = Workspace(...)  # Already exists as test_env!
```

**2. Don't Use Absolute Paths**
```python
# Bad - Won't work on other machines
path = Path("/Users/me/projects/comfydock/...")

# Good - Use fixture paths
path = test_env.cec_path / "workflows/test.json"
```

**3. Don't Mock Core Operations**
```python
# Bad - Defeats purpose of integration test
@patch("comfydock_core.core.environment.Environment.commit")
def test_commit(self, mock_commit, test_env):
    # Not testing real commit!
```

**4. Don't Test CLI Parsing**
```python
# Bad - Tests CLI, not business logic
result = subprocess.run(["comfydock", "commit", "-m", "test"])
assert result.returncode == 0

# Good - Tests business logic directly
test_env.execute_commit(workflow_status, message="test")
```

**5. Don't Share State Between Tests**
```python
# Bad - Mutable class variable
class TestSuite:
    shared_workflow = {}  # Tests will interfere!

    def test_1(self):
        self.shared_workflow["name"] = "test1"

    def test_2(self):
        # Might see "test1" from test_1!
        pass
```

---

## Extending Fixtures

### Adding New Workflow Fixtures

**1. Create workflow JSON:**
```bash
$ cat > tests/fixtures/workflows/my_new_workflow.json << EOF
{
  "nodes": [...],
  "metadata": {...}
}
EOF
```

**2. Use in tests:**
```python
def test_with_new_fixture(self, test_env, workflow_fixtures):
    workflow = load_workflow_fixture(workflow_fixtures, "my_new_workflow")
    simulate_comfyui_save_workflow(test_env, "test", workflow)
```

### Adding New Model Fixtures

**1. Add to `fixtures/models/test_models.json`:**
```json
{
  "filename": "my_model.safetensors",
  "path": "SDXL",
  "size_mb": 6
}
```

**2. Models are automatically created by `test_models` fixture**

### Creating New Fixtures

**Only create new fixtures if:**
- Reusable across multiple tests
- Complex setup that obscures test intent
- Expensive operation (can cache with `scope="session"`)

**Example:**
```python
# In conftest.py
@pytest.fixture
def complex_workflow_setup(test_env, test_models):
    """
    Creates a complex workflow scenario with multiple workflows.

    Use when testing multi-workflow operations.
    """
    # Setup multiple workflows
    workflows = []
    for i in range(3):
        workflow_data = {...}
        simulate_comfyui_save_workflow(test_env, f"workflow_{i}", workflow_data)
        workflows.append(f"workflow_{i}")

    return workflows
```

---

## Troubleshooting

### Tests Run Slowly

**Check:**
1. Are you accidentally cloning ComfyUI? (test_env should be fast)
2. Are you creating large files? (use 4MB stubs)
3. Are you running tests serially? (pytest can run in parallel)

**Solution:**
```bash
# Run in parallel
$ uv run pytest tests/integration/ -n auto
```

### Fixture Not Found

**Error:**
```
fixture 'test_env' not found
```

**Solution:**
- Make sure you're in the correct directory
- Check that `conftest.py` is present
- Import path might be wrong

### Model Index Errors

**Error:**
```
No models directory set
```

**Solution:**
- Make sure test uses `test_workspace` (sets up models dir)
- Check `workspace.json` has `global_model_directory` set
- Verify `test_workspace` fixture ran successfully

### Git Errors in Tests

**Error:**
```
Git command failed: nothing to commit
```

**This might be expected!** Check:
- Is the test validating a bug where files aren't copied?
- Does the test expect commit to fail?

### Workflow Not Found

**Error:**
```
FileNotFoundError: .../workflows/test.json
```

**Check:**
1. Did you call `simulate_comfyui_save_workflow()`?
2. Is the workflow name correct?
3. Are you looking in the right path?
   - Active workflows: `comfyui_path/user/default/workflows/`
   - Committed workflows: `cec_path/workflows/`

---

## Architecture Decisions

### Why Not Clone ComfyUI?

**Original Plan:**
```python
clone_comfyui(test_env.comfyui_path)  # ~30-60 seconds
```

**Problem:** Too slow for integration tests

**Solution:** Create minimal directory structure
```python
(test_env.comfyui_path / "user/default/workflows").mkdir(parents=True)
```

**Result:** 10x faster (7.6s vs 60s for full suite)

### Why Function-Scoped Fixtures?

**Decision:** All fixtures use `scope="function"` (default)

**Rationale:**
- Complete isolation between tests
- No shared state
- Tests can run in any order
- Easier to debug (each test is independent)

**Trade-off:** Slightly slower (but still fast with optimizations)

### Why Real File Operations?

**Decision:** Use real file I/O, not mocks

**Rationale:**
- Tests actual behavior
- Catches real errors (permissions, paths, etc.)
- More confidence in test results
- Integration tests should test integration!

**Trade-off:** Slightly slower than mocked tests (but worth it)

---

## Quick Reference

### Running Tests

```bash
# All integration tests
$ uv run pytest tests/integration/ -v

# Specific test file
$ uv run pytest tests/integration/test_workflow_commit_flow.py -v

# Specific test
$ uv run pytest tests/integration/test_workflow_commit_flow.py::TestWorkflowCommitFlow::test_name -v

# With detailed output
$ uv run pytest tests/integration/ -vv -s

# Stop on first failure
$ uv run pytest tests/integration/ -x

# Run in parallel
$ uv run pytest tests/integration/ -n auto
```

### Key Paths in Tests

```python
# Workspace root
test_workspace.paths.root

# Environment root
test_env.path

# ComfyUI directory
test_env.comfyui_path

# Active workflows (ComfyUI saves here)
test_env.comfyui_path / "user/default/workflows"

# .cec directory (git tracked)
test_env.cec_path

# Committed workflows
test_env.cec_path / "workflows"

# Models directory
test_workspace.workspace_config_manager.get_models_directory()
```

---

## Summary

**Test Infrastructure Provides:**
- ✅ Fast execution (~7-8s for full suite)
- ✅ Complete isolation (tmpdir per test)
- ✅ Realistic operations (real files, real git)
- ✅ Easy to extend (reusable fixtures)
- ✅ Clear patterns (documented examples)

**When Adding Tests:**
1. Choose appropriate fixtures
2. Follow AAA pattern (Arrange, Act, Assert)
3. Use clear assertions with messages
4. Document expected behavior
5. Keep tests focused and independent

**Need Help?**
- Check existing tests in `tests/integration/test_workflow_commit_flow.py`
- Review fixture implementations in `conftest.py`
- See integration testing docs in `docs/tasks/`

---

**Document Version:** 1.0
**Last Updated:** 2025-10-02
