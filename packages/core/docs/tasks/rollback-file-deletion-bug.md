# Bug Fixes: Workflow Commit Flow Issues

## Bug 1: Rollback Does Not Delete Files Added After Target Version

**Status**: Open
**Priority**: High
**Component**: Git Manager, Rollback
**Created**: 2025-10-03

## Summary

When rolling back to a previous version, files that were added **after** that version are not deleted from the working tree. This causes workflows (and potentially other files) to persist even when rolling back to a version before they existed.

## Impact

- **Workflows**: Users rolling back past when a workflow was added will still see that workflow in both `.cec/workflows/` and `ComfyUI/workflows/`
- **Status confusion**: Status shows workflows as synced when they shouldn't exist at that version
- **Incorrect state**: Environment state doesn't match the git commit being rolled back to
- **Potential data issues**: Could affect other files beyond workflows

## How to Reproduce

### Setup
```bash
# v1: Create environment with one workflow
cfd create test-env
# Add test_default.json workflow
cfd commit -m "v1: Initial setup"

# v2: Add a second workflow
# Create test_default1.json in ComfyUI
cfd commit -m "v2: Added test_default1"

# v3: Make a change to first workflow
# Edit test_default.json
cfd commit -m "v3: Updated test_default"
```

### Reproduce Bug
```bash
# Rollback to v1 (before test_default1 existed)
cfd rollback v1

# Check status
cfd status
# BUG: Shows both test_default AND test_default1
# Expected: Should only show test_default
```

### Verify Bug in Filesystem
```bash
# Check .cec (tracked state)
ls .cec/workflows/
# Shows: test_default.json, test_default1.json  ❌

# Check git history at v1
git ls-tree v1 workflows/
# Shows: Only test_default.json  ✓

# Check ComfyUI (active state)
ls ComfyUI/user/default/workflows/
# Shows: test_default.json, test_default1.json  ❌
```

## Root Cause Analysis

### Current Rollback Flow

1. **Git Manager** (`git_manager.py:323`):
   ```python
   def apply_version(self, version: str, leave_unstaged: bool = True):
       commit_hash = self.resolve_version(version)
       # This only restores files that exist in the commit
       # It does NOT delete files that don't exist in the commit
       git_checkout(self.repo_path, commit_hash, files=["."], unstage=leave_unstaged)
   ```

2. **Workflow Manager** (`workflow_manager.py:257-292`):
   ```python
   def restore_all_from_cec(self):
       # Copy every workflow from .cec to ComfyUI
       for workflow_file in self.cec_workflows.glob("*.json"):
           # Copies all files in .cec, including ones that shouldn't be there!
           ...

       # Remove workflows from ComfyUI that don't exist in .cec
       # This part works correctly, but .cec has the wrong files!
       cec_names = {f.stem for f in self.cec_workflows.glob("*.json")}
       for comfyui_file in self.comfyui_workflows.glob("*.json"):
           if name not in cec_names:
               comfyui_file.unlink()  # Would delete if .cec was correct
   ```

### The Problem

**`git checkout <commit> -- <file>` behavior**:
- ✅ **Restores** files that exist in `<commit>`
- ✅ **Updates** files that differ from `<commit>`
- ❌ **Does NOT delete** files that don't exist in `<commit>`

This is standard git behavior - checkout only affects specified files, it doesn't clean up extras.

### Example Trace

Rolling back from v3 → v1:

```
v1 state (target):
  workflows/test_default.json  ✓

v3 state (current):
  workflows/test_default.json  ✓
  workflows/test_default1.json  ✓ (added in v2)

After git checkout v1 -- .:
  workflows/test_default.json  ✓ (restored to v1 content)
  workflows/test_default1.json  ✓ (STILL EXISTS! Not in v1, so not touched)

After restore_all_from_cec():
  ComfyUI/workflows/test_default.json  ✓
  ComfyUI/workflows/test_default1.json  ✓ (copied from .cec wrongly!)
```

## Proposed Solutions

### Option A: Two-Phase Rollback (Recommended)

**Phase 1**: Determine what files should exist
```python
def apply_version(self, version: str, leave_unstaged: bool = True):
    commit_hash = self.resolve_version(version)

    # Get list of all tracked files in target commit
    target_files = self._get_files_in_commit(commit_hash)

    # Get list of all tracked files currently
    current_files = self._get_tracked_files()

    # Files to delete (in current but not in target)
    files_to_delete = current_files - target_files

    # Phase 1: Checkout files from target
    git_checkout(self.repo_path, commit_hash, files=["."], unstage=leave_unstaged)

    # Phase 2: Delete files that shouldn't exist
    for file_path in files_to_delete:
        full_path = self.repo_path / file_path
        if full_path.exists():
            full_path.unlink()
            logger.info(f"Deleted {file_path} (not in target version)")
```

**Helper methods needed**:
```python
def _get_files_in_commit(self, commit_hash: str) -> set[str]:
    """Get all tracked file paths in a commit."""
    result = git_ls_tree(self.repo_path, commit_hash, recursive=True)
    return {line.split('\t')[1] for line in result.splitlines()}

def _get_tracked_files(self) -> set[str]:
    """Get all currently tracked file paths."""
    result = git_ls_files(self.repo_path)
    return set(result.splitlines())
```

**Pros**:
- ✅ Correct behavior - matches git commit exactly
- ✅ Explicit - clear what's being deleted
- ✅ Safe - only deletes tracked files, not user data

**Cons**:
- ⚠️ Slightly more complex
- ⚠️ Need to add git utility functions

### Option B: Use git reset --hard (Simpler but Riskier)

```python
def apply_version(self, version: str, leave_unstaged: bool = True):
    commit_hash = self.resolve_version(version)

    if leave_unstaged:
        # Current behavior: checkout with unstaged changes
        git_reset(self.repo_path, commit_hash, mode="mixed")
    else:
        # Hard reset: exactly match the commit
        git_reset(self.repo_path, commit_hash, mode="hard")
```

**Pros**:
- ✅ Simple - one git command
- ✅ Exactly matches commit state

**Cons**:
- ❌ Loses ALL uncommitted changes (may surprise users)
- ❌ Can't leave changes unstaged for review
- ❌ Might delete user files if they're tracked

### Option C: Hybrid Approach

Use Option A for safety, but add a "hard" rollback option for users who want clean state:

```python
def apply_version(self, version: str, mode: str = "safe"):
    """
    Args:
        mode: "safe" (keep unstaged), "clean" (exact match, delete extras)
    """
    if mode == "clean":
        # Two-phase: checkout + delete
        # ...Option A implementation
    else:
        # Current behavior (buggy but backwards compatible)
        # ...current implementation
```

## Implementation Plan

### Phase 1: Fix the Core Bug (Option A)

**Files to modify**:
1. `packages/core/src/comfydock_core/managers/git_manager.py`
   - Add `_get_files_in_commit()` helper
   - Add `_get_tracked_files()` helper
   - Modify `apply_version()` to delete extra files

2. `packages/core/src/comfydock_core/utils/git.py`
   - Add `git_ls_tree()` function if not exists
   - Add `git_ls_files()` function if not exists

**Testing**:
1. Unit tests for new helper methods
2. Integration test for workflow deletion on rollback
3. Integration test for multi-file rollback scenarios

### Phase 2: Add User Communication

**Files to modify**:
1. `packages/cli/comfydock_cli/env_commands.py`
   - Show which files will be deleted during rollback
   - Add confirmation prompt if deleting files

**Example UX**:
```bash
$ cfd rollback v1

⚠️  Rolling back will delete these workflows:
    • test_default1.json (added in v2)

Continue? (y/N): y

⏮ Rolling back to v1...
  ✓ Restored test_default.json
  🗑️  Deleted test_default1.json
✓ Rollback complete
```

### Phase 3: Regression Testing

**Test scenarios**:
1. Rollback past workflow addition → workflow deleted ✓
2. Rollback to workflow modification → workflow content restored ✓
3. Rollback with uncommitted changes → handled gracefully ✓
4. Rollback with no changes → no-op ✓
5. Multiple rollbacks forward/backward → consistent state ✓

## Technical Details

### Git Commands Needed

**List files in a commit**:
```bash
git ls-tree -r --name-only <commit-hash>
```

**List currently tracked files**:
```bash
git ls-files
```

**Example output**:
```bash
$ git ls-tree -r --name-only fe8830d
pyproject.toml
uv.lock
workflows/test_default.json

$ git ls-tree -r --name-only b204d35
pyproject.toml
uv.lock
workflows/test_default.json
workflows/test_default1.json  # Added in later commit
```

### Code References

**Current rollback implementation**:
- `packages/core/src/comfydock_core/core/environment.py:220-259` - Main rollback orchestration
- `packages/core/src/comfydock_core/managers/git_manager.py:293-327` - Git operations
- `packages/core/src/comfydock_core/managers/workflow_manager.py:257-292` - Workflow restoration

**Git utilities**:
- `packages/core/src/comfydock_core/utils/git.py` - Low-level git commands

### Related Issues

- **Resolve → Commit bug**: Fixed by not updating `.cec` during resolve (completed)
- **This bug**: Git rollback doesn't clean up added files (current task)
- **Potential**: Same issue might affect other file types beyond workflows

## Testing Strategy

### Unit Tests

Add to `packages/core/tests/unit/managers/test_git_manager.py`:

```python
class TestGitManagerRollback:
    """Test rollback file deletion behavior."""

    def test_rollback_deletes_files_added_after_target(self):
        """Files added after target version should be deleted."""
        # Setup: Create v1 with file1, v2 with file1+file2
        # Rollback to v1
        # Assert: file2 is deleted, file1 remains

    def test_rollback_restores_deleted_files(self):
        """Files deleted after target should be restored."""
        # Setup: Create v1 with file1+file2, v2 deletes file2
        # Rollback to v1
        # Assert: file2 is restored
```

### Integration Tests

Add to `packages/core/tests/integration/test_workflow_commit_flow.py`:

```python
class TestWorkflowRollback:
    """Test workflow rollback scenarios."""

    def test_rollback_removes_workflow_added_after_target(self):
        """Rollback should delete workflows added after target version."""
        # v1: one workflow
        # v2: add second workflow
        # v3: modify first workflow
        # Rollback to v1
        # Assert: Only first workflow exists

    def test_rollback_multiple_times(self):
        """Multiple rollbacks should maintain consistent state."""
        # Create v1, v2, v3 with different workflows
        # Rollback v3 → v1 → v3 → v2
        # Assert: State matches expected version each time
```

## Acceptance Criteria

- [ ] Rolling back past workflow creation deletes the workflow from both `.cec` and `ComfyUI`
- [ ] Rolling back to a version restores exact file list from that commit
- [ ] Status after rollback shows only files that existed in target version
- [ ] Rollback logs clearly show which files were deleted
- [ ] All existing rollback tests continue to pass
- [ ] New integration tests cover file deletion scenarios
- [ ] User confirmation required before deleting files (safety)

## Migration Notes

**Breaking Change**: Yes - rollback behavior changes

**User Impact**:
- Users who rolled back will now see files properly deleted
- Previous rollbacks may have left files in inconsistent state
- No data loss - only affects working tree, git history intact

**Communication**:
- Document in changelog
- Add warning in release notes
- Update PRD rollback section

## Related Documentation

- **PRD**: `packages/core/docs/prd.md` - Section "Rollback Behavior" (lines 220-259)
- **Architecture**: Two-tier reproducibility model
- **Git Integration**: `prd.md` lines 739-756

## Questions for Discussion

1. Should we add a `--hard` flag for "clean" rollback vs current "safe" rollback?
2. Should rollback ask for confirmation before deleting files?
3. How do we handle `.disabled` files from node removals during rollback?
4. Should we log deleted files to a recovery file in case user wants to undo?

## Next Steps

1. Review proposed solution approach
2. Decide on Option A vs Option B vs Option C
3. Implement core fix in git_manager.py
4. Add integration tests
5. Update CLI to show deleted files
6. Update documentation
7. Test edge cases (empty rollback, same version, etc.)

---

## Bug 2: Workflow Modified After Commit ✅ FIXED

**Date:** 2025-10-03
**Status:** ✅ Fixed
**Component:** Environment, Workflow Manager
**Related Issue:** Workflow shows as "modified" immediately after committing

### Problem

When committing a workflow with resolved models, the workflow would show as "modified" immediately after the commit succeeded, instead of showing as "synced".

#### User Report

```bash
❯ cfd status
Environment: test4

📋 Workflows:
  🆕 test1 (new, ready to commit)

❯ cfd commit -m "Initial commit of test1 after resolving model"
✅ Commit successful: Initial commit of test1 after resolving model

❯ cfd status  # Immediately after commit
Environment: test4

📋 Workflows:
  📝 test1 (modified)  # ❌ BUG: Should be synced!
```

### Root Cause

The commit process had a **timing bug** in `execute_commit()`:

```python
# BEFORE (buggy code):
def execute_commit(...):
    # 1. Copy workflows from ComfyUI to .cec
    copy_results = self.workflow_manager.copy_all_workflows()

    # 2. Apply resolution (updates ComfyUI workflows with resolved paths)
    self.workflow_manager.apply_all_resolution(workflow_status)

    # 3. Git commit
    self.commit(message)
```

**Problem:** Workflows were copied to `.cec` BEFORE model path resolution was applied. This meant:
1. `.cec/workflows/test1.json` had old model paths
2. `ComfyUI/user/default/workflows/test1.json` had NEW resolved paths
3. When `status` compared them, they differed → showed as "modified"

### Solution

Reorder operations to copy workflows AFTER applying resolution:

```python
# AFTER (fixed code):
def execute_commit(...):
    # 1. Apply resolution (updates ComfyUI workflows with resolved paths)
    self.workflow_manager.apply_all_resolution(workflow_status)

    # 2. Copy workflows from ComfyUI to .cec (gets updated paths)
    copy_results = self.workflow_manager.copy_all_workflows()

    # 3. Git commit
    self.commit(message)
```

Now both versions have the same content after commit → workflow shows as "synced".

### Files Changed

- `packages/core/src/comfydock_core/core/environment.py`: Fixed `execute_commit()` method (3 code paths)
- `packages/core/tests/integration/test_workflow_commit_flow.py`: Added regression test

### Test Coverage

**New Test:**
`test_commit_after_model_resolution_shows_synced`:
- Creates workflow with indexed model
- Commits (triggers model resolution)
- Verifies workflow shows as "synced" (not "modified")
- Confirms ComfyUI and .cec versions are identical

**All Tests Pass:**
- 29 integration tests ✅
- Workflow commit flow tests ✅
- Model resolution tests ✅
- Rollback tests ✅
- State transition tests ✅

### TDD Approach

1. **Red**: Wrote test that reproduced the bug (test failed)
2. **Green**: Implemented fix (test passed)
3. **Refactor**: Removed debug code, verified all tests pass

### Verification

```bash
# Test passes with fix
❯ uv run pytest tests/integration/test_workflow_commit_flow.py::TestWorkflowRollback::test_commit_after_model_resolution_shows_synced -v
PASSED ✅

# All integration tests pass
❯ uv run pytest tests/integration/ -v
29 passed ✅
```

### Impact

- ✅ Workflows now correctly show as "synced" after commit
- ✅ No breaking changes to API or behavior
- ✅ All existing tests continue to pass
- ✅ User experience is now consistent with expectations

---

## Bug 3: Rollback Leaves Uncommitted Changes ✅ FIXED

**Date:** 2025-10-03
**Status:** ✅ Fixed
**Component:** Environment, Git Manager
**Related Issue:** After rollback completes, status shows uncommitted changes

### Problem

After a successful rollback, running `status` would show uncommitted changes, even though the user didn't make any changes - they just rolled back.

#### User Report

```bash
$ cfd rollback v3
✓ Rollback complete

$ cfd status
📦 Uncommitted changes:
  • 1 workflow(s) changed  # ❓ Why? I just rolled back!

$ cfd log
v4: Changed model
v3: Updated model  # ← I'm at v3 now
v2: Initial commit
```

**User confusion:**
- "I just rolled back... why are there uncommitted changes?"
- "What am I supposed to commit? I didn't change anything!"
- "Is this a bug?"

### Root Cause

The rollback implementation was using git's "unstaged changes" mode:

```python
# Old behavior:
git checkout v3 -- .      # Restore files from v3
git reset HEAD .          # Unstage them (leaves as "modified")
restore_all_from_cec()    # Copy .cec → ComfyUI

# Result: Both .cec and ComfyUI match, but git thinks .cec is "modified"
```

This created a confusing state where:
1. Git status: "workflows/test1.json is modified" ❌
2. Workflow status: "test1 ✓" (ComfyUI and .cec match) ✓
3. **Contradiction!**

The `leave_unstaged=True` (safe mode) was meant to let users review changes, but for rollback this doesn't make sense - the user didn't make changes, they're just restoring a checkpoint.

### Design Decision: Checkpoint-Style Rollback

We decided to implement "checkpoint-style" rollback (like video game saves):

**Mental Model:**
- Rollback = instant teleportation to old state
- Auto-commits as new version
- No "uncommitted changes"
- Full history preserved

**Implementation:**
```python
def rollback(self, target: str):
    # 1. Apply target version (clean, not unstaged)
    self.git_manager.rollback_to(target, safe=False)

    # 2. Restore workflows
    self.workflow_manager.restore_all_from_cec()

    # 3. Auto-commit the rollback
    self.git_manager.commit_all(f"Rollback to {target}")

    # Result: Clean state, new version created
```

**User Experience:**
```bash
$ cfd rollback v3
✓ Rolled back to v3
✓ Created checkpoint v6

$ cfd status
✓ All workflows synced  # Clean!

$ cfd log
v6: Rollback to v3      # Auto-committed
v5: Changed model
v4: Updated workflow
v3: Initial commit      # This is what v6 restored
...
```

### Benefits

1. **No confusion**: Clean state after every rollback
2. **Audit trail**: Can see "At 2pm I rolled back to v3"
3. **Reversibility**: Can rollback the rollback (v6 → v3 → v6 → v2)
4. **Linear history**: v1→v2→v3→v4→v5(rollback to v2)→v6
5. **Matches user mental model**: Rollback is an ACTION that creates a checkpoint

### Files Changed

- `packages/core/src/comfydock_core/core/environment.py`: Auto-commit rollbacks
- `packages/core/src/comfydock_core/managers/git_manager.py`: Changed default to `safe=False`
- `packages/core/tests/integration/test_workflow_commit_flow.py`: Added comprehensive test

### Test Coverage

**New Test:**
`test_rollback_creates_clean_state_with_auto_commit`:
- Creates v2, v3, v4 with different workflow states
- Rolls back to v2
- Verifies rollback created v5 (auto-commit)
- Verifies git status is clean (no uncommitted changes)
- Verifies full history preserved (can still see v3, v4)
- Tests rolling forward (v5 → v4 creates v6)

**All Tests Pass:**
- 30 integration tests ✅
- All rollback behavior tests updated ✅
- No breaking changes to existing functionality ✅

### Verification

```bash
# Test passes with fix
❯ uv run pytest tests/integration/test_workflow_commit_flow.py::TestWorkflowRollback::test_rollback_creates_clean_state_with_auto_commit -v
PASSED ✅

# All integration tests pass
❯ uv run pytest tests/integration/ -v
30 passed ✅
```

### Design Rationale

**Why auto-commit instead of leaving unstaged?**

1. **Target users**: Workflow artists, not git experts
2. **Mental model**: Video game saves/checkpoints, not source control
3. **Simplicity**: One action, one result, no extra steps
4. **Clarity**: Status always shows clean or dirty, never "dirty from rollback"
5. **Safety**: Can always rollback the rollback

**Alternative considered**: Two-mode rollback (`--preview` flag)
- Rejected: Adds complexity for minimal benefit
- Philosophy: Keep it simple for MVP

### Impact

- ✅ Clean state after every rollback
- ✅ Matches user mental model (checkpoints)
- ✅ Preserves full history
- ✅ No "uncommitted changes" confusion
- ✅ All existing tests pass
- ✅ Better UX for target audience (artists, not engineers)
