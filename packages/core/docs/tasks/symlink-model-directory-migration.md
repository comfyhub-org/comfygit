# Symlink-Based Model Directory Implementation Plan

**Status**: Ready to Implement
**Priority**: High (Architectural Foundation)
**Estimated Effort**: 0.5-1 day
**Complexity**: Low (Simple, clean refactor)

---

## Executive Summary

Replace the `extra_model_paths.yaml` approach with direct symlink/junction-based model directory linking. This eliminates custom node compatibility issues and simplifies the architecture.

### Why This Change

**Problem with Current Approach:**
- Many custom nodes **ignore** `extra_model_paths.yaml`
- Custom nodes override `folder_paths.folder_names_and_paths` directly
- Requires per-node path translation logic
- Breaks workflows when custom nodes expect specific paths
- ComfyUI GitHub issues show community uses symlinks as standard workaround

**Benefits of Symlinks:**
- ✅ **Universal compatibility** - ALL nodes (builtin + custom) see same models
- ✅ **Zero translation** - Paths work as-is in workflows
- ✅ **Simpler code** - No YAML management, no path stripping logic
- ✅ **Future-proof** - New custom nodes automatically work
- ✅ **Community-proven** - Matches ecosystem best practices

### Pre-Customer MVP Context

**No backwards compatibility needed:**
- Zero production users
- Can manually delete test environment `extra_model_paths.yaml` files
- Clean slate for correct architecture

---

## Current Architecture Analysis

### File: `model_path_manager.py`

**Current Responsibilities:**
1. Generate `extra_model_paths.yaml` from global models directory
2. Discover subdirectories in global models path
3. Sync YAML file when models directory changes
4. Clean up YAML on environment deletion

**Problems:**
- 254 lines of YAML generation logic (unnecessary with symlinks)
- Complex directory discovery and change tracking
- No guarantee custom nodes respect the YAML
- Path translation needed in `workflow_manager.py`

### Integration Points

**Where `ModelPathManager` is Used:**

1. **`Environment.__init__`** (line 72)
   - Creates `self.model_path_manager` property
   - Stores reference to manager instance

2. **`Environment.sync_model_paths()`** (line 310-317)
   - Public method calling `model_path_manager.sync_model_paths()`
   - Returns stats dictionary

3. **`Environment.sync()`** (line 206)
   - Calls `sync_model_paths()` during environment sync
   - Handles errors gracefully (non-fatal)

4. **`EnvironmentFactory.create()`** (line 89-95)
   - Calls `env.sync_model_paths()` after environment creation
   - Non-fatal if it fails

5. **`Workspace.status()`** (line 440)
   - Loops through envs calling `env.sync_model_paths()`
   - Part of workspace-wide sync operation

---

## New Architecture Design

### Core Concept

```
User's Global Models:
/home/user/models/
  ├── checkpoints/
  ├── loras/
  └── depthanything/

ComfyUI Environment:
/workspace/environments/test/ComfyUI/
  ├── models/ → SYMLINK to /home/user/models/  ✓
  └── custom_nodes/
```

**When ComfyUI starts:**
- Default behavior: looks in `ComfyUI/models/`
- Symlink transparently resolves to `/home/user/models/`
- ALL nodes (builtin + custom) see the same models
- No YAML parsing, no overrides, just works

### Platform-Specific Implementation

#### Linux/macOS
```python
os.symlink(src="/home/user/models", dst="ComfyUI/models")
# Works without special permissions
```

#### Windows
```python
# Use junction (directory-only symlink, no admin required)
subprocess.run(
    ['mklink', '/J', 'ComfyUI\\models', 'C:\\Users\\user\\models'],
    shell=True
)
# OR use ctypes for programmatic creation (no subprocess)
```

**Key Decision: Use Junctions on Windows**
- No Administrator privileges required
- No Developer Mode needed
- Only works for directories (perfect for our use case)
- Full compatibility with Windows 7+

---

## Implementation Steps

### Step 1: Create New `ModelSymlinkManager`

**File:** `packages/core/src/comfydock_core/managers/model_symlink_manager.py`

**Responsibilities:**
1. Create symlink/junction from `ComfyUI/models/` to global models directory
2. Validate symlink exists and points to correct target
3. Handle platform differences (Linux/macOS/Windows)
4. Clean up symlink on environment deletion

**Interface:**
```python
class ModelSymlinkManager:
    """Manages symlink/junction to global models directory."""

    def __init__(self, comfyui_path: Path, global_models_path: Path):
        self.comfyui_path = comfyui_path
        self.global_models_path = global_models_path
        self.models_link_path = comfyui_path / "models"

    def create_symlink(self) -> None:
        """Create symlink/junction from ComfyUI/models to global models."""

    def validate_symlink(self) -> bool:
        """Check if symlink exists and points to correct target."""

    def remove_symlink(self) -> None:
        """Remove symlink/junction (safe cleanup)."""

    def get_status(self) -> dict:
        """Get current symlink status for debugging."""
```

**Key Methods:**

1. **`create_symlink()`** - Main workhorse
   ```python
   def create_symlink(self) -> None:
       """Create platform-appropriate link to global models."""

       # Handle existing models/ directory
       if self.models_link_path.exists():
           if self.models_link_path.is_symlink():
               # Already a symlink - check if correct target
               if self._resolve_link() == self.global_models_path:
                   logger.debug("Symlink already points to correct target")
                   return
               else:
                   # Points to wrong target - remove and recreate
                   self.remove_symlink()
           else:
               # Real directory exists - ERROR (don't destroy data)
               raise CDError(
                   f"models/ directory exists and is not a symlink: {self.models_link_path}\n"
                   f"Manual action required:\n"
                   f"  1. Backup: mv {self.models_link_path} {self.models_link_path}.backup\n"
                   f"  2. Retry: comfydock sync\n"
               )

       # Create symlink/junction
       try:
           if os.name == 'nt':  # Windows
               self._create_windows_junction()
           else:  # Linux/macOS
               os.symlink(self.global_models_path, self.models_link_path)

           logger.info(f"Created model link: {self.models_link_path} → {self.global_models_path}")
       except Exception as e:
           raise CDError(f"Failed to create model symlink: {e}")
   ```

2. **`_create_windows_junction()`** - Windows-specific
   ```python
   def _create_windows_junction(self) -> None:
       """Create junction on Windows (no admin required)."""

       # Option 1: Use subprocess (simple, reliable)
       result = subprocess.run(
           ['mklink', '/J', str(self.models_link_path), str(self.global_models_path)],
           shell=True,
           capture_output=True,
           text=True
       )

       if result.returncode != 0:
           # Option 2: Try ctypes if mklink fails
           try:
               self._create_junction_ctypes()
           except Exception as e:
               raise CDError(
                   f"Failed to create Windows junction:\n"
                   f"  mklink error: {result.stderr}\n"
                   f"  ctypes error: {e}\n"
               )

   def _create_junction_ctypes(self) -> None:
       """Create junction using ctypes (fallback for mklink failures)."""
       import ctypes
       from ctypes import wintypes

       # CreateSymbolicLink API with SYMBOLIC_LINK_FLAG_DIRECTORY
       CreateSymbolicLink = ctypes.windll.kernel32.CreateSymbolicLinkW
       CreateSymbolicLink.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD)
       CreateSymbolicLink.restype = wintypes.BOOLEAN

       SYMBOLIC_LINK_FLAG_DIRECTORY = 0x1
       SYMBOLIC_LINK_FLAG_ALLOW_UNPRIVILEGED_CREATE = 0x2

       flags = SYMBOLIC_LINK_FLAG_DIRECTORY | SYMBOLIC_LINK_FLAG_ALLOW_UNPRIVILEGED_CREATE

       result = CreateSymbolicLink(
           str(self.models_link_path),
           str(self.global_models_path),
           flags
       )

       if not result:
           error_code = ctypes.get_last_error()
           raise OSError(f"CreateSymbolicLink failed with error code: {error_code}")
   ```

3. **`validate_symlink()`** - Health check
   ```python
   def validate_symlink(self) -> bool:
       """Verify symlink exists and points to correct target."""

       if not self.models_link_path.exists():
           return False

       if not self.models_link_path.is_symlink():
           logger.warning(f"models/ is not a symlink: {self.models_link_path}")
           return False

       target = self._resolve_link()
       if target != self.global_models_path:
           logger.warning(
               f"Symlink points to wrong target:\n"
               f"  Expected: {self.global_models_path}\n"
               f"  Actual: {target}"
           )
           return False

       return True

   def _resolve_link(self) -> Path:
       """Get symlink target path."""
       if os.name == 'nt':
           # Windows junctions need special handling
           return Path(os.readlink(str(self.models_link_path)))
       else:
           return self.models_link_path.resolve()
   ```

4. **`remove_symlink()`** - Safe cleanup
   ```python
   def remove_symlink(self) -> None:
       """Remove symlink/junction safely."""

       if not self.models_link_path.exists():
           return  # Nothing to remove

       if not self.models_link_path.is_symlink():
           raise CDError(
               f"Cannot remove models/: not a symlink\n"
               f"Manual deletion required: {self.models_link_path}"
           )

       try:
           self.models_link_path.unlink()
           logger.info(f"Removed model symlink: {self.models_link_path}")
       except Exception as e:
           raise CDError(f"Failed to remove symlink: {e}")
   ```

---

### Step 2: Update `Environment` Class

**File:** `packages/core/src/comfydock_core/core/environment.py`

**Changes:**

1. **Replace `model_path_manager` with `model_symlink_manager`** (line 72+)
   ```python
   # OLD:
   @cached_property
   def model_path_manager(self) -> ModelPathManager:
       return ModelPathManager(self.comfyui_path, self.global_models_path)

   # NEW:
   @cached_property
   def model_symlink_manager(self) -> ModelSymlinkManager:
       return ModelSymlinkManager(self.comfyui_path, self.global_models_path)
   ```

2. **Update `sync_model_paths()` method** (line 310-317)
   ```python
   # OLD:
   def sync_model_paths(self) -> dict | None:
       """Configure model paths for this environment."""
       logger.info(f"Configuring model paths for environment '{self.name}'")
       return self.model_path_manager.sync_model_paths()

   # NEW:
   def sync_model_paths(self) -> dict | None:
       """Ensure model symlink is configured for this environment."""
       logger.info(f"Configuring model symlink for environment '{self.name}'")

       try:
           self.model_symlink_manager.create_symlink()
           return {
               "status": "linked",
               "target": str(self.global_models_path),
               "link": str(self.models_path)
           }
       except Exception as e:
           logger.error(f"Failed to configure model symlink: {e}")
           raise
   ```

3. **Update `sync()` method** (line 206)
   ```python
   # Sync model paths to ensure models are available
   try:
       self.model_symlink_manager.create_symlink()  # ← Direct call, simpler
       result.model_paths_configured = True
   except Exception as e:
       logger.warning(f"Failed to configure model symlink: {e}")
       result.errors.append(f"Model symlink configuration failed: {e}")
       # Continue anyway - ComfyUI might still work
   ```

---

### Step 3: Update `EnvironmentFactory`

**File:** `packages/core/src/comfydock_core/factories/environment_factory.py`

**Changes:**

**Update environment creation** (line 89-95)
```python
# OLD:
if env.model_path_manager:
    try:
        env.sync_model_paths()
        # ModelPathManager handles its own logging
    except Exception as e:
        logger.warning(f"Failed to configure initial model paths: {e}")
        # Non-fatal - environment is still usable

# NEW:
try:
    env.model_symlink_manager.create_symlink()
    logger.info("Model directory linked successfully")
except Exception as e:
    logger.error(f"Failed to link model directory: {e}")
    raise  # FATAL - environment won't work without models
```

**Why make it FATAL now?**
- Symlink creation is simple and should always succeed
- If it fails, something is seriously wrong (permissions, disk full, etc.)
- Better to fail fast than create broken environment
- Previous "non-fatal" was because YAML might be optional

---

### Step 4: Handle ComfyUI's Default `models/` Directory

**Problem:** When ComfyUI is cloned, it comes with a `models/` directory containing empty subdirectories.

**Solution:** Remove or rename before creating symlink

**In `EnvironmentFactory.create()` or `ModelSymlinkManager.create_symlink()`:**

```python
def _handle_existing_models_dir(self) -> None:
    """Handle ComfyUI's default models/ directory."""

    if not self.models_link_path.exists():
        return  # Nothing to handle

    if self.models_link_path.is_symlink():
        # Already a symlink - verify or recreate
        return

    # It's a real directory from ComfyUI clone
    logger.info(f"Removing ComfyUI default models/ directory")

    # Check if it's empty or has only empty subdirectories
    if self._is_safe_to_remove():
        shutil.rmtree(self.models_link_path)
        logger.debug("Removed empty ComfyUI models/ directory")
    else:
        # Has actual content - DON'T destroy data
        backup_path = self.models_link_path.parent / "models.backup"
        self.models_link_path.rename(backup_path)
        logger.warning(
            f"Moved existing models/ directory to {backup_path}\n"
            f"Review and merge any models manually if needed"
        )

def _is_safe_to_remove(self) -> bool:
    """Check if models/ directory is safe to delete (empty or default structure)."""

    # Get all files (excluding directories)
    files = list(self.models_link_path.rglob('*'))
    files = [f for f in files if f.is_file()]

    if len(files) == 0:
        return True  # Completely empty

    # Check for only .gitkeep or .gitignore files
    safe_files = {'.gitkeep', '.gitignore', 'Put models here.txt'}
    for f in files:
        if f.name not in safe_files:
            return False  # Has real content

    return True  # Only placeholder files
```

---

### Step 5: Remove Old Code

**Files to Delete/Simplify:**

1. **DELETE: `model_path_manager.py`**
   - 254 lines of YAML generation logic (no longer needed)
   - Replaced by ~150 lines of simple symlink logic

2. **SIMPLIFY: `workflow_manager.py`**
   - **DELETE:** `_strip_base_directory_for_node()` method (line 734-758)
   - **DELETE:** `update_workflow_model_paths()` method (line 628-670)
   - **MODIFY:** `apply_resolution()` to skip workflow JSON updates entirely

   ```python
   # OLD (line 726-732):
   if workflow_name and model_refs and resolution.models_resolved:
       self.update_workflow_model_paths(
           workflow_name=workflow_name,
           resolution=resolution,
           model_refs=model_refs
       )

   # NEW:
   # NO WORKFLOW JSON UPDATES - symlink makes paths work as-is
   # Models are visible at correct paths through symlink
   ```

3. **UPDATE: `Workspace.status()` calls** (line 440)
   ```python
   # Still call sync_model_paths() but it's now simpler
   # Just validates symlink exists
   ```

---

### Step 6: Update Tests

**Files to Update:**

1. **Test: `test_environment_creation.py`** (if exists)
   ```python
   def test_environment_has_model_symlink(workspace, env):
       """Verify model symlink is created."""
       models_path = env.models_path

       assert models_path.exists()
       assert models_path.is_symlink()
       assert models_path.resolve() == env.global_models_path
   ```

2. **Test: `test_model_symlink_manager.py`** (new file)
   ```python
   def test_create_symlink(tmp_path):
       """Test symlink creation."""

   def test_symlink_already_exists():
       """Test idempotent behavior."""

   def test_real_directory_exists():
       """Test error when models/ is real directory."""

   def test_remove_symlink():
       """Test cleanup."""
   ```

3. **Remove/Update: Any tests for `ModelPathManager`**

---

## Edge Cases & Error Handling

### 1. Global Models Directory Doesn't Exist

**Scenario:** User hasn't configured global models directory yet

**Solution:**
```python
def create_symlink(self) -> None:
    # Check if global models path exists
    if not self.global_models_path.exists():
        raise CDError(
            f"Global models directory does not exist: {self.global_models_path}\n"
            f"Create it first: mkdir -p {self.global_models_path}\n"
            f"Or configure different path: comfydock config set-models-dir <path>"
        )
```

### 2. Symlink Validation Fails

**Scenario:** Symlink exists but points to wrong directory (user moved global models)

**Solution:**
```python
def create_symlink(self) -> None:
    if self.models_link_path.is_symlink():
        target = self._resolve_link()
        if target != self.global_models_path:
            logger.warning(f"Symlink points to old location: {target}")
            logger.warning(f"Updating to new location: {self.global_models_path}")
            self.remove_symlink()
            # Fall through to recreate with correct target
```

### 3. Windows Junction Creation Fails

**Scenario:** mklink command fails (rare but possible)

**Solution:** Fallback to ctypes implementation (see Step 1.2)

### 4. Permission Errors

**Scenario:** User doesn't have write access to ComfyUI directory

**Solution:**
```python
except PermissionError as e:
    raise CDError(
        f"Permission denied creating symlink:\n"
        f"  Path: {self.models_link_path}\n"
        f"  Error: {e}\n"
        f"  Fix: Check directory permissions"
    )
```

---

## Migration Guide (For Manual Test Cleanup)

**Since this is pre-customer MVP, manual cleanup is acceptable:**

### For Each Test Environment:

```bash
# 1. Delete extra_model_paths.yaml
cd /path/to/environment/ComfyUI/
rm extra_model_paths.yaml

# 2. Remove models/ directory (backup first if it has content)
ls models/  # Check if it has any real model files
# If empty:
rm -rf models/
# If has content:
mv models/ models.backup/

# 3. Sync environment (creates symlink)
comfydock use <env-name>
comfydock sync

# 4. Verify symlink
ls -la | grep models
# Should show: models -> /home/user/global/models/

# 5. Test ComfyUI can see models
comfydock run
# Check UI shows models in dropdowns
```

**Automated Alternative (add to CLI):**
```bash
comfydock migrate-to-symlinks  # Future enhancement if needed
```

---

## Testing Strategy

### Unit Tests

1. **`ModelSymlinkManager` tests:**
   - Create symlink on empty directory
   - Handle existing symlink (idempotent)
   - Error on real directory exists
   - Remove symlink safely
   - Validate symlink status

2. **Platform-specific tests:**
   - Mock `os.name` for Windows testing on Linux
   - Test junction creation logic
   - Test symlink creation logic

### Integration Tests

1. **Environment lifecycle:**
   - Create environment → verify symlink created
   - Delete environment → verify symlink removed
   - Multiple environments → each has own symlink to same target

2. **ComfyUI integration:**
   - Start ComfyUI
   - Verify models visible in UI
   - Load workflow using models
   - Verify custom nodes see models

### Manual Testing Checklist

- [ ] Create new environment
- [ ] Verify symlink created
- [ ] Start ComfyUI
- [ ] Check models appear in loader dropdowns
- [ ] Test workflow with builtin model loader
- [ ] Test workflow with custom node model loader
- [ ] Delete environment
- [ ] Verify symlink cleaned up
- [ ] Verify global models still intact

---

## Implementation Timeline

### Phase 1: Core Implementation (4 hours)
- [ ] Create `ModelSymlinkManager` class
- [ ] Implement Linux/macOS symlink logic
- [ ] Implement Windows junction logic
- [ ] Add error handling

### Phase 2: Integration (2 hours)
- [ ] Update `Environment` class
- [ ] Update `EnvironmentFactory`
- [ ] Remove `ModelPathManager`
- [ ] Simplify `WorkflowManager` (remove path updates)

### Phase 3: Testing (2 hours)
- [ ] Write unit tests
- [ ] Manual testing on Linux
- [ ] Manual testing on Windows (if accessible)
- [ ] Test custom node compatibility

### Phase 4: Cleanup (1 hour)
- [ ] Remove old test `extra_model_paths.yaml` files
- [ ] Update documentation
- [ ] Verify all environments work

**Total: 0.5-1 day** (accounting for unexpected issues)

---

## Success Criteria

✅ **All custom nodes see models** - No more `extra_model_paths.yaml` issues
✅ **Workflow paths work as-is** - No path translation needed
✅ **Cross-platform support** - Linux, macOS, Windows all work
✅ **Simpler codebase** - Less code, fewer edge cases
✅ **Test environments migrated** - Manual cleanup completed

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Windows junction creation fails | High | Fallback to ctypes, clear error messages |
| Symlink permissions on Windows | Medium | Document Developer Mode requirement (if needed) |
| Existing models/ has content | Medium | Safe backup/rename, never delete data |
| Custom node still doesn't work | Low | Not our problem - node is broken |

---

## Future Enhancements

**Not included in MVP, but possible later:**

1. **Automated migration command**
   - `comfydock migrate-to-symlinks`
   - Scan all environments
   - Remove YAML + create symlinks

2. **Symlink health check**
   - `comfydock doctor`
   - Verify all symlinks valid
   - Detect and fix broken links

3. **Per-environment model overrides**
   - Allow environment-specific models directory
   - Override global default
   - Advanced use case

---

## Conclusion

This refactor **eliminates a fundamental architecture flaw** by aligning with how the ComfyUI ecosystem actually works. Symlinks are simpler, more reliable, and universally compatible.

**Key Benefits:**
- ✅ Fixes custom node model path issues permanently
- ✅ Reduces code complexity (254 lines → ~150 lines)
- ✅ Eliminates workflow JSON path translation
- ✅ Future-proof against new custom nodes
- ✅ Matches community best practices

**Next Steps:**
1. Implement `ModelSymlinkManager`
2. Update `Environment` integration points
3. Remove `ModelPathManager`
4. Test on all platforms
5. Manually clean up test environments
6. Ship! 🚀
