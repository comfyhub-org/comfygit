# Missing Model Resolution Tests

## Overview

Tests for the content-addressable model resolution system. These tests document the expected behavior using TDD (Test-Driven Development) approach.

**Current Status:** 8 failed, 2 passed (as expected - features not yet implemented)

## Design Principles

The tests verify the **content-addressable, hash-based** model resolution system:

1. **Workflow JSON files are NEVER modified** during local resolution
2. Models mapped via hash in `pyproject.toml`
3. Fuzzy search against existing model index (no arbitrary file indexing)
4. Original workflow references preserved for shareability
5. Workflow JSON only rewritten during import (future feature)

## Test Structure

### ✅ TestFuzzySearchResolution (3 tests) - PRIMARY MVP FEATURE
Core fuzzy search functionality for finding similar models.

**Tests:**
- `test_fuzzy_search_finds_similar_models` - Similarity scoring works
- `test_user_selects_from_fuzzy_results` - User can select from results
- `test_pyproject_mapping_created_after_selection` - Creates hash mapping in pyproject

**What needs implementation:**
- `WorkflowManager.find_similar_models()` method
- Uses `ModelConfig` for node-type → directory mappings
- Python's `difflib.SequenceMatcher` for scoring
- Returns scored matches from model index

### ✅ TestManualPathResolution (2 tests)
Manual path entry as fallback option.

**Tests:**
- `test_manual_path_finds_model_in_index` - User enters valid path
- `test_manual_path_not_in_index_stays_unresolved` - Invalid path handled gracefully (PASSES)

**What needs implementation:**
- Handle `("select", "path/to/model.safetensors")` return value
- Lookup model in index by path
- Create mapping if found

### ✅ TestResolutionSkip (1 test)
Skip/cancel behavior.

**Tests:**
- `test_skip_resolution` - User returns `None` to skip (PASSES)

**Status:** Already works correctly

### ✅ TestResolutionPersistence (2 tests) - CRITICAL
Ensures resolutions survive status re-runs (prevents infinite loops).

**Tests:**
- `test_resolution_survives_status_rerun` - Mapping persists in pyproject
- `test_model_deleted_after_resolution_detected` - Detects stale mappings

**What needs implementation:**
- Analysis checks pyproject mappings BEFORE searching index
- Verifies mapped models still exist
- Auto-resolves when mapping found

### ✅ TestPartialResolutions (1 test)
Multiple missing models, some resolved, some skipped.

**Tests:**
- `test_partial_resolution_saves_individually` - Incremental saving

**What needs implementation:**
- Each resolution saved to pyproject immediately
- Re-running only prompts for unresolved models

### ✅ TestMultipleWorkflowsSameModel (1 test)
Content-addressable deduplication.

**Tests:**
- `test_same_model_hash_stored_once` - Same model hash = single registry entry

**What needs implementation:**
- Model registry keyed by hash (not path)
- Multiple workflow mappings can reference same hash
- Deduplication happens automatically

## Running Tests

```bash
# All resolution tests
uv run pytest tests/integration/test_missing_model_resolution.py -v

# Specific test class
uv run pytest tests/integration/test_missing_model_resolution.py::TestFuzzySearchResolution -v

# Single test
uv run pytest tests/integration/test_missing_model_resolution.py::TestFuzzySearchResolution::test_fuzzy_search_finds_similar_models -v

# Watch mode (re-run on file changes)
uv run pytest tests/integration/test_missing_model_resolution.py -v --looponfail
```

## Implementation Order

### Phase 1: Core Fuzzy Search (Highest Priority)
1. Add `find_similar_models()` to `WorkflowManager`
2. Use `ModelConfig` for node-type mappings
3. Implement `difflib` similarity scoring
4. Tests to pass: `TestFuzzySearchResolution` (3 tests)

### Phase 2: Strategy Integration
1. Update `fix_resolution()` to handle `("select", path)` return value
2. Lookup model in index by path
3. Create hash mappings in pyproject
4. Tests to pass: `TestManualPathResolution`, `TestFuzzySearchResolution` (5 tests total)

### Phase 3: Persistence
1. Update analysis to check pyproject first
2. Add `_add_workflow_model_mapping()` helper
3. Update `apply_resolution()` to save mappings
4. Tests to pass: `TestResolutionPersistence`, `TestPartialResolutions` (9 tests total)

### Phase 4: Deduplication
1. Ensure model registry uses hash as key
2. Multiple workflows can reference same hash
3. Tests to pass: `TestMultipleWorkflowsSameModel` (ALL 10 tests)

## Success Criteria

All 10 tests pass:
```
tests/integration/test_missing_model_resolution.py::TestFuzzySearchResolution::test_fuzzy_search_finds_similar_models PASSED
tests/integration/test_missing_model_resolution.py::TestFuzzySearchResolution::test_user_selects_from_fuzzy_results PASSED
tests/integration/test_missing_model_resolution.py::TestFuzzySearchResolution::test_pyproject_mapping_created_after_selection PASSED
tests/integration/test_missing_model_resolution.py::TestManualPathResolution::test_manual_path_finds_model_in_index PASSED
tests/integration/test_missing_model_resolution.py::TestManualPathResolution::test_manual_path_not_in_index_stays_unresolved PASSED
tests/integration/test_missing_model_resolution.py::TestResolutionSkip::test_skip_resolution PASSED
tests/integration/test_missing_model_resolution.py::TestResolutionPersistence::test_resolution_survives_status_rerun PASSED
tests/integration/test_missing_model_resolution.py::TestResolutionPersistence::test_model_deleted_after_resolution_detected PASSED
tests/integration/test_missing_model_resolution.py::TestPartialResolutions::test_partial_resolution_saves_individually PASSED
tests/integration/test_missing_model_resolution.py::TestMultipleWorkflowsSameModel::test_same_model_hash_stored_once PASSED

========================= 10 passed in ~2s =========================
```

## Key Design Points

### Strategy Return Values

The `ModelResolutionStrategy.handle_missing_model()` return value protocol:

| Return Value | Meaning | Action |
|--------------|---------|--------|
| `None` | Skip | Model stays unresolved |
| `("select", "path")` | User selected model from index | Create hash mapping |

### pyproject.toml Schema

```toml
[tool.comfydock.models.required]
# Universal model registry - keyed by hash
"48835672f5450d120..." = {
  filename = "photon_v1.safetensors",
  size = 4194336,
  relative_path = "SD1.5/photon_v1.safetensors"
}

[tool.comfydock.workflows.my_workflow.models]
# Workflow mappings - original ref → hash
"sd15-missing.safetensors" = {
  hash = "48835672f5450d120...",
  nodes = [
    {node_id = "1", widget_idx = 0}
  ]
}
```

### Why Workflow JSON Stays Unchanged

During local resolution:
- ✅ Mapping saved to pyproject.toml
- ✅ Hash used as universal identifier
- ✅ Workflow JSON preserved
- ✅ Workflows remain shareable without local paths

During import (future):
- Workflow JSON IS rewritten to use local paths
- Hash mappings guide path rewrites
- Recipients map hashes to their local files

## Related Documents

- `/docs/prd.md` - Full system specification
- `/docs/tasks/missing-model-resolution-implementation.md` - Detailed implementation plan
- `/tests/README.md` - General testing infrastructure
