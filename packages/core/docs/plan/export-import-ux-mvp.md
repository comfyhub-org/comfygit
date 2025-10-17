# Export/Import UX - MVP Implementation Plan

## Overview

Export/import enables sharing complete ComfyUI environments as single `.tar.gz` files. This unlocks the network effect - users can distribute working setups with all dependencies.

**Core Value**: "I can share my entire working setup as a single file that others can import and run immediately"

## MVP Principles

1. **Get environment to "minimally viable" state** - Don't try to solve every problem during import
2. **Reuse existing tools** - `workflow resolve` already handles model substitution and interactive fixes
3. **Simple, clear UX** - Three choices (all/required/skip), no complex per-item prompting
4. **Fail fast on catastrophic issues** - Cleanup and error if environment can't be created
5. **Allow partial success** - Some models/nodes failing is OK, user can fix with existing tools

## What Gets Bundled

### Included (in .tar.gz)
- `manifest.json` - Basic export metadata
- `pyproject.toml` - All config, nodes, model references with hashes
- `uv.lock` - Python dependency lockfile
- `.python-version` - Python version used in creating .venv
- `workflows/` - All tracked workflow JSON files
- `dev_nodes/` - Full source code of development nodes (respecting `.gitignore`)

### Referenced (downloaded on import)
- **Registry nodes**: By ID + version (downloaded from cache/registry)
- **Git nodes**: By repo URL + commit hash (cloned fresh)
- **Models**: By hash + source URLs (downloaded on import)

### Never Included
- Model files (too large - use hash references instead)
- Registry/git node binaries (cached globally, re-downloaded on import)
- Virtual environment (`.venv/`) - recreated via `uv.lock`
- ComfyUI itself (cloned fresh during environment creation)

---

## Export Process

### Phase 1: Pre-Export Validation

**Goal**: Ensure environment is export-ready.

```bash
$ comfydock export my-env
```

**Steps**:

1. **Check for uncommitted changes**
   ```python
   if git_manager.has_uncommitted_changes():
       raise ExportError(
           "Cannot export with uncommitted changes.\n"
           "Commit first: comfydock commit -m 'Pre-export checkpoint'"
       )
   ```

2. **Analyze all workflows** (validation only - no fixes)
   ```python
   validation_result = workflow_manager.validate_all_workflows()

   if validation_result.has_unresolved_issues:
       print("❌ Cannot export - workflows have unresolved issues:\n")

       for workflow, issues in validation_result.issues.items():
           print(f"  • {workflow}:")
           for issue in issues:
               print(f"    - {issue}")

       print("\nResolve issues first:")
       print("  comfydock workflow resolve <workflow_name>")
       raise ExportError("Unresolved workflow issues")
   ```

3. **Check development node sizes**
   ```python
   for node_name, node_path in dev_nodes.items():
       size = calculate_size_with_gitignore_filter(node_path)

       if size > 200 * 1024 * 1024:  # 200MB
           print(f"❌ Dev node '{node_name}' is {size / 1024**2:.0f} MB")
           print(f"   Max allowed: 200 MB")
           print(f"   Review .gitignore or use --allow-large-dev-nodes")
           raise ExportError("Development node too large")

       if size > 50 * 1024 * 1024:  # 50MB
           print(f"⚠️  Dev node '{node_name}' is {size / 1024**2:.0f} MB")
   ```

### Phase 2: Bundle Creation

**Goal**: Package everything into distributable `.tar.gz`.

**Steps**:

1. **Create manifest**
   ```json
   {
     "timestamp": "2025-01-15T10:30:00Z",
     "comfydock_version": "0.5.0",
     "environment_name": "my-env",
     "workflows": ["workflow_1.json", "workflow_2.json"],
     "python_version": "3.11",
     "comfyui_version": "v0.2.2",
     "platform": "linux",
     "total_models": 5,
     "total_nodes": 12
   }
   ```

2. **Bundle files**
   ```
   my_env_export_2025-01-15.tar.gz
   ├── manifest.json
   ├── pyproject.toml
   ├── uv.lock
   ├── .python-version
   ├── workflows/
   │   ├── workflow_1.json
   │   └── workflow_2.json
   └── dev_nodes/
       └── my-custom-node/
           ├── __init__.py
           └── nodes.py
   ```

3. **Show summary**
   ```
   ✅ Export complete: my_env_export_2025-01-15.tar.gz (12.5 MB)

   Summary:
     • 3 workflows
     • 12 custom nodes (2 development, 10 registry/git)
     • 5 models referenced

   Share this file to distribute your complete environment!
   ```

---

## Import Process

### Phase 1: Validation & Extraction

```bash
$ comfydock import my_env_export.tar.gz --name imported-env
```

**Steps**:

1. **Extract and validate bundle**
   ```python
   temp_dir = tempfile.mkdtemp()

   try:
       with tarfile.open(bundle_path, "r:gz") as tar:
           tar.extractall(temp_dir)
   except Exception as e:
       raise ImportError(f"Failed to extract bundle: {e}")

   # Validate structure
   required_files = ["manifest.json", "pyproject.toml", "uv.lock", "workflows"]
   for file in required_files:
       if not (temp_dir / file).exists():
           raise ImportError(f"Invalid bundle: missing {file}")

   # Validate content integrity
   try:
       manifest = json.loads((temp_dir / "manifest.json").read_text())
       pyproject = toml.loads((temp_dir / "pyproject.toml").read_text())
   except Exception as e:
       raise ImportError(f"Bundle appears corrupted: {e}")
   ```

2. **Show import summary**
   ```
   📦 Import Summary:

   Source: my-env (exported 2025-01-15 10:30 UTC)
   ComfyUI: v0.2.2
   Python: 3.11

   Contents:
     • 3 workflows
     • 12 custom nodes (2 dev, 8 registry, 2 git)
     • 8 unique models (23.5 GB total)

   Target environment: imported-env

   [Y] Continue  [c] Cancel
   ```

3. **Version compatibility check** (warning only)
   ```python
   if manifest.comfydock_version > current_version:
       print(f"⚠️  Bundle created with newer comfydock ({manifest.comfydock_version})")
       print("   May have compatibility issues")

   if manifest.platform != current_platform:
       print(f"⚠️  Bundle created on {manifest.platform}, importing to {current_platform}")
       print("   May have path/symlink compatibility issues")
   ```

### Phase 2: Environment Setup

**Goal**: Create new environment with base ComfyUI.

**Steps**:

1. **Check for name collision**
   ```python
   target_name = args.name
   if workspace.environment_exists(target_name):
       counter = 1
       while workspace.environment_exists(f"{target_name}-{counter}"):
           counter += 1
       target_name = f"{target_name}-{counter}"
       print(f"⚠️  Environment '{args.name}' exists, using '{target_name}'")
   ```

2. **Create environment** (with cleanup on catastrophic failure)
   ```python
   env = None
   try:
       # Extract metadata
       pyproject_data = toml.loads((temp_dir / "pyproject.toml").read_text())
       metadata = pyproject_data["tool"]["comfydock"]

       # Create environment (uv will handle Python version automatically)
       print(f"\n📦 Creating environment '{target_name}'...")
       env = workspace.create_environment(
           name=target_name,
           python_version=metadata["python_version"],
           comfyui_version=metadata["comfyui_version"]
       )
       print("  ✓ Environment created")

   except Exception as e:
       # Catastrophic failure - cleanup
       if env and env.cec_path.exists():
           shutil.rmtree(env.cec_path)
       raise ImportError(f"Failed to create environment: {e}")
   ```

3. **Copy bundle files**
   ```python
   # Copy core files
   shutil.copy(temp_dir / "pyproject.toml", env.pyproject_path)
   shutil.copy(temp_dir / "uv.lock", env.cec_path / "uv.lock")
   shutil.copytree(temp_dir / "workflows", env.workflows_cec_path, dirs_exist_ok=True)

   # Copy development nodes
   if (temp_dir / "dev_nodes").exists():
       for node_dir in (temp_dir / "dev_nodes").iterdir():
           target = env.custom_nodes_path / node_dir.name
           shutil.copytree(node_dir, target)
   ```

### Phase 3: Dependency Acquisition

**Goal**: Install nodes and download models with simple UX.

#### Stage 3A: Node Installation

1. **Categorize nodes**
   ```python
   pyproject = PyprojectManager(env.pyproject_path)
   nodes = pyproject.nodes.get_existing()

   registry_nodes = [v for v in nodes.values() if v.source == "registry"]
   git_nodes = [v for v in nodes.values() if v.source == "git"]
   dev_nodes = [v for v in nodes.values() if v.source == "development"]

   nodes_to_install = registry_nodes + git_nodes
   ```

2. **Show summary and install**
   ```
   📦 Custom Nodes Required:

   Registry nodes (8): comfyui-manager, comfyui-impact-pack, ...
   Git nodes (2): https://github.com/user/custom-node, ...
   Development nodes (2): my-custom-node (bundled), ...

   Installing 10 nodes...
   ```

3. **Install sequentially** (don't fail on individual node failures)
   ```python
   print("\n📦 Installing nodes...\n")

   installed = []
   failed = []

   for node_name, node_info in nodes_to_install.items():
       try:
           print(f"  • {node_name}...", end=" ", flush=True)
           env.add_node(node_info.source_url, no_test=True)
           print("✓")
           installed.append(node_name)
       except Exception as e:
           print(f"✗ ({e})")
           failed.append((node_name, str(e)))
           logger.error(f"Node install failed: {node_name}", exc_info=True)

   print(f"\n✅ Installed {len(installed)}/{len(nodes_to_install)} nodes")
   if failed:
       print(f"⚠️  {len(failed)} node(s) failed (can fix later with 'node add')")
   ```

#### Stage 3B: Model Acquisition (Simplified)

1. **Aggregate model info**
   ```python
   # Aggregate models across workflows
   model_aggregates = {}

   for wf_name, wf_data in pyproject.workflows.get_all().items():
       for model in wf_data.get('models', []):
           if model.hash not in model_aggregates:
               model_aggregates[model.hash] = {
                   'model': model,
                   'criticality': model.criticality,
                   'workflows': [wf_name]
               }
           else:
               # Promote criticality (optional < flexible < required)
               current = model_aggregates[model.hash]['criticality']
               promoted = promote_criticality(current, model.criticality)
               model_aggregates[model.hash]['criticality'] = promoted
               model_aggregates[model.hash]['workflows'].append(wf_name)
   ```

2. **Check disk space**
   ```python
   total_size = sum(agg['model'].file_size for agg in model_aggregates.values())
   available_space = shutil.disk_usage(env.models_path).free

   if total_size > available_space:
       raise ImportError(
           f"Insufficient disk space.\n"
           f"  Need: {total_size / 1024**3:.1f} GB\n"
           f"  Available: {available_space / 1024**3:.1f} GB\n"
       )
   ```

3. **Categorize by criticality and availability**
   ```python
   available_models = []
   missing_models = []

   for hash_key, agg in model_aggregates.items():
       existing = model_repository.get_model(hash_key)
       if existing:
           available_models.append((hash_key, agg, existing))
       else:
           missing_models.append((hash_key, agg))

   # Calculate sizes by criticality
   required_models = [m for m in missing_models if m[1]['criticality'] == 'required']
   flexible_models = [m for m in missing_models if m[1]['criticality'] == 'flexible']
   optional_models = [m for m in missing_models if m[1]['criticality'] == 'optional']

   required_size = sum(m[1]['model'].file_size for m in required_models)
   flexible_size = sum(m[1]['model'].file_size for m in flexible_models)
   optional_size = sum(m[1]['model'].file_size for m in optional_models)
   ```

4. **Show simplified acquisition prompt**
   ```
   📦 Model Acquisition:

   8 unique models required (23.5 GB total):
     • Required: 3 models (6.8 GB)
     • Flexible: 3 models (12.5 GB)
     • Optional: 2 models (4.2 GB)

   Local availability:
     ✓ 2 models found locally (14.3 GB)
     ⬇ 6 models need download (17.2 GB)

   Choose acquisition strategy:
     [a] Download ALL available (17.2 GB)
     [r] Download REQUIRED only (6.8 GB) - recommended
     [s] Skip downloads (I'll handle models manually)

   Choice [r]/a/s: _
   ```

5. **Execute download based on strategy**
   ```python
   if strategy == 'skip':
       print("\n⊗ Skipping all model downloads")
       print("  Use 'workflow resolve' to acquire models after import")
       to_download = []

   elif strategy == 'required':
       to_download = [
           (hash_key, agg)
           for hash_key, agg in missing_models
           if agg['criticality'] == 'required' and agg['model'].sources
       ]

   elif strategy == 'all':
       to_download = [
           (hash_key, agg)
           for hash_key, agg in missing_models
           if agg['model'].sources
       ]

   # Download with progress
   if to_download:
       print(f"\n📥 Downloading {len(to_download)} model(s)...\n")

       downloaded = []
       failed = []

       for idx, (hash_key, agg) in enumerate(to_download, 1):
           model = agg['model']
           print(f"[{idx}/{len(to_download)}] {model.filename} ({model.file_size / 1024**3:.1f} GB)")

           try:
               result = downloader.download(
                   request=DownloadRequest(
                       url=model.sources[0],
                       target_path=env.models_path / model.relative_path,
                       workflow_name=None
                   ),
                   progress_callback=create_progress_callback()
               )

               if result.success:
                   print("  ✓ Complete\n")
                   downloaded.append(model.filename)
               else:
                   print(f"  ✗ Failed: {result.error}\n")
                   failed.append((model.filename, result.error))

           except Exception as e:
               print(f"  ✗ Failed: {e}\n")
               failed.append((model.filename, str(e)))

       print(f"\n✅ Downloaded {len(downloaded)}/{len(to_download)} models")
       if failed:
           print(f"⚠️  {len(failed)} model(s) failed (can fix later with 'workflow resolve')")
   ```

### Phase 4: Finalization

**Goal**: Sync Python environment and finalize.

**Steps**:

1. **Sync Python environment**
   ```python
   print("\n📦 Syncing Python environment...")
   env.uv_manager.sync_project(all_groups=True)
   print("  ✓ Complete")
   ```

2. **Copy workflows from .cec to ComfyUI**
   ```python
   print("\n📋 Finalizing workflows...")
   env.workflow_manager.restore_all_from_cec()
   print("  ✓ Workflows copied to ComfyUI")
   ```

3. **Create initial commit**
   ```python
   env.commit("Initial import from bundle")
   print("  ✓ Initial commit created")
   ```

4. **Final summary** (with status info)
   ```
   ✅ Import Complete!

   Environment: imported-env

   Workflows: 3 workflows imported

   Custom Nodes: 10/12 installed
     ✓ 2 development nodes (bundled)
     ✓ 8 registry/git nodes installed
     ✗ 2 nodes failed to install

   Models: 6/8 available
     ✓ 2 found locally (14.3 GB)
     ⬇ 4 downloaded (6.3 GB)
     ⊗ 2 skipped

   Next steps:
     1. Set as active: comfydock use imported-env
     2. Run ComfyUI: comfydock run

   Optional - fix remaining issues:
     • Resolve workflows: comfydock workflow resolve <workflow>
     • Add failed nodes: comfydock node add <node-url>
   ```

---

## Implementation Plan

### New Components

1. **`ExportService`** (`packages/core/src/comfydock_core/services/export_service.py`)
   - `validate_for_export()` - Check uncommitted changes + workflow issues
   - `create_bundle()` - Package into .tar.gz
   - Uses: `PyprojectManager`, `WorkflowManager`, `GitManager`

2. **`ImportService`** (`packages/core/src/comfydock_core/services/import_service.py`)
   - `validate_bundle()` - Extract and validate structure
   - `create_environment()` - Create base environment
   - `install_nodes()` - Install registry/git nodes
   - `acquire_models()` - Download models based on strategy
   - `finalize_import()` - Sync environment + commit
   - Uses: `WorkspaceFactory`, `ModelDownloader`, `NodeManager`, `WorkflowManager`

3. **CLI Commands** (`packages/cli/comfydock_cli/global_commands.py`)
   ```python
   @cmd.command()
   def export(env_name: str, output: str = None, allow_large_dev_nodes: bool = False):
       """Export environment to .tar.gz bundle."""

   @cmd.command()
   def import_bundle(bundle: str, name: str):
       """Import environment from .tar.gz bundle."""
   ```

### Data Structures

```python
@dataclass
class ExportManifest:
    """Metadata for exported bundle."""
    timestamp: str
    comfydock_version: str
    environment_name: str
    workflows: list[str]
    python_version: str
    comfyui_version: str
    platform: str
    total_models: int
    total_nodes: int

@dataclass
class ImportResult:
    """Result of import operation."""
    success: bool
    environment_name: str

    # Nodes
    nodes_installed: int
    nodes_failed: list[tuple[str, str]]

    # Models
    models_downloaded: int
    models_found_local: int
    models_skipped: int
    models_failed: list[tuple[str, str]]

@dataclass
class ModelAggregate:
    """Aggregated model info across workflows."""
    model: ManifestWorkflowModel
    criticality: str  # Most conservative across all workflows
    workflows: list[str]

def promote_criticality(current: str, new: str) -> str:
    """Pick most conservative criticality."""
    priority = {"optional": 0, "flexible": 1, "required": 2}
    return max(current, new, key=lambda c: priority[c])
```

---

## Edge Cases & Error Handling

### Export Edge Cases

1. **Uncommitted changes**
   - Error and tell user to commit first
   - No automatic commit

2. **Unresolved workflow issues**
   - Error and tell user to run `workflow resolve`
   - No interactive resolution during export

3. **Development node too large**
   - Hard limit: 200MB (override with `--allow-large-dev-nodes`)
   - Warning at: 50MB

### Import Edge Cases

1. **Environment creation fails** (catastrophic)
   - Cleanup: Remove partially created environment
   - Error out completely

2. **Some nodes fail to install** (partial success)
   - Continue with import
   - Report in final summary
   - User can fix with `node add` or `workflow resolve`

3. **Some models fail to download** (partial success)
   - Continue with import
   - Report in final summary
   - User can fix with `workflow resolve`

4. **Insufficient disk space**
   - Check before downloading
   - Error with clear message about needed space

5. **Bundle corrupted**
   - Validate structure and content early
   - Error: "Bundle appears corrupted"

6. **Version mismatch**
   - Warn but allow import (best-effort)

7. **Platform mismatch** (linux→windows)
   - Warn but allow import (may have path issues)

---

## What We're NOT Doing (Post-MVP)

- ❌ Pre-export interactive resolution → Use `workflow resolve` first
- ❌ Hash enrichment during export → Keep exports fast
- ❌ Model substitution during import → Use `workflow resolve` after
- ❌ Per-model custom prompting → Three simple strategies only
- ❌ Parallel downloads → Sequential for simplicity
- ❌ Differential exports → Always full bundle
- ❌ Workflow subset exports → Export whole environment
- ❌ Python version validation → uv handles automatically
- ❌ Sophisticated cancellation → Ctrl+C leaves partial state

---

## Success Criteria

**Export works when**:
- User can export environment with all workflows resolved
- Bundle is < 100MB (no model files)
- Export takes < 30 seconds (no hash calculation)

**Import works when**:
- New user can import bundle and get minimally viable environment
- Models download automatically for simple cases
- User can skip models and fix later with existing tools
- Partial failures don't block import completion

**UX wins**:
- Simple three-choice model acquisition (all/required/skip)
- Clear error messages that point to fix commands
- Reuses existing `workflow resolve` for complex cases
- Fast exports (no blocking operations)
