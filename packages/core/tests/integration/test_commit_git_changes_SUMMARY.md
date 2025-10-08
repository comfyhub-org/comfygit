# Commit with Git-Only Changes Bug Fix

## Summary

Fixed critical architectural issue where `comfydock commit` would refuse to commit when only git had changes (pyproject.toml modifications) but workflows were synced. Implemented clean core API to properly check for ALL committable changes.

## The Bugs

### Bug 1: CLI Only Checks Workflow File Changes

**Location:** `packages/cli/comfydock_cli/env_commands.py:791-793`

**Symptom:**
```bash
$ cfd commit -m "Add nodes" --allow-issues
📋 Analyzing workflows...
✓ No changes to commit - workflows are already up to date

$ cfd status
📦 Uncommitted changes:
  • Added node: rgthree-comfy
  • ... and 17 more nodes
```

**Root Cause:** CLI layer checked ONLY workflow file sync status, ignoring git uncommitted changes in `.cec/pyproject.toml`.

**Before:**
```python
# Check if there are no changes to commit
if not workflow_status.sync_status.has_changes:
    print("✓ No changes to commit - workflows are already up to date")
    return  # Early exit - never calls execute_commit()
```

### Bug 2: CLI Blocks Commits Without Workflows

**Location:** `packages/cli/comfydock_cli/env_commands.py:786-788`

**Symptom:**
```bash
$ cfd node add rgthree-comfy
$ cfd commit -m "Add node"
No workflows found to commit
```

**Root Cause:** CLI prevented committing ANY changes if no workflows existed.

**Before:**
```python
# Check if no workflows to commit
if workflow_status.sync_status.total_count == 0:
    print("No workflows found to commit")
    return
```

This blocked legitimate commits like:
- Adding nodes before creating workflows
- Adding constraints
- Manual pyproject.toml edits

## The Architectural Problem

### Two Types of Committable Changes

1. **Workflow File Changes** (ComfyUI → `.cec/workflows/`)
   - New/modified/deleted `.json` files
   - Checked by `workflow_status.sync_status.has_changes`

2. **Git Changes** (`.cec/` tracked files)
   - `pyproject.toml` (node metadata, mappings, constraints)
   - `uv.lock` (Python dependencies)
   - Workflow JSONs in `.cec/workflows/`
   - Checked by `git_manager.has_uncommitted_changes()`

### Interface Mismatch

**Status command** (works correctly):
```python
status = env.status()  # Returns EnvironmentStatus

# Shows BOTH types:
status.workflow.sync_status.has_changes  # Workflow files
status.git.has_changes                    # Git changes
```

**Commit command** (was broken):
```python
workflow_status = env.workflow_manager.get_workflow_status()

# Only checked workflows:
if not workflow_status.sync_status.has_changes:
    return  # BUG: Ignores git changes!
```

## Real-World Scenarios That Failed

### Scenario 1: Node Resolution Without Workflow Changes
```
1. User has workflow committed in v2
2. User resolves 18 missing nodes interactively
3. Nodes added to pyproject.toml
4. Workflow JSON unchanged (nodes already referenced)
5. Run: cfd commit --allow-issues
6. Result (before fix): "No changes to commit"
7. Result (after fix): Commits successfully
```

### Scenario 2: Manual Node Addition
```
1. User runs: cfd node add rgthree-comfy
2. pyproject.toml updated
3. No workflows exist yet
4. Run: cfd commit -m "Add node"
5. Result (before fix): "No workflows found to commit"
6. Result (after fix): Commits successfully
```

### Scenario 3: Constraint Addition
```
1. User runs: cfd constraint add "numpy<2.0"
2. pyproject.toml updated
3. Workflows unchanged
4. Run: cfd commit -m "Add constraint"
5. Result (before fix): "No changes to commit"
6. Result (after fix): Commits successfully
```

## The Fix: Clean Core API

### Implementation

**Added to `environment.py:506-522`:**

```python
def has_committable_changes(self) -> bool:
    """Check if there are any committable changes (workflows OR git).

    This is the clean API for determining if a commit is possible.
    Checks both workflow file sync status AND git uncommitted changes.

    Returns:
        True if there are committable changes, False otherwise
    """
    # Check workflow file changes (new/modified/deleted workflows)
    workflow_status = self.workflow_manager.get_workflow_status()
    has_workflow_changes = workflow_status.sync_status.has_changes

    # Check git uncommitted changes (pyproject.toml, uv.lock, etc.)
    has_git_changes = self.git_manager.has_uncommitted_changes()

    return has_workflow_changes or has_git_changes
```

**Updated CLI `env_commands.py:785-788`:**

```python
# Before (11 lines, 2 checks):
if workflow_status.sync_status.total_count == 0:
    print("No workflows found to commit")
    return

if not workflow_status.sync_status.has_changes:
    print("✓ No changes to commit - workflows are already up to date")
    return

# After (3 lines, 1 check):
if not env.has_committable_changes():
    print("✓ No changes to commit")
    return
```

### Design Benefits

1. **Single Responsibility:** Core layer owns "committable" logic
2. **DRY:** One place to check for committable changes
3. **Thin CLI:** CLI becomes simple wrapper, doesn't duplicate business logic
4. **Clean Interface:** `has_committable_changes()` is self-documenting
5. **Future-Proof:** Easy to add more committable change types

### What Gets Committed

The fix allows committing when ANY of these have changes:
- ✅ New/modified/deleted workflow files
- ✅ Node additions/removals (pyproject.toml)
- ✅ Node resolution mappings (pyproject.toml)
- ✅ Constraint additions (pyproject.toml)
- ✅ Dependency changes (pyproject.toml)
- ✅ Python lock changes (uv.lock)
- ✅ Any manual edits to tracked files

## Test Coverage

**Created:** `test_commit_git_changes.py` with 9 comprehensive tests

### TestCommitWithGitChangesOnly (5 tests)

1. ✅ `test_commit_with_node_resolution_but_synced_workflow`
   - Node resolution without workflow JSON changes
   - Tests exact bug from user report

2. ✅ `test_commit_with_manual_node_addition_no_workflows`
   - Adding nodes before workflows exist
   - Tests the "no workflows found" bug

3. ✅ `test_commit_with_constraint_addition_no_workflow_changes`
   - Constraint additions with synced workflows

4. ✅ `test_commit_with_both_workflow_and_git_changes`
   - Baseline: both types of changes (should always work)

5. ✅ `test_no_changes_at_all_returns_gracefully`
   - Edge case: truly no changes

### TestCoreLayerCommitAPI (4 tests)

1. ✅ `test_has_committable_changes_with_workflow_changes`
   - New API detects workflow file changes

2. ✅ `test_has_committable_changes_with_git_changes`
   - New API detects git changes without workflow changes

3. ✅ `test_has_committable_changes_with_both`
   - New API detects both types of changes

4. ✅ `test_has_committable_changes_with_no_changes`
   - New API returns False when truly no changes

## Impact

### Before Fix
- ❌ Cannot commit node additions without workflow changes
- ❌ Cannot commit constraints
- ❌ Cannot commit when no workflows exist
- ❌ Node resolution changes lost (not committable)
- ❌ Manual pyproject.toml edits not committable
- ❌ Confusing UX: status shows changes, commit refuses

### After Fix
- ✅ All git changes are committable
- ✅ Workflows optional for commits
- ✅ Clean, predictable behavior
- ✅ UX consistency: status and commit agree
- ✅ Proper abstraction: core owns commit logic
- ✅ Future-proof extensibility

## Code Changes Summary

**Core layer:**
- Added: `environment.py:has_committable_changes()` method (18 lines)

**CLI layer:**
- Removed: Lines 786-793 (11 lines of incorrect logic)
- Added: Line 786-788 (3 lines using new API)
- Net change: -8 lines, cleaner code

**Tests:**
- Added: `test_commit_git_changes.py` (313 lines, 9 tests)

**Total impact:**
- **Core API:** +1 method
- **CLI code:** -8 lines (cleaner)
- **Test coverage:** +9 integration tests
- **Bugs fixed:** 2 critical commit bugs

## Architecture Improvements

### Clean Separation of Concerns

**Before:** CLI had business logic about what's committable
```python
# CLI knows about internal details
if workflow_status.sync_status.total_count == 0:
    # ...
if not workflow_status.sync_status.has_changes:
    # ...
```

**After:** Core owns committable logic, CLI uses clean API
```python
# CLI asks core: "can I commit?"
if not env.has_committable_changes():
    # ...
```

### Single Source of Truth

**Before:** Multiple places checked "committable"
- CLI checked workflow status
- Core checked git status
- Inconsistent logic between status and commit

**After:** One method in core layer
- `env.has_committable_changes()` is the source of truth
- Used by CLI for pre-commit validation
- Could be used by status, rollback, etc.

### Extensibility

Adding new committable change types is now trivial:

```python
def has_committable_changes(self) -> bool:
    has_workflow_changes = self.workflow_manager.get_workflow_status().sync_status.has_changes
    has_git_changes = self.git_manager.has_uncommitted_changes()

    # Easy to extend:
    # has_model_changes = self.model_manager.has_pending_downloads()
    # has_node_updates = self.node_manager.has_available_updates()

    return has_workflow_changes or has_git_changes
```

## Verification

**All tests pass:**
```
95 passed, 1 skipped in 87.39s
```

**New tests:**
```
9 passed in 1.50s
```

**Specific coverage:**
- ✅ Git-only changes committable
- ✅ Workflow-only changes committable
- ✅ Both types committable
- ✅ No changes handled gracefully
- ✅ Node additions without workflows
- ✅ Constraints without workflows
- ✅ Node resolution without workflow changes

## Conclusion

Clean architectural fix following MVP best practices:

✅ **Code Economy:** Net -8 lines in CLI, +18 lines in core
✅ **DRY:** Single method for committable check
✅ **No Backwards Compatibility:** Clean break, fixed old bugs
✅ **Clean Interface:** Core library properly abstracted
✅ **Future-Proof:** Easy to extend with new change types
✅ **Well-Tested:** 9 new tests covering all scenarios

The fix transforms a leaky CLI/core interface into a clean API where business logic lives in the core layer and the CLI is a thin, dumb wrapper.
