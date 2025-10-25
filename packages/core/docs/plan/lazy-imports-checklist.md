# Lazy Imports Implementation Checklist

Track progress implementing lazy imports optimization.

## Pre-Implementation

- [x] Benchmark current import times (baseline: ~150ms)
- [x] Identify heavy imports (model_downloader: 66ms, workflow: 74ms)
- [x] Create implementation plan
- [ ] Review plan with team/self

## Phase 1: Add lazy_loader Package

### 1.1 Install Dependency

- [ ] Update `packages/core/pyproject.toml`
  - Add `lazy-loader>=0.4` to dependencies list
- [ ] Run `cd packages/core && uv add lazy-loader`
- [ ] Verify: `uv pip list | grep lazy-loader` shows version 0.4+

### 1.2 Root Package Lazy Loader

- [ ] Edit `packages/core/src/comfydock_core/__init__.py`
  - Add `import lazy_loader as lazy`
  - Add `__getattr__, __dir__, __all__ = lazy.attach(...)`
  - List all submodules to lazy-load
- [ ] Test import still works: `python -c "import comfydock_core"`
- [ ] Run quick benchmark: `python -c "import time; s=time.time(); import comfydock_cli.cli; print(f'{(time.time()-s)*1000:.0f}ms')"`
  - Record result: _____ms (expect ~100ms if successful)

### 1.3 Submodule Lazy Loaders

- [ ] Update `packages/core/src/comfydock_core/caching/__init__.py`
  - Convert to lazy.attach() pattern
  - Test: `python -c "from comfydock_core.caching import APICacheManager"`

- [ ] Update `packages/core/src/comfydock_core/clients/__init__.py`
  - Convert to lazy.attach() pattern
  - Test: `python -c "from comfydock_core.clients import ComfyRegistryClient"`

- [ ] Create `packages/core/src/comfydock_core/services/__init__.py`
  - Add lazy.attach() with ModelDownloader, RegistryDataManager, etc.
  - Test: `python -c "from comfydock_core.services import ModelDownloader"`

- [ ] Create `packages/core/src/comfydock_core/managers/__init__.py`
  - Add lazy.attach() with all manager classes
  - Test: `python -c "from comfydock_core.managers import NodeManager"`

- [ ] Create `packages/core/src/comfydock_core/analyzers/__init__.py`
  - Add lazy.attach() with all analyzer classes
  - Test: `python -c "from comfydock_core.analyzers import ModelScanner"`

- [ ] Optional: Update `packages/core/src/comfydock_core/models/__init__.py` if it exists
  - Convert to lazy pattern
  - Test type imports still work

### Checkpoint: Measure Impact

- [ ] Run benchmark script: `uv run python packages/core/scripts/benchmark_imports.py`
- [ ] Record results:
  - `comfydock_cli.cli`: _____ms (target: <80ms)
  - `comfydock_core`: _____ms (target: <10ms)
- [ ] Test help command: `uv run comfydock --help` (should feel instant)
- [ ] Decision point: If >40% improvement, proceed to Phase 2. Otherwise debug.

## Phase 2: Defer CLI Heavy Imports

### 2.1 env_commands.py

- [ ] Edit `packages/cli/comfydock_cli/env_commands.py`
  - Line 8-12: Move formatters/strategies to TYPE_CHECKING
  - Line 634: Add lazy import in `node_add()` method
  - Line 1209: Add lazy import in `workflow_resolve()` method
- [ ] Test: `uv run comfydock node add --help`
- [ ] Test: `uv run comfydock workflow resolve --help`

### 2.2 global_commands.py

- [ ] Edit `packages/cli/comfydock_cli/global_commands.py`
  - Lines 7-9: Move to TYPE_CHECKING
  - Line 26-28: Add lazy import in `workspace` property
  - Line 149: Add lazy import in `import_env()` method
  - Line 295: Add lazy import in `export_env()` method
- [ ] Test: `uv run comfydock import --help`
- [ ] Test: `uv run comfydock export --help`

### 2.3 cli_utils.py

- [ ] Edit `packages/cli/comfydock_cli/cli_utils.py`
  - Move WorkspaceFactory import to TYPE_CHECKING
  - Add lazy import inside `get_workspace_or_exit()` function
- [ ] Test: `uv run comfydock list`
- [ ] Test: `uv run comfydock status`

### Checkpoint: Measure Final Impact

- [ ] Run benchmark again: `uv run python packages/core/scripts/benchmark_imports.py`
- [ ] Record results:
  - `comfydock_cli.cli`: _____ms (target: 50-70ms)
- [ ] Compare to baseline (should be 2-3x faster)

## Phase 3: Testing & Validation

### Create Test Infrastructure

- [ ] Create `packages/core/scripts/benchmark_imports.py`
  - Copy from implementation plan
  - Test: `uv run python packages/core/scripts/benchmark_imports.py`

- [ ] Create `packages/core/tests/test_lazy_imports.py`
  - Add test_lazy_core_package()
  - Add test_lazy_managers()
  - Add test_cli_import_speed()
- [ ] Run: `uv run pytest packages/core/tests/test_lazy_imports.py -v`

### Integration Testing

- [ ] Test all major CLI commands:
  - [ ] `uv run comfydock --help`
  - [ ] `uv run comfydock list`
  - [ ] `uv run comfydock status`
  - [ ] `uv run comfydock create test-env`
  - [ ] `uv run comfydock node add comfyui-manager`
  - [ ] `uv run comfydock workflow list`
  - [ ] `uv run comfydock model index status`

- [ ] Run full test suite:
  - [ ] `uv run pytest packages/core/tests/ -v`
  - [ ] `uv run pytest packages/cli/tests/ -v`

- [ ] Test type checking:
  - [ ] `uv run mypy packages/core/src/comfydock_core/`

### Performance Validation

- [ ] Confirm improvements:
  - [ ] `--help` command: ≥2x faster
  - [ ] `list` command: ≥2x faster
  - [ ] Work commands (node add, etc.): no regression

## Documentation

- [ ] Update CHANGELOG.md with performance improvements
- [ ] Add note to README about lazy imports (optional)
- [ ] Archive this checklist when complete

## Rollback (if needed)

If issues arise, rollback steps:

- [ ] `cd packages/core && uv remove lazy-loader`
- [ ] `git checkout HEAD -- packages/core/src/comfydock_core/__init__.py`
- [ ] `git checkout HEAD -- packages/core/src/comfydock_core/caching/__init__.py`
- [ ] `git checkout HEAD -- packages/core/src/comfydock_core/clients/__init__.py`
- [ ] `rm packages/core/src/comfydock_core/services/__init__.py`
- [ ] `rm packages/core/src/comfydock_core/managers/__init__.py`
- [ ] `rm packages/core/src/comfydock_core/analyzers/__init__.py`
- [ ] `git checkout HEAD -- packages/cli/comfydock_cli/`

## Results Summary

**Before:**
- Import time: ~150ms
- Help command: slow

**After:**
- Import time: _____ms
- Help command: _____ms
- Improvement: _____x faster

**Issues encountered:**
- (list any issues here)

**Lessons learned:**
- (capture insights for future optimizations)

---

## Quick Commands Reference

```bash
# Benchmark import time
python3 -c "import time; s=time.time(); import comfydock_cli.cli; print(f'{(time.time()-s)*1000:.0f}ms')"

# Detailed import profile
python3 -X importtime -c "import comfydock_cli.cli" 2>&1 | grep comfydock

# Test CLI
uv run comfydock --help

# Run tests
uv run pytest packages/core/tests/test_lazy_imports.py -v

# Type check
uv run mypy packages/core/src/comfydock_core/
```
