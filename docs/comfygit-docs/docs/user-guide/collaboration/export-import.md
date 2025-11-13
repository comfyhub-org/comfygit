# Export and Import

Share complete ComfyUI environments as portable tarballs that include configuration, workflows, and development nodes.

## Overview

Export/import allows you to package an entire environment into a single `.tar.gz` file that can be shared offline. This is ideal for:

- **One-time sharing**: Send environments to colleagues or clients
- **Backup and archival**: Save environment snapshots for later restoration
- **CI/CD artifacts**: Deploy tested environments to production
- **Template distribution**: Share starter environments with the community

Unlike git remotes (which require continuous sync), export creates a self-contained package that works offline.

---

## Exporting an Environment

Export packages your environment configuration, workflows, and development nodes into a tarball.

### Basic Export

Export the active environment:

```bash
cg export
```

**Output:**

```
📦 Exporting environment: my-env

✅ Export complete: my-env_export_20250109.tar.gz (2.3 MB)

Share this file to distribute your complete environment!
```

By default, the tarball is created in the current directory with a timestamp.

### Custom Output Path

Specify where to save the export:

```bash
cg export ~/exports/my-workflow.tar.gz
```

### Export Specific Environment

Use the `-e` flag to export a non-active environment:

```bash
cg -e production export production.tar.gz
```

---

## What Gets Exported

The tarball contains everything needed to recreate your environment:

```
environment_export.tar.gz
├── pyproject.toml          # Environment configuration
│                           # - ComfyUI version
│                           # - Custom nodes list
│                           # - Model metadata
│                           # - Workflow dependencies
├── uv.lock                 # Locked Python dependencies
├── .python-version         # Python version constraint
├── workflows/              # All committed workflows
│   ├── workflow1.json
│   └── workflow2.json
└── dev_nodes/              # Development node source code
    └── my-custom-node/     # (Only nodes with source="development")
```

!!! note "Only Committed Content"
    Export only includes committed workflows and configuration. Uncommitted changes are excluded to ensure consistency.

---

## Export Validation

ComfyGit validates your export to ensure recipients can recreate the environment successfully.

### Model Source Check

Before exporting, ComfyGit checks if all models have download sources:

```bash
cg export
```

**Output (showing first 3 models):**

```
📦 Exporting environment: my-env

⚠️  Export validation:

5 model(s) have no source URLs.

  • sd_xl_base_1.0.safetensors
    Used by: txt2img, img2img

  • control_v11p_sd15_openpose.pth
    Used by: pose_workflow

  • vae-ft-mse-840000.safetensors
    Used by: txt2img

  ... and 2 more

⚠️  Recipients won't be able to download these models automatically.
   Add sources: cg model add-source

Continue export? (y/N) or (s)how all models:
```

**Progressive Disclosure:**

If more than 3 models are missing sources, ComfyGit shows only the first 3 initially. Type `s` to expand and view all models before making a decision.

**After typing 's':**

```
  • sd_xl_base_1.0.safetensors
    Used by: txt2img, img2img

  • control_v11p_sd15_openpose.pth
    Used by: pose_workflow

  • vae-ft-mse-840000.safetensors
    Used by: txt2img

  • lora_style.safetensors
    Used by: portrait_workflow

  • upscaler_4x.pth
    Used by: img2img

⚠️  Recipients won't be able to download these models automatically.
   Add sources: cg model add-source

Continue export? (y/N):
```

**Options:**

- **Add sources first** (recommended): Use `cg model add-source` to add download URLs
- **Continue anyway** (type `y`): Export proceeds, recipients will need to manually provide the models
- **Show all models** (type `s`): Expand the list to see all models without sources (only available if more than 3)
- **Cancel** (type `N` or anything else): Abort export and fix issues first
- **Skip validation**: Use `--allow-issues` flag to bypass the check entirely

!!! tip "Understanding the Prompt"
    - If you have 3 or fewer models without sources, you'll only see `(y/N)`
    - If you have more than 3, you'll see `(y/N) or (s)how all models` to expand the list first

### Adding Model Sources

Add download URLs so recipients can auto-download models:

```bash
# Interactive mode - walks through all models without sources
cg model add-source

# Direct mode - add source to specific model
cg model add-source sd_xl_base <civitai-url>
```

!!! tip "Interactive Mode"
    Interactive mode is the fastest way to add sources for multiple models. It shows each model and prompts for a URL.

See [Adding Model Sources](../models/adding-sources.md) for details.

### Uncommitted Changes Check

Export fails if you have uncommitted workflows or git changes:

```
✗ Cannot export: uncommitted changes detected

📋 Uncommitted workflows:
  • new_workflow
  • modified_workflow

💡 Commit first:
   cg commit -m 'Pre-export checkpoint'
```

This ensures the export matches a specific version in your history.

**Fix:**

```bash
cg commit -m "Prepare for export"
cg export
```

---

## Importing an Environment

Import creates a new environment from a tarball or git repository.

### Import from Tarball

Import a local tarball file:

```bash
cg import environment.tar.gz
```

**Interactive prompts:**

```
📦 Importing environment from environment.tar.gz

Environment name: my-imported-env

Model download strategy:
  1. all      - Download all models with sources
  2. required - Download only required models
  3. skip     - Skip all downloads (can resolve later)
Choice (1-3) [1]: 1

🔧 Initializing environment...
   Cloning ComfyUI v0.2.7
   Configuring PyTorch backend: cu128
   Installing Python dependencies
   Initializing git repository...

📝 Setting up workflows...
   Copied: txt2img

📦 Syncing custom nodes...
   Installed: rgthree-comfy

🔄 Resolving workflows (all strategy)...

⬇️  Downloading 3 model(s)...

[1/3] sd_xl_base_1.0.safetensors
Downloading... 6533.8 MB / 6633.5 MB (98%)
  ✓ Complete

[2/3] control_v11p_sd15_openpose.pth
Downloading... 729.4 MB / 729.4 MB (100%)
  ✓ Complete

✅ Downloaded 2 model(s)

✅ Import complete: my-imported-env
   Environment ready to use!

Activate with: cg use my-imported-env
```

### Import from Git Repository

Import directly from a git URL:

```bash
cg import https://github.com/user/comfy-workflow
```

This clones the repository to the environment's `.cec` directory, preserving the git history and remote connection for future updates.

**Specify branch or tag:**

```bash
cg import https://github.com/user/comfy-workflow --branch v1.0
```

**Git Import vs Tarball Import:**

- **Git imports** preserve the `.git` directory with remote tracking - you can push/pull changes later
- **Tarball imports** create a fresh git repository with no remote - ideal for one-time distributions

!!! note "Remote Preservation"
    When importing from git, the original remote is preserved. You can push updates back to the source repository or pull new changes. See [Git Remotes](git-remotes.md) for collaboration workflows.

### Non-Interactive Import

Skip prompts by providing all options via flags:

```bash
cg import environment.tar.gz \
    --name production \
    --torch-backend cu128 \
    --use
```

**Flags:**

- `--name NAME`: Environment name (skip prompt)
- `--torch-backend BACKEND`: PyTorch backend (auto, cpu, cu128, cu126, rocm6.3, xpu)
- `--use`: Set as active environment immediately after import (changes output message)

**With `--use` flag:**

```bash
cg import environment.tar.gz --name production --use
```

**Completion message changes to:**

```
✅ Import complete: production
   Environment ready to use!
   'production' set as active environment
```

No need to run `cg use production` separately - you can start using it immediately.

---

## Import Internals & Performance

Understanding what happens during import helps you optimize the process and troubleshoot issues.

### ComfyUI Caching

ComfyGit caches ComfyUI installations to speed up imports and environment creation.

**First import of a ComfyUI version:**

```
🔧 Initializing environment...
   Cloning ComfyUI v0.2.7
```

ComfyGit clones from GitHub and caches the result by commit SHA.

**Subsequent imports with the same version:**

```
🔧 Initializing environment...
   Restoring ComfyUI v0.2.7 from cache...
```

This is **significantly faster** - a simple directory copy instead of a git clone.

**Cache behavior:**

- Cache location: `~/comfygit/cache/comfyui/`
- Keyed by: ComfyUI version (release tag, branch, or commit SHA)
- Shared across: All environments in the workspace
- Automatic: No configuration needed

!!! tip "Performance Boost"
    The first import of ComfyUI v0.2.7 might take 30-60 seconds to clone. Subsequent imports using the same version complete in 2-5 seconds.

### PyTorch Backend Management

When importing with the `--torch-backend` flag, ComfyGit intelligently manages PyTorch:

**Automatic stripping (prevents conflicts):**

1. Removes imported PyTorch index URLs from `pyproject.toml`
2. Strips PyTorch package source configurations
3. Clears PyTorch version constraints

**Then installs fresh:**

1. Creates Python virtual environment
2. Installs PyTorch packages with specified backend (cu128, cpu, rocm, etc.)
3. Detects installed backend from package version
4. Updates `pyproject.toml` with correct backend configuration
5. Locks versions to prevent drift

**Why this matters:**

If you export an environment on a CUDA 12.8 system and import on a Mac (CPU only), the imported PyTorch config would fail. ComfyGit strips the old config and installs the right backend for your system.

### Automatic Git Commits

All import changes are automatically committed to git:

- Workflow files copied to `ComfyUI/user/default/workflows/`
- Custom nodes installed and synced
- Models downloaded and resolved
- PyTorch backend configured in `pyproject.toml`

**Final commit message:** `"Imported environment"`

This ensures the imported environment starts with a clean, committed state ready for development.

---

## Model Download Strategies

During import, you choose how to handle model downloads:

### Strategy: All (Default)

Downloads all models that have source URLs:

```
Choice (1-3) [1]: 1
```

- **Downloads**: All models with sources
- **Skips**: Models without sources (creates download intents)
- **Best for**: Complete environment setup

### Strategy: Required

Downloads only models marked as "required":

```
Choice (1-3) [1]: 2
```

- **Downloads**: Required models only
- **Skips**: Flexible and optional models
- **Best for**: Quick setup, storage constraints

Model criticality is set using `cg workflow model importance`.

### Strategy: Skip

Skips all downloads during import:

```
Choice (1-3) [1]: 3
```

- **Downloads**: None
- **Creates**: Download intents for all models
- **Best for**: Offline imports, manual model management

You can resolve downloads later:

```bash
cg -e my-env workflow resolve --all
```

---

## Import Analysis Preview

Before importing, ComfyGit analyzes what will be installed.

### Import Breakdown

The import process shows what will be set up in real-time:

```
🔧 Initializing environment...
   Cloning ComfyUI v0.2.7
   Configuring PyTorch backend: cu128
   Installing Python dependencies
   Initializing git repository...
```

During dependency installation, you'll see each group being installed with inline progress:

```
      Installing main... ✓
      Installing torch-cu128... ✓
      Installing comfyui... ✓
      Installing optional (optional)... ✗
```

!!! note "Terminal Output Format"
    The check mark (✓) or X (✗) appears **on the same line** as "Installing..." after the installation completes. The `(optional)` marker indicates non-critical dependency groups.

**If optional groups fail:**

```
⚠️  Some optional dependency groups failed to install:
   ✗ optional

Some functionality may be degraded or some nodes may not work properly.
The environment will still function with reduced capabilities.
```

**If all groups succeed:**

```
✅ Import complete: my-imported-env
   Environment ready to use!
```

### Dependency Group Failures

Optional dependency groups may fail without breaking the import:

- **Main groups** (main, torch-*, comfyui): Must succeed or import fails
- **Optional groups**: Allowed to fail, shows warning but import continues

**Common reasons for failures:**

- Platform-specific packages not available (e.g., Windows-only package on Linux)
- Network issues downloading packages
- Version conflicts in optional dependencies
- Missing system libraries (e.g., CUDA libraries for GPU packages)

The environment remains usable with reduced functionality when optional groups fail.

---

## Development Nodes

Export includes source code for development nodes (nodes with `source = "development"`).

### What Gets Included

Development node source code is bundled in the tarball:

```
dev_nodes/
└── my-custom-node/
    ├── __init__.py
    ├── nodes.py
    └── requirements.txt
```

**Filtering:**

- Excludes `__pycache__/` directories
- Excludes `.pyc` files
- Includes all other source files

### Import Behavior

During import, development nodes are:

1. Extracted to `.cec/dev_nodes/`
2. Symlinked to `ComfyUI/custom_nodes/`
3. Dependencies installed from `requirements.txt`

This allows sharing custom nodes under development without publishing to a registry.

---

## Advanced Import Behaviors

ComfyGit performs several automatic operations during import to ensure environment consistency and cross-platform compatibility.

### Automatic Configuration Adjustments

**PyTorch Configuration Stripping:**

When you specify `--torch-backend`, ComfyGit automatically:

1. **Removes all imported PyTorch configuration** from the tarball/git repository:
   - PyTorch index URLs (e.g., `https://download.pytorch.org/whl/cu128`)
   - Package source specifications for torch, torchvision, torchaudio
   - Version constraints that might conflict with target platform

2. **Installs fresh PyTorch** for your target platform:
   - Uses the backend you specify (cu128, cpu, rocm, etc.)
   - Detects actual installed versions
   - Locks those versions in `pyproject.toml`
   - Configures correct index URLs and sources

**Why this happens:**

If you export on a Linux machine with CUDA 12.8 and import on a Mac, the CUDA-specific PyTorch won't work. ComfyGit strips the old config and installs the correct backend automatically.

### Git Repository Initialization

**For tarball imports:**

- Creates fresh `.git` repository in `.cec/`
- No remote configured (one-time distribution)
- Initial commit message: `"Imported environment"`

**For git imports:**

- Preserves existing `.git` directory with full history
- Keeps remote tracking (you can push/pull)
- Ensures `.gitignore` is properly configured
- Adds commit: `"Imported environment"` with all setup changes

### Automatic Commits

All import operations are committed automatically:

```
Imported environment

- Copied workflow files to ComfyUI/user/default/workflows/
- Installed X custom nodes
- Downloaded Y models
- Configured PyTorch backend: cu128
```

This ensures:

- Clean starting state
- All changes tracked from the beginning
- Easy rollback if needed
- Clear history of what was imported

### Workflow File Handling

During import, workflow JSON files are:

1. **Extracted** from tarball to `.cec/workflows/`
2. **Copied** to ComfyUI runtime at `ComfyUI/user/default/workflows/`
3. **Tracked** in git automatically

Both locations are kept in sync - the `.cec/workflows/` directory is the source of truth, and ComfyUI's workflows directory is kept updated.

### Model Download Intent Preservation

If models can't be downloaded during import (missing sources, network issues, strategy is "skip"):

- ComfyGit creates **download intents** in `pyproject.toml`
- These track which models are needed but not yet available
- You can resolve them later with `cg workflow resolve`
- Model metadata (filename, hash, relative path, sources) is preserved

**Example download intent:**

```toml
[[tool.comfygit.workflows.txt2img.models]]
filename = "sd_xl_base_1.0.safetensors"
hash = "abc123..."
relative_path = "checkpoints/sd_xl_base_1.0.safetensors"
status = "unresolved"
sources = [
    { type = "civitai", url = "https://civitai.com/..." }
]
```

### Development Node Extraction

Development nodes (nodes with `source = "development"`) are:

1. **Extracted** to `.cec/dev_nodes/<node-name>/`
2. **Symlinked** to `ComfyUI/custom_nodes/<node-name>`
3. **Dependencies installed** from their `requirements.txt` if present
4. **Treated as local code** (not managed via git/registry)

This allows distributing custom nodes under active development without publishing them to the ComfyUI registry.

---

## Troubleshooting

### Models Without Sources

**Problem:** Export warns about models without download URLs.

```
⚠️  3 model(s) have no source URLs.
```

**Solutions:**

1. **Add sources** (recommended):
   ```bash
   cg model add-source
   ```

2. **Export anyway**:
   ```bash
   cg export --allow-issues
   ```

   Recipients will need to manually provide the models.

3. **Document manual steps**: Include instructions for recipients to download models manually.

---

### CivitAI Authentication Errors

**Problem:** Import fails with `401 Unauthorized` for CivitAI downloads.

```
✗ Failed: 401 Unauthorized
```

**Solution:** Add your CivitAI API key:

```bash
cg config --civitai-key <your-api-key>
```

Get your key from: [https://civitai.com/user/account](https://civitai.com/user/account)

Then retry the import or resolve manually:

```bash
cg -e my-env workflow resolve --all
```

---

### Download Failures

**Problem:** Some models fail to download during import.

```
⚠️  2 model(s) failed:
   • sd_xl_base_1.0.safetensors: Connection timeout
   • controlnet.pth: 404 Not Found
```

**What Happens:**

- Failed downloads are saved as "download intents"
- Environment import continues
- Workflows may be incomplete

**Solutions:**

1. **Retry download**:
   ```bash
   cg -e my-env workflow resolve <workflow-name>
   ```

2. **Check model sources**:
   ```bash
   cg -e my-env model index show sd_xl_base
   ```

3. **Manual download**: Download the model manually and place it in the models directory, then sync:
   ```bash
   cg model index sync
   ```

---

### Import Fails Mid-Process

**Problem:** Import fails during environment setup.

**What Happens:**

- Partial environment is created
- May have incomplete dependencies or nodes

**Solution:**

1. **Delete the failed environment**:
   ```bash
   cg delete <env-name>
   ```

2. **Check error message** for specific cause (network, disk space, etc.)

3. **Retry import** after fixing the issue:
   ```bash
   cg import environment.tar.gz
   ```

---

## Best Practices

### Before Exporting

1. **Commit all changes**: Ensure workflows are committed
   ```bash
   cg commit -m "Finalize environment for export"
   ```

2. **Add model sources**: Use interactive mode to add all sources
   ```bash
   cg model add-source
   ```

3. **Test the export**: Import it locally to verify completeness
   ```bash
   cg export test.tar.gz
   cg import test.tar.gz --name test-import
   ```

4. **Document custom setup**: If models can't be auto-downloaded, provide manual instructions

### For Recipients

1. **Review import analysis**: Check what will be installed during import preview

2. **Choose appropriate strategy**: Select model download strategy based on needs
   - **Full setup**: Use "all"
   - **Quick start**: Use "required"
   - **Offline/manual**: Use "skip"

3. **Verify hardware compatibility**: Check PyTorch backend matches your GPU
   ```bash
   cg import env.tar.gz --torch-backend cu128
   ```

4. **Check disk space**: Imports can be large (models + dependencies)

### Naming Conventions

- **Descriptive names**: `project-v1.0-export.tar.gz`
- **Version tags**: Include version or date for clarity
- **Environment type**: Indicate purpose (dev, prod, test)

---

## Next Steps

- [Git Remotes](git-remotes.md) - Continuous collaboration with push/pull
- [Team Workflows](team-workflows.md) - Best practices for team collaboration
- [Adding Model Sources](../models/adding-sources.md) - Ensure models are downloadable
- [Workflow Resolution](../workflows/workflow-resolution.md) - Resolve missing dependencies

---

## Summary

Export/import enables offline environment sharing with intelligent automation:

**Export Features:**

- **Validation** ensures recipients can recreate environments (uncommitted changes, model sources)
- **Progressive disclosure** for models without sources - view first 3, expand to see all
- **Tarball packaging** includes pyproject.toml, workflows, development nodes, and dependency locks
- **Committed content only** - ensures consistency and reproducibility

**Import Features:**

- **Dual source support** - import from tarballs or git URLs
- **ComfyUI caching** speeds up subsequent imports (30-60s → 2-5s for same version)
- **Model strategies** control download behavior (all/required/skip)
- **PyTorch backend management** strips imported config and installs correct backend for target platform
- **Development nodes** extracted and symlinked automatically
- **Download intent preservation** tracks models that couldn't be downloaded for later resolution

**Automatic Behaviors:**

- Git repository initialization (fresh for tarballs, preserved for git imports)
- Automatic commit of all import changes
- PyTorch configuration stripping to prevent platform conflicts
- Workflow file copying to ComfyUI runtime directory
- Dependency group installation with optional failure handling

**Use Cases:**

- **One-time sharing**: Send environments to colleagues or clients (use tarballs)
- **Team collaboration**: Share via git with preserved remotes for push/pull workflows
- **Backup and archival**: Save environment snapshots for later restoration
- **CI/CD artifacts**: Deploy tested environments to production
- **Template distribution**: Share starter environments with the community
- **Cross-platform deployment**: Export on Linux/CUDA, import on Mac/CPU with automatic PyTorch adjustment

For continuous team collaboration with ongoing sync, see [Git Remotes](git-remotes.md).
