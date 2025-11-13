# Core Concepts

> Understand the fundamental concepts behind ComfyGit: workspaces, environments, and how reproducibility works.

## Overview

ComfyGit organizes your ComfyUI installations into a simple hierarchy:

```
Workspace (~/comfygit)
├── Environment 1 (production)
├── Environment 2 (testing)
└── Environment 3 (experiments)
```

Each level serves a specific purpose and has its own responsibilities.

## Workspace

A **workspace** is the top-level container for all your ComfyGit environments and shared resources.

### What it contains

```
~/comfygit/                      # Workspace root
├── environments/                 # All your environments
│   ├── production/
│   ├── testing/
│   └── experiments/
├── models/                       # Shared models directory
├── comfygit_cache/              # Registry cache, model index
├── logs/                         # Application logs
└── .metadata/                    # Workspace configuration
    └── workspace.json            # Settings (active env, models dir)
```

### Key features

* **One per machine** — You typically have one workspace per computer
* **Shared model index** — All environments share the same model database
* **Global configuration** — Settings like CivitAI API key are workspace-wide

### Creating a workspace

```bash
# Create in default location (~/comfygit)
cg init

# Custom location
cg init /path/to/workspace
```

The `COMFYGIT_HOME` environment variable determines the workspace location. If not set, defaults to `~/comfygit`.

## Environment

An **environment** is an isolated ComfyUI installation with its own dependencies, custom nodes, and configuration.

### What it contains

```
~/comfygit/environments/my-project/
├── .cec/                         # Configuration and version control
│   ├── pyproject.toml            # Dependencies, nodes, models
│   ├── uv.lock                   # Locked dependency versions
│   ├── workflows/                # Tracked workflows
│   └── .git/                     # Git repository
├── .venv/                        # Python virtual environment
└── ComfyUI/                      # ComfyUI installation
    ├── custom_nodes/             # Custom nodes
    ├── models/                   # Symlinks to workspace models
    └── user/default/workflows/   # Workflow files
```

### Key features

* **Isolated dependencies** — Each environment has its own Python packages
* **Version controlled** — State tracked in git for commits/rollbacks
* **Shareable** — Export as tarball or push to Git remote

### Creating an environment

```bash
# Basic creation
cg create my-env

# With Python version
cg create my-env --python 3.11

# With ComfyUI version
cg create my-env --comfyui v0.2.2

# With specific PyTorch backend
cg create my-env --torch-backend cu128

# Create and set as active
cg create my-env --use
```

## The .cec directory

The `.cec/` (ComfyUI Environment Configuration) directory is the heart of each environment. It's a git repository that tracks everything needed to reproduce your environment.

### Structure

```
.cec/
├── pyproject.toml                # Dependencies manifest
├── uv.lock                       # Locked versions
├── workflows/                    # Tracked workflows
├── .gitignore                    # Git ignore rules
└── .git/                         # Git history
```

### pyproject.toml

The main configuration file tracking:

**Custom nodes:**

```toml
[project.optional-dependencies]
"node/comfyui-manager" = ["GitPython>=3.1.0", "packaging>=23.0"]
"node/comfyui-impact-pack" = ["ultralytics>=8.0.0"]
```

**Model references:**

```toml
[tool.comfygit.models]
checkpoints = [
    "checkpoints/sd15.safetensors:blake3:abc123...",
]
```

**Development nodes:**

```toml
[tool.comfygit.dev-nodes]
my-custom-node = "../my-custom-node"  # Local path
```

### Why .cec?

* **Standard format** — Uses pyproject.toml, the Python standard
* **Human readable** — Edit manually if needed
* **Git-friendly** — Track changes over time
* **Lockfile included** — uv.lock ensures exact reproducibility

## Reproducibility model

ComfyGit uses a **two-tier approach** to reproducibility:

### Tier 1: Local versioning (Git commits)

**What it tracks:**

- Custom nodes (URLs, commits, versions)
- Python dependencies (via pyproject.toml + uv.lock)
- Model references (hashes, paths)
- Workflow files

**Commands:**

```bash
# Save current state
cg commit -m "Added IPAdapter nodes"

# View history
cg commit log

# Restore previous version
cg rollback v1
```

**When to use:**

- During development and experimentation
- Creating savepoints before risky changes
- Team collaboration via Git remotes

### Tier 2: Export/import packages

**What it includes:**

- Node metadata (registry IDs, git URLs + commits)
- Model download sources (CivitAI URLs, HuggingFace)
- Python dependency lockfile (uv.lock)
- Development node source code
- Tracked workflow files

**Commands:**

```bash
# Export environment
cg export my-workflow.tar.gz

# Import on another machine
cg import my-workflow.tar.gz --name imported-env
```

**When to use:**

- Sharing complete environments with others
- Moving between machines
- Long-term archival
- Distributing workflows to users

### How they work together

```
┌─────────────────────────────────────────────┐
│  Your Machine                               │
│  ┌─────────────────────────────────────┐   │
│  │  Environment                        │   │
│  │  - Custom nodes                     │   │
│  │  - Models                           │   │
│  │  - Workflows                        │   │
│  └─────────────────────────────────────┘   │
│           │                 │               │
│           │ commit          │ export        │
│           ↓                 ↓               │
│  ┌──────────────┐  ┌──────────────────┐   │
│  │ .cec/.git/   │  │ .tar.gz package  │───┼─→ Share
│  │ (commits)    │  │ (complete env)   │   │
│  └──────────────┘  └──────────────────┘   │
│           │                                 │
│           │ push/pull                       │
│           ↓                                 │
│  ┌──────────────────────┐                  │
│  │ Git Remote (GitHub)  │                  │
│  └──────────────────────┘                  │
└─────────────────────────────────────────────┘
```

## Model management

ComfyGit uses a **content-addressable model index** to solve path-dependency issues.

### The problem

ComfyUI workflows reference models by path:

```json
{
  "ckpt_name": "checkpoints/sd15.safetensors"
}
```

But different users have different folder structures:

- `~/models/checkpoints/sd15.safetensors`
- `D:\AI\Models\sd15.safetensors`
- `/mnt/storage/comfyui/checkpoints/sd15.safetensors`

### ComfyGit's solution

Models are indexed by **hash** (Blake3), not path:

1. Scan your models directory
2. Compute quick hash for each model
3. Store in workspace-wide database
4. Workflows reference models by hash
5. ComfyGit resolves hash → actual file path

### How it works

**Indexing models:**

```bash
# Point to your existing models
cg model index dir /path/to/models

# Scan and index
cg model index sync
```

**Workflow resolution:**

```bash
# Resolve workflow dependencies
cg workflow resolve my-workflow.json
```

ComfyGit will:

1. Extract model hashes from workflow
2. Look up in global index
3. Symlink from `workspace/models/` to `environment/ComfyUI/models/`
4. Download missing models from known sources

### Benefits

* **Path-independent** — Works regardless of folder structure
* **Deduplication** — Same model used by multiple environments
* **Source tracking** — Remember where models came from (CivitAI, HuggingFace)
* **Fast lookups** — SQLite database for quick queries

### Model importance

Mark models in workflows as required/flexible/optional:

```bash
# Required - workflow won't work without it
cg workflow model importance my-workflow checkpoint.safetensors required

# Flexible - can substitute with similar models
cg workflow model importance my-workflow style-lora.safetensors flexible

# Optional - nice to have but not critical
cg workflow model importance my-workflow detail-lora.safetensors optional
```

This helps when sharing workflows or importing on different machines. See [Workflow Model Importance](../user-guide/workflows/workflow-model-importance.md) for details.

## Node resolution

ComfyGit resolves custom nodes through multiple sources:

### 1. ComfyUI Registry

The official registry of custom nodes:

```bash
# Add by registry ID
cg node add comfyui-depthflow-nodes
```

ComfyGit queries the registry for:

- Git repository URL
- Latest version/commit
- Python dependencies

### 2. GitHub URLs

Direct from GitHub:

```bash
# Latest commit
cg node add https://github.com/akatz-ai/ComfyUI-AKatz-Nodes

# Specific version
cg node add https://github.com/akatz-ai/ComfyUI-AKatz-Nodes@v1.0.0

# Specific commit
cg node add https://github.com/akatz-ai/ComfyUI-AKatz-Nodes@abc123
```

### 3. Development nodes

Local nodes you're developing:

```bash
# Track local node
cg node add /path/to/my-node --dev
```

This creates a symbolic link and tracks the path in pyproject.toml.

### 4. Workflow-based resolution

When resolving workflows, ComfyGit:

1. Extracts node class names from workflow JSON
2. Looks up in cached registry mappings
3. Prompts for installation if not found
4. Uses embeddings + scoring for fuzzy matching

## Dependency isolation

Each custom node gets its own dependency group in pyproject.toml:

```toml
[project.optional-dependencies]
"node/comfyui-depthflow-nodes" = [
    "opencv-python>=4.0.0",
    "numpy>=1.24.0"
]

"node/comfyui-impact-pack" = [
    "ultralytics>=8.0.0",
    "onnxruntime>=1.15.0"
]
```

### Benefits

* **Conflict detection** — UV reports if nodes have incompatible deps
* **Selective installation** — Install only what you need
* **Clean removal** — Remove node and its unique dependencies

### Handling conflicts

If two nodes require incompatible versions:

```bash
# ComfyGit detects conflict
✗ Dependency conflict detected:
  - comfyui-depthflow-nodes requires torch>=2.0,<2.1
  - comfyui-video requires torch>=2.1

Options:
  1. Skip comfyui-video
  2. Use constraint to force version
  3. Contact node maintainer
```

Use constraints to override:

```bash
cg constraint add "torch==2.4.1"
```

## Python dependencies

ComfyGit uses UV for Python package management:

### Adding dependencies

```bash
# Add package
cg py add requests

# Add with version constraint
cg py add "numpy>=1.24,<2.0"

# Add from requirements.txt
cg py add -r requirements.txt
```

### Listing dependencies

```bash
# Show project dependencies
cg py list

# Show all (including transitive)
cg py list --all
```

### Removing dependencies

```bash
cg py remove numpy
```

## Active environment

ComfyGit tracks which environment is currently active:

```bash
# Set active
cg use my-project

# Commands use active env by default
cg run
cg status
cg node add comfyui-depthflow-nodes

# Or specify explicitly
cg -e testing run
cg -e production status
```

The active environment is stored in `workspace/.metadata/workspace.json`.

## Key takeaways

!!! success "Workspaces"
    * One per machine
    * Contains all environments
    * Shared model index

!!! success "Environments"
    * Isolated ComfyUI installations
    * Tracked in .cec git repository
    * Shareable via export/import

!!! success "Reproducibility"
    * **Tier 1**: Git commits for local versioning
    * **Tier 2**: Export packages for sharing

!!! success "Models"
    * Content-addressable (hash-based)
    * Workspace-wide index
    * Path-independent resolution

!!! success "Nodes"
    * Multiple sources (registry, GitHub, local)
    * Dependency groups in pyproject.toml
    * Conflict detection via UV

## Next steps

Now that you understand the concepts:

<div class="grid cards" markdown>

-   :material-cube-outline: **[Managing Custom Nodes](../user-guide/custom-nodes/adding-nodes.md)**

    ---

    Learn how to add, update, and remove nodes

-   :material-file-image: **[Model Management](../user-guide/models/model-index.md)**

    ---

    Deep dive into the model index system

-   :material-git: **[Version Control](../user-guide/environments/version-control.md)**

    ---

    Master commits, rollbacks, and Git remotes

-   :material-export: **[Export & Import](../user-guide/collaboration/export-import.md)**

    ---

    Share environments with your team

</div>
