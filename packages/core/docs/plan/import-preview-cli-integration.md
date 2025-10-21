# Import Preview CLI Integration Plan

## Executive Summary

This document outlines how to integrate the newly created `ImportAnalyzer` service into the CLI to provide users with a preview of what will be imported before committing to the operation.

**Goal:** Give users visibility into import contents (models, nodes, workflows) before choosing a download strategy, with smart defaults based on analysis.

**Status:**
- ✅ Backend complete: `ImportAnalyzer` service implemented
- ✅ Workspace methods: `preview_import()` and `preview_git_import()` ready
- ⏳ CLI integration: Needs implementation (this document)

## Current State (As of Implementation)

### Backend Complete

**ImportAnalyzer Service** (`packages/core/src/comfydock_core/services/import_analyzer.py`)
- Created with full functionality
- Analyzes models, nodes, workflows from extracted .cec directory
- Returns rich `ImportAnalysis` dataclass with:
  - Model breakdown (available locally, needs download, missing sources)
  - Node breakdown (registry, development, git)
  - Workflow breakdown (required vs optional models)
  - Smart recommendation: `get_download_strategy_recommendation()`

**Workspace Preview Methods** (`packages/core/src/comfydock_core/core/workspace.py`)
- `preview_import(tarball_path)` - Lines 269-291
  - Extracts to temp dir, analyzes, cleans up
- `preview_git_import(git_url, branch)` - Lines 293-319
  - Clones to temp dir, analyzes, cleans up
- `import_analyzer` cached property - Lines 123-130

**Tests** (`packages/core/tests/unit/services/test_import_analyzer.py`)
- Comprehensive unit tests covering all analysis scenarios
- All existing tests still passing (493 tests, 0 failures)

### CLI Current Behavior

**File:** `packages/cli/comfydock_cli/global_commands.py`

**Method:** `import_env()` (lines 150-292)

**Current flow:**
1. Detect git URL vs tarball
2. Prompt for environment name
3. **Prompt for model strategy (lines 187-194)**
   - Shows generic menu: all/required/skip
   - No context about what models actually need downloading
4. Run import with chosen strategy
5. Show progress via callbacks

**Problem:** User chooses strategy blind, without knowing:
- How many models need downloading
- Total download size
- Which models are already available
- Whether any models lack download sources

## Proposed User Experience

### Default Flow (Auto-Preview)

```
$ comfydock import bundle.tar.gz

Environment name: my-workflow

📋 Analyzing import...

📋 Import Preview

ComfyUI: v0.2.7 (release)
Workflows: 3 workflow(s)
Custom Nodes: 5 node(s) (2 registry, 1 development, 2 git)

Models:
  • 15 total model(s)
  • 12 already available ✓
  • 2 need downloading (10.5 GB)
  • 1 missing source ⚠️

Model download strategy:
  [1] all      - Download 2 models (10.5 GB)
  [2] required - Download required models only
  [3] skip     - Skip downloads (resolve later)

  ⚠️  Note: 1 model(s) have no source - must be provided manually

Choice [1]/2/3:
```

### Fast Path (Skip Preview)

```bash
# Power users can bypass preview with flags
comfydock import bundle.tar.gz --name myenv --strategy all
```

### Preview-Only Mode

```bash
# Dry-run analysis without importing
comfydock import --preview bundle.tar.gz

# Shows analysis then exits without importing
```

## Implementation Guide

### Step 1: Add CLI Helper Methods

**File:** `packages/cli/comfydock_cli/global_commands.py`

**Location:** After `import_env()` method (around line 293)

#### Helper 1: Display Preview

```python
def _display_import_preview(self, analysis) -> None:
    """Display import analysis in readable format.

    Args:
        analysis: ImportAnalysis object from preview
    """
    print("\n📋 Import Preview\n")

    # ComfyUI version
    if analysis.comfyui_version:
        version_type = analysis.comfyui_version_type or "unknown"
        print(f"ComfyUI: {analysis.comfyui_version} ({version_type})")

    # Workflows
    print(f"Workflows: {analysis.total_workflows} workflow(s)")

    # Nodes
    if analysis.total_nodes > 0:
        parts = []
        if analysis.registry_nodes > 0:
            parts.append(f"{analysis.registry_nodes} registry")
        if analysis.dev_nodes > 0:
            parts.append(f"{analysis.dev_nodes} development")
        if analysis.git_nodes > 0:
            parts.append(f"{analysis.git_nodes} git")
        node_detail = f" ({', '.join(parts)})" if parts else ""
        print(f"Custom Nodes: {analysis.total_nodes} node(s){node_detail}")
    else:
        print("Custom Nodes: None")

    # Models
    if analysis.total_models > 0:
        print(f"\nModels:")
        print(f"  • {analysis.total_models} total model(s)")

        if analysis.models_locally_available > 0:
            print(f"  • {analysis.models_locally_available} already available ✓")

        if analysis.models_needing_download > 0:
            print(f"  • {analysis.models_needing_download} need downloading")

        if analysis.models_without_sources > 0:
            print(f"  • {analysis.models_without_sources} missing source ⚠️")
    else:
        print("\nModels: None")

    print()
```

#### Helper 2: Smart Strategy Prompt

```python
def _prompt_model_strategy(self, analysis) -> str:
    """Prompt for model download strategy with context-aware defaults.

    Args:
        analysis: ImportAnalysis object from preview

    Returns:
        Strategy string: "all", "required", or "skip"
    """
    # If no models need downloading, auto-skip
    if not analysis.needs_model_downloads:
        print("✓ All models available locally - no downloads needed\n")
        return "skip"

    # Show strategy menu with context
    print("Model download strategy:")

    if analysis.models_without_sources > 0:
        # Has models without sources - explain limitation
        print(f"  [1] all      - Download {analysis.models_needing_download} available model(s)")
        print(f"  [2] required - Download required models only")
        print(f"  [3] skip     - Skip downloads (resolve {analysis.models_without_sources} manually)")
        print(f"\n  ⚠️  Note: {analysis.models_without_sources} model(s) have no source - must be provided manually\n")
    else:
        # All models have sources
        print(f"  [1] all      - Download {analysis.models_needing_download} model(s)")
        print(f"  [2] required - Download required models only")
        print(f"  [3] skip     - Skip downloads (resolve later)\n")

    # Get recommendation from analysis
    recommended = analysis.get_download_strategy_recommendation()
    default_map = {"all": "1", "required": "2", "skip": "3"}
    default = default_map.get(recommended, "1")

    # Prompt user
    choice = input(f"Choice [{default}]/1/2/3: ").strip() or default

    strategy_map = {"1": "all", "2": "required", "3": "skip"}
    return strategy_map.get(choice, "all")
```

### Step 2: Modify `import_env()` Method

**File:** `packages/cli/comfydock_cli/global_commands.py`

**Method:** `import_env()` (lines 150-292)

**Changes:**

#### A. Add Strategy Flag to CLI Arguments

This change happens in the CLI argument parser (likely in `packages/cli/comfydock_cli/cli.py`):

```python
import_parser.add_argument(
    '--strategy',
    choices=['all', 'required', 'skip'],
    help='Model download strategy (skips preview if specified)'
)

import_parser.add_argument(
    '--preview',
    action='store_true',
    help='Show preview without importing'
)
```

#### B. Replace Lines 186-194 (Current Strategy Prompt)

**Current code to replace:**
```python
# Ask for model download strategy
print("\nModel download strategy:")
print("  1. all      - Download all models with sources")
print("  2. required - Download only required models")
print("  3. skip     - Skip all downloads (can resolve later)")
strategy_choice = input("Choice (1-3) [1]: ").strip() or "1"

strategy_map = {"1": "all", "2": "required", "3": "skip"}
strategy = strategy_map.get(strategy_choice, "all")
```

**New code:**
```python
# Check for preview-only mode
if hasattr(args, 'preview') and args.preview:
    # Preview-only mode - show analysis and exit
    print("\n📋 Analyzing import...")
    if is_git:
        analysis = self.workspace.preview_git_import(
            args.path,
            branch=getattr(args, 'branch', None)
        )
    else:
        analysis = self.workspace.preview_import(Path(args.path))

    self._display_import_preview(analysis)
    print("Preview complete - no import performed")
    return 0

# Check if strategy provided via flag
if hasattr(args, 'strategy') and args.strategy:
    # Skip preview - use provided strategy
    strategy = args.strategy
    print(f"\nUsing strategy: {strategy}")
else:
    # Run preview and smart prompt
    print("\n📋 Analyzing import...")

    try:
        if is_git:
            analysis = self.workspace.preview_git_import(
                args.path,
                branch=getattr(args, 'branch', None)
            )
        else:
            analysis = self.workspace.preview_import(Path(args.path))

        # Display preview
        self._display_import_preview(analysis)

        # Smart strategy prompt
        strategy = self._prompt_model_strategy(analysis)

    except Exception as e:
        # Preview failed - fall back to manual prompt
        print(f"⚠️  Could not analyze import: {e}")
        print("\nModel download strategy:")
        print("  1. all      - Download all models with sources")
        print("  2. required - Download only required models")
        print("  3. skip     - Skip all downloads")
        choice = input("Choice (1-3) [1]: ").strip() or "1"
        strategy_map = {"1": "all", "2": "required", "3": "skip"}
        strategy = strategy_map.get(choice, "all")
```

### Step 3: Add Required Imports

**File:** `packages/cli/comfydock_cli/global_commands.py`

**Location:** Top of file (around line 14)

Add:
```python
from comfydock_core.services.import_analyzer import ImportAnalysis
```

Note: This import is optional since we're using it via `workspace.preview_import()` which returns the object. But it's good for type hints if needed.

### Step 4: Update CLI Argument Parser

**File:** `packages/cli/comfydock_cli/cli.py` (or wherever import args are defined)

Find the import subcommand parser and add:

```python
# Add to import command parser
import_parser.add_argument(
    '--strategy',
    choices=['all', 'required', 'skip'],
    help='Model download strategy (skips preview if specified)'
)

import_parser.add_argument(
    '--preview',
    action='store_true',
    help='Show preview and exit without importing'
)

import_parser.add_argument(
    '--name',
    help='Environment name (skips interactive prompt)'
)
```

### Step 5: Handle Environment Name Prompt

**Location:** `import_env()` method, lines 177-184

**Current code:**
```python
# Get environment name from args or prompt
if hasattr(args, 'name') and args.name:
    env_name = args.name
else:
    env_name = input("Environment name: ").strip()
    if not env_name:
        print("✗ Environment name required")
        return 1
```

**Change to handle preview mode:**
```python
# Get environment name from args or prompt (skip if preview-only)
if hasattr(args, 'preview') and args.preview:
    env_name = None  # Not needed for preview
elif hasattr(args, 'name') and args.name:
    env_name = args.name
else:
    env_name = input("Environment name: ").strip()
    if not env_name:
        print("✗ Environment name required")
        return 1
```

## Testing Plan

### Manual Testing

**Test Case 1: Normal Import with Preview**
```bash
cd packages/cli
COMFYDOCK_HOME=/tmp/test_workspace uv run comfydock import test.tar.gz
```
Expected:
1. Prompts for name
2. Shows "Analyzing import..."
3. Displays preview
4. Shows smart strategy prompt
5. Proceeds with import

**Test Case 2: Fast Path with Strategy Flag**
```bash
COMFYDOCK_HOME=/tmp/test_workspace uv run comfydock import test.tar.gz --name test --strategy all
```
Expected:
1. Skips name prompt
2. Skips preview
3. Prints "Using strategy: all"
4. Proceeds with import

**Test Case 3: Preview-Only Mode**
```bash
COMFYDOCK_HOME=/tmp/test_workspace uv run comfydock import --preview test.tar.gz
```
Expected:
1. Skips name prompt
2. Shows "Analyzing import..."
3. Displays preview
4. Prints "Preview complete - no import performed"
5. Exits (no import)

**Test Case 4: Git Import with Preview**
```bash
COMFYDOCK_HOME=/tmp/test_workspace uv run comfydock import https://github.com/user/env.git
```
Expected:
1. Detects git URL
2. Prompts for name
3. Shows "Analyzing import..."
4. Uses `preview_git_import()`
5. Displays preview
6. Proceeds with import

**Test Case 5: Preview Failure Fallback**
- Use corrupted tarball or invalid git repo
- Should catch exception and fall back to manual strategy prompt

### Automated Testing

Create integration test:

**File:** `packages/core/tests/integration/test_import_preview_cli.py`

```python
"""Integration tests for import preview CLI functionality."""
import tempfile
from pathlib import Path
import pytest

def test_preview_import_shows_analysis(sample_workspace, sample_tarball):
    """Test that preview_import returns analysis without importing."""
    # Should not create environment, just return analysis
    analysis = sample_workspace.preview_import(sample_tarball)

    assert analysis.total_models >= 0
    assert analysis.total_nodes >= 0
    assert analysis.total_workflows >= 0

    # Verify no environment created
    assert not (sample_workspace.paths.environments / "preview_test").exists()

def test_preview_git_import_cleans_up_temp(sample_workspace, sample_git_url):
    """Test that preview_git_import cleans up temp directory."""
    import tempfile
    import os

    # Count temp dirs before
    temp_count_before = len(os.listdir(tempfile.gettempdir()))

    # Run preview
    analysis = sample_workspace.preview_git_import(sample_git_url)

    # Count temp dirs after
    temp_count_after = len(os.listdir(tempfile.gettempdir()))

    # Should have cleaned up (may vary slightly due to other processes)
    assert abs(temp_count_after - temp_count_before) <= 1
```

## Edge Cases to Handle

### 1. Invalid Tarball/Git URL

**Scenario:** User provides corrupted tarball or invalid git URL

**Handling:**
```python
try:
    analysis = self.workspace.preview_import(tarball_path)
except Exception as e:
    print(f"⚠️  Could not analyze import: {e}")
    # Fall back to manual strategy prompt
```

### 2. Missing Model File Sizes

**Scenario:** Models in pyproject.toml don't have file_size metadata

**Handling:** Don't try to display total GB, just show count:
```python
if analysis.models_needing_download > 0:
    print(f"  • {analysis.models_needing_download} need downloading")
    # Skip size display if not available
```

### 3. Preview Timeout

**Scenario:** Large tarball or slow git clone for preview

**Handling:** Add timeout to preview operations:
```python
import signal

# Set 30-second timeout for preview
signal.alarm(30)
try:
    analysis = self.workspace.preview_import(tarball_path)
    signal.alarm(0)  # Cancel alarm
except TimeoutError:
    print("⚠️  Preview timed out - proceeding without analysis")
    # Fall back to manual prompt
```

### 4. Empty Environment

**Scenario:** Import has no models, nodes, or workflows

**Handling:** Already handled in `_display_import_preview()`:
```python
if analysis.total_models == 0:
    print("\nModels: None")
```

## File Reference Summary

### Files to Modify

1. **packages/cli/comfydock_cli/global_commands.py**
   - Add `_display_import_preview()` helper (after line 293)
   - Add `_prompt_model_strategy()` helper (after _display_import_preview)
   - Modify `import_env()` method (lines 150-292)
     - Replace lines 177-184 (name prompt) to handle preview mode
     - Replace lines 186-194 (strategy prompt) with preview logic

2. **packages/cli/comfydock_cli/cli.py** (or argument parser location)
   - Add `--strategy` argument to import command
   - Add `--preview` argument to import command
   - Add `--name` argument to import command (if not exists)

### Files Already Complete (No Changes Needed)

1. **packages/core/src/comfydock_core/services/import_analyzer.py**
   - ImportAnalyzer service - fully implemented

2. **packages/core/src/comfydock_core/core/workspace.py**
   - `preview_import()` method (lines 269-291)
   - `preview_git_import()` method (lines 293-319)
   - `import_analyzer` cached property (lines 123-130)

3. **packages/core/tests/unit/services/test_import_analyzer.py**
   - Comprehensive unit tests - all passing

### Dependencies

**Python Packages:** (already available)
- `tomlkit` - for parsing pyproject.toml
- `tempfile` - for temp directory operations
- No new dependencies required

**Core Services Used:**
- `ImportAnalyzer` from `comfydock_core.services.import_analyzer`
- `Workspace.preview_import()` / `preview_git_import()`

## Success Criteria

### Functional Requirements

- [ ] `comfydock import <tarball>` shows preview before strategy prompt
- [ ] `comfydock import --preview <tarball>` shows preview and exits
- [ ] `comfydock import <tarball> --strategy all` skips preview
- [ ] Preview shows: ComfyUI version, workflows, nodes, models
- [ ] Model breakdown shows: total, available, needs download, missing source
- [ ] Strategy prompt uses smart defaults from analysis
- [ ] Git imports work: `comfydock import <git-url>`
- [ ] Preview failure falls back gracefully to manual prompt
- [ ] Temp directories cleaned up after preview

### UX Requirements

- [ ] Preview displays in < 5 seconds for typical imports
- [ ] Preview follows existing CLI formatting patterns (emojis, indentation)
- [ ] Strategy prompt shows context (download count, warnings)
- [ ] Error messages are clear and actionable
- [ ] Fast path (--strategy flag) remains fast (no preview overhead)

### Code Quality

- [ ] No breaking changes to existing import flow
- [ ] Helper methods are < 50 lines each
- [ ] Error handling covers all edge cases
- [ ] Integration tests added for preview functionality
- [ ] All existing tests still pass

## Timeline Estimate

- Step 1 (Add helpers): 30 minutes
- Step 2 (Modify import_env): 45 minutes
- Step 3-4 (Imports and args): 15 minutes
- Step 5 (Name prompt): 10 minutes
- Testing (manual): 30 minutes
- Testing (automated): 20 minutes
- Edge cases and polish: 30 minutes

**Total: ~3 hours**

## Future Enhancements

After initial implementation, consider:

1. **Detailed Model View**
   - Flag: `--show-models` to list each model with sources
   - Interactive drill-down into model details

2. **Size Estimation**
   - Add file_size to ModelAnalysis
   - Show total download size in GB

3. **Source Validation**
   - Check if download URLs are reachable
   - Warn about broken sources during preview

4. **Security Analysis**
   - Flag untrusted git node sources
   - Warn about models from unknown hosts

5. **Export Preview**
   - Add `comfydock export --preview` to show what would be included
   - List models without sources before export

## References

- **Architecture Refactor Plan:** `packages/core/docs/plan/import-export-architecture-refactor.md`
- **ImportAnalyzer Implementation:** `packages/core/src/comfydock_core/services/import_analyzer.py`
- **ImportAnalyzer Tests:** `packages/core/tests/unit/services/test_import_analyzer.py`
- **Current Import Flow:** `packages/cli/comfydock_cli/global_commands.py:150-292`
- **Interactive Patterns:** `packages/cli/comfydock_cli/strategies/interactive.py`
