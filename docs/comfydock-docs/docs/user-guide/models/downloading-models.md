# Downloading Models

> Download models from CivitAI, HuggingFace, and direct URLs with automatic indexing and source tracking.

## Overview

ComfyGit can download models from multiple sources:

- **CivitAI** - Community model sharing platform
- **HuggingFace** - AI model repository
- **Direct URLs** - Any direct download link

All downloads are:

- **Automatically indexed** - Added to model database immediately
- **Hash-verified** - BLAKE3 computed during download
- **Source-tracked** - URL saved for future reference
- **Atomic** - Downloads to `.tmp` file, renamed on success (prevents corruption)

## Basic download

Download a model from any URL:

```bash
cg model download https://civitai.com/api/download/models/128078
```

**What happens:**

1. **Source detection** - Identifies CivitAI, HuggingFace, or custom URL
2. **Path suggestion** - Suggests appropriate category subdirectory
3. **Interactive confirmation** - Shows suggested path, allows changes
4. **Streaming download** - Downloads with progress display
5. **Hash computation** - BLAKE3 computed inline during download
6. **Automatic indexing** - Model added to database
7. **Source registration** - URL saved for re-downloads

**Example session:**

```
📥 Downloading from: https://civitai.com/api/download/models/128078
   Model will be saved to: checkpoints/realistic_vision_v5.safetensors

   [Y] Continue  [m] Change path  [c] Cancel
Choice [Y]/m/c: y

📥 Downloading to: checkpoints/realistic_vision_v5.safetensors
████████████████████████████████████ 4.27 GB / 4.27 GB [100%] 12.3 MB/s

✓ Download complete: realistic_vision_v5.safetensors
  Size: 4.27 GB
  Hash: f6e5d4c3b2a1e9876543210abcdef123456789
  Path: checkpoints/realistic_vision_v5.safetensors
  Source: CivitAI
```

## Download sources

### CivitAI

CivitAI is the largest ComfyUI model community. Download models by:

**API download URL:**

```bash
cg model download https://civitai.com/api/download/models/128078
```

**Direct model page URL:**

```bash
# ComfyGit extracts the API URL automatically
cg model download https://civitai.com/models/4201/realistic-vision-v51
```

!!! info "CivitAI API keys"
    Some models require authentication. Set your API key once:

    ```bash
    cg config --civitai-key YOUR_API_KEY_HERE
    ```

    Get your key from: [https://civitai.com/user/account](https://civitai.com/user/account)

### HuggingFace

HuggingFace hosts official and community models:

```bash
# Full URL to specific file
cg model download https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors

# Shortened hf.co URL
cg model download https://hf.co/stabilityai/sdxl-vae/resolve/main/sdxl_vae.safetensors
```

ComfyGit detects HuggingFace URLs and handles authentication if needed.

### Direct URLs

Any direct download link works:

```bash
# Direct .safetensors file
cg model download https://example.com/models/my_model.safetensors

# GitHub releases
cg model download https://github.com/user/repo/releases/download/v1.0/model.safetensors
```

## Path confirmation

### Interactive mode (default)

By default, ComfyGit shows the suggested path and asks for confirmation:

```
📥 Downloading from: https://civitai.com/api/download/models/128078
   Model will be saved to: checkpoints/realistic_vision_v5.safetensors

   [Y] Continue  [m] Change path  [c] Cancel
Choice [Y]/m/c:
```

**Options:**

- **Y** or Enter - Continue with suggested path
- **m** - Change the path
- **c** - Cancel download

**Changing the path:**

```
Choice [Y]/m/c: m

Enter path (relative to models dir): loras/my_custom_lora.safetensors

📥 Downloading from: https://civitai.com/api/download/models/128078
   Model will be saved to: loras/my_custom_lora.safetensors

   [Y] Continue  [m] Change path  [c] Cancel
Choice [Y]/m/c: y
```

### Specifying exact path

Skip interaction by providing the full path:

```bash
cg model download https://example.com/model.safetensors --path checkpoints/my_model.safetensors
```

Path is relative to your models directory.

### Specifying category

Auto-generate path in a specific category:

```bash
cg model download https://example.com/some_lora.safetensors --category loras
```

ComfyGit extracts the filename and places it in `loras/some_lora.safetensors`.

**Available categories:**

- `checkpoints` - Base models
- `loras` - LoRA adapters
- `vae` - VAE models
- `controlnet` - ControlNet models
- `upscale_models` - Upscalers
- `embeddings` - Textual inversions
- `clip_vision` - CLIP vision encoders
- `style_models` - Style models
- Plus 13 more specialized categories

### Non-interactive downloads

Skip all prompts with `--yes`:

```bash
cg model download https://example.com/model.safetensors --yes
```

Uses the auto-suggested path without confirmation. Useful for:

- Scripting batch downloads
- CI/CD pipelines
- Automated environment setup

## Path suggestion logic

ComfyGit suggests paths based on:

1. **Filename analysis** - Looks for category keywords in filename
2. **Source metadata** - Uses CivitAI/HuggingFace model type
3. **File extension** - Maps `.safetensors`, `.ckpt`, `.pt`, etc.
4. **Default category** - Falls back to `checkpoints/` for unknown types

**Examples:**

```
URL: civitai.com/.../anime_lora_v2.safetensors
→ Suggested: loras/anime_lora_v2.safetensors

URL: huggingface.co/.../sdxl_vae.safetensors
→ Suggested: vae/sdxl_vae.safetensors

URL: example.com/my_model.safetensors
→ Suggested: checkpoints/my_model.safetensors (default)
```

## Download progress

During download, ComfyGit shows:

```
████████████████████████████████████ 4.27 GB / 4.27 GB [100%] 12.3 MB/s
```

- **Progress bar** - Visual completion indicator
- **Downloaded / Total** - Current and total size
- **Percentage** - Completion percentage
- **Speed** - Current download speed

For large models (>5 GB), this helps track progress.

## After download completes

### Download statistics

ComfyGit shows detailed stats after successful download:

```
✓ Download complete: realistic_vision_v5.safetensors
  Size: 4.27 GB
  Hash: f6e5d4c3b2a1e9876543210abcdef123456789
  Path: checkpoints/realistic_vision_v5.safetensors
  Source: CivitAI
```

**Fields:**

- **Filename** - Model filename on disk
- **Size** - File size in human-readable format
- **Hash** - BLAKE3 hash (short form)
- **Path** - Relative path in models directory
- **Source** - Detected source type

### Automatic indexing

The model is immediately available in:

```bash
# Find it in the index
cg model index find realistic_vision

# See detailed info
cg model index show realistic_vision_v5.safetensors

# Use it in workflows right away
# (ComfyUI will see it in checkpoints/ folder)
```

### Source tracking

The download URL is saved as a source:

```bash
cg model index show realistic_vision_v5.safetensors
```

```
  Sources (1):
    • CivitAI
      URL: https://civitai.com/api/download/models/128078
      Added: 2025-01-15 14:32:18
```

This enables:

- Re-downloading if file is deleted
- Sharing environments with download URLs
- Updating models from source

## CivitAI authentication

### When authentication is needed

Some CivitAI models require an API key:

- NSFW/mature content models
- Creator-gated models
- Early access models

Without a key, you'll see:

```
✗ Download failed: 401 Unauthorized

⚠️  CivitAI Authentication Required

This model requires a CivitAI API key.

1. Get your API key:
   → Visit: https://civitai.com/user/account
   → Copy your API key

2. Configure ComfyGit:
   → Run: cg config --civitai-key YOUR_KEY_HERE

3. Retry download:
   → Run: cg model download <url>
```

### Setting your API key

Configure authentication once per workspace:

```bash
cg config --civitai-key YOUR_API_KEY_HERE
```

**Example:**

```bash
cg config --civitai-key a1b2c3d4e5f67890abcdef1234567890
```

```
✓ CivitAI API key saved
```

Your key is stored securely in `.metadata/workspace.json` and used for all future CivitAI downloads.

### Viewing configured key

Check if key is set:

```bash
cg config --show
```

```
ComfyGit Configuration:

  Workspace Path:  /home/user/.comfydock
  CivitAI API Key: ••••••••7890
  Registry Cache:  Enabled
```

The key is masked showing only the last 4 characters.

### Clearing your key

Remove stored API key:

```bash
cg config --civitai-key ""
```

```
✓ CivitAI API key cleared
```

## Common patterns

### Downloading multiple models

Download several models in sequence:

```bash
# LoRAs
cg model download https://civitai.com/.../lora1.safetensors --yes
cg model download https://civitai.com/.../lora2.safetensors --yes
cg model download https://civitai.com/.../lora3.safetensors --yes

# Checkpoints
cg model download https://huggingface.co/.../sdxl.safetensors --yes
cg model download https://huggingface.co/.../sd15.safetensors --yes
```

Use `--yes` to skip confirmation for each download.

### Downloading to specific subdirectories

Organize models with custom paths:

```bash
# Character LoRAs
cg model download https://civitai.com/.../character.safetensors --path loras/characters/character.safetensors

# Style LoRAs
cg model download https://civitai.com/.../anime_style.safetensors --path loras/styles/anime_style.safetensors

# Project-specific models
cg model download https://example.com/project_model.safetensors --path checkpoints/client_projects/model.safetensors
```

Subdirectories are created automatically.

### Re-downloading a model

If you deleted a model with tracked source:

```bash
# Find the model (even if deleted)
cg model add-source

# Shows models without sources, skip to re-download
# Or download directly if you have the URL
cg model download https://civitai.com/api/download/models/128078 --yes
```

### Downloading from workflow requirements

When a workflow needs a model:

```bash
# Resolve workflow to see missing models
cg workflow resolve my_workflow

# Copy download URL from output
cg model download <url> --yes
```

## Troubleshooting

### "401 Unauthorized" from CivitAI

**Problem:** Model requires authentication

**Solution:**

```bash
# Set your API key
cg config --civitai-key YOUR_KEY_HERE

# Retry download
cg model download <url>
```

Get API key from: [https://civitai.com/user/account](https://civitai.com/user/account)

### "403 Forbidden" errors

**Problem:** Model is private, deleted, or access-restricted

**Possible causes:**

- Model removed by creator
- DMCA takedown
- Creator restricted access
- Invalid download URL

**Solution:**

Find an alternative model or contact model creator.

### "404 Not Found"

**Problem:** URL is incorrect or model doesn't exist

**Solutions:**

```bash
# Verify URL is correct
# Check browser - can you access it?

# For CivitAI, ensure using API URL:
# https://civitai.com/api/download/models/123456
# NOT: https://civitai.com/models/4201/model-name
```

### Download hangs or is very slow

**Problem:** Slow connection or server throttling

**Solutions:**

- Wait - large models (5+ GB) take time
- Check internet speed
- Try again later if server is overloaded
- Use `Ctrl+C` to cancel and retry

### "Disk space" errors

**Problem:** Not enough space for download

```
✗ Download failed: No space left on device
```

**Solutions:**

```bash
# Check available space
df -h ~

# Free up space
rm -rf ~/.comfydock/workspace/models/old_models/

# Or change models directory to larger disk
cg model index dir /mnt/large_drive/models
```

### File already exists

**Problem:** Model with same filename already exists

```
✗ File already exists: checkpoints/model.safetensors
```

**Solutions:**

```bash
# Download to different name
cg model download <url> --path checkpoints/model_v2.safetensors

# Or delete old file first
rm ~/.comfydock/workspace/models/checkpoints/model.safetensors
cg model download <url>
```

### "Invalid URL" errors

**Problem:** URL format not recognized

**Solutions:**

```bash
# Ensure URL is direct download link
# Not a webpage showing the download button

# For CivitAI, use API URLs:
cg model download https://civitai.com/api/download/models/128078

# For HuggingFace, use resolve URLs:
cg model download https://huggingface.co/USER/REPO/resolve/main/file.safetensors
```

### Hash mismatch warnings

**Problem:** Downloaded file hash doesn't match expected (rare)

This indicates:

- Corrupted download
- Modified file on server
- Network issue

**Solution:**

```bash
# Delete corrupted file
rm ~/.comfydock/workspace/models/path/to/model.safetensors

# Re-download
cg model download <url>
```

### Cannot write to models directory

**Problem:** Permission denied

```
✗ Download failed: Permission denied
```

**Solutions:**

```bash
# Check directory permissions
ls -la ~/.comfydock/workspace/models/

# Fix permissions
chmod -R u+w ~/.comfydock/workspace/models/

# Or use different directory
cg model index dir ~/my_models
cg model download <url>
```

## Advanced usage

### Downloading to temporary location first

Download elsewhere, then move to models directory:

```bash
# Download to Downloads folder
cd ~/Downloads
wget https://example.com/model.safetensors

# Move to models directory
mv model.safetensors ~/.comfydock/workspace/models/checkpoints/

# Sync index
cg model index sync
```

### Verifying downloads with external tools

Verify hash independently:

```bash
# Download model
cg model download <url> --yes

# Get ComfyGit's computed hash
cg model index show model.safetensors

# Compare with external tool
b3sum ~/.comfydock/workspace/models/checkpoints/model.safetensors
```

### Batch downloads from file

Create a list of URLs and download all:

```bash
# urls.txt
https://civitai.com/api/download/models/128078
https://civitai.com/api/download/models/128079
https://civitai.com/api/download/models/128080
```

```bash
# Download all
while read url; do
  cg model download "$url" --yes
done < urls.txt
```

## Next steps

<div class="grid cards" markdown>

-   :material-database: **[Model Index](model-index.md)**

    ---

    Understand how models are indexed and organized

-   :material-folder-open: **[Managing Models](managing-models.md)**

    ---

    Search, organize, and maintain your model collection

-   :material-link-variant: **[Adding Sources](adding-sources.md)**

    ---

    Register download URLs for sharing and re-downloads

</div>
