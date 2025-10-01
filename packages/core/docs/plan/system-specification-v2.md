# ComfyDock System Specification v2.0

## Executive Summary

ComfyDock v2.0 implements a **one-way sync architecture** where ComfyUI is the single source of truth. The system focuses on environment reproducibility through careful tracking of workflows, custom nodes, models, and Python dependencies. All synchronization flows from ComfyUI to ComfyDock, never in reverse, eliminating complex bidirectional state management.

## Table of Contents

1. [Core Architecture](#core-architecture)
2. [Key Concepts](#key-concepts)
3. [Command Reference](#command-reference)
4. [System Behaviors](#system-behaviors)
5. [Data Structures](#data-structures)
6. [Implementation Details](#implementation-details)
7. [User Workflows](#user-workflows)

## Core Architecture

### Design Principles

1. **One-Way Data Flow**: ComfyUI → ComfyDock (only reverse on restores)
2. **Lazy Resolution**: Model/Node analysis only at commit/export time
3. **Git-Based Versioning**: Every commit creates a restorable snapshot
4. **Workspace Isolation**: Multiple environments with shared model index
5. **Progressive Enhancement**: Simple tracking evolves to full reproducibility
6. **Two-Tier Reproducibility**: Local versioning (commit/rollback) for iteration, global packaging (export/import) for distribution
7. **Imperative Node Management**: Nodes are added/removed immediately to filesystem, not on sync
8. **Filesystem-First Safety**: Never silently destroy user data; detect conflicts and require explicit confirmation

### Architecture Summary

ComfyDock v2 fundamentally separates **local iteration** from **global distribution**:

**Local Iteration** (Git-based):
- `commit` snapshots configuration (pyproject.toml, uv.lock, workflows)
- `rollback` restores configuration to any previous commit
- Development nodes NOT tracked (user manages source code)
- Fast iteration, local version history
- Git repository stays on current branch

**Global Distribution** (Package-based):
- `export` creates .tar.gz with everything needed to reproduce
- Bundles development node source code
- References registry nodes (downloaded on import)
- References models (with download URLs)
- Complete reproducibility for sharing

**Node Management Philosophy**:
- **Imperative**: Changes happen immediately (add downloads, remove deletes)
- **Filesystem-first**: Manual git clones respected, conflicts detected
- **Non-destructive**: Development nodes preserved with .disabled suffix
- **Three node types**: Registry (deletable), Git (deletable), Development (protected)

**Sync Role**:
- Primarily syncs Python packages (uv sync)
- Reconciles node state after git operations (rollback)
- Never silently deletes user data
- Warns about untracked nodes

**Safety Mechanisms**:
1. Git conflict detection before any download
2. .disabled suffix preserves development nodes
3. Force flag required for destructive operations
4. Clear error messages with suggested fixes

### System Components

```
┌─────────────────────────────────────────────────────────┐
│                    ComfyUI (Source of Truth)            │
│  - Browser Memory (user edits)                          │
│  - Disk Storage (ComfyUI/user/default/workflows/)       │
│  - Custom Nodes (ComfyUI/custom_nodes/)                 │
└───────────────────┬─────────────────────────────────────┘
                    │ One-way flow
┌───────────────────▼─────────────────────────────────────┐
│                    ComfyDock Environment                 │
│  ┌──────────────────────────────────────────────────┐  │
│  │ .cec/ (Git Repository)                           │  │
│  │  ├── workflows/        (tracked workflows)       │  │
│  │  ├── pyproject.toml    (dependencies & config)   │  │
│  │  ├── uv.lock          (Python lockfile)          │  │
│  │  └── comfydock.lock   (model/node URLs)         │  │
│  └──────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────┐
│              Workspace-Wide Components                    │
│  - Model Index (SQLite database)                         │
│  - Node Cache (downloaded custom nodes)                  │
│  - Multiple Environments                                 │
└──────────────────────────────────────────────────────────┘
```

## Key Concepts

### Environment
A complete ComfyUI installation with its own virtual environment, custom nodes, and workflow tracking. Each environment is isolated but shares the workspace's model index.

### Model Index
A workspace-wide SQLite database tracking all model files across a configured directory. Uses quick hash sample (Blake3 15MB from front/middle/end of file) for quick identification and full hashing (SHA256/Blake3) for verification.

**Hash Types:**
- **Quick Hash**: First/middle/last 15MB using Blake3 (fast identification)
- **Full Hash**: Complete file hash for export/import verification

### Workflow Tracking
Lightweight registration of workflows to monitor. No analysis occurs during tracking - just name registration in pyproject.toml.

### Model Resolution
The process of mapping workflow model references to actual files in the model index. Happens only at commit/export time.

**Resolution Strategy:**
1. Exact path match
2. Directory-aware search based on node type
3. Filename similarity matching
4. Interactive user resolution for ambiguities

### Custom Node Management
Nodes are installed from ComfyUI registry or git repositories. Each node gets its own dependency group in pyproject.toml to isolate potential conflicts.

### Version Snapshots
Git commits that capture the complete environment state including workflows, dependencies, and model resolutions. Can be restored but changes are applied to current branch (not checkout).

### Two-Tier Reproducibility Model

ComfyDock provides two distinct levels of reproducibility for different use cases:

#### Local Reproducibility (commit/rollback)
**Purpose**: Personal version control for iteration and experimentation

**What's tracked**:
- pyproject.toml (node metadata, model references)
- uv.lock (Python dependency lockfile)
- .cec/workflows/ (workflow copies)

**What's NOT tracked**:
- Development node source code (in custom_nodes/)
- Registry/git node binaries (downloaded separately)
- Model files (too large, shared globally)

**Use case**:
- Developer iterating on workflows
- Testing different node versions
- Rolling back problematic changes
- Local version history

**Workflow**:
```bash
$ comfydock commit -m "Added sampler"
$ # Make changes...
$ comfydock commit -m "Refined parameters"
$ # Oops, broke something
$ comfydock rollback v1  # Back to previous state
```

#### Global Reproducibility (export/import)
**Purpose**: Share complete working environments with others

**What's bundled**:
- pyproject.toml + uv.lock (Python dependencies)
- workflows/ (all workflow files)
- dev_nodes/ (full source of development nodes)
- comfydock.lock (model download URLs, node metadata)

**What's referenced** (downloaded on import):
- Registry nodes (by ID + version)
- Models (by hash + download URLs)

**Use case**:
- Sharing workflow templates
- Team collaboration
- Publishing environments
- Cross-machine reproducibility

**Workflow**:
```bash
# Developer creates environment
$ comfydock export my-workflow-v1.tar.gz
$ # Share package via file transfer

# Recipient imports
$ comfydock import my-workflow-v1.tar.gz
$ # Downloads missing nodes/models
$ # Environment ready to use
```

**Key Distinction**: Git tracks configuration changes over time (local history), while export creates a snapshot package for distribution (global sharing).

### Node Management Architecture

ComfyDock uses an **imperative, filesystem-first** approach to node management:

#### Core Principle
**Nodes are managed immediately on add/remove, NOT deferred to sync**

This differs from declarative package managers where changes are queued until sync. ComfyDock applies node changes immediately to:
1. Prevent user confusion (what you add is instantly present)
2. Allow manual filesystem manipulation (users can git clone nodes)
3. Respect existing data (never silently overwrite)

#### Node Addition Flow

```bash
$ comfydock node add comfyui-impact-pack
```

**What happens immediately**:
1. ✓ Check for filesystem conflicts (see Git Conflict Detection)
2. ✓ Resolve identifier (registry/GitHub)
3. ✓ Download node to custom_nodes/
4. ✓ Scan Python requirements
5. ✓ Add to pyproject.toml
6. ✓ Test dependency resolution
7. ✓ Sync Python virtual environment

**Result**: Node is PRESENT on filesystem and TRACKED in pyproject.toml

#### Node Removal Flow

```bash
$ comfydock node remove comfyui-impact-pack
```

**What happens immediately**:
1. ✓ Remove from pyproject.toml
2. ✓ Handle filesystem (see .disabled pattern)
3. ✓ Remove dependency group
4. ✓ Sync Python virtual environment

**Result**: Node is either .disabled or deleted from filesystem

#### Three Node Types

**1. Registry Nodes** (`source="registry"`)
- Downloaded from ComfyUI registry
- Cached globally for reuse
- Deleted on removal (can re-download from cache)
- Example: `comfydock node add comfyui-manager`

**2. Git Nodes** (`source="git"`)
- Cloned from GitHub URL
- Cached globally
- Deleted on removal (can re-clone)
- Example: `comfydock node add https://github.com/user/repo`

**3. Development Nodes** (`source="development"`)
- User's own nodes under active development
- Added via `--dev` flag
- **Protected from deletion** (uses .disabled pattern)
- Bundled in export packages
- Example: `comfydock node add my-node --dev`

#### Git Conflict Detection

**Problem**: Users often manually clone nodes, then try to add them via comfydock, leading to silent data loss.

**Solution**: Three-way conflict detection before any filesystem modification.

**Detection Flow**:
```python
# On node add:
1. Resolve identifier → get expected node info
2. Check if directory exists in custom_nodes/
3. If exists:
   a. Is it a git repo? (check .git/)
   b. Get remote URL (git remote get-url origin)
   c. Compare with expected repository
   d. Raise helpful conflict error
```

**Conflict Scenarios**:

**Scenario 1: Regular directory exists**
```bash
$ mkdir custom_nodes/my-node
$ comfydock node add my-node

✗ Directory 'my-node' already exists in custom_nodes/
  → Track as dev node: comfydock node add my-node --dev
  → Force replace: comfydock node add <identifier> --force
```

**Scenario 2: Git repo, no remote**
```bash
$ cd custom_nodes/my-node && git init
$ comfydock node add my-node

✗ Git repository 'my-node' exists locally (no remote)
  → Track as dev node: comfydock node add my-node --dev
  → Force replace: comfydock node add <identifier> --force
```

**Scenario 3: Same repository already cloned**
```bash
$ git clone https://github.com/user/my-node custom_nodes/my-node
$ comfydock node add https://github.com/user/my-node

✗ Git clone of 'my-node' already exists
  Remote: https://github.com/user/my-node
  → Track existing: comfydock node add my-node --dev
  → Force re-download: comfydock node add <identifier> --force
```

**Scenario 4: Different repositories (name collision)**
```bash
$ git clone https://github.com/user/fork custom_nodes/my-node
$ comfydock node add https://github.com/original/my-node

✗ Repository conflict for 'my-node':
  Filesystem: https://github.com/user/fork
  Registry:   https://github.com/original/my-node
These appear to be different nodes.
  → Rename yours: mv custom_nodes/my-node custom_nodes/my-node-fork
  → Force replace: comfydock node add <identifier> --force
```

**URL Normalization**: Compares git URLs intelligently
- Handles https://, git@, ssh:// protocols
- Ignores .git suffix
- Case-insensitive comparison

**Force Override**: `--force` flag bypasses all checks
```bash
$ comfydock node add my-node --force  # Overwrites existing
```

#### .disabled Pattern (Non-Destructive Removal)

**Problem**: Deleting nodes permanently loses user data and git history.

**Solution**: Development nodes are preserved with `.disabled` suffix on removal.

**Behavior on `node remove`**:

**Development nodes**:
```bash
$ comfydock node remove my-dev-node
# custom_nodes/my-dev-node/ → custom_nodes/my-dev-node.disabled/
```
- Directory renamed, not deleted
- Git history preserved
- User data intact
- ComfyUI won't load it (doesn't end in expected name)

**Registry/Git nodes**:
```bash
$ comfydock node remove comfyui-manager
# custom_nodes/ComfyUI-Manager/ → DELETED
```
- Safe to delete (cached globally, can re-download)
- No user modifications expected

**Re-enabling nodes**:
```bash
$ comfydock node add my-dev-node
# Checks for .disabled version
# Removes my-dev-node.disabled/ before proceeding
```

**Rollback behavior**:
```bash
# v1: has node-a, node-b (dev), node-c
# v2: has node-a, node-c (removed node-b)
$ comfydock rollback v2
# → node-b.disabled/ created (not deleted!)
```

**Conflict handling**:
```bash
# If both exist:
# - custom_nodes/my-node/
# - custom_nodes/my-node.disabled/

$ comfydock node add my-node
# → Deletes my-node.disabled/ first
# → Then proceeds with fresh install
```

#### Sync Behavior (Reconciliation)

**Important**: `sync` is now primarily for Python packages, not nodes.

**What sync DOES**:
```bash
$ comfydock sync
1. ✓ Sync Python packages from pyproject.toml (uv sync)
2. ✓ Sync model path configuration
3. ✓ Reconcile node state (see below)
```

**Node Reconciliation during sync**:
- **Install missing registry/git nodes** (if in pyproject but not on disk)
- **Disable extra development nodes** (if on disk but not in pyproject)
- **Never delete without user confirmation**

**Reconciliation logic**:
```python
expected_nodes = pyproject.toml nodes
filesystem_nodes = custom_nodes/ directories

# Missing from filesystem → download
to_install = expected_nodes - filesystem_nodes
for node in to_install:
    if node.source == "development":
        warn("Dev node '{node}' missing from filesystem")
    else:
        download_node(node)

# Extra on filesystem → disable or warn
to_remove = filesystem_nodes - expected_nodes
for node in to_remove:
    if is_dev_node_from_history(node):
        move_to_disabled(node)  # Safe preservation
    else:
        delete(node)  # Registry node, can re-download
```

**User experience**:
```bash
# User manually adds node
$ git clone custom_nodes/my-manual-node

# Sync doesn't delete it (just warns)
$ comfydock sync
⚠️  Untracked node found: my-manual-node
   Run 'comfydock node add my-manual-node --dev' to track

# User tracks it
$ comfydock node add my-manual-node --dev
✓ Added development node 'my-manual-node'
```

## Command Reference

### Environment Management

#### `comfydock init [path]`
Initialize a new ComfyDock workspace.

**Behavior:**
- Creates workspace directory structure
- Initializes global configuration
- Sets up model index database
- Creates cache directories

#### `comfydock create <name>`
Create a new environment within the workspace.

**Options:**
- `--python <version>` - Python version (default: 3.11)
- `--comfyui-version <ref>` - ComfyUI git ref (default: latest)

**Behavior:**
- Clones ComfyUI repository
- Creates virtual environment via uv
- Initializes pyproject.toml with base dependencies
- Creates .cec directory with git repository
- Configures model directory path

#### `comfydock run [args...]`
Run ComfyUI in the current environment.

**Options:**
- All args passed to ComfyUI

**Behavior:**
- Launches ComfyUI with proper environment
- Passes through all ComfyUI arguments

#### `comfydock status`
Show current environment state and pending changes.

**Behavior:**
- Compares ComfyUI state with last commit
- Shows workflow changes (added/modified/deleted)
- Lists node additions/removals
- Identifies model changes in workflows
- Displays uncommitted changes

**Output Example:**
```
Environment Status: test-env

Workflows:
  Modified: my_workflow.json
    - Models: 2 unresolved, 1 changed
  Added: new_workflow.json
    - Not yet tracked (use 'comfydock workflow track')

Custom Nodes:
  Added: comfyui-impact-pack (not in last commit)

Changes ready to commit:
  - 2 workflow changes
  - 1 node addition

Run 'comfydock commit' to save current state
```

### Node Management

#### `comfydock node add <identifier>`
Add a custom node to the environment.

**Identifier Types:**
- Registry ID: `comfyui-impact-pack`
- Registry ID with version: `comfyui-impact-pack@1.2.3`
- GitHub URL: `https://github.com/user/repo`
- Local directory name: `my-node` (with `--dev` flag for existing directory)

**Options:**
- `--dev` - Track as development node (for existing directories or git repos)
- `--no-test` - Skip Python dependency resolution testing
- `--force` - Force overwrite existing directory (bypasses conflict detection)

**Behavior**:

**Standard Add (Registry/GitHub)**:
1. ✓ Detect filesystem conflicts (git repos, existing directories)
2. ✓ Check for .disabled version (remove if exists)
3. ✓ Resolve identifier (registry lookup or GitHub validation)
4. ✓ Download to global cache (if not cached)
5. ✓ Extract/clone to custom_nodes/
6. ✓ Scan Python requirements
7. ✓ Add to pyproject.toml with isolated dependency group
8. ✓ Test resolution with uv (unless --no-test)
9. ✓ Sync Python virtual environment

**Development Add** (`--dev`):
1. ✓ Check directory exists in custom_nodes/
2. ✓ Check not already tracked in pyproject.toml
3. ✓ Scan Python requirements from filesystem
4. ✓ Add to pyproject.toml with `source="development"`
5. ✓ Test resolution (unless --no-test)
6. ✓ Sync virtual environment

**Force Add** (`--force`):
- Bypasses all conflict detection
- Deletes existing directory without warning
- Proceeds with standard add flow

**Conflict Detection**:
- **Git repository detected**: Suggests `--dev` to track existing clone
- **Directory exists**: Suggests `--dev` to track or `--force` to replace
- **URL mismatch**: Warns about repository conflict (name collision)
- **Already tracked**: Shows error with update/remove suggestions

**Examples**:
```bash
# Add registry node
$ comfydock node add comfyui-manager

# Add GitHub node
$ comfydock node add https://github.com/ltdrdata/ComfyUI-Impact-Pack

# Track existing git clone as dev node
$ git clone https://github.com/me/my-node custom_nodes/my-node
$ comfydock node add my-node --dev

# Force overwrite existing directory
$ comfydock node add comfyui-manager --force
```

#### `comfydock node remove <identifier>`
Remove a custom node from the environment.

**Behavior**:
1. ✓ Lookup node by identifier or name in pyproject.toml
2. ✓ Remove from pyproject.toml
3. ✓ Remove associated dependency group
4. ✓ Handle filesystem based on node type:
   - **Development nodes**: Rename to `.disabled` suffix (preserved)
   - **Registry/Git nodes**: Delete from filesystem (cached globally)
5. ✓ Clean up orphaned UV sources (if any)
6. ✓ Re-sync Python virtual environment

**Development Node Protection**:
```bash
$ comfydock node remove my-dev-node
✓ Development node 'my-dev-node' removed from tracking
ℹ️  Files preserved at: custom_nodes/my-dev-node.disabled/
```

**Registry/Git Node Deletion**:
```bash
$ comfydock node remove comfyui-manager
✓ Removed node 'comfyui-manager' from environment
# custom_nodes/ComfyUI-Manager/ deleted (can re-download from cache)
```

**Re-enabling Disabled Node**:
```bash
$ comfydock node add my-dev-node --dev
✓ Removed old disabled version
✓ Added development node 'my-dev-node'
```

#### `comfydock node list`
List all installed custom nodes.

**Options:**
- `--dev` - Show only development nodes
- `--registry` - Include registry metadata

### Workflow Management

NOTE: No specific workflow tracking for this MVP! We're going to try automatically tracking ALL workflows in the environment.
The behavior below is for a post-MVP release (if users want it/we find commits slow with many large workflows etc.)

#### TODO: `comfydock workflow track <name>`
Start tracking a workflow for version control.

**Behavior:**
- Registers workflow name in pyproject.toml
- No copying or analysis (lazy approach)
- Workflow remains in ComfyUI directory

**Note:** Tracking alone doesn't preserve the workflow. Use `commit` to snapshot.

#### TODO: `comfydock workflow untrack <name>`
Stop tracking a workflow.

**Behavior:**
- Removes from pyproject.toml
- Deletes from .cec/workflows/ if exists
- Doesn't affect ComfyUI workflow file

#### `comfydock workflow list`
List all workflows in the environment. (Currently ALL workflows will be tracked!)

**Output:**
```
Tracked Workflows:
  ✓ my_workflow      (committed)
  ⚠ test_workflow    (modified since commit)
  ○ new_workflow     (not committed)

TODO: Untracked Workflows in ComfyUI:
  - experiment_1
  - old_backup
```

### Version Control

#### `comfydock commit [-m "<message>"]`
Create a version snapshot of the current environment state.

**Behavior:**
1. **Copy Workflows**: All tracked workflows copied from ComfyUI to .cec/workflows/
2. **Resolve Models**: Parse workflows for model references and resolve against index
3. **Update pyproject.toml**: Record resolved models with hashes (as well as unresolved/skipped), and locations in workflow file via node ID and widget index.
4. **Git Commit**: Create git commit with all changes

**Model Resolution Process:**
```python
# For each model reference in workflow:
0. See if we already have resolved the same model in our pyproject.toml
1. Try exact path match in index
2. Try directory-aware match (e.g., checkpoints/ for checkpoint loaders)
3. Try filename similarity
4. If multiple matches → interactive prompt
5. Store resolution: {filename, hash, node_id, widget_index}
```

**Interactive Resolution Example:**
```
Resolving model: "sd15.safetensors"
Multiple matches found:
  1. models/checkpoints/sd15.safetensors (4.2 GB)
  2. models/backup/sd15.safetensors (4.2 GB)
  3. models/test/sd15.safetensors (2.1 GB)

Select [1-3] or (s)kip: _
```

> **NOTE:** We only ask the user to help resolve models if we haven't previously resolved the model in the pyproject.toml via user choice/skipping model.
> <br> i.e. we find model in workflow parsing that could be ambiguous (a custom node with "model.ckpt" which could map to checkpoints/model.ckpt or loras/model.ckpt).
> <br> We then check if that same node ID + widget value exists in our pyproject.toml with the same model filename "model.ckpt", if so we choose what exists in pyproject.toml.

#### `comfydock rollback <target>`
Restore environment to a previous state.

**Target Options:**
- Version tag: `v1`, `v2`, etc. (simple versioning)
- Commit hash: `abc123`
- Relative: `HEAD~1`
- Empty: Discard all uncommitted changes

**Behavior:**
1. **Git Operations**:
   - Apply historical state to current branch (NOT git checkout)
   - pyproject.toml reverts to historical state
   - uv.lock reverts to historical versions
   - .cec/workflows/ reverts to historical workflows

2. **Node Reconciliation** (via sync):
   - **Install missing registry/git nodes** from cache
   - **Disable extra development nodes** (add .disabled suffix)
   - **Delete extra registry/git nodes**
   - **Skip development nodes** (not version controlled)

3. **Workflow Updates**:
   - Copy workflows from .cec/ to ComfyUI/ (overwrite)
   - Delete workflows not in .cec/
   - Update model paths if files moved (using hashes + node_id:widget mapping)

4. **Python Environment Sync**:
   - Run `uv sync` with historical uv.lock
   - Recreate virtual environment at exact historical state

**Important Notes:**
- Changes applied to current branch (status shows as modifications)
- **Development nodes NOT rolled back** (user manages git state)
- Can commit rollback as new version: `comfydock commit -m "Reverted to v1"`
- Development node dependencies may change - run `node update <dev-node>` if needed

**Development Node Warning**:
```bash
$ comfydock rollback v1
⚠️  Development nodes are not version controlled:
   - my-dev-node (dependencies may have changed)

Suggestion: Check dev node requirements and run:
  comfydock node update my-dev-node
```

**Examples:**
```bash
# Rollback to previous version
$ comfydock rollback v1

# Discard uncommitted changes
$ comfydock rollback

# Rollback specific commit
$ comfydock rollback abc123

# Commit the rollback as new version
$ comfydock commit -m "Reverted workflow changes"
```

#### `comfydock log`
Show commit history for the environment.

**Options:**
- `--limit <n>` - Number of commits to show
- `--oneline` - Compact format

### Import/Export

#### `comfydock export <workflow_name>`
Create a distributable bundle of a workflow with all dependencies.

**Options:**
- `--output <path>` - Output file path
- `--no-interactive` - Skip interactive model URL resolution

**Behavior:**
1. **Fresh Copy**: Copy latest workflow from ComfyUI
2. **Full Analysis**:
   - Extract all model references
   - Identify custom nodes
   - Parse Python dependencies
3. **Model Resolution**:
   - Generate full hashes (SHA256 + Blake3)
   - Attempt API lookups (CivitAI, HuggingFace)
   - Interactive URL input for unknowns
4. **Bundle Creation**:
   - pyproject.toml (with full dependency specs)
   - comfydock.lock (model/node download URLs)
   - uv.lock (Python dependencies)
   - workflows/ directory
   - dev_nodes/ (if any development nodes)

**Export Interactive Process:**
```
Exporting workflow: my_workflow

Analyzing models...
✓ sd15.safetensors → https://civitai.com/api/download/models/4384
✓ vae.safetensors → https://huggingface.co/vae/resolve/main/vae.safetensors
? lora_custom.safetensors → Model not found in registries

Enter download URL for lora_custom.safetensors
(or press Enter to skip): https://example.com/lora_custom.safetensors

Resolving custom nodes...
✓ comfyui-impact-pack → Registry version 4.18
✓ my-custom-node → Bundled (development node)

Creating bundle...
✓ Export complete: my_workflow_bundle.tar.gz
```

#### `comfydock import <bundle_path>`
Import a workflow bundle into a new or existing environment.

**Options:**
- `--env <name>` - Target environment (creates if doesn't exist)
- `--skip-models` - Don't download models
- `--skip-nodes` - Don't install nodes

**Behavior:**
1. **Unpack Bundle**: Extract all files
2. **Environment Setup**: Create/select target environment
3. **Model Resolution**:
   ```
   For each required model:
     - Check if exists in index (by hash)
     - If missing → offer download/substitute/skip
     - Update workflow paths to local locations
   ```
4. **Node Installation**:
   ```
   For each required node:
     - Check if in cache
     - Download if missing
     - Install with dependencies
   ```
5. **Final Setup**:
   - Copy workflows to ComfyUI
   - Sync Python environment
   - Initial commit

**Import Interactive Process:**
```
Importing bundle: my_workflow_bundle.tar.gz

Creating environment: imported-workflow

Checking models...
✓ sd15.safetensors (found locally)
✗ special_lora.safetensors (not found)

Download special_lora.safetensors? (2.1 GB)
  1. Download from URL
  2. Select local substitute
  3. Skip (workflow may not function)
Choice [1-3]: 1

Downloading... ████████████ 100%

Installing custom nodes...
✓ comfyui-impact-pack (from cache)
✓ my-custom-node (from bundle)

Import complete! Run with: comfydock run
```

### Model Management

#### `comfydock models index <directory>`
Index a directory of model files.

**Behavior:**
- Scans directory recursively
- Generates quick hashes for all files
- Updates SQLite database
- Shows progress for large directories

#### `comfydock models list`
List all indexed models.

**Options:**
- `--filter <pattern>` - Filter by filename
- `--verify` - Check file existence

#### `comfydock models resolve <workflow_name>`
Manually resolve models in a workflow.

**Behavior:**
- Interactive resolution process
- Updates pyproject.toml
- Useful before export

## System Behaviors

### Workflow Lifecycle

#### Development Phase
```
1. User creates workflow in ComfyUI browser
2. User saves in ComfyUI (to disk)
3. User runs: comfydock workflow track my_workflow
4. User continues editing in browser
5. User adds nodes: comfydock node add <node>
6. User saves in ComfyUI again
7. User commits: comfydock commit -m "Added new sampler"
```

#### Distribution Phase
```
1. User exports: comfydock export my_workflow
2. System analyzes all dependencies
3. User provides missing URLs
4. Bundle created with all metadata
```

#### Consumption Phase
```
1. New user imports: comfydock import bundle.tar.gz
2. System checks for models/nodes
3. User approves downloads
4. Environment configured automatically
5. Workflow ready to run
```

### Model Resolution Logic

#### Resolution Hierarchy
1. **Exact Match**: Full path matches exactly
2. **Directory Context**: Node type implies directory
   - CheckpointLoaderSimple → checkpoints/
   - LoraLoader → loras/
   - VAELoader → vae/
3. **Filename Match**: Same filename, different path
4. **Interactive**: Multiple matches or no matches

#### Hash Verification
- **Quick Hash**: For fast local lookups during development
- **Full Hash**: For export/import verification
- **API Lookup**: SHA256 for CivitAI, Blake3 for HuggingFace

### Custom Node Isolation

Each custom node gets its own dependency group:
```toml
[dependency-groups]
comfyui-core = ["torch>=2.0", "numpy", "pillow"]

# Each node isolated
"node:comfyui-impact-pack" = ["opencv-python>=4.5"]
"node:comfyui-animatediff" = ["einops>=0.6"]

[tool.comfydock.nodes]
"comfyui-impact-pack" = {
    source = "registry",
    version = "4.18",
    registry_id = "comfyui-impact-pack"
}
```

### Git Integration

#### Commit Structure
```
.cec/
├── .git/                  # Git repository
├── workflows/             # Tracked workflow copies
│   └── my_workflow.json
├── pyproject.toml         # Dependencies and config
├── uv.lock               # Python lockfile
└── comfydock.lock        # Model/node URLs (export only)
```

#### Rollback Behavior
- **NOT** a git checkout (stays on current branch)
- Applies historical state as new changes
- Shows as modifications in `git status`
- Can be committed as new version

### Development Nodes

Development nodes are bundled with exports:
```
bundle.tar.gz
├── pyproject.toml
├── workflows/
└── dev_nodes/
    └── my-custom-node/    # Full source included
        ├── __init__.py
        ├── nodes.py
        └── requirements.txt
```

### .comfydock_ignore

Users can specify a .comfydock_ignore file under their environment's .cec/ which will:
- Allow for specific custom nodes to be ignored by the system (both tracking and disabling etc.)
- Allow for specific workflows to be ignored from tracking (wont be copied to and from .cec/workflows)

CLI commands can be made to help manage workflows/nodes that are ignored (FUTURE ENHANCEMENT)

## Data Structures

### pyproject.toml Structure

```toml
[project]
name = "comfydock-env-test"
version = "1.0.0" # Comfydock version
requires-python = ">=3.11"
dependencies = [ # Core ComfyUI dependencies
    "torch>=2.0.0",
    "torchvision",
    "torchaudio",
    "numpy",
    "pillow",
    "requests",
]

[tool.uv]
dev-dependencies = []

[dependency-groups]
"comfyui-impact-pack" = [
    "opencv-python>=4.5.0",
]

[tool.comfydock.environment]
comfyui_version = "v1.0.0" # Can also use git commit hash
python_version = "3.11"

[tool.comfydock.workflows]
my_workflow = { 
  path = "workflows/my_workflow.json",
  models = { # Order should ideally be stable across model resolves/commits
    "abc123..." = { # Key models by quick hash
      nodes = [
          {node_id = "3", widget_idx = "0"}
      ]
    }
  }
}

[tool.comfydock.models.required]
"abc123..." = { # Key models by quick hash
  filename: "sd15.safetensors",
  relative_path: "checkpoints"
  hash = "abc123...",  # Quick hash
  sha256 = "def456...",  # Full hash (export only)
  blake3 = "ghi789...",  # Full hash (export only)
}

[tool.comfydock.nodes]
"comfyui-impact-pack" = {
    source = "github",
    registry_id = "comfyui-impact-pack",
    version = "4.18"
}
"my-custom-node" = {
    source = "dev",
    path = "dev_nodes/my-custom-node"
}
```

### comfydock.lock Structure (Export Only)

```toml
# Generated file - do not edit
lock_version = 1
revision = 1

[[model]]
hash = "abc123..."
name = "sd15.safetensors",
url = "https://civitai.com/api/download/models/4384",
sha256 = "abc123...",
blake3 = "def456...",
size = 4265380512

[[node]]
id = "comfyui-impact-pack"
url = "https://github.com/ltdrdata/ComfyUI-Impact-Pack",
method = "git-clone",
ref = "4.18"
```

### Model Index Schema

#### Models table: One entry per unique model file (by hash)
```sql
CREATE TABLE IF NOT EXISTS models (
    hash TEXT PRIMARY KEY, -- Quick hash key
    file_size INTEGER NOT NULL,
    sha256_hash TEXT,  -- Computed on demand
    blake3_hash TEXT,  -- Computed on demand
    last_modified INTEGER NOT NULL,
    indexed_at INTEGER NOT NULL,
    metadata TEXT DEFAULT '{}'
);
```

#### Model locations: All instances of each model in tracked directory
```sql
CREATE TABLE IF NOT EXISTS model_locations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_hash TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    filename TEXT NOT NULL,
    mtime REAL NOT NULL,
    last_seen INTEGER NOT NULL,
    FOREIGN KEY (model_hash) REFERENCES models(hash) ON DELETE CASCADE,
    UNIQUE(relative_path)
);
```

#### Model sources: Track where models can be downloaded from
```sql
CREATE TABLE IF NOT EXISTS model_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_hash TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_url TEXT NOT NULL,
    metadata TEXT DEFAULT '{}',
    added_time INTEGER NOT NULL,
    FOREIGN KEY (model_hash) REFERENCES models(hash) ON DELETE CASCADE,
    UNIQUE(model_hash, source_url)
);
```

#### Model index schema version
```sql
CREATE TABLE IF NOT EXISTS schema_info (
    version INTEGER PRIMARY KEY
)
```

#### Indexes for efficient queries
```sql
CREATE INDEX IF NOT EXISTS idx_locations_hash ON model_locations(model_hash);
CREATE INDEX IF NOT EXISTS idx_locations_path ON model_locations(relative_path)
CREATE INDEX IF NOT EXISTS idx_models_blake3 ON models(blake3_hash)
CREATE INDEX IF NOT EXISTS idx_models_sha256 ON models(sha256_hash)
CREATE INDEX IF NOT EXISTS idx_locations_filename ON model_locations(filename)
CREATE INDEX IF NOT EXISTS idx_sources_hash ON model_sources(model_hash)
CREATE INDEX IF NOT EXISTS idx_sources_type ON model_sources(source_type)
```


## Implementation Details

### File Organization

```
workspace/
├── .metadata/
│   └── workspace.json              # Workspace configuration
├── comfydock_cache/
│   ├── custom_nodes/
│   │   ├── store/                  # Downloaded custom nodes (hashed directories like a1b2c3/ containing content/ and metadata.json)
│   │   ├── index.json              # Index mapping node directory hashes to node info for efficient lookups
│   │   └── node_mappings.json      # Global table mapping node types to node info (used for resolving unknown custom nodes in workflows)
│   ├── api_cache/                  # Global caches for api calls to external services (can have short expiration e.g. 4 hours)
│   │   ├── registry_cache.json     # Comfy Registry API cached queries + responses
│   │   └── github_cache.json       # Github API cached queries + responses
│   └── models.db                   # Model index database
├── environments/
│   ├── test/
│   │   ├── ComfyUI/                # ComfyUI installation
│   │   ├── .venv/                  # Managed Python virtual environment
│   │   └── .cec/                   # Git repository for tracking
│   └── production/
├── logs/                           # Workspace + Environment logs
│   ├── workspace/
│   │   └── workspace.log
│   ├── test.log
│   └── production.log
├── uv/python/                      # UV managed python interpreter cache
└── uv_cache/                       # UV managed package cache
```

### Workspace Metadata
We store workspace-level configuration details under workspace/.metadata/workspace.json
File structure example:
```json
{
  "version": 1,
  "active_environment": "test1",
  "created_at": "2025-09-14T19:34:46.840921",
  "global_model_directory": {
    "path": "/home/<user>/ComfyUI/models",
    "added_at": "2025-09-15T22:40:32.846419",
    "last_sync": "2025-09-15T22:40:32.846423"
  }
}
```
Currently workspace config includes:
- Which environment is currently 'active' (via use command)
- Path to the global model directory on the host machine (set up at init or using config command)

### Error Recovery

#### Failed Node Installation
- Custom node fails to resolve dependencies in test environment
- Warn user with about failed resolution
- Keep downloaded node in cache
- User can modify python dependencies in pyproject.toml and try install again
- User can choose to force add node + dependencies to pyproject without resolution testing via --no-test

#### Model Resolution Conflicts
- Present all options to user
- Allow skipping
- Mark as unresolved in pyproject.toml
- Continue with rest of workflow

#### Rollback Failures
- Keep current state intact
- Show what couldn't be restored
- Suggest manual fixes
- Never leave broken environment

### Performance Optimizations

#### Model Indexing
- Parallel hashing for large directories
- Incremental updates (only new/modified files)
- Cache hash results in SQLite

#### Node Caching
- Global cache across all environments
- Content-addressed storage
- Compression for space efficiency

#### Resolution Testing
- Cached resolution results
- Skip tests with --no-test flag
- Batch multiple changes

## User Workflows

### Starting Fresh

```bash
# Initialize workspace
comfydock init ~/my-workspace # Enters interactive setup unless user specifies --no-interactive
# Prompts user to specify global models directory path
# Asks user if they'd like to migrate/import an existing ComfyUI installation
# On complete: export COMFYDOCK_HOME pointing at new workspace (defaults to ~/comfydock_workspace if no path specified via init <path>)

# Create first environment
comfydock create test-env --python 3.11

# Start working
comfydock run
```

### Daily Development

```bash
# Add custom node
comfydock node add comfyui-impact-pack

# TODO: Track workflow (FUTURE ENHANCEMENT)
# comfydock workflow track my_workflow

# Work in ComfyUI browser...

# Commit changes
comfydock commit -m "Added impact pack and new workflow"

# Continue working...

# Check status
comfydock status

# Commit again
comfydock commit -m "Refined sampler settings"
```

### Sharing Work

```bash
# Export workflow
comfydock export my_workflow

# Answer prompts for model URLs (if needed)
# → Creates my_workflow_bundle.tar.gz

# Share bundle file
```

### Receiving Work

```bash
# Import shared bundle, set name as "imported", set as active
comfydock import shared_workflow.tar.gz --name imported --use

# Approve model downloads
# Wait for setup...

# Run imported workflow
comfydock run
```

### Version Management

```bash
# View history
comfydock log --limit 10

# Outputs (e.g.): 
# Version history for environment 'test1':
# v2: Updated workflow
# v1: Initial environment setup
# Use 'comfydock rollback <version>' to restore to a specific version

# Rollback to previous
comfydock rollback

# Or to specific commit
comfydock rollback v1 # Currently organizing commits with simple v<num> (v1, v2, etc.)

# Status shows rollback changes
comfydock status

# Commit rollback as new version
comfydock commit -m "Reverted to previous sampler"
```

## Future Enhancements

### Phase 2 Features
- Workflow diffing between versions
- Batch workflow operations
- Model download queue management
- Custom node version upgrades
- Workspace templates

### Phase 3 Features
- Cloud model registry integration
- Workflow testing automation
- Dependency conflict auto-resolution
- Bundle signing and verification
- Multi-environment batch operations

## Migration Path

### From v1 (bidirectional sync)
1. Final sync in v1
2. Upgrade ComfyDock
3. Run migration command
4. Verify workflows match
5. First commit in v2

### Breaking Changes
- No more `sync` command
- No workflow metadata injection
- Rollback behavior changed (applies changes vs checkout)
- Model resolution now lazy (at commit/export)

## Implementation Status

### ✅ Implemented (MVP Complete)

**Node Management**:
- ✅ Imperative add/remove (immediate filesystem changes)
- ✅ Git conflict detection with URL normalization
- ✅ .disabled pattern for development node preservation
- ✅ --force flag for explicit overwrites
- ✅ Three node types (registry, git, development)
- ✅ Isolated dependency groups per node
- ✅ Development node requirement scanning

**Version Control**:
- ✅ Git-based commit/rollback for local versioning
- ✅ Workflow copying to .cec/
- ✅ pyproject.toml + uv.lock tracking
- ✅ Simple version tags (v1, v2, etc.)

**Safety Features**:
- ✅ Filesystem conflict detection
- ✅ Non-destructive .disabled suffix
- ✅ Clear error messages with suggestions
- ✅ Protected development nodes

**Sync Behavior**:
- ✅ Python package reconciliation (uv sync)
- ✅ Node reconciliation (install missing, disable extra)
- ✅ Model path synchronization

### 🚧 In Progress

**Export/Import**:
- ⚠️ Export command structure defined (not fully implemented)
- ⚠️ Import command structure defined (not fully implemented)
- ⚠️ comfydock.lock format designed (not implemented)
- ⚠️ Model URL resolution (partially implemented)
- ⚠️ Dev node bundling in exports (not implemented)

**Model Management**:
- ⚠️ Model resolution (basic implementation exists)
- ⚠️ CivitAI/HuggingFace API integration (planned)
- ⚠️ Interactive model resolution UI (basic exists)

### 📋 Planned (Post-MVP)

**Enhanced Features**:
- ⏱ Workflow diffing between versions
- ⏱ Batch node operations
- ⏱ Model download queue management
- ⏱ Node version upgrade paths
- ⏱ Cloud package registry integration
- ⏱ Workflow testing automation
- ⏱ Bundle signing and verification

**UX Improvements**:
- ⏱ Interactive conflict resolution prompts
- ⏱ Uncommitted changes detection (git status check)
- ⏱ Current branch/commit display in node add
- ⏱ Better progress indicators for large operations

**Optimization**:
- ⏱ Parallel node downloads
- ⏱ Smarter model hash caching
- ⏱ Incremental workflow analysis

### 🔧 Technical Debt

**Testing**:
- ⚠️ Integration tests for full add/remove/rollback flows
- ⚠️ Export/import end-to-end tests (when implemented)
- ⚠️ Model resolution edge cases

**Documentation**:
- ✅ Architecture specification (this document)
- ⚠️ User guide (needs update with new features)
- ⚠️ API documentation (needs generation)

**Code Quality**:
- ⚠️ Obsolete test cleanup (3 tests reference removed methods)
- ⚠️ Error message consistency audit
- ⚠️ Logging standardization

## Summary

ComfyDock v2.0 implements a **two-tier reproducibility model** that separates local iteration from global distribution. The architecture embraces an **imperative, filesystem-first** approach to node management that respects user data and manual interventions.

Key innovations:
1. **Git for iteration**: Fast local versioning without tracking binary data
2. **Packages for distribution**: Complete reproducibility for sharing
3. **Conflict detection**: Never silently destroys user data
4. **Protected dev nodes**: .disabled suffix preserves work in progress
5. **Three node types**: Clear distinction between registry, git, and development

The system provides robust reproducibility through git versioning and comprehensive dependency tracking while maintaining a clear, predictable data flow that matches user expectations.