# ComfyGit

Version control for ComfyUI environments - manage your AI workflows like code.

## Why ComfyGit?

If you've worked with ComfyUI for a while, you've probably hit these problems:

- **Dependency hell**: Installing a new custom node breaks your existing workflows
- **No reproducibility**: "It worked last month" but you can't remember what changed
- **Sharing is painful**: Sending someone your workflow means a wall of text about which models/nodes to install
- **Environment sprawl**: Testing new nodes means risking your stable setup

ComfyGit solves this by treating your ComfyUI environments like Git repositories:

- ✅ **Multiple isolated environments** — test new nodes without breaking production
- ✅ **Git-based versioning** — commit changes, rollback when things break
- ✅ **One-command sharing** — export/import complete working environments
- ✅ **Smart model management** — content-addressable index, no duplicate storage
- ✅ **Standard tooling** — built on UV and pyproject.toml, works with Python ecosystem

## Installation

**Requirements:** Python 3.10+, Windows/Linux/macOS

Install with UV (recommended):
```bash
# Install UV first (Linux/macOS)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install UV first (Windows)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```
```bash
# Install ComfyGit
uv tool install comfygit
```

Or with pip:
```bash
pip install comfygit
```

> **Note**: The old Docker-based `comfydock` (v0.x) is a different tool that's being deprecated. See [Migration](#migrating-from-docker-based-comfydock) if you were using that version.

## Quick Start

### Scenario 1: Basic Environment Setup

```bash
# Initialize workspace (one-time setup)
cg init

# Create an environment
cg create my-project --use

# Add some custom nodes
cg node add comfyui-akatz-nodes
cg node add https://github.com/ltdrdata/ComfyUI-Impact-Pack

# Run ComfyUI
cg run
```

Your ComfyUI opens at `http://localhost:8188` with an isolated environment.

### Scenario 2: Version Control Workflow

```bash
# Save current state
cg commit -m "Initial setup with Impact Pack"

# Add more nodes, test things out
cg node add https://github.com/cubiq/ComfyUI_IPAdapter_plus
cg commit -m "Added IPAdapter"

# Oops, something broke
cg rollback v1  # Back to the first commit

# Or discard uncommitted changes
cg rollback
```

### Scenario 3: Sharing Workflows (Export/Import)

```bash
# Package your environment
cg export my-workflow-pack.tar.gz

# Share the .tar.gz file, then on another machine:
cg import my-workflow-pack.tar.gz --name imported-workflow
# Downloads all nodes and models, ready to run
```

### Scenario 4: Team Collaboration (Git Remote)

```bash
# Add a git remote (GitHub, GitLab, etc)
cg remote add origin https://github.com/username/my-comfyui-env.git

# Push your environment
cg push

# On another machine, import from git:
cg import https://github.com/username/my-comfyui-env.git --name team-env

# Pull updates
cg pull
```

## How It Works

ComfyGit uses a **two-tier reproducibility model**:

### Local Tier: Git-Based Versioning
Each environment has a `.cec/` directory (a git repository) tracking:
- `pyproject.toml` — custom nodes, model references, Python dependencies
- `uv.lock` — locked Python dependency versions
- `workflows/` — tracked workflow files

When you run `cg commit`, it snapshots this state. Rollback restores any previous commit.

### Global Tier: Export/Import Packages
Export bundles everything needed to recreate the environment:
- Node metadata (registry IDs, git URLs + commits)
- Model download sources (CivitAI URLs, HuggingFace, etc)
- Python dependency lockfile
- Development node source code

Import recreates the environment on any machine with compatible hardware.

### Under the Hood
- **UV for Python** — Fast dependency resolution and virtual environments
- **Standard pyproject.toml** — Each custom node gets its own dependency group to avoid conflicts
- **Content-addressable models** — Models identified by hash, allowing path-independent resolution
- **Registry integration** — Uses ComfyUI's official registry for node lookup

## Model Management

### The Problem
ComfyUI workflows reference models by path (e.g., `checkpoints/mymodel.safetensors`), but:
- Different machines have different folder structures
- Models get duplicated across projects
- Sharing workflows means "download this from CivitAI and put it here..."

### ComfyGit's Solution
A **workspace-wide model index** using content-addressable storage:
1. Point ComfyGit at your existing models directory (or use ComfyGit's)
2. It scans and indexes models by hash (Blake3 quick hash for speed)
3. When importing workflows, models are matched by hash, not path
4. Download sources (CivitAI URLs, etc) are tracked and can be auto-downloaded

### Basic Usage

```bash
# During init, you're prompted to set models directory
cg init  # Interactive setup

# Or point to existing models
cg model index dir ~/my-huge-model-library

# Sync the index
cg model index sync

# Download models
cg model download https://civitai.com/models/...

# Find models
cg model index find "juggernaut"
```

Models are symlinked into each environment from the global directory, so no duplication.

## Comparison to Alternatives

| Tool | Approach | Pros | Cons |
|------|----------|------|------|
| **ComfyUI Manager** | In-UI node installer | Easy, visual | No versioning, no isolation, one global environment |
| **Manual Git Clones** | Clone nodes to `custom_nodes/` | Full control | Dependency conflicts, no reproducibility |
| **Docker** | Containerize everything | Isolation | Heavy, slow iteration, complex setup |
| **ComfyGit** | Git-based package manager | Fast, reproducible, shareable, standard tooling | CLI-focused, newer/less mature |

## Workspace Structure

```
~/comfygit/                     # Default workspace root
├── environments/               # Your environments
│   ├── production/
│   │   ├── ComfyUI/           # Actual ComfyUI installation
│   │   │   ├── custom_nodes/  # Installed nodes
│   │   │   ├── models/        # Symlinks to workspace models
│   │   │   └── .venv/         # Python virtual environment
│   │   └── .cec/              # Version control (git repo)
│   │       ├── workflows/     # Tracked workflows
│   │       ├── pyproject.toml # Dependencies & config
│   │       └── uv.lock        # Dependency lockfile
│   └── experimental/          # Another environment
├── models/                     # Shared models (optional)
└── .metadata/                  # Workspace config & model index DB
```

## Features

### Environment Management
```bash
cg create <name>              # Create new environment
cg list                       # List all environments
cg use <name>                 # Set active environment
cg delete <name>              # Delete environment
cg status                     # Show environment state
```

### Custom Nodes
```bash
cg node add <id>              # Add from registry
cg node add <github-url>      # Add from GitHub
cg node add <dir> --dev       # Track development node
cg node remove <id>           # Remove node
cg node list                  # List installed nodes
cg node update <id>           # Update node
```

### Versioning
```bash
cg commit -m "message"        # Save snapshot
cg log                        # View history
cg rollback <version>         # Restore previous state
cg rollback                   # Discard uncommitted changes
```

### Sharing & Collaboration
```bash
cg export <file.tar.gz>       # Export environment
cg import <file.tar.gz>       # Import environment
cg import <git-url>           # Import from git repo
cg remote add origin <url>    # Add git remote
cg push                       # Push to remote
cg pull                       # Pull from remote
```

### Workflows
```bash
cg workflow list              # List tracked workflows
cg workflow resolve <name>    # Resolve missing dependencies
```

### Python Dependencies
```bash
cg py add <package>           # Add Python package
cg py remove <package>        # Remove Python package
cg py list                    # List dependencies
```

## Documentation

Full documentation at **[docs.comfyhub.org/comfygit](https://docs.comfyhub.org/comfygit)**

## Migrating from Docker-based comfydock

The old Docker-based comfydock (v0.x, `pip install comfydock`) is a different tool that's being deprecated. ComfyGit is a complete rewrite with a different architecture. Both can coexist on the same system:

- **Old comfydock**: `comfydock` command, Docker containers, GUI-focused
- **ComfyGit**: `cg` command, UV-based, CLI-focused, shareable

There's no automatic migration path. We recommend starting fresh with ComfyGit for new projects. See [migration guide](https://docs.comfyhub.org/comfygit/migration) for details.

## Project Structure

ComfyGit is a Python monorepo:
- **comfygit-core** — Core library for environment/node/model management
- **comfygit** — Command-line interface (`cg` command)

For development setup, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Contributing

This project is currently maintained by a single developer. Contributions are welcome!

- **Issues**: Bug reports and feature requests
- **Discussions**: Questions, ideas, showcase your workflows
- **PRs**: Code contributions (see CONTRIBUTING.md)

## Community

- **Docs**: [docs.comfyhub.org/comfygit](https://docs.comfyhub.org/comfygit)
- **Issues**: [GitHub Issues](https://github.com/comfyhub-org/comfygit/issues)
- **Discussions**: [GitHub Discussions](https://github.com/comfyhub-org/comfygit/discussions)

## License

ComfyGit is **dual-licensed** to support both open-source and commercial use:

### Open Source: AGPL-3.0

The project is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)** for open-source use.

- ✅ **Free forever** - Use, modify, and distribute freely
- ✅ **Strong copyleft** - Modifications must be open-sourced under AGPL-3.0
- ✅ **Network use** - SaaS deployments must make source available to users
- ✅ **Community-driven** - Ensures improvements benefit everyone

See [LICENSE.txt](LICENSE.txt) for the full license text.

### Commercial: Proprietary Licensing

**For businesses** requiring proprietary use without AGPL-3.0 obligations:

- 🏢 **Proprietary deployments** - No requirement to open-source your modifications
- 🏢 **SaaS without disclosure** - Run network services without sharing code
- 🏢 **Custom terms** - Tailored licensing for enterprise needs
- 🏢 **Support options** - Priority support and custom development available

**Contact us** to discuss commercial licensing options and pricing.

### Why Dual Licensing?

This model allows us to:
- Keep the project **free and open-source** for the community
- Generate **sustainable funding** for continued development
- Offer **flexibility** for businesses with different needs

### Contributing

By contributing to ComfyGit, you agree to our [Contributor License Agreement](CLA.md), which allows us to distribute your contributions under both licenses. See [CONTRIBUTING.md](CONTRIBUTING.md) for details.
