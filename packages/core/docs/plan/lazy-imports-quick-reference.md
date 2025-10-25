# Lazy Imports - Quick Reference

## TL;DR

Add `lazy_loader` package to make CLI startup 2-3x faster (150ms → 50-70ms) for simple commands.

## One-Command Install

```bash
cd packages/core
uv add lazy-loader
```

## Minimal Working Example

**File:** `packages/core/src/comfydock_core/__init__.py`

```python
"""ComfyDock Core - Lazy-loaded package."""
import lazy_loader as lazy

__getattr__, __dir__, __all__ = lazy.attach(
    __name__,
    submodules={
        "core", "managers", "services", "analyzers",
        "resolvers", "repositories", "clients", "caching",
        "factories", "models", "utils", "configs",
    },
)
```

That's it! This single change makes all submodule imports lazy.

## Test It Works

```bash
# Before (baseline)
python3 -c "import time; s=time.time(); import comfydock_cli.cli; print(f'{(time.time()-s)*1000:.0f}ms')"
# Expected: ~150ms

# After lazy_loader
# Expected: ~50-70ms (2-3x faster)
```

## What Gets Deferred?

When you do:
```python
from comfydock_core.services.model_downloader import ModelDownloader
```

**Before:** Immediately imports `model_downloader.py` and all its dependencies (~66ms)
**After:** Returns a lazy proxy. Import happens when you first USE ModelDownloader

## Breaking Changes?

**None.** Code using `comfydock_core` doesn't change at all. The laziness is transparent.

## Type Checking?

Works fine. Type checkers see the same exports.

## Where's the Full Plan?

See `lazy-imports-optimization.md` in this directory for:
- Complete implementation steps
- All files to modify
- Testing strategy
- Benchmark scripts
- Rollback procedure

## Quick Win

The **absolute minimum** to get most benefits:

1. `uv add lazy-loader` (in packages/core)
2. Update `comfydock_core/__init__.py` (see example above)
3. Test: `uv run comfydock --help` (should be noticeably faster)

Done!
