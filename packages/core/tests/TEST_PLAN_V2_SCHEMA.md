# Test Plan for v2.0 Schema Migration

## Overview

This document describes the test suite for the global node mappings schema v2.0 migration.
All tests are written to **FAIL** with the current v1.0 implementation and **PASS** after implementing v2.0 changes.

## Key Changes Being Tested

### 1. Data Model Changes
- `GlobalNodeMapping`: Single `package_id` → List of `PackageMapping` objects
- `PackageMapping`: New dataclass with `package_id`, `versions`, `rank`, `source`
- `GlobalNodeMappingsStats`: Rename `synthetic_packages` → `manager_packages`
- `GlobalNodePackage`: Add optional `icon` field

### 2. Resolution Logic Changes
- Return **all ranked packages** from registry mappings (not just one)
- Auto-select based on installed packages + rank priority
- Configurable auto-selection via `auto_select_ambiguous` setting
- Distinguish registry multi-package from fuzzy search results

### 3. Behavioral Changes
- **Q1 Answer**: Check installed nodes first, then fall back to rank 1
- **Q2 Answer**: Single selected package goes to `nodes_resolved`, multiple go to `nodes_ambiguous` (if auto-select disabled)
- **Q3 Answer**: Rank information preserved for CLI display

## Test Files

### Unit Tests: `tests/unit/resolvers/test_global_node_resolver_v2.py`

**Class: TestSchemaV2Loading**
- ✅ `test_load_single_package_mapping`: Single package (backward compatible)
- ✅ `test_load_multi_package_mapping_with_ranking`: Multiple ranked packages (NEW)

**Class: TestResolutionWithRanking**
- ✅ `test_resolve_exact_match_returns_all_ranked_packages`: Returns all packages sorted by rank
- ✅ `test_resolve_type_only_match_returns_ranked_packages`: Type-only also returns ranked list

**Class: TestAutoSelectionLogic**
- ✅ `test_auto_select_installed_over_higher_rank`: Rank 2 installed → auto-select rank 2 (NOT rank 1)
- ✅ `test_auto_select_rank_1_when_none_installed`: No installed → auto-select rank 1
- ✅ `test_return_all_when_auto_select_disabled`: Config flag disables auto-selection

**Class: TestRankFieldPersistence**
- ✅ `test_resolved_package_includes_rank`: Rank flows through to ResolvedNodePackage

**Class: TestManagerSourceHandling**
- ✅ `test_manager_package_loaded_correctly`: Manager packages have `source='manager'`
- ✅ `test_registry_package_has_no_source_field`: Registry packages omit source field

**Class: TestBackwardCompatibility**
- ✅ `test_single_package_behaves_like_v1`: Single package mapping resolves cleanly
- ✅ `test_empty_packages_list_returns_none`: Empty list = not found

### Integration Tests: `tests/integration/test_workflow_resolve_v2_schema.py`

**Class: TestRegistryMultiPackageResolution**
- ✅ `test_auto_select_installed_package_over_rank_1`: Full workflow resolution with installed check
- ✅ `test_auto_select_rank_1_when_none_installed`: Default to rank 1
- ✅ `test_multiple_installed_picks_highest_rank`: Multiple installed → pick best rank

**Class: TestAutoSelectConfiguration**
- ✅ `test_auto_select_disabled_returns_all_packages`: Config disables auto-select
- ✅ `test_auto_select_enabled_by_default`: Default behavior

**Class: TestRegistryVsFuzzySearchAmbiguity**
- ✅ `test_registry_multi_package_not_treated_as_fuzzy`: Registry multi != fuzzy search

**Class: TestManagerPackageHandling**
- ✅ `test_manager_package_in_multi_package_mapping`: Manager packages work with ranking

**Class: TestRankInformation**
- ✅ `test_rank_displayed_in_resolution_result`: Rank accessible for CLI display

**Class: TestSinglePackageBehavior**
- ✅ `test_single_package_cleanly_resolves`: Backward compatibility

### Updated Tests: `tests/integration/test_ambiguous_node_mapping_persistence.py`

- ✅ Updated to use v2.0 schema (array of packages)
- ✅ Added `auto_select_ambiguous=False` to test ambiguous behavior
- ✅ Tests user selection persistence

## Running the Tests

### Run All v2.0 Schema Tests
```bash
uv run pytest packages/core/tests/unit/resolvers/test_global_node_resolver_v2.py -v
uv run pytest packages/core/tests/integration/test_workflow_resolve_v2_schema.py -v
```

### Run Specific Test Classes
```bash
# Unit tests for loading
uv run pytest packages/core/tests/unit/resolvers/test_global_node_resolver_v2.py::TestSchemaV2Loading -v

# Unit tests for auto-selection
uv run pytest packages/core/tests/unit/resolvers/test_global_node_resolver_v2.py::TestAutoSelectionLogic -v

# Integration tests for workflow resolution
uv run pytest packages/core/tests/integration/test_workflow_resolve_v2_schema.py::TestRegistryMultiPackageResolution -v
```

### Expected Results

**Before Implementation (Current State)**:
```
FAILED test_load_single_package_mapping - AttributeError: 'dict' object has no attribute 'packages'
FAILED test_resolve_exact_match_returns_all_ranked_packages - AssertionError: assert 1 == 2
...
```

**After Implementation**:
```
PASSED test_load_single_package_mapping
PASSED test_resolve_exact_match_returns_all_ranked_packages
...
```

## Implementation Checklist

### Phase 1: Data Models (node_mapping.py)
- [ ] Add `PackageMapping` dataclass
- [ ] Change `GlobalNodeMapping.package_id` → `packages: list[PackageMapping]`
- [ ] Rename `synthetic_packages` → `manager_packages` in stats
- [ ] Add `icon` field to `GlobalNodePackage`

### Phase 2: Resolution Logic (global_node_resolver.py)
- [ ] Update `_load_mappings()` to parse package arrays
- [ ] Update `resolve_single_node_from_mapping()` to return all ranked packages
- [ ] Implement auto-select logic in `resolve_single_node_with_context()`
- [ ] Add installed package priority check
- [ ] Add `auto_select_ambiguous` configuration support

### Phase 3: Workflow Manager (workflow_manager.py)
- [ ] Add `rank` field to `ResolvedNodePackage` model
- [ ] Update `resolve_workflow()` disambiguation logic
- [ ] Read `auto_select_ambiguous` from pyproject config
- [ ] Pass config to resolution context

### Phase 4: Configuration
- [ ] Add `auto_select_ambiguous` to pyproject schema
- [ ] Default to `True` (enabled)
- [ ] Document in user-facing config

## Test Coverage Summary

Total Tests: **23**
- Unit tests: 12
- Integration tests: 10
- Updated legacy tests: 1

Coverage Areas:
- ✅ Schema loading (v2.0 format)
- ✅ Multi-package resolution
- ✅ Auto-selection logic (installed + rank priority)
- ✅ Configuration (auto_select_ambiguous)
- ✅ Manager packages
- ✅ Rank persistence
- ✅ Backward compatibility (single package)
- ✅ Full workflow resolution pipeline

## Notes

1. **No Backward Compatibility**: Tests assume complete cutover to v2.0 schema
2. **Configuration Default**: `auto_select_ambiguous=True` by default
3. **Rank Display**: CLI can access `resolved_node.rank` for display
4. **Manager Packages**: Treated equally to Registry packages in ranking
5. **Empty Lists**: Empty package list = node not found (returns `None`)

## Success Criteria

- All 23 tests pass
- No regressions in existing tests
- Configuration properly defaults to enabled
- CLI can display rank information
- Installed package priority works correctly
