# Workflow Model Importance

> Control which models are required, flexible, or optional for your workflows.

## Overview

ComfyGit lets you mark models in workflows as:

- **Required** - Must be present to run the workflow
- **Flexible** - Can substitute with similar models
- **Optional** - Nice to have but not critical

This helps when sharing workflows or importing environments on machines with different model collections.

## Why model importance?

When you share a workflow that uses 10 different models, not everyone may have all of them. By marking models appropriately:

- **Recipients know** what's critical vs. nice-to-have
- **ComfyGit can warn** about missing required models
- **Imports can succeed** even without optional models
- **Team collaboration improves** with clear expectations

## Setting model importance

### Interactive mode (recommended)

```bash
cg workflow model importance
```

Walks you through:

1. **Select workflow** - Choose from tracked workflows
2. **Select model** - Pick model to configure
3. **Set importance** - Choose required/flexible/optional

**Example session:**

```
Select workflow:
  1. portrait-generation.json
  2. anime-style.json
  3. sdxl-upscale.json

Choice: 1

Models in portrait-generation.json:
  1. sd_xl_base_1.0.safetensors (no importance set)
  2. perfectEyesXL.safetensors (no importance set)
  3. DetailedEyes.safetensors (no importance set)

Select model: 1

Set importance for sd_xl_base_1.0.safetensors:
  1. required
  2. flexible
  3. optional

Choice: 1

✓ Set sd_xl_base_1.0.safetensors to required
```

### Non-interactive mode

Specify everything on the command line:

```bash
cg workflow model importance portrait-generation sd_xl_base_1.0.safetensors required
```

Arguments:

1. Workflow name (without .json)
2. Model identifier (filename or hash)
3. Importance level (required/flexible/optional)

## Importance levels explained

### Required

**Use when:**

- Workflow won't run without this model
- Model is core to the workflow's purpose
- No reasonable substitutes exist

**Example:** Base SDXL checkpoint for SDXL workflow

```bash
cg workflow model importance my-workflow sd_xl_base_1.0.safetensors required
```

### Flexible

**Use when:**

- Model can be swapped with alternatives
- Any checkpoint in the same category works
- Style/quality varies but workflow still runs

**Example:** Style LoRA that can be replaced

```bash
cg workflow model importance my-workflow anime-style-lora.safetensors flexible
```

### Optional

**Use when:**

- Model enhances output but isn't necessary
- Workflow has fallback without it
- Nice-to-have refinement

**Example:** Eye detail LoRA for portraits

```bash
cg workflow model importance my-workflow detail-eyes.safetensors optional
```

## Viewing model importance

Use `cg status` to see workflow model status:

```bash
cg status
```

Output shows models by importance:

```
📋 Workflows:
  ⚠️  portrait-generation.json (synced)
      2 models with importance set, 1 missing optional model
```

For detailed view:

```bash
cg workflow resolve portrait-generation.json --auto
```

Shows model resolution with importance indicators.

## How ComfyGit uses importance

### During `cg commit`

- **Required models missing** → Commit blocked (unless `--allow-issues`)
- **Flexible models missing** → Warning shown, commit allowed
- **Optional models missing** → No warning

### During `cg import`

- **Required models missing** → Download attempted or error shown
- **Flexible models missing** → Warning, suggests alternatives
- **Optional models missing** → Silently skipped

### During `cg repair`

With `--models` flag:

```bash
# Download all models (default)
cg repair --models all

# Download only required models
cg repair --models required

# Skip model downloads entirely
cg repair --models skip
```

### During `cg workflow resolve`

Shows importance in model resolution output:

```
Models:
  ✓ sd_xl_base_1.0.safetensors (required) - found
  ⚠️  anime-style.safetensors (flexible) - missing, suggest alternatives
  • detail-eyes.safetensors (optional) - missing, can proceed
```

## Batch setting importance

For workflows with many models, you can script importance:

```bash
# Set all checkpoints as required
for model in sd_xl_base_1.0 sd15_base; do
  cg workflow model importance my-workflow "$model.safetensors" required
done

# Set all LoRAs as flexible
for lora in style1 style2 style3; do
  cg workflow model importance my-workflow "$lora.safetensors" flexible
done
```

## Best practices

!!! success "Recommended"
    - **Mark base checkpoints as required** - They're essential
    - **Mark style LoRAs as flexible** - Users can substitute
    - **Mark refinement models as optional** - Nice but not critical
    - **Document in commit messages** - "Set model importance for sharing"

!!! warning "Avoid"
    - **Marking everything required** - Makes imports fragile
    - **No importance set** - ComfyGit assumes required by default
    - **Inconsistent across workflows** - Confuses recipients

## Common patterns

### Portrait workflow

```bash
# Base checkpoint - required
cg workflow model importance portrait sd_xl_base_1.0.safetensors required

# Style LoRA - flexible
cg workflow model importance portrait portrait-style.safetensors flexible

# Eye detail - optional
cg workflow model importance portrait perfect-eyes.safetensors optional

# Skin detail - optional
cg workflow model importance portrait skin-detail.safetensors optional
```

### Anime workflow

```bash
# Anime checkpoint - required
cg workflow model importance anime anime-xl.safetensors required

# Character LoRA - flexible
cg workflow model importance anime character-style.safetensors flexible

# Background LoRA - optional
cg workflow model importance anime detailed-bg.safetensors optional
```

## Clearing importance

To remove importance setting (revert to default):

Edit `.cec/pyproject.toml` manually and remove the importance annotation, or set it again to change the value.

!!! note "Future enhancement"
    A `cg workflow model clear-importance` command may be added for easier management.

## Troubleshooting

### "Model not found in workflow"

**Problem:** Model identifier doesn't match workflow

**Solution:** Use exact filename or hash from `cg status` output

### Changes not reflected in status

**Problem:** Set importance but status doesn't show it

**Solution:** Commit changes first:
```bash
cg commit -m "Set model importance"
```

### Import still fails with optional models

**Problem:** Import fails even though models are optional

**Solution:** Check if required models are missing - those will block imports

## Next steps

- [Workflow resolution](workflow-resolution.md) (Coming soon) - How model matching works
- [Export/Import](../collaboration/export-import.md) (Coming soon) - Share workflows with importance set
- [Model management](../models/model-index.md) (Coming soon) - Finding and organizing models
