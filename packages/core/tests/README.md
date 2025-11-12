# ComfyGit Core Testing Infrastructure

Testing architecture reference for comfygit-core integration tests.

## Overview

**Goals:** Fast (~7s full suite), isolated (tmpdir per test), realistic (real file ops), simple (minimal setup)

**Test Types:**
```
tests/
├── unit/           # Fast, isolated, mocked
├── integration/    # Realistic end-to-end
└── fixtures/       # Shared test data
```

**Design Philosophy:** Test through Core API, not CLI. Use `test_env.execute_commit()` directly rather than subprocess CLI calls for faster execution, better errors, and testing actual business logic.

## Fixture Hierarchy

```
test_workspace → test_env → test_models → YOUR TEST
```

- **`test_workspace`**: Workspace with config, models directory, metadata
- **`test_env`**: Environment with minimal ComfyUI structure (no clone!), git repo in `.cec/`
- **`test_models`**: Creates/indexes 4MB stub model files from `fixtures/models/test_models.json`

Fixtures are **function-scoped** for complete test isolation.

## Core Fixtures

### `test_workspace`
Creates isolated workspace with WorkspaceFactory initialization, configured models directory, metadata files, clean git state.

```python
def test_something(test_workspace):
    assert test_workspace.paths.root.exists()
    env = test_workspace.create_environment("my-env")
```

**Structure:**
```
{tmp}/comfygit_workspace/
├── .metadata/workspace.json
├── environments/
├── comfygit_cache/
└── models/
```

### `test_env`
Creates minimal environment without cloning ComfyUI (10x faster: 7.6s vs 60s).

```python
def test_something(test_env):
    assert test_env.comfyui_path.exists()
    status = test_env.status()
```

**Structure:**
```
environments/test-env/
├── .cec/
│   ├── .git/
│   ├── pyproject.toml
│   └── workflows/              # Committed workflows
└── ComfyUI/
    └── user/default/workflows/ # Active workflows (ComfyUI saves)
```

### `test_models`
Creates indexed model stubs. Returns dict with model metadata.

```python
def test_something(test_env, test_models):
    assert "photon_v1.safetensors" in test_models
    model = test_models["photon_v1.safetensors"]
```

### `workflow_fixtures` / `model_fixtures`
Path references to `fixtures/workflows/` and `fixtures/models/`.

**Available workflows:**
- `simple_txt2img.json` - Valid workflow
- `with_missing_model.json` - Missing model scenario

## Helper Functions

### `simulate_comfyui_save_workflow(env, name, workflow_data)`
Mimics ComfyUI saving workflow JSON (real file I/O, no mocks).

```python
workflow = load_workflow_fixture(workflow_fixtures, "simple_txt2img")
simulate_comfyui_save_workflow(test_env, "my_workflow", workflow)
```

### `load_workflow_fixture(fixtures_dir, name)`
Loads workflow JSON from fixtures as dict.

## Helper Libraries

Fluent builders and assertions for workflow resolution testing (located in `tests/helpers/`).

### ModelIndexBuilder

Fluent builder for populating model index with test data.

```python
from helpers.model_index_builder import ModelIndexBuilder

builder = ModelIndexBuilder(test_workspace)

# Add models
builder.add_model(
    filename="sd15.safetensors",
    relative_path="checkpoints",
    size_mb=4,
    category="checkpoints"  # Optional
)

# Index all at once
models = builder.index_all()

# Get hash for assertions
hash = builder.get_hash("sd15.safetensors")
```

**Key methods:**
- `add_model(filename, relative_path, size_mb=4, category=None)` - Add model file with deterministic hash
- `index_all()` - Scan and index all added models
- `get_hash(filename)` - Retrieve hash for a created model

### WorkflowBuilder

Fluent builder for ComfyUI workflow JSON.

```python
from helpers.workflow_builder import WorkflowBuilder, make_minimal_workflow

# Full builder API
workflow = (
    WorkflowBuilder()
    .add_checkpoint_loader("model.safetensors")
    .add_lora_loader("style.safetensors", strength=0.8)
    .add_custom_node("MyCustomNode", widgets=["value1", "value2"])
    .add_builtin_node("KSampler", widgets=[123, "fixed", 20, 8.0])
    .build()
)

# Quick helper for simple cases
workflow = make_minimal_workflow(
    checkpoint_file="sd15.safetensors",
    custom_node_type="MyNode"  # Optional
)
```

**Key methods:**
- `add_checkpoint_loader(checkpoint_file)` - Add CheckpointLoaderSimple node
- `add_lora_loader(lora_file, strength=1.0)` - Add LoraLoader node
- `add_custom_node(node_type, widgets=None)` - Add custom node
- `add_builtin_node(node_type, widgets=None)` - Add builtin ComfyUI node
- `build()` - Build final workflow JSON dict

### PyprojectAssertions

Fluent assertions for validating pyproject.toml state after resolution.

```python
from helpers.pyproject_assertions import PyprojectAssertions

assertions = PyprojectAssertions(test_env)

# Workflow assertions
(
    assertions
    .has_workflow("my_workflow")
    .has_model_count(2)
    .has_node_count(1)
    .has_node("comfyui-custom-node")
)

# Model assertions (chained)
(
    assertions
    .has_workflow("my_workflow")
    .has_model_with_filename("sd15.safetensors")
    .has_status("resolved")
    .has_criticality("flexible")
    .has_category("checkpoints")
    .and_workflow()  # Return to workflow level
    .has_model_with_filename("lora.safetensors")
    .has_status("unresolved")
)

# Global models table
(
    assertions
    .has_global_model("abc123...")
    .has_filename("sd15.safetensors")
    .has_relative_path("checkpoints/sd15.safetensors")
    .has_category("checkpoints")
)
```

**Workflow assertions:**
- `has_workflow(name)` - Assert workflow exists
- `has_model_count(expected)` - Assert number of models
- `has_node_count(expected)` - Assert number of node packages
- `has_node(package_id)` - Assert node package exists
- `has_model_with_hash(hash)` - Assert model with hash exists
- `has_model_with_filename(filename)` - Assert model exists and chain to model assertions

**Model assertions:**
- `has_status(expected)` - Assert model status (resolved/unresolved)
- `has_criticality(expected)` - Assert criticality (required/flexible/optional)
- `has_category(expected)` - Assert category (checkpoints/loras/etc)
- `has_no_sources()` - Assert model has no sources (cleaned after download)
- `has_no_relative_path()` - Assert model has no relative_path (cleaned after download)
- `and_workflow()` - Return to workflow-level assertions

**Global model assertions:**
- `has_global_model(hash)` - Assert model in global table
- `has_filename(expected)` - Assert filename
- `has_relative_path(expected)` - Assert relative path
- `has_category(expected)` - Assert category
- `has_source(expected_url)` - Assert model has specific source URL

### Helper Design Philosophy

1. **Fluent/Chainable**: All methods return `self` or context objects for chaining
2. **Self-Documenting**: Method names clearly state what they verify
3. **Fail Fast**: Assertions fail immediately with clear error messages
4. **Minimal Boilerplate**: Builders handle tedious JSON construction
5. **Type-Safe**: Uses actual hash from resolution, not hardcoded values

## Adding Tests

**Choose fixtures by need:**
```python
def test_workspace_level(test_workspace):      # Create envs, scan models
def test_env_level(test_env):                  # Test commits, status
def test_with_models(test_env, test_models):   # Test model resolution
```

**Test structure (AAA pattern):**
```python
def test_descriptive_name(self, test_env, test_models):
    """Clear description of behavior being tested."""
    # ARRANGE
    workflow = load_workflow_fixture(workflow_fixtures, "simple_txt2img")
    simulate_comfyui_save_workflow(test_env, "test", workflow)

    # ACT
    result = test_env.some_operation()

    # ASSERT
    assert result.property == expected, "Clear failure message"
```

## Common Patterns

**Workflow Lifecycle:**
```python
workflow = load_workflow_fixture(workflow_fixtures, "simple_txt2img")
simulate_comfyui_save_workflow(test_env, "my_wf", workflow)
status = test_env.status()
assert "my_wf" in status.workflow.sync_status.new

workflow_status = test_env.workflow_manager.get_workflow_status()
test_env.execute_commit(workflow_status, message="Add workflow")
assert (test_env.cec_path / "workflows/my_wf.json").exists()
```

**State Transitions:**
```python
# Initial state
status = test_env.status()
assert status.is_synced

# After workflow save
simulate_comfyui_save_workflow(test_env, "test", workflow)
status = test_env.status()
assert not status.is_synced
assert "test" in status.workflow.sync_status.new

# After commit
test_env.execute_commit(workflow_status, message="Commit")
status = test_env.status()
assert status.is_synced
```

**Error Conditions:**
```python
workflow = load_workflow_fixture(workflow_fixtures, "with_missing_model")
simulate_comfyui_save_workflow(test_env, "test", workflow)
status = test_env.status()
assert status.workflow.total_issues > 0
assert len(status.workflow.workflows_with_issues[0].resolution.models_unresolved) > 0
```

## Best Practices

**DO:**
- ✅ Use fixtures for common setup
- ✅ Assert with clear messages: `assert path.exists(), f"Expected {path}"`
- ✅ Test one thing per test
- ✅ Document expected failures with BUG references
- ✅ Use descriptive variable names

**DON'T:**
- ❌ Create duplicate fixtures (use existing `test_env`)
- ❌ Use absolute paths (use fixture paths)
- ❌ Mock core operations in integration tests
- ❌ Test CLI parsing (test business logic directly)
- ❌ Share state between tests (use function-scoped fixtures)

## Extending Fixtures

**Add workflow fixture:**
```bash
$ cat > tests/fixtures/workflows/my_workflow.json
```
Use with: `load_workflow_fixture(workflow_fixtures, "my_workflow")`

**Add model fixture:**
Add to `fixtures/models/test_models.json`, automatically created by `test_models` fixture.

**Create new fixture:**
Only if reusable across tests, complex setup, or expensive operation. Mark expensive ops with `scope="session"`.

## Quick Reference

**Running Tests:**
```bash
uv run pytest tests/integration/ -v              # All tests
uv run pytest tests/integration/test_file.py -v  # Specific file
uv run pytest path::TestClass::test_name -v      # Specific test
uv run pytest tests/integration/ -x              # Stop on failure
```

**Key Paths:**
```python
test_workspace.paths.root
test_env.path
test_env.comfyui_path
test_env.comfyui_path / "user/default/workflows"  # Active workflows
test_env.cec_path                                  # .cec directory
test_env.cec_path / "workflows"                    # Committed workflows
```

## Architecture Rationale

- **No ComfyUI clone:** Create directory structure only (10x faster)
- **Function-scoped fixtures:** Complete isolation, no shared state
- **Real file operations:** Tests actual behavior, catches real errors
