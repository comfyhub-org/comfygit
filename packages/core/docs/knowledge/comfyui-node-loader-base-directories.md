# ComfyUI Node Loader Base Directories

**Context Document**
**Last Updated**: 2025-01-06
**Importance**: Critical for workflow portability and import/export

---

## The Core Quirk

ComfyUI's built-in model loader nodes (CheckpointLoaderSimple, LoraLoader, VAELoader, etc.) have **hardcoded base directories** that they automatically prepend to the model paths in workflow JSON files.

**This means**: The path stored in the workflow JSON widget value should **NOT** include the base directory prefix, because the node will add it automatically.

---

## How ComfyUI Node Loaders Work

### Internal Node Behavior (Conceptual)

```python
# Inside ComfyUI source code
class CheckpointLoaderSimple:
    BASE_DIRECTORY = "checkpoints"  # Hardcoded in node definition

    def load_checkpoint(self, ckpt_name):
        # User's workflow JSON has: "sd15/my-model.ckpt"
        full_path = f"models/{self.BASE_DIRECTORY}/{ckpt_name}"
        # Resolves to: "models/checkpoints/sd15/my-model.ckpt"
        return load_model(full_path)

class LoraLoader:
    BASE_DIRECTORY = "loras"  # Different base for different node type

    def load_lora(self, lora_name):
        # User's workflow JSON has: "style.safetensors"
        full_path = f"models/{self.BASE_DIRECTORY}/{lora_name}"
        # Resolves to: "models/loras/style.safetensors"
        return load_lora(full_path)
```

**Key Insight**: The node adds the base directory. The widget value should be **relative to that base**.

---

## The Path Doubling Problem

### ❌ Incorrect: Including Base Directory in Widget Value

```json
{
  "nodes": [{
    "type": "CheckpointLoaderSimple",
    "widgets_values": ["checkpoints/sd15/my-model.ckpt"]
  }]
}
```

**What happens**:
```
1. Widget value: "checkpoints/sd15/my-model.ckpt"
2. Node prepends: "models/checkpoints/"
3. Final lookup: "models/checkpoints/checkpoints/sd15/my-model.ckpt"
                                      ^^^^^^^^^^^
                                      DOUBLED PREFIX!
4. Result: File not found ❌
```

### ✅ Correct: Excluding Base Directory in Widget Value

```json
{
  "nodes": [{
    "type": "CheckpointLoaderSimple",
    "widgets_values": ["sd15/my-model.ckpt"]
  }]
}
```

**What happens**:
```
1. Widget value: "sd15/my-model.ckpt"
2. Node prepends: "models/checkpoints/"
3. Final lookup: "models/checkpoints/sd15/my-model.ckpt"
4. Result: File found ✅
```

---

## ComfyDock's Data Model

We maintain **two different path representations** for the same model:

### Internal Storage (pyproject.toml)

```toml
[tool.comfydock.models.required]
"abc123hash" = {
  filename = "my-model.ckpt",
  relative_path = "checkpoints/sd15/my-model.ckpt",  # ✅ FULL path WITH base
  hash = "abc123..."
}
```

**Why full path?**
- We need to know the complete filesystem path to find the model
- We need to know it's under `checkpoints/` to understand which nodes can use it
- We use this to look up the model in the model index
- This is our **internal representation** for model identity and location

### External Format (Workflow JSON)

```json
{
  "nodes": [{
    "type": "CheckpointLoaderSimple",
    "widgets_values": ["sd15/my-model.ckpt"]  # ✅ STRIPPED path WITHOUT base
  }]
}
```

**Why stripped path?**
- ComfyUI expects paths relative to the node's base directory
- The node will prepend `checkpoints/` automatically
- This is **ComfyUI's expected format** for interoperability

---

## The Stripping Function

```python
def _strip_base_directory_for_node(node_type: str, relative_path: str) -> str:
    """Strip the base directory prefix that the node will automatically prepend.

    Args:
        node_type: ComfyUI node type (e.g., "CheckpointLoaderSimple")
        relative_path: Full path including base (e.g., "checkpoints/sd15/model.ckpt")

    Returns:
        Path without base directory prefix (e.g., "sd15/model.ckpt")
    """
    # Get base directory for this node type from model config
    # CheckpointLoaderSimple → ["checkpoints"]
    # LoraLoader → ["loras"]
    base_dirs = ModelConfig.get_directories_for_node(node_type)

    for base_dir in base_dirs:
        prefix = base_dir + "/"
        if relative_path.startswith(prefix):
            # Remove the prefix but preserve subdirectories
            return relative_path[len(prefix):]

    # If path doesn't have expected prefix, return unchanged
    return relative_path
```

### Examples

```python
# Nested subdirectories are preserved
strip("CheckpointLoaderSimple", "checkpoints/sd15/special/model.ckpt")
→ "sd15/special/model.ckpt"

# File directly in base directory
strip("LoraLoader", "loras/style.safetensors")
→ "style.safetensors"

# Already stripped (idempotent)
strip("CheckpointLoaderSimple", "sd15/model.ckpt")
→ "sd15/model.ckpt"  # No change

# Different node type
strip("VAELoader", "vae/vae-ft-mse.safetensors")
→ "vae-ft-mse.safetensors"
```

---

## When Stripping Happens

### 1. During Commit (Local Development)

```python
# User commits workflow
1. Workflow JSON may have full paths: "checkpoints/sd15/model.ckpt"
2. We analyze and resolve models in model index
3. We store FULL path in pyproject.toml: "checkpoints/sd15/model.ckpt"
4. We strip base directory for workflow JSON: "sd15/model.ckpt"
5. We update BOTH copies:
   - .cec/workflows/my_workflow.json (committed state)
   - ComfyUI/user/default/workflows/my_workflow.json (active working copy)
```

**Why update both?**
- `.cec/workflows/`: Committed state (for git tracking)
- `ComfyUI/user/default/workflows/`: Active working copy (so ComfyUI sees correct paths)

### 2. During Import (Cross-User)

```python
# User B imports environment bundle
1. Load model hash from pyproject.toml: "abc123"
2. Look up hash in User B's local model index
   → Found at: "checkpoints/SDXL/model.ckpt"  # Different subdirectory!
3. Determine node type from workflow: "CheckpointLoaderSimple"
4. Strip base directory for User B's path:
   "checkpoints/SDXL/model.ckpt" → "SDXL/model.ckpt"
5. Update workflow JSON with User B's stripped path
6. Save to User B's ComfyUI directory
```

**Result**: Workflow works even though User B has different subdirectory organization!

---

## The Critical Constraint: Type-Specific Directories

**Important**: Models must be organized under the correct type directory for their intended node loaders.

### ✅ Valid Organization

```
models/
├── checkpoints/
│   ├── sd15/
│   │   └── my-model.ckpt          ✅ CheckpointLoaderSimple can find this
│   └── sdxl/
│       └── another-model.ckpt     ✅ CheckpointLoaderSimple can find this
├── loras/
│   └── style.safetensors          ✅ LoraLoader can find this
└── vae/
    └── vae-ft-mse.safetensors     ✅ VAELoader can find this
```

### ❌ Invalid Organization

```
models/
├── my-models/
│   └── checkpoint.ckpt            ❌ CheckpointLoaderSimple CANNOT find this
│                                     (not under "checkpoints/" directory)
└── loras/
    └── checkpoint.ckpt            ❌ CheckpointLoaderSimple CANNOT find this
                                      (under wrong type directory)
```

**Why?**
- CheckpointLoaderSimple **only** looks under `models/checkpoints/`
- LoraLoader **only** looks under `models/loras/`
- You cannot force a checkpoint loader to load from `models/loras/` by changing the widget value

**Consequence for Import**:
If User B has a checkpoint model stored at `models/custom/model.ckpt` (not under `checkpoints/`), the import will fail with a clear error: "Model must be under checkpoints/ directory for CheckpointLoaderSimple to find it."

---

## Why Symlinks Don't Solve This

The symlink (`ComfyUI/models/ → /path/to/global/models/`) solves **filesystem access** but not **widget value format**:

### What Symlink Solves

```
ComfyUI node tries to load:
"models/checkpoints/sd15/model.ckpt"

With symlink:
ComfyUI/models/checkpoints/sd15/model.ckpt
→ /home/user/global-models/checkpoints/sd15/model.ckpt
✅ File accessible through symlink
```

### What Symlink Doesn't Solve

```
If workflow JSON has incorrect format:
{"widgets_values": ["checkpoints/sd15/model.ckpt"]}  # Includes base

Node prepends base:
path = "models/checkpoints/" + "checkpoints/sd15/model.ckpt"

With symlink:
ComfyUI/models/checkpoints/checkpoints/sd15/model.ckpt
→ /home/user/global-models/checkpoints/checkpoints/sd15/model.ckpt
❌ Path doubling happens before symlink resolution!
```

**Conclusion**:
- Symlink solves **where** models are stored (filesystem location)
- Path stripping solves **how** models are referenced (JSON format)
- Both are necessary and complementary

---

## Implementation Notes

### Files Involved

1. **`workflow_manager.py`**:
   - `_strip_base_directory_for_node()`: Core stripping logic
   - `update_workflow_model_paths()`: Apply stripping after resolution
   - `apply_resolution()`: Orchestrates workflow JSON updates

2. **`model_config.py`**:
   - `node_directory_mappings`: Maps node types to base directories
   - `get_directories_for_node()`: Returns base dirs for a node type

3. **`pyproject_manager.py`**:
   - Stores full paths with base directory included
   - Used for model index lookups and reproducibility

### Key Design Decisions

1. **Store full paths internally**: Makes model index lookups reliable
2. **Strip paths in workflow JSON**: Makes workflows ComfyUI-compatible
3. **Idempotent stripping**: Safe to call multiple times on same path
4. **Preserve subdirectories**: Only strip the type-level base directory
5. **Fail on invalid organization**: Better than silent failures

---

## Testing Strategy

### Unit Tests

```python
def test_strip_checkpoint_loader():
    """CheckpointLoaderSimple expects no 'checkpoints/' prefix."""
    result = strip("CheckpointLoaderSimple", "checkpoints/sd15/model.ckpt")
    assert result == "sd15/model.ckpt"

def test_strip_preserves_subdirectories():
    """Nested paths after base are preserved."""
    result = strip("CheckpointLoaderSimple", "checkpoints/a/b/c/model.ckpt")
    assert result == "a/b/c/model.ckpt"

def test_strip_idempotent():
    """Already stripped paths return unchanged."""
    result = strip("CheckpointLoaderSimple", "sd15/model.ckpt")
    assert result == "sd15/model.ckpt"
```

### Integration Tests

```python
def test_workflow_json_has_stripped_paths_after_commit():
    """After committing, workflow JSON should have stripped paths."""
    # Setup: workflow with full paths
    # Commit: resolve and apply stripping
    # Assert: workflow JSON has paths without base directories

def test_import_remaps_to_local_paths():
    """Import should remap models to local organization and re-strip."""
    # Setup: bundle with User A's paths
    # Import: resolve hashes in User B's index
    # Assert: workflow JSON updated with User B's stripped paths
```

---

## Common Pitfalls

### ❌ Pitfall 1: Forgetting to Update Both Workflow Copies

```python
# Wrong: Only update .cec/workflows/
update_workflow_in_cec()

# Right: Update both .cec/ and ComfyUI/
update_workflow_in_cec()
update_workflow_in_comfyui()  # Keep active working copy in sync
```

### ❌ Pitfall 2: Stripping During Model Index Lookup

```python
# Wrong: Strip before index lookup
stripped_path = strip(node_type, "checkpoints/model.ckpt")  # "model.ckpt"
model = index.find_by_path(stripped_path)  # ❌ Won't find it!

# Right: Use full path for index lookup, strip for workflow JSON
model = index.find_by_path("checkpoints/model.ckpt")  # ✅ Found
stripped = strip(node_type, model.relative_path)  # Then strip
workflow.update(stripped)
```

### ❌ Pitfall 3: Assuming Symlink Eliminates Need for Stripping

```python
# Wrong assumption: "Symlink handles paths, no stripping needed"
# Reality: Symlink and stripping solve different problems
# - Symlink: Filesystem access (where files are)
# - Stripping: JSON format (how nodes reference files)
```

---

## References

- ComfyUI source: `folder_paths.py` (defines model folder mappings)
- Our implementation: `workflow_manager.py`, `model_config.py`
- Configuration: `comfyui_models.py` (node type → directory mappings)

---

## Summary

**The Quirk**: ComfyUI node loaders prepend base directories automatically.

**The Solution**: Store full paths internally, strip bases in workflow JSON.

**The Consequence**: Models must be organized under type-specific directories.

**The Benefit**: Workflows are portable across different user model organizations.

**Remember**: Symlinks and path stripping are complementary, not alternatives!
