# Model Index

> Learn how ComfyGit indexes your models for fast lookup, deduplication, and cross-environment sharing.

## Overview

ComfyGit maintains a global model index that tracks all models across your workspace:

- **Fast lookup** - Find models by filename or hash in milliseconds
- **Deduplication** - Detect duplicate models across directories
- **Cross-environment sharing** - One model collection shared by all environments
- **Source tracking** - Remember where models came from for re-downloads
- **Automatic categorization** - Organize models by type (checkpoints, loras, etc.)

## How the index works

The model index is a SQLite database that stores:

- **Model identity** - BLAKE3 hash computed from file sampling (~200ms per file)
- **Locations** - Where each model file exists on disk
- **Sources** - Download URLs for re-acquiring models
- **Metadata** - Size, category, last-seen timestamp

**Why sampling instead of full file hashing?**

ComfyGit uses a smart sampling strategy that reads 3 small chunks (start, middle, end) from each file instead of reading the entire file. This provides:

- **200ms indexing** per file vs 30-60 seconds for full hash
- **Collision detection** - Falls back to full hash if duplicates detected
- **Good enough uniqueness** - Sufficient for model deduplication

!!! info "Index location"
    The model index is stored at `~/comfygit/workspace/.metadata/models.db` and is shared across all environments in your workspace.

## Setting your models directory

ComfyGit needs to know where your models are stored. Set this once per workspace:

```bash
cg model index dir ~/ComfyUI/models
```

**What happens:**

1. **Validates directory** - Checks path exists and is a directory
2. **Updates workspace config** - Saves directory path to configuration
3. **Initial scan** - Scans all model files and builds index
4. **Updates symlinks** - All environment `ComfyUI/models/` directories now point here

**Example output:**

```
📁 Setting global models directory: /home/user/ComfyUI/models

Scanning directory...
  Scanned 150 files in 30.2s
  Found 145 models
  5 duplicates detected

✓ Models directory set successfully: /home/user/ComfyUI/models
  Found 145 models (12.3 GB)
  Use 'cg model index sync' to rescan when models change
```

### Using an existing ComfyUI models directory

If you already have models from a ComfyUI installation:

```bash
cg model index dir ~/ComfyUI/models
```

ComfyGit will index all existing models immediately. Your environments can use them right away through symlinks.

### Starting with an empty directory

If you're starting fresh:

```bash
# ComfyGit creates this during init
cg model index dir ~/comfygit/workspace/models
```

Download models later with `cg model download` - they'll be automatically indexed.

## Viewing indexed models

### List all models

See all models in your index:

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

The list is paginated (5 models per page) for easy browsing.

### Search for specific models

Find models by filename or hash:

```bash
# Search by filename
cg model index find "anime"

# Search by hash prefix
cg model index find a1b2c3
```

**Example output:**

```
🔍 Found 2 unique model(s) (3 locations) matching 'anime':

   anime_v2.safetensors
   Size: 4.27 GB
   Hash: f6e5d4c3b2a1e9876543210abcdef123456789
   Locations (2):
     • /home/user/ComfyUI/models/checkpoints/anime_v2.safetensors
     • /home/user/backup/anime_v2.safetensors

   anime_style_lora.safetensors
   Size: 144 MB
   Hash: 9876543210abcdef123456789abcdef123456789
   Location: /home/user/ComfyUI/models/loras/anime_style_lora.safetensors

[Page 1 of 1]
```

!!! tip "Hash searches are exact"
    Hash searches match from the beginning of the hash. `a1b2` matches `a1b2c3d4...` but not `xyz1a1b2...`.

### View detailed model information

Get complete details about a specific model:

```bash
# By hash prefix
cg model index show a1b2c3

# By exact filename
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
    • /home/user/ComfyUI/models/checkpoints/sd_xl_base_1.0.safetensors
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

**Understanding the output:**

- **Hash** - Short hash (42 chars) for display and searches
- **Blake3** - Full BLAKE3 hash from sampling
- **SHA256** - Full file hash (only computed if collision detected)
- **Locations** - All places this file exists with modification times
- **Sources** - Download URLs registered for this model

## Syncing the index

When you add, remove, or move model files manually, update the index:

```bash
cg model index sync
```

**What happens:**

1. **Scans directory** - Walks through entire models directory
2. **Computes hashes** - Samples new files for BLAKE3 hashes
3. **Updates database** - Adds new models, removes deleted ones
4. **Reports changes** - Shows what was added, removed, or moved

**Example output:**

```
📁 Syncing models directory: /home/user/ComfyUI/models

Scanning directory...
  Scanned 152 files in 28.4s
  Found 3 new models
  Removed 1 deleted model
  147 models unchanged

✓ Sync complete
  Total models: 148 unique, 152 files
  Total size: 124.7 GB
```

### When to sync

Run `cg model index sync` when you:

- Download models directly from web browsers
- Copy models from other machines
- Manually delete or move model files
- Import models from other ComfyUI installations
- Notice models missing from workflows

!!! tip "Automatic syncing"
    ComfyGit automatically indexes models when you use `cg model download`. Manual syncing is only needed for files added outside ComfyGit.

## Index status and health

Check your index statistics:

```bash
cg model index status
```

**Example output:**

```
📊 Model Index Status:

   Models Directory: ✓ /home/user/ComfyUI/models
   Total Models: 148 unique models
   Total Files: 152 files indexed
   Duplicates: 4 duplicate files detected
```

**Understanding duplicates:**

If total files > unique models, you have duplicates (same file in multiple locations). This is normal if you:

- Keep backups in multiple directories
- Have the same model in different category folders
- Migrated from another ComfyUI installation

Duplicates are harmless but waste disk space.

## Model categories

ComfyGit automatically categorizes models based on their directory path:

| Category | Directory | Examples |
|----------|-----------|----------|
| **checkpoints** | checkpoints/ | Base models (SD 1.5, SDXL, Flux) |
| **loras** | loras/ | LoRA adapters for style/character |
| **vae** | vae/ | Variational Auto-Encoders |
| **controlnet** | controlnet/ | ControlNet models |
| **clip_vision** | clip_vision/ | CLIP vision encoders |
| **embeddings** | embeddings/ | Textual inversions |
| **upscale_models** | upscale_models/ | ESRGAN, RealESRGAN upscalers |
| **style_models** | style_models/ | Style transfer models |
| **unet** | unet/ | Custom UNet models |
| **clip** | clip/ | CLIP text encoders |
| **text_encoders** | text_encoders/ | T5, CLIP text encoders |
| **configs** | configs/ | YAML configuration files |

Plus 8 more specialized categories for gligen, photomaker, diffusion_models, etc.

**Category detection:**

ComfyGit determines category from the relative path:

```
checkpoints/sd_xl_base_1.0.safetensors → checkpoints
loras/style/anime_v2.safetensors       → loras
vae/sdxl_vae.safetensors               → vae
```

Categories are used for:

- Organizing search results
- Suggesting download paths
- Setting default model importance in workflows
- Filtering and queries

## Understanding model identity

### Hash-based identity

Models are identified by their **content hash**, not filename:

```bash
# These are the SAME model (same hash):
checkpoints/sd_xl_base_1.0.safetensors
backup/sdxl_base.safetensors
```

ComfyGit tracks them as one model with two locations.

### Multiple locations

A single model can exist in multiple places:

```bash
cg model index show sd_xl_base_1.0.safetensors
```

```
  Locations (3):
    • /home/user/ComfyUI/models/checkpoints/sd_xl_base_1.0.safetensors
    • /mnt/backup/models/checkpoints/sd_xl_base_1.0.safetensors
    • /mnt/external/ComfyUI_old/models/checkpoints/sdxl_base.safetensors
```

All three are tracked as locations of the same model.

### Short hash vs full hash

- **Short hash** (16 chars) - Used for display: `a1b2c3d4e5f67890`
- **Full hash** (42 chars) - Used internally: `a1b2c3d4e5f67890abcdef1234567890abcdef12`

Search accepts either:

```bash
cg model index find a1b2      # Matches short hash prefix
cg model index find a1b2c3d4  # More specific short hash
```

## Changing models directory

Switch to a different models directory:

```bash
cg model index dir /mnt/external/models
```

**What happens:**

1. **Clears old index** - Removes entries for old directory
2. **Scans new directory** - Indexes all models in new location
3. **Updates symlinks** - All environment `models/` directories point to new location
4. **Preserves sources** - Download URLs are NOT lost when switching directories

!!! warning "Environments will use new directory"
    All environments immediately use the new models directory. Make sure it contains the models your workflows need, or re-download them.

### Switching back

You can switch back to the previous directory anytime:

```bash
cg model index dir ~/ComfyUI/models
```

Model metadata (sources, download intents) is preserved in the database, so switching is safe.

## Common patterns

### Finding duplicates

List all duplicates to save disk space:

```bash
cg model index list | grep "Locations (2)"
```

Models with multiple locations are duplicates.

### Checking model availability

Verify a workflow's model exists:

```bash
cg model index find "sd_xl_base_1.0.safetensors"
```

If no results, the model is not indexed (missing or not scanned yet).

### Indexing a new models directory

After copying models from another machine:

```bash
cg model index dir /path/to/copied/models
```

ComfyGit will index everything in one scan.

### Verifying index is up to date

Check when the index was last synced:

```bash
cg model index status
```

If you've added models since the last sync:

```bash
cg model index sync
```

## Troubleshooting

### Models not showing up

**Problem:** Downloaded a model but it's not in the index

**Solutions:**

```bash
# Verify models directory is set
cg model index status

# Run a manual sync
cg model index sync

# Check if file is in the directory
ls ~/ComfyUI/models/checkpoints/
```

### Index shows deleted models

**Problem:** Deleted model files but they still appear in index

**Solution:**

```bash
cg model index sync
```

Sync removes entries for files that no longer exist.

### "Multiple models found matching..."

**Problem:** Search returns multiple results

**Solution:**

Use more specific identifier:

```bash
# Too ambiguous
cg model index show anime

# More specific - use longer hash
cg model index show a1b2c3d4e5f6

# Most specific - full hash or exact filename
cg model index show anime_v2.safetensors
```

### Models directory doesn't exist

**Problem:** Set directory but path is invalid

```
✗ Directory does not exist: /path/to/models
```

**Solutions:**

```bash
# Check path spelling
ls /path/to/models

# Create directory first
mkdir -p ~/ComfyUI/models

# Then set it
cg model index dir ~/ComfyUI/models
```

### Slow indexing

**Problem:** Index scan takes a very long time

**Cause:** Large model collection (>500 files) or slow disk

**Solutions:**

- Be patient - first scan is slowest (~200ms per file)
- Subsequent syncs are faster (only new files scanned)
- Use SSD instead of HDD for models directory
- Exclude non-model files from models directory

### "No models directory configured"

**Problem:** Trying to list/sync without setting directory

```
✗ No models directory configured
   Run 'cg model index dir <path>' to set your models directory
```

**Solution:**

```bash
# Set models directory first
cg model index dir ~/ComfyUI/models

# Then list/sync works
cg model index list
```

### Hash collision detected

**Problem:** Two different files have the same sampled hash (extremely rare)

ComfyGit automatically:

1. Computes full file hash for both files
2. Distinguishes them by full hash
3. Logs the collision for debugging

This is handled transparently - no action needed.

## Next steps

<div class="grid cards" markdown>

-   :material-download: **[Downloading Models](downloading-models.md)**

    ---

    Download models from CivitAI, HuggingFace, and direct URLs

-   :material-folder-open: **[Managing Models](managing-models.md)**

    ---

    Search, organize, and maintain your model collection

-   :material-link-variant: **[Adding Sources](adding-sources.md)**

    ---

    Register download URLs for re-downloads and sharing

</div>
