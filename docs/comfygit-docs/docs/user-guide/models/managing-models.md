# Managing Models

> Search, organize, and maintain your model collection across all environments.

## Overview

ComfyGit provides powerful tools for managing models:

- **Search** - Find models instantly by name or hash
- **Browse** - Paginated views of your entire collection
- **Inspect** - Detailed information about any model
- **Sync** - Keep index up-to-date with filesystem changes
- **Organize** - Understand categories and structure
- **Share** - Global model directory used by all environments

## Viewing your model collection

### List all models

See everything in your collection:

```bash
cg model index list
```

**Example output:**

```
📦 All indexed models (145 unique, 150 files):

   sd_xl_base_1.0.safetensors
   Size: 6.46 GB
   Hash: a1b2c3d4e5f6...
   Path: checkpoints/sd_xl_base_1.0.safetensors

   anime_v2.safetensors
   Size: 4.27 GB
   Hash: f6e5d4c3b2a1...
   Path: checkpoints/anime_v2.safetensors

   realistic_vision.safetensors
   Size: 5.13 GB
   Hash: 9876543210ab...
   Path: checkpoints/realistic_vision.safetensors

   perfectEyes_lora.safetensors
   Size: 144 MB
   Hash: abcdef123456...
   Path: loras/perfectEyes_lora.safetensors

   detail_tweaker.safetensors
   Size: 144 MB
   Hash: 123456abcdef...
   Path: loras/detail_tweaker.safetensors

[Page 1 of 29] [n]ext [p]rev [q]uit
```

**Navigation:**

- Press `n` or Enter - Next page
- Press `p` - Previous page
- Press `q` - Quit

The list shows 5 models per page for easy browsing.

### Browse by category

Models are automatically organized by category based on their directory:

```bash
# List all models, filtered by category
cg model index list | grep "Path: checkpoints/"
cg model index list | grep "Path: loras/"
cg model index list | grep "Path: vae/"
```

!!! tip "Category structure"
    ComfyGit automatically detects 20+ model categories from directory structure. See [Model Index](model-index.md#model-categories) for the complete list.

## Searching for models

### Search by filename

Find models with matching filenames:

```bash
cg model index find "anime"
```

**Example output:**

```
🔍 Found 2 unique model(s) (3 locations) matching 'anime':

   anime_v2.safetensors
   Size: 4.27 GB
   Hash: f6e5d4c3b2a1e9876543210abcdef123456789
   Locations (2):
     • /home/user/comfygit/workspace/models/checkpoints/anime_v2.safetensors
     • /home/user/backup/checkpoints/anime_v2.safetensors

   anime_style_lora.safetensors
   Size: 144 MB
   Hash: 9876543210abcdef123456789abcdef123456789
   Location: /home/user/comfygit/workspace/models/loras/anime_style_lora.safetensors
```

**Search is case-insensitive and matches anywhere in filename:**

```bash
cg model index find "realistic"    # Matches realistic_vision.safetensors
cg model index find "REALISTIC"    # Same result
cg model index find "vision"       # Also matches realistic_vision.safetensors
```

### Search by hash

Find models by hash prefix:

```bash
cg model index find a1b2c3
```

**Example output:**

```
🔍 Found 1 model(s) matching 'a1b2c3':

   sd_xl_base_1.0.safetensors
   Size: 6.46 GB
   Hash: a1b2c3d4e5f67890abcdef1234567890abcdef12
   Location: /home/user/comfygit/workspace/models/checkpoints/sd_xl_base_1.0.safetensors
```

Hash searches match from the beginning:

```bash
cg model index find a1b2      # Matches a1b2c3d4...
cg model index find a1b2c3d4  # More specific
```

### Understanding search results

**Unique models vs locations:**

```
🔍 Found 2 unique model(s) (3 locations) matching 'anime':
```

- **2 unique models** - Two different files (different hashes)
- **3 locations** - Total files on disk (one model exists in 2 places)

**Multiple locations for same model:**

```
   anime_v2.safetensors
   Size: 4.27 GB
   Hash: f6e5d4c3b2a1e9876543210abcdef123456789
   Locations (2):
     • /home/user/comfygit/workspace/models/checkpoints/anime_v2.safetensors
     • /home/user/backup/checkpoints/anime_v2.safetensors
```

Both locations contain the exact same file (same hash).

## Detailed model information

Get complete details about any model:

```bash
cg model index show sd_xl_base_1.0.safetensors
```

**Example output:**

```
📦 Model Details: sd_xl_base_1.0.safetensors

  Hash:           a1b2c3d4e5f67890abcdef1234567890abcdef12
  Blake3:         a1b2c3d4e5f67890abcdef1234567890abcdef12
  SHA256:         Not computed
  Size:           6.46 GB
  Category:       checkpoints
  Last Seen:      2025-01-15 14:32:18

  Locations (2):
    • /home/user/comfygit/workspace/models/checkpoints/sd_xl_base_1.0.safetensors
      Modified: 2025-01-10 09:15:43
    • /mnt/backup/models/checkpoints/sd_xl_base_1.0.safetensors
      Modified: 2025-01-10 09:20:12

  Sources (2):
    • HuggingFace
      URL: https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors
      Added: 2025-01-10 09:15:00
    • CivitAI
      URL: https://civitai.com/api/download/models/128078
      Added: 2025-01-12 16:42:31
```

### Understanding model details

**Hashes:**

- **Hash** - Short hash (42 chars) for display
- **Blake3** - Hash from file sampling (~200ms computation)
- **SHA256** - Full file hash (only computed if collision detected)

**Size:**

Human-readable file size (GB, MB, KB).

**Category:**

Auto-detected from directory path. See [Model Index](model-index.md#model-categories) for category list.

**Last Seen:**

Timestamp when model was last scanned. If a file is moved or deleted, this shows when it was last known to exist.

**Locations:**

All places this exact file exists (by hash). Each location shows:

- Full absolute path
- Last modified timestamp

**Sources:**

Registered download URLs. Each source shows:

- Source type (CivitAI, HuggingFace, custom)
- Full download URL
- When source was added

## Keeping the index synced

### When to sync

Run `cg model index sync` when you:

- Download models outside ComfyGit (browser downloads)
- Copy models from other machines
- Manually delete or move model files
- Import models from another ComfyUI installation
- Notice models missing from workflows

### Running a sync

Update the index to match your filesystem:

```bash
cg model index sync
```

**Example output:**

```
📁 Syncing models directory: /home/user/comfygit/workspace/models

Scanning directory...
  Scanned 152 files in 28.4s
  Found 3 new models
  Removed 1 deleted model
  147 models unchanged

✓ Sync complete
  Total models: 148 unique, 152 files
  Total size: 124.7 GB
```

**What gets updated:**

- **New models** - Files added since last sync
- **Deleted models** - Removed from index if files no longer exist
- **Unchanged models** - Verified still present

### Sync performance

Sync time depends on:

- Number of files (~200ms per new file)
- Disk speed (SSD vs HDD)
- File sizes (larger = slower sampling)

**Typical times:**

- 50 models - ~10 seconds
- 150 models - ~30 seconds
- 500 models - ~2 minutes

!!! tip "Unchanged files are fast"
    ComfyGit uses modification time (mtime) caching. Files that haven't changed since last sync are skipped, making repeated syncs very fast.

## Understanding global vs environment models

### Global models directory

ComfyGit uses a **single global models directory** shared by all environments:

```
~/comfygit/workspace/models/
  ├── checkpoints/
  ├── loras/
  ├── vae/
  └── ...
```

**Benefits:**

- **Disk savings** - One copy shared across all environments
- **Consistency** - All environments see same models
- **Easy management** - One place to organize models

### Environment symlinks

Each environment's `ComfyUI/models/` directory is a **symlink** to the global directory:

```bash
# Environment directory structure
~/comfygit/environments/my-env/ComfyUI/
  ├── main.py
  ├── models/  → ~/comfygit/workspace/models/  (symlink)
  └── custom_nodes/
```

ComfyUI follows the symlink and sees all models as if they were local.

### Verifying symlinks

Check if symlinks are correct:

```bash
# List environment directory
ls -la ~/comfygit/environments/my-env/ComfyUI/

# You should see:
# lrwxrwxrwx models -> /home/user/comfygit/workspace/models
```

If the symlink is broken or missing, repair it:

```bash
cg -e my-env repair
```

## Organizing your models

### Recommended directory structure

Organize models by category and purpose:

```
models/
  ├── checkpoints/
  │   ├── realistic/
  │   │   ├── realistic_vision_v5.safetensors
  │   │   └── deliberate_v2.safetensors
  │   ├── anime/
  │   │   ├── anime_v2.safetensors
  │   │   └── anything_v5.safetensors
  │   └── sdxl/
  │       └── sd_xl_base_1.0.safetensors
  ├── loras/
  │   ├── characters/
  │   ├── styles/
  │   └── effects/
  ├── vae/
  └── controlnet/
```

ComfyGit will automatically index all subdirectories within each category.

### Moving models between categories

If you put a model in the wrong category:

```bash
# Move the file
mv ~/comfygit/workspace/models/checkpoints/lora.safetensors \
   ~/comfygit/workspace/models/loras/lora.safetensors

# Update the index
cg model index sync
```

The model's category will update automatically.

### Cleaning up duplicates

Find and remove duplicate models to save space:

```bash
# List all duplicates
cg model index list --duplicates
```

**Example output:**

```
📦 Duplicate models (12 models, 28 files):

   sd_xl_base_1.0.safetensors
   Size: 6.46 GB
   Hash: a1b2c3d4e5f6...
   Locations (3):
     • /home/user/comfygit/workspace/models/checkpoints/sd_xl_base_1.0.safetensors
     • /home/user/backup/models/checkpoints/sd_xl_base_1.0.safetensors
     • /mnt/external/old_comfyui/models/checkpoints/sd_xl_base_1.0.safetensors
```

**Get details about a specific duplicate:**

```bash
cg model index show sd_xl_base_1.0.safetensors
```

**Remove unnecessary copies:**

```bash
# Keep the one in workspace, delete backups
rm /home/user/backup/models/checkpoints/sd_xl_base_1.0.safetensors
rm /mnt/external/old_comfyui/models/checkpoints/sd_xl_base_1.0.safetensors

# Update index
cg model index sync
```

## Removing models

### Organic removal via workflows

ComfyGit **does not have a direct delete command**. Models are removed organically:

1. **Remove from workflows** - Delete the model-loading node in ComfyUI
2. **Resolve or commit** - Run `cg workflow resolve` or `cg commit`
3. **Automatic cleanup** - Model reference removed from pyproject.toml
4. **File remains** - Physical file stays in models directory

**Why this design?**

Prevents accidental deletion of expensive-to-redownload models. Files are only tracked when actively used.

### Manual file deletion

To actually delete model files:

```bash
# Delete the file manually
rm ~/comfygit/workspace/models/checkpoints/unused_model.safetensors

# Update the index
cg model index sync
```

The model will be removed from the index.

!!! warning "Deleting files"
    Make absolutely sure you don't need the model before deleting. Re-downloading large models (5+ GB) takes time and bandwidth.

### Identifying unused models

Find models not referenced by any workflow:

```bash
# Check each environment
cg -e my-env status

# Look for models with no workflow references
cg model index show model_name.safetensors
```

If a model has sources registered, you can safely delete it (can re-download later).

## Model statistics and health

### Index status

Check overall index health:

```bash
cg model index status
```

**Example output:**

```
📊 Model Index Status:

   Models Directory: ✓ /home/user/comfygit/workspace/models
   Total Models: 148 unique models
   Total Files: 152 files indexed
   Duplicates: 4 duplicate files detected
```

**Interpreting the output:**

- **Models Directory** - ✓ means directory exists and is accessible
- **Total Models** - Number of unique files (by hash)
- **Total Files** - Total file count (includes duplicates)
- **Duplicates** - Files that exist in multiple locations

### Finding duplicates

If `Total Files > Total Models`, you have duplicates:

```
   Total Models: 148 unique models
   Total Files: 152 files indexed
   Duplicates: 4 duplicate files detected
```

**Find which models are duplicated:**

```bash
# Show only duplicate models
cg model index list --duplicates
```

This will display only models that exist in multiple locations, making it easy to identify duplicates for cleanup.

## Common workflows

### Importing models from another ComfyUI

Copy models from existing ComfyUI installation:

```bash
# Option 1: Point to existing directory
cg model index dir ~/old_comfyui/models

# Option 2: Copy then scan
cp -r ~/old_comfyui/models/* ~/comfygit/workspace/models/
cg model index sync
```

### Sharing models between workspaces

If you have multiple workspaces:

```bash
# Workspace 1 uses global location
cd ~/comfygit/workspace1
cg model index dir /mnt/shared/comfyui_models

# Workspace 2 uses same location
cd ~/comfygit/workspace2
cg model index dir /mnt/shared/comfyui_models
```

Both workspaces share the same model collection.

### Backing up your models

Create backups of your model collection:

```bash
# Full backup
rsync -av ~/comfygit/workspace/models/ /mnt/backup/models/

# Backup only checkpoints
rsync -av ~/comfygit/workspace/models/checkpoints/ /mnt/backup/checkpoints/
```

After backup, sync to register backup locations:

```bash
cg model index sync
```

### Verifying workflow requirements

Check if a workflow's models are available:

```bash
# Resolve workflow
cg -e my-env workflow resolve my_workflow

# Look for "unresolved" models
# Then search for them
cg model index find missing_model
```

If found: workflow will work
If not found: download the model

## Troubleshooting

### Models not appearing in ComfyUI

**Problem:** Downloaded a model but ComfyUI doesn't show it

**Solutions:**

```bash
# 1. Verify model is indexed
cg model index find model_name

# 2. Check symlink is correct
ls -la ~/comfygit/environments/my-env/ComfyUI/models

# 3. Repair environment if symlink broken
cg -e my-env repair

# 4. Restart ComfyUI
cg -e my-env run
```

### "No models directory configured"

**Problem:** Commands fail with this error

**Solution:**

```bash
# Set models directory first
cg model index dir ~/comfygit/workspace/models

# Then retry command
cg model index list
```

### Duplicate models consuming space

**Problem:** Same model exists in multiple places

**Solution:**

```bash
# Find the duplicate
cg model index show model.safetensors

# Shows all locations - delete unwanted copies
rm /unwanted/location/model.safetensors

# Update index
cg model index sync
```

### Models in wrong category

**Problem:** Model shows wrong category in index

**Solution:**

```bash
# Move file to correct category folder
mv ~/comfygit/workspace/models/checkpoints/lora.safetensors \
   ~/comfygit/workspace/models/loras/lora.safetensors

# Sync to update category
cg model index sync
```

### Sync shows deleted models as present

**Problem:** Deleted files still appear in index

**Solution:**

```bash
# Run sync to clean up
cg model index sync

# Verify removed
cg model index find deleted_model
# Should show: No models found matching...
```

### Cannot find model by filename

**Problem:** Search returns no results for known file

**Solutions:**

```bash
# Check exact filename
ls ~/comfygit/workspace/models/checkpoints/ | grep -i model_name

# Sync if recently added
cg model index sync

# Try hash search if you know partial hash
cg model index find a1b2c3
```

### Symlink points to wrong directory

**Problem:** Environment models/ points to old location

**Solution:**

```bash
# Remove old symlink
rm ~/comfygit/environments/my-env/ComfyUI/models

# Set correct directory (recreates symlinks)
cg model index dir /correct/path/to/models

# Or repair environment
cg -e my-env repair
```

### Index shows very old "Last Seen" date

**Problem:** Model shows old timestamp

**Cause:** File hasn't been scanned recently (possibly in backup location)

**Solution:**

This is normal if:

- Model is in a backup directory
- File hasn't changed in months
- Model was imported from old installation

Not a problem unless file is actually missing.

## Advanced management

### Using external tools

ComfyGit is compatible with external file managers:

```bash
# Use any tool to organize
ranger ~/comfygit/workspace/models/
thunar ~/comfygit/workspace/models/
# etc.

# Sync after changes
cg model index sync
```

### Scripting model operations

Automate model management:

```bash
#!/bin/bash
# Find all LoRAs over 500MB
cg model index list | \
  grep "Path: loras/" | \
  grep "Size: [0-9]\{3,\} MB" | \
  awk '{print $2}'
```

### Monitoring model usage

Track which models workflows actually use:

```bash
# Check all workflows
cg -e my-env workflow list

# Resolve each to see model requirements
cg -e my-env workflow resolve workflow_name
```

Cross-reference with your index to find unused models.

## Next steps

<div class="grid cards" markdown>

-   :material-database: **[Model Index](model-index.md)**

    ---

    Deep dive into how indexing works

-   :material-download: **[Downloading Models](downloading-models.md)**

    ---

    Get models from CivitAI, HuggingFace, and more

-   :material-link-variant: **[Adding Sources](adding-sources.md)**

    ---

    Register download URLs for sharing environments

</div>
