# Repair Command - Model Download Support

## Context Files

**Read these files first for understanding:**

### Data Models & Structures
- @packages/core/src/comfydock_core/models/manifest.py#L8-74 - `ManifestWorkflowModel` (workflow model entries)
- @packages/core/src/comfydock_core/models/manifest.py#L76-129 - `ManifestModel` (global model table entries)
- @packages/core/src/comfydock_core/models/environment.py#L85-91 - `EnvironmentState` (where to add `MissingModelInfo`)
- @packages/core/src/comfydock_core/models/environment.py#L137-252 - `EnvironmentStatus` (status data structure)
- @packages/core/src/comfydock_core/models/sync.py#L8-34 - `SyncResult` (sync operation result)
- @packages/core/src/comfydock_core/models/workflow.py#L59-79 - `BatchDownloadCallbacks` (progress callbacks)
- @packages/core/src/comfydock_core/models/workflow.py#L35-53 - `NodeResolutionContext` (for resolve_workflow)

### Core Environment Methods (Template for Implementation)
- @packages/core/src/comfydock_core/core/environment.py#L153-173 - `Environment.status()` (where to call detect_missing_models)
- @packages/core/src/comfydock_core/core/environment.py#L175-237 - `Environment.sync()` (where to add model download logic)
- @packages/core/src/comfydock_core/core/environment.py#L931-1030 - `Environment.prepare_import_with_model_strategy()` (THE KEY METHOD - study this!)
- @packages/core/src/comfydock_core/core/environment.py#L741-837 - `Environment._execute_pending_downloads()` (actual download execution)

### PyProject Management (How to Access Data)
- @packages/core/src/comfydock_core/managers/pyproject_manager.py#L30-281 - `PyprojectManager` (handler pattern)
- @packages/core/src/comfydock_core/managers/pyproject_manager.py#L994-1127 - `ModelHandler` (global models table access)
- @packages/core/src/comfydock_core/managers/pyproject_manager.py#L713-992 - `WorkflowHandler` (workflow models access)
- @packages/core/src/comfydock_core/managers/pyproject_manager.py#L595-708 - `NodeHandler` (for node context)

### Model Repository (Model Existence Checks)
- @packages/core/src/comfydock_core/repositories/model_repository.py#L239-249 - `ModelRepository.get_model()`
- @packages/core/src/comfydock_core/repositories/model_repository.py#L251-261 - `ModelRepository.has_model()`

### CLI Commands (Where to Add UI)
- @packages/cli/comfydock_cli/env_commands.py#L728-787 - `repair()` command (where to add model preview/download)
- @packages/cli/comfydock_cli/env_commands.py#L181-306 - `status()` command (where to show missing models)
- @packages/cli/comfydock_cli/env_commands.py#L339-406 - `_show_smart_suggestions()` (where to suggest repair)

### Reference Implementation (Study This Pattern)
- @packages/cli/comfydock_cli/global_commands.py#L149-293 - `import_env()` (shows model download pattern we're copying)

## Problem

When Dev A pulls changes from Dev B that include new models in workflows, `cfd repair` currently doesn't download the missing models. The workflow gets restored but fails at runtime because models are missing from the local index.

**Current behavior:**
```bash
git pull  # Gets new pyproject.toml with model references
cfd repair  # Restores workflow JSON but ignores missing models
cfd run  # ❌ Workflow fails: "Model not found"
```

**Expected behavior:**
```bash
git pull
cfd repair  # Shows missing models, downloads them
cfd run  # ✅ Works
```

## Solution Overview

Reuse existing import machinery (`prepare_import_with_model_strategy()` + `_execute_pending_downloads()`) to detect and download missing models during repair.

**Key insight:** All the download logic exists - we just need to wire it into repair.

## Implementation Steps

### 1. Add Missing Model Detection (Core)

**File:** @packages/core/src/comfydock_core/models/environment.py#L85-91

Add new dataclass after `EnvironmentState` (line 92):

```python
@dataclass
class MissingModelInfo:
    """Model in pyproject but not in local index."""
    model: ManifestModel  # From global models table
    workflow_names: list[str]  # Which workflows need it
    criticality: str  # "required", "flexible", "optional"
    can_download: bool  # Has sources available

    @property
    def is_required(self) -> bool:
        return self.criticality == "required"
```

**File:** @packages/core/src/comfydock_core/models/environment.py#L137-252

Update `EnvironmentStatus` class (line 137):
- Add field: `missing_models: list[MissingModelInfo] = field(default_factory=list)`
- Update `is_synced` property to check `not self.missing_models` (line 154)
- Update `get_sync_preview()` method to include model preview data (line 244)

**File:** @packages/core/src/comfydock_core/core/environment.py#L931-1030

Add new method before `prepare_import_with_model_strategy()` (line 930):

> **IMPORTANT:** Study `prepare_import_with_model_strategy()` at lines 931-1030 first! Your `detect_missing_models()` method will use the same pattern but WITHOUT mutating pyproject.toml - it's read-only detection.

```python
def detect_missing_models(self) -> list[MissingModelInfo]:
    """Detect models in pyproject that don't exist in local index."""
    missing_by_hash: dict[str, MissingModelInfo] = {}

    # Check all workflows
    all_workflows = self.pyproject.workflows.get_all_with_resolutions()
    for workflow_name in all_workflows.keys():
        workflow_models = self.pyproject.workflows.get_workflow_models(workflow_name)

        for wf_model in workflow_models:
            if wf_model.status == "unresolved":
                continue  # Already marked as needing download

            # Check resolved model exists
            if wf_model.hash and not self.model_repository.has_model(wf_model.hash):
                if wf_model.hash not in missing_by_hash:
                    global_model = self.pyproject.models.get_by_hash(wf_model.hash)
                    if global_model:
                        missing_by_hash[wf_model.hash] = MissingModelInfo(
                            model=global_model,
                            workflow_names=[workflow_name],
                            criticality=wf_model.criticality,
                            can_download=bool(global_model.sources)
                        )
                else:
                    # Track workflow and upgrade criticality
                    missing_info = missing_by_hash[wf_model.hash]
                    missing_info.workflow_names.append(workflow_name)
                    if wf_model.criticality == "required":
                        missing_info.criticality = "required"

    return list(missing_by_hash.values())
```

**Key methods used:**
- `self.pyproject.workflows.get_all_with_resolutions()` - @packages/core/src/comfydock_core/managers/pyproject_manager.py#L854-860
- `self.pyproject.workflows.get_workflow_models(name)` - @packages/core/src/comfydock_core/managers/pyproject_manager.py#L734-754
- `self.model_repository.has_model(hash)` - @packages/core/src/comfydock_core/repositories/model_repository.py#L251-261
- `self.pyproject.models.get_by_hash(hash)` - @packages/core/src/comfydock_core/managers/pyproject_manager.py#L1043-1061

**File:** @packages/core/src/comfydock_core/core/environment.py#L153-173

Update `status()` method (line 153):
```python
def status(self) -> EnvironmentStatus:
    # ... existing code ...
    missing_models = self.detect_missing_models()  # NEW (add after line 169)

    return EnvironmentStatus.create(
        comparison=comparison,
        git_status=git_status,
        workflow_status=workflow_status,
        missing_models=missing_models  # NEW (add to create() call)
    )
```

### 2. Add Model Download to Sync (Core)

**File:** @packages/core/src/comfydock_core/models/sync.py#L8-34

Update `SyncResult` dataclass (line 8):

```python
@dataclass
class SyncResult:
    # ... existing fields ...

    # NEW: Model tracking
    models_downloaded: List[str] = field(default_factory=list)
    models_failed: List[tuple[str, str]] = field(default_factory=list)  # (filename, error)
```

**File:** @packages/core/src/comfydock_core/core/environment.py#L175-237

Update `sync()` method signature (line 175):

> **IMPORTANT:** Study the existing `sync()` implementation (lines 175-237) to understand the pattern. Your changes will follow the same structure.

```python
def sync(
    self,
    dry_run: bool = False,
    model_strategy: str = "all",  # NEW
    callbacks: BatchDownloadCallbacks | None = None  # NEW
) -> SyncResult:
```

Add model download logic after workflow restore (after line 220, before line 223 "Ensure model symlink"):

> **REFERENCE:** This logic mirrors the import flow in @packages/cli/comfydock_cli/global_commands.py#L264-277

```python
# 4. NEW: Handle missing models
if not dry_run and model_strategy != "skip":
    try:
        workflows_with_intents = self.prepare_import_with_model_strategy(
            strategy=model_strategy
        )

        if workflows_with_intents:
            logger.info(f"Downloading models for {len(workflows_with_intents)} workflow(s)")

            for workflow_name in workflows_with_intents:
                # Create resolution context
                from comfydock_core.models.workflow import NodeResolutionContext
                node_context = NodeResolutionContext(
                    installed_packages=self.pyproject.nodes.get_existing(),
                    custom_mappings=self.pyproject.workflows.get_custom_node_map(workflow_name)
                )

                # Resolve workflow
                resolution_result = self.workflow_manager.resolve_workflow(
                    workflow_name,
                    context=node_context
                )

                # Execute downloads
                download_results = self._execute_pending_downloads(
                    resolution_result,
                    callbacks=callbacks
                )

                # Track results
                for dr in download_results:
                    if dr["success"]:
                        result.models_downloaded.append(
                            dr["model"].filename if dr["model"] else "unknown"
                        )
                    else:
                        result.models_failed.append((
                            dr.get("model", {}).get("filename", "unknown"),
                            dr.get("error", "Unknown error")
                        ))
    except Exception as e:
        logger.warning(f"Model download failed: {e}", exc_info=True)
        result.errors.append(f"Model download failed: {e}")
```

**Key methods called:**
- `self.prepare_import_with_model_strategy(strategy)` - @packages/core/src/comfydock_core/core/environment.py#L931-1030
- `self.workflow_manager.resolve_workflow(name, context)` - Analyzes workflow dependencies
- `self._execute_pending_downloads(result, callbacks)` - @packages/core/src/comfydock_core/core/environment.py#L741-837

### 3. Update Repair CLI (CLI)

**File:** @packages/cli/comfydock_cli/env_commands.py#L728-787

Update `repair()` method (line 728):

> **PATTERN:** Follow the same preview structure used for nodes/workflows. See lines 745-761 for existing preview code.

Add model preview in confirmation prompt (after line 761, before "Continue?" prompt at line 763):

```python
# Models
if preview.get('models_downloadable'):
    print(f"\n  Models:")
    count = len(preview['models_downloadable'])
    print(f"    • Download {count} missing model(s):")
    for missing_info in preview['models_downloadable'][:5]:
        workflows = ', '.join(missing_info.workflow_names[:2])
        if len(missing_info.workflow_names) > 2:
            workflows += f", +{len(missing_info.workflow_names) - 2} more"
        print(f"      - {missing_info.model.filename} ({missing_info.criticality}, for {workflows})")
    if count > 5:
        print(f"      ... and {count - 5} more")

if preview.get('models_unavailable'):
    print(f"\n  ⚠️  Models unavailable:")
    for missing_info in preview['models_unavailable'][:3]:
        print(f"      - {missing_info.model.filename} (no sources)")
```

Create download callbacks before calling `env.sync()` (before line 772):

> **REFERENCE:** Same callback pattern as import command - see @packages/cli/comfydock_cli/global_commands.py#L217-227

```python
# Create download callbacks for progress
from comfydock_core.models.workflow import BatchDownloadCallbacks

def on_file_start(filename, idx, total):
    print(f"   [{idx}/{total}] Downloading {filename}...")

def on_file_complete(filename, success, error):
    if success:
        print(f"   ✓ {filename}")
    else:
        print(f"   ✗ {filename}: {error}")

callbacks = BatchDownloadCallbacks(
    on_file_start=on_file_start,
    on_file_complete=on_file_complete
)

# Apply sync with models
model_strategy = getattr(args, 'models', 'all')
sync_result = env.sync(model_strategy=model_strategy, callbacks=callbacks)
```

Add result reporting after sync (after existing error checking around line 775):

```python
# Show model download summary
if sync_result.models_downloaded:
    print(f"\n✓ Downloaded {len(sync_result.models_downloaded)} model(s)")

if sync_result.models_failed:
    print(f"\n⚠️  {len(sync_result.models_failed)} model(s) failed:")
    for filename, error in sync_result.models_failed[:3]:
        print(f"   • {filename}: {error}")
```

**File:** @packages/cli/comfydock_cli/cli.py

Add `--models` flag to repair parser (find the repair_parser definition, likely around line 200-300):

> **NOTE:** Search for `repair_parser = subparsers.add_parser("repair"` to find the exact location.

```python
repair_parser.add_argument(
    '--models',
    choices=['all', 'required', 'skip'],
    default='all',
    help='Model download strategy (default: all)'
)
```

### 4. Update Status Display (CLI)

**File:** @packages/cli/comfydock_cli/env_commands.py#L181-306

Update `status()` method (line 181) to show model info with workflows:

> **CONTEXT:** The status method displays workflows around lines 199-246. You'll enhance the "modified" workflow display to show missing models.

```python
# Show workflows with model counts
for name in status.workflow.sync_status.modified:
    wf = all_workflows[name]['analysis']

    # Check if workflow has missing models
    missing_for_wf = [m for m in status.missing_models if name in m.workflow_names]

    if wf.has_issues or wf.has_path_sync_issues:
        print(f"  ⚠️  {name} (modified)")
        self._print_workflow_issues(wf)
    elif missing_for_wf:
        print(f"  ⬇️  {name} (updates available from .cec/)")
        print(f"      {len(missing_for_wf)} model(s) need downloading")
    else:
        print(f"  📝 {name} (modified)")
```

**Location:** Find where modified workflows are displayed (around line 234-242) and add the missing model check.

**File:** @packages/cli/comfydock_cli/env_commands.py#L339-406

Update `_show_smart_suggestions()` (line 339) to suggest repair for missing models:

> **CONTEXT:** This method shows contextual suggestions. Add missing models as a high-priority condition.

```python
# Missing models - high priority
if status.missing_models:
    suggestions.append("Pull updates: comfydock repair")
```

## Testing Plan

### Manual Test Scenario

**Setup (Dev B):**
```bash
cd test_env/.cec
# Add new model to workflow in ComfyUI
cfd commit -m "Added flux model"
git push
```

**Test (Dev A):**
```bash
cd test_env/.cec
git pull

# Should show model needs downloading
cfd status
# Expected: "⬇️  workflow (updates available)" + "1 model needs downloading"

# Should preview model download
cfd repair
# Expected: Shows "Download 1 missing model(s): flux_dev.safetensors (required, for workflow)"

# Should actually download
cfd repair
# Expected: Downloads model with progress, updates pyproject hash

# Should work
cfd run
# Expected: Workflow loads successfully with new model
```

### Edge Cases to Test

1. **Model with no sources** - Should show in preview as unavailable
2. **Multiple workflows same model** - Should deduplicate, show all workflows
3. **Required vs optional models** - Test with `--models required`
4. **Download failure** - Should report error, continue with rest
5. **Already downloaded** - Should detect via URL dedup

## Implementation Notes

### Reused Components

- ✅ `prepare_import_with_model_strategy()` - Existing, converts missing models to download intents
- ✅ `_execute_pending_downloads()` - Existing, handles batch downloads with dedup
- ✅ `BatchDownloadCallbacks` - Existing, provides progress reporting
- ✅ `ModelRepository.has_model()` - Existing, checks if model in index
- ✅ `PyprojectManager.models.*` - Existing, accesses global models table
- ✅ `PyprojectManager.workflows.*` - Existing, accesses workflow models

### New Components

- `MissingModelInfo` - Simple dataclass, groups missing model data
- `detect_missing_models()` - Pure read operation, no side effects
- Model preview in repair CLI - Just display logic
- Model download in sync - Orchestration of existing methods

### Key Decisions

1. **Use ManifestModel/ManifestWorkflowModel** - Proper types, not dicts
2. **Track missing by hash** - Deduplicate across workflows
3. **Add to sync()** - Clean integration point, reusable
4. **Callbacks pattern** - Same as import, consistent UX
5. **Default strategy "all"** - Most intuitive for repair use case

## Estimated Effort

- Core detection logic: 1-2 hours
- Sync integration: 1 hour
- CLI preview/display: 1 hour
- Testing: 1-2 hours

**Total: 4-6 hours**

## Future Enhancements (Not MVP)

- Interactive model resolution (like import command)
- Model diff showing what changed between .cec and local
- Dry-run mode for repair preview
- Repair history/rollback

---

## Quick Implementation Checklist

Use this checklist to implement the feature in order:

### Phase 1: Data Structures (30 min)
- [ ] Read @packages/core/src/comfydock_core/models/manifest.py#L8-129 (understand model structures)
- [ ] Add `MissingModelInfo` dataclass to @packages/core/src/comfydock_core/models/environment.py after line 91
- [ ] Update `EnvironmentStatus` in same file (add field, update properties)
- [ ] Update `SyncResult` in @packages/core/src/comfydock_core/models/sync.py (add model tracking fields)

### Phase 2: Core Detection (1-2 hours)
- [ ] **STUDY FIRST:** Read @packages/core/src/comfydock_core/core/environment.py#L931-1030 (`prepare_import_with_model_strategy`)
- [ ] Add `detect_missing_models()` method before line 930 in same file
  - Use `self.pyproject.workflows.get_all_with_resolutions()`
  - Use `self.pyproject.workflows.get_workflow_models(name)`
  - Use `self.model_repository.has_model(hash)`
  - Use `self.pyproject.models.get_by_hash(hash)`
- [ ] Update `status()` method at line 153 to call `detect_missing_models()`

### Phase 3: Sync Integration (1 hour)
- [ ] **STUDY FIRST:** Read @packages/core/src/comfydock_core/core/environment.py#L741-837 (`_execute_pending_downloads`)
- [ ] Update `sync()` method signature at line 175 (add `model_strategy` and `callbacks` parameters)
- [ ] Add model download logic after line 220 (after workflow restore, before model symlink)
  - Call `self.prepare_import_with_model_strategy(strategy)`
  - Loop workflows, create `NodeResolutionContext`
  - Call `self.workflow_manager.resolve_workflow(name, context)`
  - Call `self._execute_pending_downloads(result, callbacks)`
  - Track results in `sync_result`

### Phase 4: CLI Preview (30 min)
- [ ] **REFERENCE:** Study @packages/cli/comfydock_cli/global_commands.py#L149-293 (import pattern)
- [ ] Update `repair()` in @packages/cli/comfydock_cli/env_commands.py#L728-787
  - Add model preview display after line 761
  - Create `BatchDownloadCallbacks` before line 772
  - Pass callbacks to `env.sync()`
  - Add result reporting after line 775

### Phase 5: CLI Display (30 min)
- [ ] Update `status()` in @packages/cli/comfydock_cli/env_commands.py#L181-306
  - Enhance modified workflow display (around line 234)
  - Show missing model counts
- [ ] Update `_show_smart_suggestions()` around line 339
  - Add missing models as high-priority suggestion
- [ ] Add `--models` flag to repair parser in @packages/cli/comfydock_cli/cli.py

### Phase 6: Testing (1-2 hours)
- [ ] Manual test: Two workspaces, git push/pull workflow with new model
- [ ] Test edge case: Model with no sources
- [ ] Test edge case: Multiple workflows using same model
- [ ] Test `--models required` flag
- [ ] Test download failure scenario

### Total Estimated Time: 4-6 hours

**Implementation Order Note:** Follow the phases in order. Each phase builds on the previous one. Don't skip Phase 1 (data structures) or you'll have type errors later!
