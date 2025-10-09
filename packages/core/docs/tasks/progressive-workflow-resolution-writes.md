# Progressive Writes During Workflow Resolution

**Date:** 2025-10-08
**Status:** Partially Implemented (Models ✅, Nodes ❌)
**Priority:** High (Nodes block Ctrl+C safety)
**Effort:** 1-2 hours (nodes only)
**Risk:** Low

## Current Status

**Models: ✅ WORKING**
- Progressive writes implemented via `_write_single_model_resolution()`
- Ctrl+C preserves all model resolutions made so far
- Auto-resume works via pyproject cache

**Nodes: ❌ BROKEN**
- No progressive writes (was planned but never implemented)
- Node resolutions only written in `apply_resolution()`
- Ctrl+C loses ALL node resolutions (KeyboardInterrupt propagates out before `apply_resolution()` runs)

## Problem

Users lose all node progress if they Ctrl+C during `workflow resolve`:

```bash
$ comfydock workflow resolve "my_workflow"

⚠️  Ambiguous model: sd15.safetensors
  [1-3]: _  # User selects [1]

⚠️  Missing model: lora_A.safetensors
  Path: _  # User provides path

⚠️  Missing model: lora_B.safetensors
  Path: ^C  # User hits Ctrl+C

# ALL PROGRESS LOST!
# Resolutions for sd15 + lora_A are not saved
```

**Current behavior:**
- All user choices collected in `fix_resolution()`
- Written at END via single `apply_resolution()` call
- Ctrl+C = start over from scratch

**Desired behavior:**
- Each user choice written immediately to `pyproject.toml` + workflow JSON
- Ctrl+C preserves all work done so far
- Resume via `workflow resolve` (already-resolved items auto-skip)
- `commit --allow-issues` can checkpoint partial state

---

## Solution

Write to disk after each user decision instead of batching all writes at the end.

**Key insight:** The architecture already supports this!
- `apply_resolution()` accepts partial `ResolutionResult` objects
- Each `pyproject.models.add_model()` call is independent
- Strategies yield one decision at a time

We just need to **call `apply_resolution()` more frequently**.

---

## Implementation

### What Was Already Done (Models)

Models already have progressive writes working:

```python
def _write_single_model_resolution(self, workflow_name, model_ref, model):
    """Write ONE model immediately to pyproject + workflow JSON."""
    # 1. Write to pyproject.models
    self.pyproject.models.add_model(...)
    # 2. Update workflow mappings
    self.pyproject.workflows.set_model_resolutions(...)
    # 3. Update workflow JSON
    WorkflowRepository.save(...)
```

Called inside `fix_resolution()` at lines 618, 651, 665.

### What Still Needs Done (Nodes)

**Node progressive writes are SIMPLER than models** (no JSON updates, no mappings complexity).

**1. Add `_write_single_node_resolution()` helper (30 min)**

```python
def _write_single_node_resolution(
    self,
    node_type: str,
    package_id: str,
    match_type: str,
    is_optional: bool = False
) -> None:
    """Write a single node resolution immediately (progressive mode).

    Simpler than models - just write the mapping, no JSON updates needed.
    """
    # Normalize GitHub URLs to registry IDs
    normalized_id = self._normalize_package_id(package_id)

    # Only save user-resolved nodes (same filter as apply_resolution)
    user_intervention_types = ("user_confirmed", "manual", "heuristic")
    if match_type in user_intervention_types:
        self.pyproject.node_mappings.add_mapping(node_type, normalized_id)
        logger.debug(f"Progressive write: {node_type} -> {normalized_id}")
    elif is_optional:
        self.pyproject.node_mappings.add_mapping(node_type, False)
        logger.debug(f"Progressive write: {node_type} marked optional")
```

**2. Call it inside `fix_resolution()` node loops (30 min)**

Add progressive writes + KeyboardInterrupt handling:

```python
# Line 568-583: Ambiguous nodes loop
if node_strategy:
    for packages in resolution.nodes_ambiguous:
        try:  # ← ADD
            selected = node_strategy.resolve_unknown_node(...)
            if selected:
                nodes_to_add.append(selected)

                # PROGRESSIVE MODE: Write immediately (like models!)
                if workflow_name:
                    self._write_single_node_resolution(
                        node_type=selected.node_type,
                        package_id=selected.package_id,
                        match_type=selected.match_type
                    )
            elif hasattr(...) and strategy._last_choice == 'optional':
                optional_node_types.append(packages[0].node_type)
                # PROGRESSIVE MODE: Write optional immediately
                if workflow_name:
                    self._write_single_node_resolution(
                        node_type=packages[0].node_type,
                        package_id="",
                        match_type="",
                        is_optional=True
                    )
        except KeyboardInterrupt:  # ← ADD
            logger.info("Cancelled - preserving partial node resolutions")
            break  # Exit loop, allow apply_resolution() to run

# Line 586-600: Unresolved nodes loop (same pattern)
```

**3. Update `environment.resolve_workflow()` to skip nodes in `apply_resolution()` (5 min)**

Already has `nodes_only=True` flag, just need to pass it:

```python
# Line 470-474 (already exists, just use it!)
self.workflow_manager.apply_resolution(
    result,
    workflow_name=name,
    model_refs=original_unresolved,
    nodes_only=True  # ← Already implemented! Skip models (written progressively)
)
```

**Why this is simpler than models:**
- ✅ No workflow JSON to update
- ✅ No hash mappings to build
- ✅ No category determination (required/optional)
- ✅ Just one call: `add_mapping(node_type, package_id)`

---

## Benefits

✅ **Ctrl+C safety** - Users don't lose work
✅ **Resumability** - Already works via pyproject cache, now even better
✅ **Checkpointing** - `commit --allow-issues` saves partial state
✅ **Low risk** - Leverages existing write paths, no new abstractions
✅ **Simple** - Just move write calls inside loops

---

## Trade-offs

**Performance:**
- Before: 1 pyproject.toml write, 1 workflow JSON write
- After: N pyproject.toml writes, N workflow JSON writes (where N = number of resolutions)
- Impact: Minimal (files are small, writes are fast)

**Consistency:**
- Before: All-or-nothing (atomic)
- After: Progressive (partial state possible)
- Mitigation: Rollback on unexpected errors, preserve on Ctrl+C

---

## Testing

**Manual test cases:**

1. **Happy path (no interruption)**
   ```bash
   $ comfydock workflow resolve "test"
   # Resolve all items
   # Verify: pyproject.toml updated, workflow JSON updated
   ```

2. **Ctrl+C mid-resolution**
   ```bash
   $ comfydock workflow resolve "test"
   # Resolve 3/5 models
   # Hit Ctrl+C
   # Verify: pyproject.toml has 3 models saved
   # Resume:
   $ comfydock workflow resolve "test"
   # Verify: Only asks about remaining 2 models
   ```

3. **Error during resolution**
   ```bash
   $ comfydock workflow resolve "test"
   # Trigger error (e.g., invalid model path)
   # Verify: pyproject.toml rolled back to initial state
   ```

4. **Commit with partial resolution**
   ```bash
   $ comfydock workflow resolve "test"
   # Resolve 3/5, Ctrl+C
   $ comfydock commit -m "WIP" --allow-issues
   # Verify: Git commit includes partial resolutions
   ```

**Integration tests:**
- Test Ctrl+C behavior (simulate via exception)
- Test resumability (resolve → partial → resolve again)
- Test rollback on error

---

## Why Nodes Were Skipped Originally

Models were implemented first (more complex), nodes were planned but **never finished**. No technical barrier - just incomplete implementation.

**Evidence:**
- Original plan (line 88-99) shows node progressive writes were intended
- `_write_single_model_resolution()` exists for models ✅
- `_write_single_node_resolution()` was never created ❌
- Models have KeyboardInterrupt handlers ✅
- Nodes have NO KeyboardInterrupt handlers ❌

## Timeline

| Task | Effort | Risk |
|------|--------|------|
| Add `_write_single_node_resolution()` helper | 30 min | Low |
| Update node loops in `fix_resolution()` | 30 min | Low |
| Add KeyboardInterrupt handlers | 10 min | Low |
| Testing (manual + integration) | 30 min | Low |
| **TOTAL** | **1-2 hours** | **Low** |

*Much faster than original estimate because models are already done and nodes are simpler.*

---

## Alternative Considered

**Option: Add `--resume` flag instead of automatic progressive writes**

Pros:
- Zero performance overhead
- Explicit user control
- Simpler implementation

Cons:
- Users must remember to use flag
- Extra cognitive load
- Less seamless UX

**Decision:** Go with progressive writes (better UX, low overhead)

---

## Success Criteria

**Must have:**
1. Ctrl+C preserves all work done so far
2. `workflow resolve` auto-resumes from pyproject.toml
3. No data loss on unexpected errors (rollback works)
4. Existing tests still pass

**Nice to have:**
- Progress indicator showing "Saved 3/5 resolutions"
- `--batch` flag to restore old behavior (if perf issues)

---

## Related Documents

- [PRD](../prd.md) - See "Model Resolution Logic" section
- [SIMPLIFIED-incremental-workflow-resolution.md](./SIMPLIFIED-incremental-workflow-resolution.md) - Related improvements
- [Layer Hierarchy](../layer-hierarchy.md) - Code organization

---

## Summary

**Models: Already working via `_write_single_model_resolution()`**

**Nodes: Need 3 simple additions:**
1. Create `_write_single_node_resolution()` helper (10 lines - simpler than models!)
2. Call it in ambiguous + unresolved node loops when `workflow_name` provided (2 lines each)
3. Add `try/except KeyboardInterrupt` to both loops (3 lines each)

**Total: ~20 lines of straightforward code, 1-2 hours work**

---

**Document Status:** Implementation Plan (Models Done, Nodes Remain)
**Last Updated:** 2025-10-08
