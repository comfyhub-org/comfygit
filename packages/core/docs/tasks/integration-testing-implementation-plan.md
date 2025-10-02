# Integration Testing Implementation Plan

**Date:** 2025-10-01
**Purpose:** Build E2E test harness to reproduce workflow commit bugs and prevent regressions
**Target:** Next engineer implementing test infrastructure

## Executive Summary

Manual testing revealed critical bugs in the workflow commit flow that unit tests would never catch. We need **integration tests** that exercise the complete system just like a real user would, but without manual CLI interaction.

**Key principle:** Test through the **core library API**, not the CLI. The CLI is just a presentation layer; testing core tests the actual business logic.

## Background: The Bug Discovery

Manual testing found these issues:

1. **Workflows never copied to .cec** - Commit says success but `.cec/workflows/` stays empty
2. **Workflows hidden in status** - Only visible when they have unresolved dependencies
3. **Wrong suggested command** - Says "models resolve" instead of "workflow resolve"
4. **`is_synced` calculation wrong** - Doesn't consider workflow changes

**Test case that revealed bugs:**

```bash
# 1. Save workflow with invalid model → Shows in status ✓
cfd status
# Output: "🆕 test_default (new) - 1 unresolved models"

# 2. Fix model and save → Workflow disappears! ✗
cfd status
# Output: "✓ Clean" (no mention of workflow)

# 3. Commit says success → But .cec/workflows/ is empty! ✗
cfd commit -m "test"
# Output: "✅ Processed 1 workflow(s)"
ls .cec/workflows/
# Output: (nothing)
```

We need automated tests that catch this automatically.

## Test Architecture Overview

### Core Principles

**1. Test the API, Not the CLI**

```python
# ❌ BAD: Testing CLI (subprocess, fragile, slow)
result = subprocess.run(["comfydock", "status"], capture_output=True)
assert "new workflow" in result.stdout

# ✅ GOOD: Testing core API (same code path, fast, debuggable)
from comfydock_core.core.environment import Environment

env = Environment(test_paths)
status = env.status()
assert "test_workflow" in status.workflow.sync_status.new
```

**Why:**
- CLI just renders what core provides
- Testing core tests actual business logic
- Faster execution (no subprocess)
- Better error messages
- Can inspect internal state

**2. Isolated Test Workspaces**

Every test gets a **completely fresh workspace** in a temp directory:

```python
@pytest.fixture
def test_workspace(tmp_path):
    """Each test gets isolated workspace."""
    workspace_path = tmp_path / "test_workspace"
    workspace = Workspace.create(workspace_path)
    return workspace
```

**Benefits:**
- Tests can't interfere with each other
- No cleanup needed (pytest deletes tmp_path)
- Can run tests in parallel
- No risk to real data

**3. Simulate ComfyUI Filesystem Operations**

ComfyUI doesn't integrate with ComfyDock - it just writes JSON files. We simulate this:

```python
def simulate_comfyui_save_workflow(env: Environment, name: str, workflow_json: dict):
    """Simulate user saving workflow in ComfyUI."""
    workflows_dir = env.comfyui_path / "user" / "default" / "workflows"
    workflows_dir.mkdir(parents=True, exist_ok=True)

    workflow_file = workflows_dir / f"{name}.json"
    with open(workflow_file, 'w') as f:
        json.dump(workflow_json, f)

    return workflow_file
```

**This is realistic** because ComfyUI literally just saves JSON files - no API calls, no special logic.

**4. Fixture-Based Test Data**

Use **version-controlled test fixtures** instead of generating data:

```
packages/core/tests/fixtures/
├── workflows/
│   ├── simple_txt2img.json           # Basic workflow, no issues
│   ├── with_missing_model.json       # References non-existent model
│   ├── with_ambiguous_model.json     # Model name matches multiple files
│   ├── with_missing_node.json        # Uses uninstalled custom node
│   └── with_lora.json               # Tests LoraLoader node
├── models/
│   └── test_models.json             # Model metadata for test stubs
└── nodes/
    └── test_nodes.json              # Node metadata
```

**Benefits:**
- Reproducible (same data every run)
- Self-documenting (filename explains scenario)
- Easy to add new test cases
- Changes tracked in git

## Implementation Guide

### Step 1: Create Test Infrastructure

**File:** `packages/core/tests/conftest.py`

```python
"""Shared fixtures for integration tests."""
import json
import pytest
import shutil
from pathlib import Path

from comfydock_core.core.workspace import Workspace
from comfydock_core.core.environment import Environment

# ============================================================================
# Path Fixtures
# ============================================================================

@pytest.fixture(scope="session")
def fixtures_dir():
    """Path to test fixtures directory."""
    return Path(__file__).parent / "fixtures"

@pytest.fixture(scope="session")
def workflow_fixtures(fixtures_dir):
    """Path to workflow fixture files."""
    return fixtures_dir / "workflows"

@pytest.fixture(scope="session")
def model_fixtures(fixtures_dir):
    """Path to model fixture metadata."""
    return fixtures_dir / "models"

# ============================================================================
# Workspace & Environment Fixtures
# ============================================================================

@pytest.fixture
def test_workspace(tmp_path):
    """Create isolated workspace for each test.

    This workspace is completely isolated:
    - In temporary directory (auto-deleted after test)
    - Won't interfere with other tests
    - Won't affect user's real workspace
    """
    workspace_path = tmp_path / "comfydock_workspace"

    # Create workspace structure
    workspace = Workspace.create(workspace_path)

    # Set up models directory
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    workspace.set_models_directory(models_dir)

    yield workspace

    # Cleanup happens automatically (tmp_path deleted by pytest)

@pytest.fixture
def test_env(test_workspace):
    """Create test environment with ComfyUI installed.

    Returns an environment ready for testing:
    - ComfyUI installed
    - Git initialized
    - Ready to add nodes/workflows
    """
    env = test_workspace.create_environment(
        name="test-env",
        python_version="3.12",
        comfyui_version="latest"
    )

    return env

# ============================================================================
# Model Management Fixtures
# ============================================================================

@pytest.fixture
def test_models(test_workspace, model_fixtures):
    """Create and index test model files.

    Creates lightweight stub files with realistic hashes.
    Returns dict mapping filename -> ModelInfo.
    """
    models_dir = test_workspace.models_directory
    created_models = {}

    # Load model specs
    with open(model_fixtures / "test_models.json") as f:
        model_specs = json.load(f)

    # Create each model
    for spec in model_specs:
        model = create_test_model_file(
            models_dir=models_dir,
            filename=spec["filename"],
            relative_path=spec["path"],
            size_mb=spec.get("size_mb", 4)  # Small stub files
        )
        created_models[spec["filename"]] = model

    # Index all models
    test_workspace.sync_model_directory()

    return created_models

def create_test_model_file(models_dir: Path, filename: str, relative_path: str, size_mb: int = 4):
    """Create a stub model file with realistic hash.

    We can't use real multi-GB models in tests, so we create
    small files with deterministic content for consistent hashing.
    """
    from comfydock_core.analyzers.model_scanner import ModelScanner
    from comfydock_core.models.shared import ModelInfo

    # Create path
    model_path = models_dir / relative_path / filename
    model_path.parent.mkdir(parents=True, exist_ok=True)

    # Write deterministic content (so hash is reproducible)
    content = b"TEST_MODEL_" + filename.encode() + b"\x00" * (size_mb * 1024 * 1024)
    with open(model_path, 'wb') as f:
        f.write(content)

    # Calculate hash
    hash_info = ModelScanner.hash_file(model_path)

    return ModelInfo(
        filename=filename,
        hash=hash_info.quick_hash,
        file_size=model_path.stat().st_size,
        relative_path=relative_path,
        path=model_path
    )

# ============================================================================
# Workflow Simulation Helpers
# ============================================================================

def simulate_comfyui_save_workflow(env: Environment, name: str, workflow_data: dict):
    """Simulate ComfyUI saving a workflow to disk.

    This mimics exactly what ComfyUI does when user clicks "Save":
    - Writes JSON to ComfyUI/user/default/workflows/
    - No API calls, no special logic
    - Just a file write

    Args:
        env: Environment to save workflow in
        name: Workflow name (without .json extension)
        workflow_data: Workflow JSON dict or Path to fixture file

    Returns:
        Path to created workflow file
    """
    workflows_dir = env.comfyui_path / "user" / "default" / "workflows"
    workflows_dir.mkdir(parents=True, exist_ok=True)

    workflow_file = workflows_dir / f"{name}.json"

    # Handle both dict and Path inputs
    if isinstance(workflow_data, Path):
        shutil.copy(workflow_data, workflow_file)
    else:
        with open(workflow_file, 'w') as f:
            json.dump(workflow_data, f)

    return workflow_file

def load_workflow_fixture(workflow_fixtures: Path, name: str) -> dict:
    """Load a workflow fixture file."""
    fixture_path = workflow_fixtures / f"{name}.json"
    with open(fixture_path) as f:
        return json.load(f)

# ============================================================================
# Test Strategy Fixtures
# ============================================================================

class TestModelStrategy:
    """Model resolution strategy for tests with predefined choices.

    Instead of prompting user, automatically selects based on config.
    """

    def __init__(self, choices: dict[str, int]):
        """
        Args:
            choices: Map model_ref.filename -> candidate index
                    Example: {"sd15.safetensors": 0}  # Select first match
        """
        self.choices = choices
        self.resolutions_attempted = []

    def resolve_ambiguous_model(self, model_ref, candidates):
        self.resolutions_attempted.append(model_ref.filename)

        if model_ref.filename in self.choices:
            idx = self.choices[model_ref.filename]
            if idx < len(candidates):
                return candidates[idx]

        return None  # Skip if not configured

class TestNodeStrategy:
    """Node resolution strategy for tests with predefined choices."""

    def __init__(self, choices: dict[str, str]):
        """
        Args:
            choices: Map node_type -> package_id
                    Example: {"ImpactWildcardProcessor": "comfyui-impact-pack"}
        """
        self.choices = choices
        self.resolutions_attempted = []

    def resolve_unknown_node(self, node_type, packages):
        self.resolutions_attempted.append(node_type)

        if node_type in self.choices:
            package_id = self.choices[node_type]
            # Find matching package
            for pkg in packages:
                if pkg.package_data.id == package_id:
                    return pkg

        return None

@pytest.fixture
def auto_model_strategy():
    """Strategy that auto-selects first match for any model."""
    class AutoFirstStrategy:
        def resolve_ambiguous_model(self, model_ref, candidates):
            return candidates[0] if candidates else None

    return AutoFirstStrategy()
```

### Step 2: Create Test Fixtures

**File:** `packages/core/tests/fixtures/workflows/simple_txt2img.json`

This is the actual workflow from the bug report, with the valid model:

```json
{
  "id": "test-workflow-001",
  "revision": 0,
  "nodes": [
    {
      "id": 4,
      "type": "CheckpointLoaderSimple",
      "widgets_values": ["SD1.5/photon_v1.safetensors"]
    },
    {
      "id": 6,
      "type": "CLIPTextEncode",
      "widgets_values": ["beautiful scenery"]
    },
    {
      "id": 7,
      "type": "CLIPTextEncode",
      "widgets_values": ["text, watermark"]
    },
    {
      "id": 5,
      "type": "EmptyLatentImage",
      "widgets_values": [512, 512, 1]
    },
    {
      "id": 3,
      "type": "KSampler",
      "widgets_values": [156680208700286, "randomize", 20, 8, "euler", "normal", 1]
    },
    {
      "id": 8,
      "type": "VAEDecode"
    },
    {
      "id": 9,
      "type": "SaveImage",
      "widgets_values": ["ComfyUI"]
    }
  ],
  "links": [
    [1, 4, 0, 3, 0, "MODEL"],
    [2, 5, 0, 3, 3, "LATENT"],
    [3, 4, 1, 6, 0, "CLIP"],
    [4, 6, 0, 3, 1, "CONDITIONING"],
    [5, 4, 1, 7, 0, "CLIP"],
    [6, 7, 0, 3, 2, "CONDITIONING"],
    [7, 3, 0, 8, 0, "LATENT"],
    [8, 4, 2, 8, 1, "VAE"],
    [9, 8, 0, 9, 0, "IMAGE"]
  ]
}
```

**File:** `packages/core/tests/fixtures/workflows/with_missing_model.json`

Same workflow but with a model that doesn't exist:

```json
{
  "id": "test-workflow-002",
  "revision": 0,
  "nodes": [
    {
      "id": 4,
      "type": "CheckpointLoaderSimple",
      "widgets_values": ["v1-5-pruned-emaonly-fp16.safetensors"]
    },
    ... (rest same as simple_txt2img.json)
  ]
}
```

**File:** `packages/core/tests/fixtures/models/test_models.json`

```json
[
  {
    "filename": "photon_v1.safetensors",
    "path": "SD1.5",
    "size_mb": 4,
    "description": "Test SD1.5 model for simple workflows"
  },
  {
    "filename": "sd15_variant_a.safetensors",
    "path": "checkpoints",
    "size_mb": 4,
    "description": "First variant for ambiguity testing"
  },
  {
    "filename": "sd15_variant_a.safetensors",
    "path": "backup/checkpoints",
    "size_mb": 4,
    "description": "Second variant (same name, different path)"
  }
]
```

### Step 3: Write Integration Tests

**File:** `packages/core/tests/integration/test_workflow_commit_flow.py`

```python
"""Integration tests reproducing workflow commit bugs."""
import json
import pytest
from pathlib import Path

from tests.conftest import (
    simulate_comfyui_save_workflow,
    load_workflow_fixture,
)

class TestWorkflowCommitFlow:
    """E2E tests for complete workflow commit cycle.

    These tests reproduce the exact bugs found during manual testing.
    """

    def test_workflow_copied_to_cec_during_commit(
        self,
        test_env,
        workflow_fixtures,
        test_models
    ):
        """
        BUG #1: Workflows are never copied to .cec during commit.

        Reproduces:
        1. User saves workflow in ComfyUI
        2. User runs commit
        3. Commit says "success"
        4. But .cec/workflows/ is empty!

        This test WILL FAIL until bug is fixed.
        """
        # Setup: Load workflow fixture
        workflow_data = load_workflow_fixture(workflow_fixtures, "simple_txt2img")

        # Action 1: Simulate user saving workflow in ComfyUI
        simulate_comfyui_save_workflow(test_env, "test_workflow", workflow_data)

        # Action 2: Commit
        test_env.execute_commit(message="Add workflow")

        # Assertion: Workflow should be in .cec/workflows/
        cec_workflow = test_env.cec_path / "workflows" / "test_workflow.json"
        assert cec_workflow.exists(), \
            "BUG: Workflow was not copied to .cec during commit"

        # Verify content matches
        with open(cec_workflow) as f:
            committed_content = json.load(f)

        assert committed_content == workflow_data, \
            "Committed workflow should match original"

    def test_workflow_appears_in_status_without_issues(
        self,
        test_env,
        workflow_fixtures,
        test_models
    ):
        """
        BUG #2: Workflows only appear in status if they have issues.

        Reproduces:
        1. User saves workflow with valid model
        2. User runs status
        3. Workflow is not shown! (because is_synced=True)

        This test WILL FAIL until bug is fixed.
        """
        # Setup: Workflow with valid model (no issues)
        workflow_data = load_workflow_fixture(workflow_fixtures, "simple_txt2img")

        # Action: Simulate user saving workflow
        simulate_comfyui_save_workflow(test_env, "test_workflow", workflow_data)

        # Get status
        status = test_env.status()

        # Assertion: Workflow should appear even without issues
        assert "test_workflow" in status.workflow.sync_status.new, \
            "BUG: Workflow should appear in status even when it has no issues"

        # Assertion: Status should not be "synced" when new workflow exists
        assert not status.is_synced, \
            "BUG: is_synced should be False when new workflow exists"

    def test_git_commit_includes_workflow_files(
        self,
        test_env,
        workflow_fixtures,
        test_models
    ):
        """
        Verify that git commit actually versions workflow files.

        Related to BUG #1.
        """
        import subprocess

        # Setup
        workflow_data = load_workflow_fixture(workflow_fixtures, "simple_txt2img")
        simulate_comfyui_save_workflow(test_env, "test_workflow", workflow_data)

        # Commit
        test_env.execute_commit(message="Add workflow")

        # Check git status - should be clean (everything committed)
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=test_env.cec_path,
            capture_output=True,
            text=True
        )

        assert result.stdout.strip() == "", \
            "Git should have no uncommitted changes after commit"

        # Verify workflow is in git
        result = subprocess.run(
            ["git", "ls-files", "workflows/test_workflow.json"],
            cwd=test_env.cec_path,
            capture_output=True,
            text=True
        )

        assert "workflows/test_workflow.json" in result.stdout, \
            "Workflow should be tracked by git"

    def test_workflow_lifecycle_with_state_transitions(
        self,
        test_env,
        workflow_fixtures,
        test_models
    ):
        """
        Test complete workflow lifecycle with state verification at each step.

        This is the comprehensive test that validates the entire flow.
        """
        # STATE 1: Clean environment
        status = test_env.status()
        assert status.is_synced
        assert status.workflow.sync_status.total_count == 0

        # ACTION 1: User saves new workflow
        workflow_data = load_workflow_fixture(workflow_fixtures, "simple_txt2img")
        simulate_comfyui_save_workflow(test_env, "my_workflow", workflow_data)

        # STATE 2: New workflow detected
        status = test_env.status()
        assert not status.is_synced, "Should be out of sync after new workflow"
        assert "my_workflow" in status.workflow.sync_status.new
        assert status.workflow.sync_status.total_count == 1

        # ACTION 2: Commit
        test_env.execute_commit(message="Add workflow")

        # STATE 3: Workflow committed
        status = test_env.status()
        assert status.is_synced, "Should be in sync after commit"
        assert "my_workflow" in status.workflow.sync_status.synced
        assert (test_env.cec_path / "workflows" / "my_workflow.json").exists()

        # ACTION 3: User modifies workflow in ComfyUI
        modified_workflow = workflow_data.copy()
        modified_workflow["nodes"][6]["widgets_values"] = ["different prompt"]
        simulate_comfyui_save_workflow(test_env, "my_workflow", modified_workflow)

        # STATE 4: Modified workflow detected
        status = test_env.status()
        assert not status.is_synced, "Should be out of sync after modification"
        assert "my_workflow" in status.workflow.sync_status.modified

        # ACTION 4: Commit changes
        test_env.execute_commit(message="Update workflow")

        # STATE 5: Changes committed
        status = test_env.status()
        assert status.is_synced

        # Verify .cec has updated content
        with open(test_env.cec_path / "workflows" / "my_workflow.json") as f:
            committed = json.load(f)

        assert committed["nodes"][6]["widgets_values"] == ["different prompt"], \
            "Committed workflow should have updated content"

class TestWorkflowModelResolution:
    """Tests for model dependency resolution."""

    def test_missing_model_detected(
        self,
        test_env,
        workflow_fixtures,
        test_models
    ):
        """Workflow with missing model should be detected in analysis."""
        # Use fixture with model that doesn't exist
        workflow_data = load_workflow_fixture(workflow_fixtures, "with_missing_model")
        simulate_comfyui_save_workflow(test_env, "test", workflow_data)

        # Analyze
        status = test_env.status()

        # Should have unresolved models
        assert status.workflow.total_issues > 0
        workflow_status = status.workflow.workflows_with_issues[0]
        assert len(workflow_status.resolution.models_unresolved) > 0

        # Model should be identified correctly
        unresolved = workflow_status.resolution.models_unresolved[0]
        assert "v1-5-pruned-emaonly-fp16.safetensors" in unresolved.filename

    def test_ambiguous_model_resolution(
        self,
        test_env,
        workflow_fixtures,
        test_models
    ):
        """
        Test resolution when multiple models match the same filename.

        This requires a test strategy to make a choice.
        """
        from tests.conftest import TestModelStrategy

        # Create two models with same filename, different paths
        # (This is set up by test_models fixture based on test_models.json)

        # Workflow references "sd15_variant_a.safetensors" (ambiguous)
        workflow_data = load_workflow_fixture(workflow_fixtures, "with_ambiguous_model")
        simulate_comfyui_save_workflow(test_env, "test", workflow_data)

        # Resolve with test strategy (selects first match)
        strategy = TestModelStrategy(choices={"sd15_variant_a.safetensors": 0})
        result = test_env.resolve_workflow("test", model_strategy=strategy)

        # Verify resolution was attempted
        assert "sd15_variant_a.safetensors" in strategy.resolutions_attempted

        # Verify correct model was selected
        assert len(result.models_resolved) == 1
        assert result.models_resolved[0].relative_path == "checkpoints"

class TestWorkflowRollback:
    """Tests for workflow versioning and rollback."""

    def test_rollback_restores_workflow_content(
        self,
        test_env,
        workflow_fixtures,
        test_models
    ):
        """Rollback should restore exact workflow content from previous version."""
        # V1: Save initial version
        v1_workflow = load_workflow_fixture(workflow_fixtures, "simple_txt2img")
        simulate_comfyui_save_workflow(test_env, "test", v1_workflow)
        test_env.execute_commit(message="v1")

        # V2: Modify and commit
        v2_workflow = v1_workflow.copy()
        v2_workflow["nodes"][6]["widgets_values"] = ["modified prompt v2"]
        simulate_comfyui_save_workflow(test_env, "test", v2_workflow)
        test_env.execute_commit(message="v2")

        # Verify we're on v2
        with open(test_env.comfyui_path / "user" / "default" / "workflows" / "test.json") as f:
            current = json.load(f)
        assert current["nodes"][6]["widgets_values"] == ["modified prompt v2"]

        # Rollback to v1
        test_env.rollback("v1")

        # Verify v1 content restored
        with open(test_env.comfyui_path / "user" / "default" / "workflows" / "test.json") as f:
            restored = json.load(f)

        assert restored["nodes"][6]["widgets_values"] == v1_workflow["nodes"][6]["widgets_values"], \
            "Rollback should restore exact v1 content"

    def test_commit_creates_retrievable_version(
        self,
        test_env,
        workflow_fixtures,
        test_models
    ):
        """Each commit should create a new version in git history."""
        # Get initial version count
        initial_versions = test_env.get_versions()
        initial_count = len(initial_versions)

        # Make change and commit
        workflow = load_workflow_fixture(workflow_fixtures, "simple_txt2img")
        simulate_comfyui_save_workflow(test_env, "test", workflow)
        test_env.execute_commit(message="Add workflow")

        # Verify new version exists
        versions = test_env.get_versions()
        assert len(versions) == initial_count + 1
        assert versions[-1]['message'] == "Add workflow"
        assert versions[-1]['version'] == f"v{initial_count + 1}"
```

### Step 4: Run and Validate Tests

**Command to run tests:**

```bash
# Run all integration tests
pytest packages/core/tests/integration/ -v

# Run specific test
pytest packages/core/tests/integration/test_workflow_commit_flow.py::TestWorkflowCommitFlow::test_workflow_copied_to_cec_during_commit -v

# Run with detailed output
pytest packages/core/tests/integration/ -vv -s

# Run tests that should fail (verify they catch bugs)
pytest packages/core/tests/integration/ -v --tb=short
```

**Expected results BEFORE fixes:**

```
FAILED test_workflow_commit_flow.py::test_workflow_copied_to_cec_during_commit
  AssertionError: BUG: Workflow was not copied to .cec during commit

FAILED test_workflow_commit_flow.py::test_workflow_appears_in_status_without_issues
  AssertionError: BUG: Workflow should appear in status even when it has no issues

PASSED test_workflow_commit_flow.py::test_git_commit_includes_workflow_files
  (Should pass once first test passes)
```

**Expected results AFTER fixes:**

```
PASSED test_workflow_commit_flow.py::test_workflow_copied_to_cec_during_commit
PASSED test_workflow_commit_flow.py::test_workflow_appears_in_status_without_issues
PASSED test_workflow_commit_flow.py::test_git_commit_includes_workflow_files
PASSED test_workflow_commit_flow.py::test_workflow_lifecycle_with_state_transitions
```

## Key Implementation Details

### Simulating ComfyUI Behavior

ComfyUI's workflow save operation is **very simple**:

1. User clicks "Save" in browser
2. Frontend sends JSON to backend
3. Backend writes to: `ComfyUI/user/default/workflows/{name}.json`

That's it. No API calls to ComfyDock, no special hooks.

**Our simulation:**

```python
def simulate_comfyui_save_workflow(env, name, workflow_data):
    # Exactly what ComfyUI does:
    path = env.comfyui_path / "user" / "default" / "workflows" / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w') as f:
        json.dump(workflow_data, f)
```

This is realistic because:
- Same file location
- Same JSON format
- Same filesystem operation
- No special ComfyDock integration needed

### Creating Test Models

Real models are 2-8GB. We can't commit those to git. Instead:

**Create stub files with realistic hashes:**

```python
def create_test_model_file(models_dir, filename, relative_path, size_mb=4):
    path = models_dir / relative_path / filename
    path.parent.mkdir(parents=True, exist_ok=True)

    # Deterministic content for reproducible hash
    content = b"TEST_MODEL_" + filename.encode() + b"\x00" * (size_mb * 1024 * 1024)
    with open(path, 'wb') as f:
        f.write(content)

    # Calculate hash (same code as production)
    hash_info = ModelScanner.hash_file(path)

    return ModelInfo(
        filename=filename,
        hash=hash_info.quick_hash,
        file_size=path.stat().st_size,
        ...
    )
```

**Benefits:**
- Small files (4MB vs 4GB)
- Deterministic hashes (same content every time)
- Real hashing code (not mocked)
- Fast to create and index

### Test Strategies for Interactive Resolution

Production uses `InteractiveModelStrategy` that prompts the user. Tests can't prompt.

**Solution: Inject test strategy**

```python
class TestModelStrategy:
    """Auto-selects models based on configuration."""

    def __init__(self, choices: dict[str, int]):
        self.choices = choices  # filename -> index

    def resolve_ambiguous_model(self, model_ref, candidates):
        if model_ref.filename in self.choices:
            idx = self.choices[model_ref.filename]
            return candidates[idx]
        return None

# In test:
strategy = TestModelStrategy(choices={
    "sd15.safetensors": 0,  # Select first match
    "lora_v1.safetensors": 1,  # Select second match
})

result = env.resolve_workflow("test", model_strategy=strategy)
```

This tests the exact same code path as production, just with automated choices.

## Test Coverage Goals

### Must Have (Blocks Release):

- ✅ Workflow copying during commit
- ✅ Workflow visibility in status
- ✅ Git versioning of workflows
- ✅ Rollback restores workflows
- ✅ Model resolution (missing, ambiguous)

### Should Have (Before 1.0):

- ✅ Node resolution (missing custom nodes)
- ✅ Complete lifecycle (save → commit → modify → commit → rollback)
- ✅ Multiple workflow handling
- ✅ Workflow deletion detection

### Nice to Have (Post-MVP):

- Edge cases (corrupt JSON, permission errors)
- Performance (100+ workflows)
- Concurrent operations

## Running Tests in CI/CD

**GitHub Actions example:**

```yaml
name: Integration Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v3

    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.12'

    - name: Install dependencies
      run: |
        pip install -e packages/core[test]

    - name: Run integration tests
      run: |
        pytest packages/core/tests/integration/ -v --tb=short
```

## Debugging Failed Tests

When a test fails:

**1. Check the temp directory:**

```python
# Add to test
def test_something(test_env, tmp_path):
    print(f"Test workspace: {tmp_path}")
    # ... test code

    # On failure, manually inspect:
    # ls -la {tmp_path}/comfydock_workspace/environments/test-env/
```

**2. Enable debug logging:**

```python
import logging
logging.basicConfig(level=logging.DEBUG)

def test_something(test_env):
    # Now see all log output
```

**3. Use pytest debugger:**

```bash
# Drop into debugger on failure
pytest tests/integration/ -v --pdb

# Drop into debugger on first failure, then stop
pytest tests/integration/ -v -x --pdb
```

## Maintenance and Evolution

### Adding New Test Cases

**To add a test for a new bug:**

1. Create workflow fixture that reproduces it
2. Write test that asserts expected behavior
3. Verify test fails (proves it catches the bug)
4. Fix the bug
5. Verify test passes

**Example:**

```python
# New bug: Workflows with LoRA nodes not analyzed correctly

# 1. Create fixture
# packages/core/tests/fixtures/workflows/with_lora.json

# 2. Write test
def test_lora_models_detected(test_env, workflow_fixtures):
    workflow = load_workflow_fixture(workflow_fixtures, "with_lora")
    simulate_comfyui_save_workflow(test_env, "test", workflow)

    status = test_env.status()
    # Assert LoRA model is in dependencies
    ...

# 3. Run test - should fail
# 4. Fix analysis code
# 5. Run test - should pass
```

### Keeping Fixtures Realistic

Periodically update fixtures from real workflows:

```bash
# Export real workflow to fixture
cp ~/.comfydock/environments/prod/ComfyUI/user/default/workflows/my_workflow.json \
   packages/core/tests/fixtures/workflows/real_world_example.json

# Sanitize (remove sensitive data, simplify)
# Use in tests
```

## Common Pitfalls to Avoid

### ❌ Don't Mock Core Business Logic

```python
# BAD: Mocking defeats the purpose
@patch('comfydock_core.managers.workflow_manager.WorkflowManager.copy_all_workflows')
def test_commit(mock_copy):
    # This doesn't test if copying actually works!
```

```python
# GOOD: Test the real thing
def test_commit(test_env):
    # Actually calls copy_all_workflows
    test_env.execute_commit(...)
    # Actually checks files exist
    assert (test_env.cec_path / "workflows" / "test.json").exists()
```

### ❌ Don't Use Real User Workspaces

```python
# BAD: Dangerous!
def test_something():
    workspace = Workspace(Path.home() / ".comfydock")
    # Could corrupt user data!
```

```python
# GOOD: Isolated
def test_something(test_workspace):
    # test_workspace is in tmp_path, auto-deleted
```

### ❌ Don't Hardcode Paths

```python
# BAD: Brittle
def test_something():
    workflow = "/home/user/test.json"
```

```python
# GOOD: Fixtures
def test_something(workflow_fixtures):
    workflow = workflow_fixtures / "test.json"
```

## Success Criteria

Tests are successful when:

1. **All bugs caught:** Tests fail on current buggy code
2. **All bugs fixed:** Tests pass after fixes
3. **Fast execution:** Full suite runs in < 30 seconds
4. **Easy to debug:** Clear assertion messages, inspectable state
5. **Easy to extend:** Adding new test takes < 30 minutes
6. **CI/CD ready:** Tests run in GitHub Actions without manual setup

## Next Steps for Implementation

**Week 1: Infrastructure**
1. Create `conftest.py` with fixtures
2. Create test model/workflow fixtures
3. Verify isolated workspace creation works

**Week 2: Core Tests**
1. Implement `test_workflow_copied_to_cec_during_commit`
2. Implement `test_workflow_appears_in_status_without_issues`
3. Verify tests fail (catch bugs)

**Week 3: Bug Fixes**
1. Fix workflow copying in core
2. Fix status display logic
3. Verify tests pass

**Week 4: Comprehensive Coverage**
1. Add lifecycle tests
2. Add rollback tests
3. Add resolution tests
4. Add to CI/CD

---

**End of Implementation Plan**

This plan provides everything needed to build a robust integration test suite that:
- Catches the bugs found manually
- Prevents regressions
- Is maintainable and extensible
- Tests real behavior, not mocks
- Runs fast and reliably

The next engineer should be able to follow this plan and have working integration tests within 2-3 weeks.
