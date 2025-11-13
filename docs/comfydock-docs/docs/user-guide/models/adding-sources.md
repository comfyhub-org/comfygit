# Adding Model Sources

> Register download URLs for your models to enable re-downloads, environment sharing, and team collaboration.

## Overview

Model sources are download URLs that tell ComfyGit where to get a model file. When you add sources:

- **Re-download capability** - Retrieve deleted models easily
- **Environment portability** - Share environments with automatic model downloads
- **Team collaboration** - Team members can download models from shared sources
- **Fallback URLs** - Multiple sources provide redundancy

## What are model sources?

A model source is a URL that points to a downloadable model file. ComfyGit stores sources in the model index:

```
Model: sd_xl_base_1.0.safetensors
  Sources:
    • HuggingFace: https://huggingface.co/.../sd_xl_base_1.0.safetensors
    • CivitAI: https://civitai.com/api/download/models/128078
```

Sources enable:

1. **Automatic downloads** - `cg import` can download models from sources
2. **Manual re-downloads** - Copy URL and run `cg model download <url>`
3. **Export validation** - `cg export` warns if models lack sources

## When to add sources

Add sources when:

- **Preparing to export** - Before sharing an environment
- **Team collaboration** - So others can download models
- **Backup strategy** - Register multiple mirrors
- **After manual downloads** - Browser downloads don't auto-register sources

!!! tip "Downloads auto-register sources"
    Models downloaded with `cg model download` automatically have their source URL registered. Manual source addition is only needed for models added other ways.

## Adding sources interactively

The easiest way to add sources is interactively:

```bash
cg model add-source
```

ComfyGit guides you through all models without sources.

**Example session:**

```
📦 Add Model Sources

Found 3 model(s) without download sources

[1/3] realistic_vision_v5.safetensors
  Hash: f6e5d4c3b2a1...
  Path: checkpoints/realistic_vision_v5.safetensors
  Status: ✓ Available locally

  URL (or 's' to skip, 'q' to quit): https://civitai.com/api/download/models/128078

  ✓ Added source

[2/3] anime_style_lora.safetensors
  Hash: 9876543210ab...
  Path: loras/anime_style_lora.safetensors
  Status: ✓ Available locally

  URL (or 's' to skip, 'q' to quit): s

  → Skipped

[3/3] detail_enhancer.safetensors
  Hash: abcdef123456...
  Path: loras/detail_enhancer.safetensors
  Status: ✓ Available locally

  URL (or 's' to skip, 'q' to quit): q

⊗ Cancelled

✅ Complete: 1/3 source(s) added

Your environment is now more shareable!
  Run 'cg export' to bundle and distribute
```

### Interactive commands

During interactive mode:

- **Enter URL** - Paste download URL and press Enter
- **s** - Skip this model
- **q** - Quit and exit

### Finding download URLs

Where to get URLs for interactive mode:

**CivitAI:**

1. Visit model page (e.g., `civitai.com/models/4201/realistic-vision`)
2. Click "Download" button
3. Right-click and copy link address
4. URL format: `https://civitai.com/api/download/models/XXXXX`

**HuggingFace:**

1. Visit model repository
2. Click on file (e.g., `sd_xl_base_1.0.safetensors`)
3. Right-click "download" link
4. URL format: `https://huggingface.co/USER/REPO/resolve/main/file.safetensors`

**Direct URLs:**

Any direct download link works.

## Adding sources directly

Add a source to a specific model without interaction:

```bash
cg model add-source <model-identifier> <url>
```

**Examples:**

```bash
# By exact filename
cg model add-source realistic_vision_v5.safetensors https://civitai.com/api/download/models/128078

# By hash prefix
cg model add-source f6e5d4c3 https://civitai.com/api/download/models/128078

# By full hash
cg model add-source f6e5d4c3b2a1e9876543210abcdef123456789 https://civitai.com/api/download/models/128078
```

**Output:**

```
✓ Added source to realistic_vision_v5.safetensors
  https://civitai.com/api/download/models/128078
```

### When to use direct mode

Direct mode is useful for:

- **Scripting** - Batch adding sources
- **Automation** - CI/CD pipelines
- **Single model** - Quick one-off source addition
- **Known identifiers** - When you already know the hash/filename

## Source types

ComfyGit tracks the type of each source:

### CivitAI sources

```bash
cg model add-source model.safetensors https://civitai.com/api/download/models/128078
```

Detected as `civitai` type. Used for:

- Community models
- LoRAs and checkpoints
- Trained on specific styles/characters

### HuggingFace sources

```bash
cg model add-source model.safetensors https://huggingface.co/stabilityai/sdxl/resolve/main/model.safetensors
```

Detected as `huggingface` type. Used for:

- Official models (Stability AI, etc.)
- Research models
- Open source releases

### Custom sources

```bash
cg model add-source model.safetensors https://example.com/models/model.safetensors
```

Detected as `custom` type. Used for:

- Private model hosting
- Self-hosted mirrors
- Organization-internal repositories

## Multiple sources per model

Models can have multiple download sources for redundancy:

```bash
# Add primary source
cg model add-source sd_xl_base_1.0.safetensors https://huggingface.co/.../sd_xl_base_1.0.safetensors

# Add backup source
cg model add-source sd_xl_base_1.0.safetensors https://civitai.com/api/download/models/128078
```

**View all sources:**

```bash
cg model index show sd_xl_base_1.0.safetensors
```

```
  Sources (2):
    • HuggingFace
      URL: https://huggingface.co/.../sd_xl_base_1.0.safetensors
      Added: 2025-01-10 09:15:00
    • CivitAI
      URL: https://civitai.com/api/download/models/128078
      Added: 2025-01-12 16:42:31
```

**Benefits of multiple sources:**

- **Redundancy** - If one source goes down, use another
- **Flexibility** - Choose fastest source per user
- **Availability** - Some users prefer CivitAI, others HuggingFace

!!! tip "Source priority"
    When importing environments, ComfyGit tries sources in the order they were added. Add most reliable source first.

## Integration with export/import

### Export validation

When exporting an environment:

```bash
cg export
```

ComfyGit checks if all models have sources:

```
📦 Exporting environment: my-project

⚠️  Export validation:

3 model(s) have no source URLs.

  • realistic_vision_v5.safetensors
    Used by: portrait_workflow, character_workflow
  • anime_style_lora.safetensors
    Used by: anime_workflow
  • detail_enhancer.safetensors
    Used by: portrait_workflow

⚠️  Recipients won't be able to download these models automatically.
   Add sources: cg model add-source

Continue export? (y/N):
```

**Options:**

- **y** - Export anyway (models without sources won't be downloadable)
- **N** - Cancel and add sources first

### Adding sources before export

Add sources to all models:

```bash
# Interactive mode
cg model add-source

# Or direct mode for each model
cg model add-source model1.safetensors <url>
cg model add-source model2.safetensors <url>

# Then export
cg export
```

### Import behavior

When importing an environment:

```bash
cg import environment.tar.gz
```

ComfyGit offers model download strategy:

```
Model download strategy:
  1. all      - Download all models with sources
  2. required - Download only required models
  3. skip     - Skip all downloads (can resolve later)
Choice (1-3) [1]:
```

**Strategies:**

- **all** - Downloads every model that has a source URL
- **required** - Downloads only models marked as "required" importance
- **skip** - Doesn't download anything (models become unresolved)

Models without sources cannot be downloaded automatically - user must download manually.

## Model importance and sources

Model importance affects download behavior during import:

### Default importance by category

ComfyGit assigns default importance based on model category:

| Category | Default Importance | Import Behavior |
|----------|-------------------|-----------------|
| **checkpoints** | flexible | Downloaded with "all" strategy |
| **vae** | flexible | Downloaded with "all" strategy |
| **loras** | flexible | Downloaded with "all" strategy |
| **controlnet** | required | Downloaded with "required" or "all" |
| **clip_vision** | required | Downloaded with "required" or "all" |
| **embeddings** | flexible | Downloaded with "all" strategy |
| **upscale_models** | flexible | Downloaded with "all" strategy |
| **style_models** | flexible | Downloaded with "all" strategy |

### Per-workflow importance

Users can override importance per workflow:

```bash
cg workflow model importance my_workflow model.safetensors required
```

This makes `model.safetensors` required for `my_workflow` even if its category defaults to "flexible".

See [Workflow Model Importance](../workflows/workflow-model-importance.md) for details.

## Common patterns

### Adding sources before sharing

Prepare environment for export:

```bash
# 1. Check which models need sources
cg model add-source  # Lists models without sources

# 2. Add sources interactively
# (Paste URLs for each model)

# 3. Verify all models have sources
cg export  # Should not show source warnings

# 4. Export and share
cg export
```

### Batch adding sources

Add sources to multiple models:

```bash
# Create a mapping file
cat > model_sources.txt << EOF
realistic_vision_v5.safetensors https://civitai.com/api/download/models/128078
anime_style_lora.safetensors https://civitai.com/api/download/models/128079
detail_enhancer.safetensors https://civitai.com/api/download/models/128080
EOF

# Add all sources
while read filename url; do
  cg model add-source "$filename" "$url"
done < model_sources.txt
```

### Adding backup sources

Register fallback URLs:

```bash
# Add primary source
cg model add-source sd_xl_base_1.0.safetensors https://huggingface.co/.../sd_xl_base_1.0.safetensors

# Add backup CivitAI mirror
cg model add-source sd_xl_base_1.0.safetensors https://civitai.com/api/download/models/128078

# Add private backup
cg model add-source sd_xl_base_1.0.safetensors https://internal-server.company.com/models/sd_xl_base_1.0.safetensors
```

### Organization model repositories

For teams with internal model repositories:

```bash
# Add sources pointing to internal server
cg model add-source company_lora.safetensors https://models.company.com/loras/company_lora.safetensors
cg model add-source company_checkpoint.safetensors https://models.company.com/checkpoints/company_checkpoint.safetensors

# Team members can import and download from internal sources
cg import team_environment.tar.gz
```

## Troubleshooting

### "Model not found"

**Problem:** Direct mode can't find model

```
✗ Model not found: model_name
```

**Solutions:**

```bash
# Check exact filename
cg model index list | grep model_name

# Use exact filename or hash
cg model index show model_name
cg model add-source exact_filename.safetensors <url>

# Or use interactive mode
cg model add-source
```

### "Multiple models match"

**Problem:** Filename is ambiguous

```
✗ Multiple models match 'anime':
  • anime_v2.safetensors (f6e5d4c3...)
  • anime_style_lora.safetensors (98765432...)
  • anime_character.safetensors (abcdef12...)

Use full hash: cg model add-source <hash> <url>
```

**Solution:**

Use full hash instead of filename:

```bash
cg model add-source f6e5d4c3b2a1e9876543210abcdef123456789 <url>
```

### "URL already exists"

**Problem:** Source already registered

```
✗ URL already exists for realistic_vision_v5.safetensors
```

**Solution:**

This is fine - source is already tracked. No action needed.

To verify:

```bash
cg model index show realistic_vision_v5.safetensors
```

### Interactive mode shows no models

**Problem:** Interactive mode says no models need sources

```
✓ All models have download sources!
```

**Meaning:**

All models in your index already have at least one source URL registered. This is the desired state.

To verify:

```bash
# Check a few models
cg model index show model1.safetensors
cg model index show model2.safetensors
```

### Models without sources still in export warning

**Problem:** Added sources but export still warns

**Solution:**

Make sure you added sources to all models mentioned in the warning:

```bash
# Run export again
cg export

# Note which models are listed

# Add sources for each
cg model add-source model1.safetensors <url>
cg model add-source model2.safetensors <url>

# Try export again
cg export
```

### Invalid URL format

**Problem:** URL doesn't work

**Solutions:**

```bash
# Ensure URL is direct download link, not webpage
# Wrong: https://civitai.com/models/4201/realistic-vision
# Right: https://civitai.com/api/download/models/128078

# For CivitAI, use API URLs
cg model add-source model.safetensors https://civitai.com/api/download/models/XXXXX

# For HuggingFace, use resolve URLs
cg model add-source model.safetensors https://huggingface.co/USER/REPO/resolve/main/file.safetensors
```

## Advanced usage

### Viewing all models with sources

List models and check for sources:

```bash
# Show all models
cg model index list

# Check each for sources
cg model index show model1.safetensors
cg model index show model2.safetensors
```

Models with sources show:

```
  Sources (X):
    • Type
      URL: ...
```

Models without sources show:

```
  Sources: None
    Add with: cg model add-source abc1234
```

### Exporting source list

Create a backup of all model sources:

```bash
# List all models
cg model index list > models.txt

# For each model, export sources
for model in $(cat models.txt | grep ".safetensors" | awk '{print $1}'); do
  echo "Model: $model"
  cg model index show "$model" | grep -A 10 "Sources"
  echo "---"
done > model_sources.txt
```

### Verifying sources work

Test that URLs are accessible:

```bash
# Get source URL
cg model index show model.safetensors | grep "URL:"

# Test with wget or curl
wget --spider <url>
curl -I <url>
```

If URL returns 200 OK, source is valid.

### Managing source metadata

Sources include metadata from API responses (CivitAI, HuggingFace):

```bash
cg model index show model.safetensors
```

```
  Sources (1):
    • CivitAI
      URL: https://civitai.com/api/download/models/128078
      model_name: Realistic Vision V5.0
      creator: SG_161222
      Added: 2025-01-10 09:15:00
```

This metadata helps identify model versions and creators.

## Future enhancements

Currently, ComfyGit only has `cg model add-source`. Future versions may add:

- `cg model list-sources` - List all models and their sources
- `cg model remove-source` - Remove a source URL
- `cg model update-source` - Update a source URL

For now, use:

- `cg model index show <model>` to view sources
- `cg model add-source` to add sources
- Manual database editing to remove sources (advanced)

## Next steps

<div class="grid cards" markdown>

-   :material-database: **[Model Index](model-index.md)**

    ---

    Understand how the model index works

-   :material-download: **[Downloading Models](downloading-models.md)**

    ---

    Download models from URLs with automatic source registration

-   :material-export: **[Export/Import](../collaboration/export-import.md)**

    ---

    Share environments with automatic model downloads

</div>
