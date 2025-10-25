# Lazy Imports Optimization - Implementation Plan

## Problem Statement

The CLI currently has a ~150ms import overhead just to display help or run simple commands. This is caused by eager importing of the entire `comfydock_core` module tree, which includes heavy dependencies like aiohttp, requests, yaml parsing, and all managers/services/analyzers.

### Current Import Profile (Baseline)

```bash
# Total CLI import time
python3 -c "import comfydock_cli.cli"  # ~150ms

# Import cascade:
comfydock_cli.cli
  → comfydock_cli.env_commands
    → comfydock_core.models.exceptions
    → comfydock_core.utils.uv_error_handler
  → comfydock_cli.global_commands
    → comfydock_core.core.workspace
    → comfydock_core.factories.workspace_factory
    → comfydock_core.models.protocols
      → [imports entire tree of managers, services, analyzers]
```

**Key bottlenecks identified:**
- `comfydock_core.models.workflow`: 74ms cumulative
- `comfydock_core.services.model_downloader`: 66ms cumulative
- `comfydock_core.repositories.node_mappings_repository`: 14ms cumulative
- `comfydock_core.analyzers.model_scanner`: 12ms cumulative
- `comfydock_core.models.node_mapping`: 8ms cumulative

Most of these modules are NOT needed for simple commands like `--help`, `status`, or `list`.

## Solution: Multi-Layered Lazy Import Strategy

We'll implement lazy imports at three levels:

1. **Package-level lazy loading** using `lazy_loader` for core modules
2. **Deferred CLI imports** moving heavy imports into command methods
3. **Strategic TYPE_CHECKING guards** to prevent type-time imports

Expected improvement: **2-3x faster startup** (~50-70ms for simple commands)

---

## Implementation Strategy

### Phase 1: Add lazy_loader to Core Package

**Goal:** Make core package modules lazy-loadable without changing caller code.

#### 1.1 Add Dependency

**File:** `packages/core/pyproject.toml`

```toml
dependencies = [
    "aiohttp>=3.9.0",
    "blake3>=1.0.5",
    "lazy-loader>=0.4",  # ADD THIS
    "packaging>=25.0",
    # ... rest unchanged
]
```

**Installation:**
```bash
cd packages/core
uv add lazy-loader
```

#### 1.2 Create Root Package Lazy Loader

**File:** `packages/core/src/comfydock_core/__init__.py`

**Current state:** Empty or minimal exports

**New implementation:**
```python
"""ComfyDock Core - Lazy-loaded package."""
import lazy_loader as lazy

# Define submodules that should be lazy-loaded
__getattr__, __dir__, __all__ = lazy.attach(
    __name__,
    submodules={
        "core",
        "managers",
        "services",
        "analyzers",
        "resolvers",
        "repositories",
        "clients",
        "caching",
        "factories",
        "models",
        "utils",
        "configs",
        "validation",
        "strategies",
        "integrations",
        "logging",
    },
)

# Package metadata
__version__ = "1.0.0"
```

**Rationale:** This makes ALL submodule imports lazy. When someone does `from comfydock_core.services import X`, the `services` module won't be imported until `X` is actually accessed.

#### 1.3 Update Submodule __init__.py Files

Apply lazy loading to major submodules that have heavy imports.

**Files to update:**

1. **`packages/core/src/comfydock_core/caching/__init__.py`**

   Current:
   ```python
   from .api_cache import APICacheManager
   from .base import CacheBase, ContentCacheBase
   from .comfyui_cache import ComfyUICacheManager, ComfyUISpec
   from .custom_node_cache import CachedNodeInfo, CustomNodeCacheManager
   ```

   New:
   ```python
   """Caching modules - lazy loaded."""
   import lazy_loader as lazy

   __getattr__, __dir__, __all__ = lazy.attach(
       __name__,
       submod_attrs={
           "api_cache": ["APICacheManager"],
           "base": ["CacheBase", "ContentCacheBase"],
           "comfyui_cache": ["ComfyUICacheManager", "ComfyUISpec"],
           "custom_node_cache": ["CachedNodeInfo", "CustomNodeCacheManager"],
       }
   )
   ```

2. **`packages/core/src/comfydock_core/clients/__init__.py`**

   Current:
   ```python
   from .registry_client import ComfyRegistryClient
   from .github_client import GitHubClient, GitHubRelease, GitHubRepoInfo
   ```

   New:
   ```python
   """API clients - lazy loaded."""
   import lazy_loader as lazy

   __getattr__, __dir__, __all__ = lazy.attach(
       __name__,
       submod_attrs={
           "registry_client": ["ComfyRegistryClient"],
           "github_client": ["GitHubClient", "GitHubRelease", "GitHubRepoInfo"],
       }
   )
   ```

3. **Create `packages/core/src/comfydock_core/services/__init__.py`** (currently doesn't exist)

   ```python
   """Services - lazy loaded."""
   import lazy_loader as lazy

   __getattr__, __dir__, __all__ = lazy.attach(
       __name__,
       submod_attrs={
           "model_downloader": ["ModelDownloader", "DownloadRequest", "DownloadResult"],
           "registry_data_manager": ["RegistryDataManager"],
           "node_lookup_service": ["NodeLookupService"],
       }
   )
   ```

4. **Create `packages/core/src/comfydock_core/managers/__init__.py`** (currently doesn't exist)

   ```python
   """Managers - lazy loaded."""
   import lazy_loader as lazy

   __getattr__, __dir__, __all__ = lazy.attach(
       __name__,
       submod_attrs={
           "node_manager": ["NodeManager"],
           "workflow_manager": ["WorkflowManager"],
           "pyproject_manager": ["PyprojectManager"],
           "uv_project_manager": ["UVProjectManager"],
           "git_manager": ["GitManager"],
           "model_symlink_manager": ["ModelSymlinkManager"],
           "model_download_manager": ["ModelDownloadManager"],
           "export_import_manager": ["ExportImportManager"],
       }
   )
   ```

5. **Create `packages/core/src/comfydock_core/analyzers/__init__.py`** (currently doesn't exist)

   ```python
   """Analyzers - lazy loaded."""
   import lazy_loader as lazy

   __getattr__, __dir__, __all__ = lazy.attach(
       __name__,
       submod_attrs={
           "workflow_dependency_parser": ["WorkflowDependencyParser"],
           "custom_node_scanner": ["CustomNodeScanner"],
           "model_scanner": ["ModelScanner"],
           "node_classifier": ["NodeClassifier"],
           "git_change_parser": ["GitChangeParser"],
           "node_git_analyzer": ["NodeGitAnalyzer"],
           "status_scanner": ["StatusScanner"],
       }
   )
   ```

**Note:** For modules that currently have no `__init__.py` (like services/, managers/, analyzers/), create these files to enable lazy loading.

---

### Phase 2: Defer CLI Heavy Imports

**Goal:** Move expensive imports from module-level to method-level in CLI command handlers.

#### 2.1 Update env_commands.py

**File:** `packages/cli/comfydock_cli/env_commands.py`

**Lines to modify:**

**Before (lines 8-12):**
```python
from comfydock_core.models.exceptions import CDEnvironmentError, CDNodeConflictError, UVCommandError
from comfydock_core.utils.uv_error_handler import handle_uv_error

from .formatters.error_formatter import NodeErrorFormatter
from .strategies.interactive import InteractiveModelStrategy, InteractiveNodeStrategy
```

**After:**
```python
from typing import TYPE_CHECKING

from comfydock_core.models.exceptions import CDEnvironmentError, CDNodeConflictError, UVCommandError

if TYPE_CHECKING:
    from comfydock_core.utils.uv_error_handler import handle_uv_error
    from .formatters.error_formatter import NodeErrorFormatter
    from .strategies.interactive import InteractiveModelStrategy, InteractiveNodeStrategy
```

**Then update methods that use these imports:**

**Method `node_add()` (line 634):**
```python
def node_add(self, args, logger=None):
    """Add custom node(s) - directly modifies pyproject.toml."""
    from .formatters.error_formatter import NodeErrorFormatter  # Lazy import

    env = self._get_env(args)
    # ... rest unchanged
```

**Method `workflow_resolve()` (line 1209):**
```python
def workflow_resolve(self, args, logger=None):
    """Resolve workflow dependencies interactively."""
    from .strategies.interactive import InteractiveModelStrategy, InteractiveNodeStrategy  # Lazy import

    env = self._get_env(args)
    # ... rest unchanged
```

**Rationale:** These imports are only needed when specific commands run, not for `--help` or `status`.

#### 2.2 Update global_commands.py

**File:** `packages/cli/comfydock_cli/global_commands.py`

**Lines to modify:**

**Before (lines 7-9):**
```python
from comfydock_core.core.workspace import Workspace
from comfydock_core.factories.workspace_factory import WorkspaceFactory
from comfydock_core.models.protocols import ExportCallbacks, ImportCallbacks
```

**After:**
```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from comfydock_core.core.workspace import Workspace
    from comfydock_core.factories.workspace_factory import WorkspaceFactory
    from comfydock_core.models.protocols import ExportCallbacks, ImportCallbacks
```

**Update cached_property (line 26-28):**
```python
@cached_property
def workspace(self) -> "Workspace":
    from comfydock_core.factories.workspace_factory import WorkspaceFactory  # Lazy import
    return get_workspace_or_exit()
```

**Method `import_env()` - add lazy imports at top (line 149):**
```python
def import_env(self, args):
    """Import a ComfyDock environment from a tarball or git repository."""
    from pathlib import Path
    from comfydock_core.utils.git import is_git_url  # Lazy import
    from comfydock_core.models.protocols import ImportCallbacks  # Lazy import

    # ... rest unchanged
```

**Method `export_env()` - add lazy import (line 295):**
```python
def export_env(self, args):
    """Export a ComfyDock environment to a package."""
    from datetime import datetime
    from pathlib import Path
    from comfydock_core.models.protocols import ExportCallbacks  # Lazy import

    # ... rest unchanged
```

#### 2.3 Update cli_utils.py

**File:** `packages/cli/comfydock_cli/cli_utils.py`

**Current imports (assumed):**
```python
from comfydock_core.factories.workspace_factory import WorkspaceFactory
from comfydock_core.models.exceptions import CDWorkspaceNotFoundError
```

**New approach:**
```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from comfydock_core.core.workspace import Workspace

def get_workspace_or_exit() -> "Workspace":
    """Get workspace, lazy-importing factory only when called."""
    from comfydock_core.factories.workspace_factory import WorkspaceFactory
    from comfydock_core.models.exceptions import CDWorkspaceNotFoundError

    try:
        return WorkspaceFactory.create()
    except CDWorkspaceNotFoundError:
        # ... existing error handling
```

**Rationale:** `get_workspace_or_exit()` is only called by commands that actually need the workspace, not by `--help`.

---

### Phase 3: Strategic Model/Protocol Lazy Loading

**Goal:** Prevent heavy model classes from loading unless actually used.

#### 3.1 Review models/__init__.py

**File:** `packages/core/src/comfydock_core/models/__init__.py`

**If this file exists and eagerly imports models, convert to lazy:**

```python
"""Data models - lazy loaded."""
import lazy_loader as lazy

__getattr__, __dir__, __all__ = lazy.attach(
    __name__,
    submod_attrs={
        "environment": ["EnvironmentStatus", "GitStatus", "PackageSyncStatus"],
        "workflow": ["WorkflowNode", "WorkflowDependencies", "DetailedWorkflowStatus",
                     "ResolutionResult", "NodeInstallCallbacks", "BatchDownloadCallbacks"],
        "shared": ["NodeInfo", "NodePackage", "ModelSourceResult"],
        "exceptions": ["ComfyDockError", "CDNodeConflictError", "CDEnvironmentError",
                       "CDWorkspaceError", "UVCommandError"],
        "workspace_config": ["WorkspaceConfig"],
        "manifest": ["EnvironmentManifest"],
        "registry": ["RegistryNode"],
        "civitai": ["CivitAIModel"],
        "commit": ["CommitInfo"],
        "node_mapping": ["NodeMapping"],
        "system": ["SystemInfo"],
        "protocols": ["ExportCallbacks", "ImportCallbacks", "ModelResolutionStrategy"],
    }
)
```

#### 3.2 Update Core Imports in environment.py

**File:** `packages/core/src/comfydock_core/core/environment.py`

**Review lines 1-50** and ensure expensive imports are under `TYPE_CHECKING`:

Already good (line 7):
```python
from typing import TYPE_CHECKING
```

Check that heavy imports like these are deferred:
```python
if TYPE_CHECKING:
    from comfydock_core.models.protocols import (
        ExportCallbacks,
        ImportCallbacks,
        ModelResolutionStrategy,
        NodeResolutionStrategy,
        RollbackStrategy,
    )
    # ... etc
```

**Keep runtime imports minimal:**
```python
from ..analyzers.status_scanner import StatusScanner  # OK - used immediately
from ..managers.node_manager import NodeManager  # OK - created in __init__
# ... etc
```

**Rationale:** Environment is created lazily via factory, so these imports won't hurt. But keep protocols under TYPE_CHECKING.

---

## Testing & Validation

### Benchmark Script

**Create:** `packages/core/scripts/benchmark_imports.py`

```python
#!/usr/bin/env python3
"""Benchmark import times before and after lazy loading."""
import sys
import time
from pathlib import Path

def time_import(module_name: str) -> float:
    """Time how long it takes to import a module (fresh)."""
    import subprocess
    cmd = [
        sys.executable, "-c",
        f"import time; start = time.time(); import {module_name}; print((time.time() - start) * 1000)"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return float(result.stdout.strip())

def main():
    modules = [
        "comfydock_cli.cli",
        "comfydock_core",
        "comfydock_core.core.workspace",
        "comfydock_core.services.model_downloader",
        "comfydock_core.managers.workflow_manager",
    ]

    print("Import Time Benchmarks")
    print("=" * 60)

    for module in modules:
        try:
            elapsed = time_import(module)
            print(f"{module:50} {elapsed:6.1f}ms")
        except Exception as e:
            print(f"{module:50} ERROR: {e}")

    print("=" * 60)

if __name__ == "__main__":
    main()
```

**Usage:**
```bash
# Before lazy loading
uv run python packages/core/scripts/benchmark_imports.py > before.txt

# After lazy loading
uv run python packages/core/scripts/benchmark_imports.py > after.txt

# Compare
diff -u before.txt after.txt
```

### Test Coverage

**Create:** `packages/core/tests/test_lazy_imports.py`

```python
"""Test that lazy imports work correctly."""
import sys
import pytest

def test_lazy_core_package():
    """Test that comfydock_core uses lazy loading."""
    # Clear any cached imports
    for mod in list(sys.modules.keys()):
        if mod.startswith('comfydock_core'):
            del sys.modules[mod]

    # Import core package
    import comfydock_core

    # Services should NOT be loaded yet
    assert 'comfydock_core.services' not in sys.modules
    assert 'comfydock_core.services.model_downloader' not in sys.modules

    # Now access a service
    from comfydock_core.services import ModelDownloader

    # NOW it should be loaded
    assert 'comfydock_core.services.model_downloader' in sys.modules

def test_lazy_managers():
    """Test that managers are lazy-loaded."""
    for mod in list(sys.modules.keys()):
        if 'managers' in mod:
            del sys.modules[mod]

    import comfydock_core
    assert 'comfydock_core.managers.node_manager' not in sys.modules

    from comfydock_core.managers import NodeManager
    assert 'comfydock_core.managers.node_manager' in sys.modules

def test_cli_import_speed():
    """Test that CLI imports under 100ms (target)."""
    import subprocess
    import sys

    cmd = [
        sys.executable, "-c",
        "import time; start = time.time(); import comfydock_cli.cli; print((time.time() - start) * 1000)"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    elapsed = float(result.stdout.strip())

    # Should be under 100ms (currently ~150ms, target is ~50-70ms)
    assert elapsed < 100, f"CLI import took {elapsed}ms, expected < 100ms"
```

**Run:**
```bash
uv run pytest packages/core/tests/test_lazy_imports.py -v
```

### Integration Testing

Test that actual CLI commands still work:

```bash
# These should all work without errors
uv run comfydock --help
uv run comfydock list
uv run comfydock status
uv run comfydock node add comfyui-manager
```

---

## Implementation Checklist

- [ ] **Phase 1: Add lazy_loader**
  - [ ] Update `packages/core/pyproject.toml` - add `lazy-loader>=0.4`
  - [ ] Run `uv add lazy-loader` in packages/core
  - [ ] Update `comfydock_core/__init__.py` with lazy.attach()
  - [ ] Update `comfydock_core/caching/__init__.py`
  - [ ] Update `comfydock_core/clients/__init__.py`
  - [ ] Create `comfydock_core/services/__init__.py`
  - [ ] Create `comfydock_core/managers/__init__.py`
  - [ ] Create `comfydock_core/analyzers/__init__.py`
  - [ ] Optional: Update `comfydock_core/models/__init__.py` if it exists

- [ ] **Phase 2: Defer CLI imports**
  - [ ] Update `env_commands.py` - move formatters/strategies to method-level
  - [ ] Update `global_commands.py` - move protocols to TYPE_CHECKING
  - [ ] Update `cli_utils.py` - lazy import WorkspaceFactory

- [ ] **Phase 3: Testing**
  - [ ] Create `scripts/benchmark_imports.py`
  - [ ] Run baseline benchmark (save output)
  - [ ] Create `tests/test_lazy_imports.py`
  - [ ] Run integration tests (`comfydock --help`, etc.)
  - [ ] Run full test suite: `uv run pytest packages/core/tests/`

- [ ] **Validation**
  - [ ] Compare before/after benchmarks (expect 2-3x improvement)
  - [ ] Verify all CLI commands still work
  - [ ] Check type checking still works: `uv run mypy packages/core/src/comfydock_core/`

---

## Expected Results

### Before
```
comfydock_cli.cli                                   150.0ms
comfydock_core                                      145.0ms
comfydock_core.services.model_downloader            66.0ms
```

### After
```
comfydock_cli.cli                                    50-70ms  (2-3x faster)
comfydock_core                                       5-10ms   (lazy stub only)
comfydock_core.services.model_downloader             0ms      (not imported for simple commands)
```

### Command Impact

| Command | Before | After | Benefit |
|---------|--------|-------|---------|
| `comfydock --help` | ~150ms | ~50ms | 3x faster |
| `comfydock list` | ~150ms | ~60ms | 2.5x faster |
| `comfydock status` | ~150ms | ~150ms | No change (needs full imports) |
| `comfydock node add X` | ~150ms | ~150ms | No change (needs full imports) |

**Key insight:** Simple informational commands become much faster, while commands that actually do work remain unchanged (since they need those imports anyway).

---

## Rollback Plan

If lazy loading causes issues:

1. **Revert pyproject.toml:**
   ```bash
   uv remove lazy-loader
   ```

2. **Revert `__init__.py` files:**
   ```bash
   git checkout HEAD -- packages/core/src/comfydock_core/__init__.py
   git checkout HEAD -- packages/core/src/comfydock_core/caching/__init__.py
   git checkout HEAD -- packages/core/src/comfydock_core/clients/__init__.py
   # Delete newly created __init__.py files
   rm packages/core/src/comfydock_core/services/__init__.py
   rm packages/core/src/comfydock_core/managers/__init__.py
   rm packages/core/src/comfydock_core/analyzers/__init__.py
   ```

3. **Revert CLI changes:**
   ```bash
   git checkout HEAD -- packages/cli/comfydock_cli/env_commands.py
   git checkout HEAD -- packages/cli/comfydock_cli/global_commands.py
   git checkout HEAD -- packages/cli/comfydock_cli/cli_utils.py
   ```

---

## References

### Documentation
- **lazy_loader GitHub:** https://github.com/scientific-python/lazy-loader
- **SPEC 1 - Scientific Python:** https://scientific-python.org/specs/spec-0001/
- **PEP 690 (rejected but educational):** https://peps.python.org/pep-0690/

### Key Files Modified

**Core Package:**
- `packages/core/pyproject.toml` - add dependency
- `packages/core/src/comfydock_core/__init__.py` - root lazy loader
- `packages/core/src/comfydock_core/caching/__init__.py`
- `packages/core/src/comfydock_core/clients/__init__.py`
- `packages/core/src/comfydock_core/services/__init__.py` (new)
- `packages/core/src/comfydock_core/managers/__init__.py` (new)
- `packages/core/src/comfydock_core/analyzers/__init__.py` (new)

**CLI Package:**
- `packages/cli/comfydock_cli/env_commands.py` - defer imports (lines 8-12, 634, 1209)
- `packages/cli/comfydock_cli/global_commands.py` - defer imports (lines 7-9, 26-28, 149, 295)
- `packages/cli/comfydock_cli/cli_utils.py` - defer WorkspaceFactory import

**Testing:**
- `packages/core/scripts/benchmark_imports.py` (new)
- `packages/core/tests/test_lazy_imports.py` (new)

### Import Profiling Commands

```bash
# Detailed import timing
python3 -X importtime -c "import comfydock_cli.cli" 2>&1 | grep "comfydock"

# Total import time
python3 -c "import time; start = time.time(); import comfydock_cli.cli; print(f'{(time.time() - start)*1000:.1f}ms')"

# Find slowest imports
python3 -X importtime -c "import comfydock_cli.cli" 2>&1 | awk '{print $4, $6, $7}' | sort -k1 -rn | head -20
```

---

## Success Criteria

✅ CLI help command (`comfydock --help`) runs in under 70ms (currently ~150ms)
✅ All existing tests pass
✅ Type checking still works (mypy)
✅ No runtime errors in lazy-loaded modules
✅ Backward compatible - no API changes for callers

---

## Notes for Next Session

1. Start with **Phase 1.1-1.2** (add lazy_loader and update root `__init__.py`)
2. Run benchmarks immediately to see impact
3. If successful, proceed with Phase 1.3 (submodule `__init__.py` files)
4. Save Phase 2 (CLI changes) for last - they have the most risk of breaking things
5. Test frequently - run `uv run comfydock --help` after each change

**Philosophy:** Implement incrementally, test after each step, rollback if issues arise. The root package lazy loader (Phase 1.2) alone might give us 50% of the benefit.
