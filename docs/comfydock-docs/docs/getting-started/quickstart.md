# Quickstart

> Get up and running with ComfyGit in 5 minutes. By the end, you'll have created an environment, added custom nodes, and understand the basics of version control for your ComfyUI workflows.

## Before you begin

Make sure you have:

* ComfyGit installed — [Installation guide](installation.md)
* A terminal or command prompt open
* Internet connection for downloading dependencies

## Step 1: Initialize your workspace

Create a ComfyGit workspace:

```bash
cg init
```

This creates `~/comfygit/` with the following structure:

```
~/comfygit/
├── environments/          # Your ComfyUI environments
├── models/                # Shared models directory
└── .metadata/             # Workspace configuration
```

!!! tip "Custom workspace location"
    Use a different path: `cg init /path/to/workspace`

## Step 2: Create your first environment

Create an isolated ComfyUI environment:

```bash
cg create my-project --use
```

This will:

1. Create a new environment called `my-project`
2. Download and install ComfyUI
3. Install PyTorch with GPU support (auto-detected)
4. Set it as your active environment
5. Take 2-5 minutes depending on your internet speed

!!! note "What's happening?"
    ComfyGit is creating an isolated Python environment with UV, downloading ComfyUI from GitHub, and installing dependencies. The `--use` flag makes this your active environment.

**What you'll see:**

```
🚀 Creating environment: my-project
   This will download PyTorch and dependencies (may take a few minutes)...

✓ Environment created: my-project
✓ Active environment set to: my-project

Next steps:
  • Run ComfyUI: cg run
  • Add nodes: cg node add <node-name>
```

## Step 3: Run ComfyUI

Start ComfyUI in your environment:

```bash
cg run
```

ComfyUI opens at `http://localhost:8188`

!!! tip "Run in background"
    ```bash
    cg run &
    ```

    Or use screen/tmux to keep it running:
    ```bash
    screen -S comfy
    cg run
    # Detach with Ctrl+A, D
    ```

## Step 4: Check environment status

Open a new terminal and check your environment's status:

```bash
cg status
```

**Output:**

```
Environment: my-project ✓

✓ No workflows
✓ No uncommitted changes
```

## Step 5: Add custom nodes

Let's add a custom node from the ComfyUI registry:

```bash
cg node add comfyui-depthflow-nodes
```

This will:

1. Look up the node in the ComfyUI registry
2. Clone the repository to `custom_nodes/`
3. Install Python dependencies
4. Update `pyproject.toml`

!!! tip "Adding nodes from GitHub"
    ```bash
    # Add by GitHub URL
    cg node add https://github.com/akatz-ai/ComfyUI-AKatz-Nodes

    # Add specific version/branch
    cg node add comfyui-depthflow-nodes@main
    ```

!!! warning "Avoid ComfyUI-Manager"
    ComfyGit replaces ComfyUI-Manager's functionality. Don't install `comfyui-manager` - use `cg node add` instead.

**Try adding more nodes:**

```bash
# Popular nodes to try
cg node add comfyui-impact-pack
cg node add comfyui-controlnet-aux
```

## Step 6: Commit your changes

Save your environment's current state:

```bash
cg commit -m "Added depthflow nodes"
```

This creates a git commit in the `.cec/` directory tracking:

- Custom nodes and their versions
- Python dependencies
- Model references
- Workflow files

**Check your commit history:**

```bash
cg commit log
```

**Output:**

```
Version history for environment 'my-project':

v1: Added depthflow nodes

Use 'cg rollback <version>' to restore to a specific version
```

!!! tip "Verbose mode"
    ```bash
    cg commit log --verbose
    ```

    Shows timestamps and full commit hashes.

## Step 7: Experiment safely

Let's add another node and see how rollback works:

```bash
# Add a test node
cg node add comfyui-video-helper-suite

# Check status
cg status
```

Now roll back to remove that change:

```bash
cg rollback v1
```

Your environment reverts to the state from your first commit—`comfyui-video-helper-suite` is removed automatically.

!!! tip "Discard uncommitted changes"
    ```bash
    # Discard all changes since last commit
    cg rollback
    ```

## Step 8: Load a workflow

Let's resolve dependencies for a workflow. Download a sample workflow JSON file, then:

```bash
# Move workflow to ComfyUI/user/default/workflows/
cp /path/to/workflow.json ~/comfygit/environments/my-project/ComfyUI/user/default/workflows/

# Resolve dependencies
cg workflow resolve workflow.json
```

ComfyGit will:

1. Analyze the workflow JSON
2. Identify required nodes
3. Prompt you to install missing nodes
4. Find required models
5. Suggest download sources

!!! info "Auto-install mode"
    ```bash
    cg workflow resolve workflow.json --install
    ```

    Automatically installs all missing nodes without prompting.

## Common workflows

Now that you have the basics, here are some common tasks:

### Switch between environments

```bash
# Create another environment
cg create testing --use

# List all environments
cg list

# Switch back to my-project
cg use my-project
```

### Update a custom node

```bash
# Update to latest version
cg node update comfyui-depthflow-nodes

# View installed nodes
cg node list
```

### Add Python dependencies

```bash
# Add a package
cg py add requests

# Add from requirements.txt
cg py add -r requirements.txt

# List installed packages
cg py list
```

### Export your environment

Share your environment with others:

```bash
cg export my-workflow-pack.tar.gz
```

This creates a tarball containing:

- Node metadata and versions
- Model download URLs
- Python dependencies
- Workflow files

**Import on another machine:**

```bash
cg import my-workflow-pack.tar.gz --name imported-env
```

## Essential commands

Here are the most important commands for daily use:

| Command | What it does | Example |
|---------|-------------|---------|
| `cg create` | Create new environment | `cg create prod --use` |
| `cg use` | Switch active environment | `cg use testing` |
| `cg list` | List all environments | `cg list` |
| `cg run` | Start ComfyUI | `cg run` |
| `cg status` | Show environment status | `cg status` |
| `cg node add` | Add custom node | `cg node add comfyui-depthflow-nodes` |
| `cg commit` | Save current state | `cg commit -m "message"` |
| `cg rollback` | Revert to previous state | `cg rollback v1` |
| `cg export` | Export environment | `cg export my-pack.tar.gz` |
| `cg import` | Import environment | `cg import my-pack.tar.gz` |

See the [CLI reference](../cli-reference/environment-commands.md) for a complete list of commands.

## Pro tips for beginners

!!! tip "Use tab completion"
    Install shell completion for faster typing:
    ```bash
    cg completion install
    ```

    Then use Tab to autocomplete environment names, node names, and commands.

!!! tip "Check logs when things fail"
    ```bash
    cg logs -n 50
    ```

    Shows the last 50 log lines for debugging.

!!! tip "Start with a clean environment"
    Don't add too many nodes at once. Start minimal, add what you need, commit often.

!!! tip "Use descriptive commit messages"
    ```bash
    cg commit -m "Added IPAdapter for style transfer"
    ```

    Makes it easy to find specific versions later.

!!! tip "Specify PyTorch backend manually"
    ```bash
    # For NVIDIA GPUs
    cg create gpu-env --torch-backend cu128

    # For AMD GPUs
    cg create amd-env --torch-backend rocm6.3

    # For CPU only
    cg create cpu-env --torch-backend cpu
    ```

## What's next?

Now that you've learned the basics, explore more advanced features:

<div class="grid cards" markdown>

-   :material-book-open-variant: **[Core Concepts](concepts.md)**

    ---

    Understand workspaces, environments, and how ComfyGit works

-   :material-cube-outline: **[Managing Custom Nodes](../user-guide/custom-nodes/adding-nodes.md)**

    ---

    Learn about registry IDs, GitHub URLs, and local development

-   :material-file-image: **[Model Management](../user-guide/models/model-index.md)**

    ---

    How the global model index works and CivitAI integration

-   :material-export: **[Collaboration](../user-guide/collaboration/export-import.md)**

    ---

    Share environments via tarballs or Git remotes

</div>

## Getting help

* **In your terminal**: Run `cg --help` or `cg <command> --help`
* **Documentation**: You're here! Browse other guides
* **Issues**: Report bugs on [GitHub Issues](https://github.com/comfyhub-org/comfygit/issues)
* **Discussions**: Ask questions on [GitHub Discussions](https://github.com/comfyhub-org/comfygit/discussions)
