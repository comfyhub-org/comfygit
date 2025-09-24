# Codebase Trimming Plan for New Architecture

## Overview

This document outlines what components need to be removed, simplified, or refactored to align with our new one-way, lazy-resolution architecture for workflow management.

## Components to Remove Entirely

### 1. Bidirectional Sync System

**Files to Remove:**
- All sync-related enums and methods in `workflow_manager.py`

**Code to Remove:**
```python
# workflow_manager.py
class SyncAction(Enum)          # REMOVE: Lines 35-42
class SyncStatus(Enum)          # REMOVE: Lines 44-52

def sync_workflows(self)        # REMOVE: Lines 262-300
def get_sync_status(self)       # REMOVE: Lines 302-330
def get_full_status(self)       # REMOVE: Lines 332-357
```

**Models to Remove:**
```python
# models/environment.py
class PackageSyncStatus         # REMOVE: Lines 9-14
class SyncDirection(Enum)       # REMOVE: Lines 74-90
class WorkflowSyncAction        # REMOVE: Lines 92-97
class SyncPreview               # REMOVE: Lines 132-149
def get_workflow_sync_actions() # REMOVE: Lines 177-225
```

**Reason:** The new architecture uses one-way copying only at commit/export time. No sync needed.

### 2. Metadata Injection System

**Files to Remove:**
```
managers/workflow_metadata_manager.py    # ENTIRE FILE
```

**Code to Remove:**
```python
# workflow_manager.py
from .workflow_metadata_manager import WorkflowMetadataManager  # REMOVE
self.metadata_manager = WorkflowMetadataManager()               # REMOVE
```

**Reason:** New architecture doesn't inject metadata into workflows.

### 3. Expensive Upfront Workflow Analysis

**Code to Simplify:**
```python
# workflow_manager.py
def track_workflow(self, name: str, analysis=None)  # SIMPLIFY: Remove analysis
def analyze_workflow(self, name: str)               # MOVE: Only for export

# core/environment.py
def track_workflow(self, name: str, analysis=None)           # SIMPLIFY
def track_workflow_with_resolution(self, ...)               # REMOVE
def analyze_workflow(self, name: str)                       # MOVE to export
```

**Reason:** New architecture only analyzes workflows at export time, not during tracking.

### 4. Workflow Sync in Environment.sync()

**Code to Remove:**
```python
# core/environment.py - sync() method
# Sync workflows (Lines ~201-218)
workflow_results = self.workflow_manager.sync_workflows()
result.workflows_synced = {...}
for name, action in workflow_results.items():
    if action != "in_sync":
        logger.info(f"Workflow '{name}': {action}")

# Re-analyze workflows if resolver provided (Lines ~209-218)
if model_resolver:
    out_of_sync_workflows = [...]
    if out_of_sync_workflows:
        result.workflow_resolutions = self._resolve_workflow_models(...)
```

**Reason:** New architecture has no sync step - just on-demand copying.

### 5. CLI Sync Command

**Code to Remove:**
```python
# cli/env_commands.py
def workflow_sync(self, args)   # REMOVE: Lines 793+
```

**Reason:** No sync command in new architecture.

## Components to Simplify

### 1. WorkflowManager Simplification

**Keep These Methods (Simplified):**
```python
def track_workflow(self, name: str) -> None:
    """Just register workflow name in pyproject.toml - no analysis"""

def untrack_workflow(self, name: str) -> None:
    """Remove from pyproject.toml and delete .cec copy"""

def copy_to_cec(self, name: str) -> None:
    """Copy single workflow from ComfyUI to .cec (for commit)"""

def copy_all_tracked(self) -> None:
    """Copy all tracked workflows (for commit)"""
```

**Remove These Methods:**
```python
def sync_workflows(self)     # REMOVE
def get_sync_status(self)    # REMOVE
def get_full_status(self)    # REMOVE
def scan_workflows(self)     # SIMPLIFY - just list what's tracked
```

### 2. CLI Commands Simplification

**Modify `workflow track`:**
```python
def workflow_track(self, args):
    """Just register workflow - no analysis"""
    env = self._get_env(args)
    env.track_workflow(args.name)  # No analysis parameter
    print(f"✓ Now tracking workflow '{args.name}'")
    print("  Run 'comfydock commit' to snapshot current state")
    print("  Run 'comfydock export {args.name}' to create bundle")
```

**Add `commit` command:**
```python
def commit(self, args):
    """Snapshot all tracked workflows"""
    env = self._get_env(args)
    env.commit_workflows(message=args.message)
```

**Add `export` command:**
```python
def export(self, args):
    """Export workflow as bundle with full analysis"""
    env = self._get_env(args)
    bundle = env.export_workflow(args.name)  # This is where analysis happens
```

### 3. Environment Class Simplification

**Remove from Environment:**
```python
def sync(self, ...)                        # Remove workflow sync parts only
def _resolve_workflow_models(self, ...)    # Move to export
def track_workflow_with_resolution(...)   # Remove entirely
```

**Add to Environment:**
```python
def commit_workflows(self, message: str = None) -> None:
    """Copy all tracked workflows to .cec and git commit"""

def export_workflow(self, name: str) -> Bundle:
    """Analyze workflow and create exportable bundle"""

def import_workflow(self, bundle: Bundle) -> None:
    """Import workflow with model substitution"""

def restore_workflow(self, name: str) -> None:
    """Copy workflow from .cec to ComfyUI directory"""
```

## Components to Keep (Reuse for Export)

### 1. WorkflowDependencyParser
**Keep entire class** - This is the core analysis engine needed for export.

**Current Usage:**
- During tracking (REMOVE this usage)
- During sync (REMOVE this usage)

**New Usage:**
- During export only
- During import for model matching

### 2. Model Resolution Logic
**Keep all model resolution in WorkflowDependencyParser:**
- `_resolve_model_dependencies()`
- `_extract_paths_from_node_info()`
- Model index lookups

**Reason:** Still needed for export-time analysis.

### 3. Node Classification
**Keep:**
- `NodeClassifier`
- `GlobalNodeResolver`
- Custom node detection logic

**Reason:** Still needed for export to identify required custom nodes.

### 4. PyProject Workflow Tracking
**Keep WorkflowHandler in PyprojectManager** but simplify:

**Current Structure:**
```toml
[tool.comfydock.workflows.tracked.my_workflow]
file = "workflows/my_workflow.json"
requires = {nodes = [...], models = [...]}
```

**New Structure (Simplified):**
```toml
[tool.comfydock.workflows]
my_workflow = {tracked = true}
another_workflow = {tracked = true}

# During export, populate full info:
[tool.comfydock.workflows.my_workflow]
tracked = true
exported_at = "2024-01-20T10:00:00Z"
requires = {nodes = [...], models = [...]}
```

## New Components to Add

### 1. Export Manager
**New file:** `managers/workflow_export_manager.py`

```python
class WorkflowExportManager:
    def analyze_for_export(self, workflow_path: Path) -> ExportAnalysis
    def create_bundle(self, workflow_name: str) -> Bundle
    def resolve_ambiguous_models(self, analysis: ExportAnalysis) -> dict
```

### 2. Import Manager
**New file:** `managers/workflow_import_manager.py`

```python
class WorkflowImportManager:
    def import_bundle(self, bundle: Bundle) -> ImportResult
    def substitute_model_paths(self, workflow: dict, mappings: dict) -> dict
    def install_missing_nodes(self, required_nodes: list) -> None
```

### 3. Commit Manager
**Add to Environment or create separate:**

```python
def commit_workflows(self, message: str = None) -> None:
    # Copy all tracked workflows from ComfyUI to .cec
    # Git add and commit
```

## Migration Strategy

### Phase 1: Remove Sync System
1. Remove sync-related enums, methods, CLI commands
2. Remove metadata injection entirely
3. Simplify track command to just register

### Phase 2: Add New Components
1. Add export manager and export command
2. Add commit functionality
3. Add import manager

### Phase 3: Clean Up
1. Remove unused models and exceptions
2. Update tests
3. Update documentation

## Code Reduction Estimate

**Current workflow-related LOC:** ~2,000 lines
**After trimming:** ~800 lines
**Reduction:** 60% fewer lines of code

**Benefits:**
- Simpler mental model
- Fewer edge cases
- More reliable (no sync conflicts)
- Faster to implement
- Easier to test

## Testing Impact

**Remove These Tests:**
- All sync-related tests
- Metadata injection tests
- Bidirectional workflow tests

**Keep These Tests:**
- Model resolution tests (for export)
- Node classification tests
- Basic tracking tests

**Add These Tests:**
- Export analysis tests
- Import substitution tests
- Commit functionality tests

## Files That Can Be Deleted

1. `managers/workflow_metadata_manager.py`
2. Various sync-related test files
3. Sync CLI command files/sections

## Files That Need Major Refactoring

1. `managers/workflow_manager.py` - Remove 60% of methods
2. `core/environment.py` - Simplify sync, add export/import/commit
3. `cli/env_commands.py` - Remove sync, add export/commit/import
4. `models/environment.py` - Remove sync models
5. `models/sync.py` - Remove workflow sync parts

This trimming aligns the codebase with the new "track → work → commit → export" flow while preserving all the valuable analysis logic for when it's actually needed.