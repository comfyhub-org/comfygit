# ComfyGit

> A package and environment manager for ComfyUI that brings reproducibility and version control to AI image generation workflows.

## Get started in 5 minutes

Prerequisites:

* Python 3.10 or newer
* Windows, Linux, or macOS

**Install UV (package manager):**

=== "macOS/Linux"
    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

=== "Windows PowerShell"
    ```powershell
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    ```

**Install ComfyGit:**

```bash
uv tool install comfygit
```

**Start using ComfyGit:**

```bash
# Initialize workspace
cg init

# Create your first environment
cg create my-project --use

# Run ComfyUI
cg run
```

Your ComfyUI opens at `http://localhost:8188` with an isolated, reproducible environment. [Continue with Quickstart (5 mins) →](getting-started/quickstart.md)

!!! tip
    See [installation guide](getting-started/installation.md) for alternative install methods or [troubleshooting](troubleshooting/common-issues.md) if you hit issues.

!!! note "Migrating from old ComfyGit (v0.x)?"
    The Docker-based ComfyGit is being deprecated. This is v1.0+, a complete rewrite with a new approach. See [migration guide](getting-started/migrating-from-v0.md) if you were using the old version.

## What ComfyGit does for you

* **Multiple isolated environments** — Test new nodes without breaking your production setup
* **Git-based version control** — Commit changes, rollback when things break, collaborate via GitHub/GitLab
* **One-command sharing** — Export/import complete working environments with all dependencies
* **Smart model management** — Content-addressable index prevents duplicate storage, resolves models by hash instead of path
* **Standard tooling** — Built on UV and pyproject.toml, works seamlessly with Python ecosystem

## Why use ComfyGit?

If you've worked with ComfyUI, you've probably hit these problems:

* **Dependency hell** — Installing a new custom node breaks your existing workflows
* **No reproducibility** — "It worked last month" but you can't remember what changed
* **Sharing is painful** — Sending someone your workflow means a wall of text about which models and nodes to install
* **Environment sprawl** — Testing new nodes means risking your stable setup

ComfyGit solves these by treating your ComfyUI environments like code projects—isolated, versioned, and shareable.

**Works in your terminal:**

```bash
# Install a custom node
cg node add comfyui-depthflow-nodes

# Commit your changes
cg commit -m "Added depthflow nodes"

# Share with your team
cg export my-workflow.tar.gz
```

**Or via Git remotes:**

```bash
# Push to GitHub
cg remote add origin https://github.com/you/your-env.git
cg push

# Pull on another machine
cg import https://github.com/you/your-env.git --name team-env
```

## How it works

ComfyGit uses a **two-tier reproducibility model**:

### Local tier: Git-based versioning

Each environment has a `.cec/` directory (a git repository) tracking:

- `pyproject.toml` — custom nodes, model references, Python dependencies
- `uv.lock` — locked Python dependency versions
- `workflows/` — tracked workflow files

When you run `cg commit`, it snapshots this state. Rollback restores any previous commit.

### Global tier: Export/import packages

Export bundles everything needed to recreate the environment:

- Node metadata (registry IDs, git URLs + commits)
- Model download sources (CivitAI URLs, HuggingFace, etc)
- Python dependency lockfile
- Development node source code

Import recreates the environment on any machine with compatible hardware.

### Under the hood

- **UV for Python** — Fast dependency resolution and virtual environments
- **Standard pyproject.toml** — Each custom node gets its own dependency group to avoid conflicts
- **Content-addressable models** — Models identified by hash, allowing path-independent resolution
- **Registry integration** — Uses ComfyUI's official registry for node lookup

## Next steps

<div class="grid cards" markdown>

-   :rocket: **[Quickstart](getting-started/quickstart.md)**

    ---

    See ComfyGit in action with practical examples

-   :material-book-open-variant: **[Core Concepts](getting-started/concepts.md)**

    ---

    Understand workspaces, environments, and the .cec directory

-   :material-console: **[CLI Reference](cli-reference/environment-commands.md)**

    ---

    Master all commands and options

-   :material-export: **[Export & Import](user-guide/collaboration/export-import.md)**

    ---

    Share environments with your team

</div>

## Key features

<div class="grid cards" markdown>

-   :material-cube-outline: **[Custom Nodes](user-guide/custom-nodes/adding-nodes.md)**

    ---

    Add nodes from registry, GitHub, or local development

-   :material-file-image: **[Model Management](user-guide/models/model-index.md)**

    ---

    Content-addressable model index with CivitAI integration

-   :material-workflow: **[Workflow Resolution](user-guide/workflows/workflow-resolution.md)**

    ---

    Automatically detect and install workflow dependencies

-   :material-git: **[Version Control](user-guide/environments/version-control.md)**

    ---

    Commit, rollback, and collaborate via Git

</div>

## Community & support

* **Documentation**: You're here! Browse the guides
* **Issues**: Report bugs on [GitHub Issues](https://github.com/comfyhub-org/comfygit/issues)
* **Discussions**: Ask questions on [GitHub Discussions](https://github.com/comfyhub-org/comfygit/discussions)
