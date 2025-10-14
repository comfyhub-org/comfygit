# Model Resolution UX Specification

## Overview

This document specifies the user experience for model resolution in ComfyDock, covering both **workflow developers** (creating/committing workflows) and **end users** (importing workflows). The design balances automatic detection with flexible user control.

## Core Design Principles

1. **Category-Based Substitution**: Some model types (checkpoints, VAEs) are interchangeable; others (trained LoRAs, ControlNets) are unique
2. **Progressive Resolution**: Models are resolved one at a time with immediate persistence (Ctrl+C safe)
3. **Smart Defaults**: Auto-resolve when unambiguous, prompt when choices matter
4. **Optional Flexibility**: Developers can mark models as optional; end users can always substitute
5. **Single Source of Truth**: Workflow JSON files remain canonical, resolutions map to them via content hashes

## Data Model

### Manifest Schema (pyproject.toml)

Workflows reference models using a unified list with both resolved and unresolved entries:

```toml
[tool.comfydock.workflows."my_workflow"]
path = "workflows/my_workflow.json"

# Unified model list (resolved and unresolved)
models = [
    # Resolved model
    {
        hash = "abc123hash",
        filename = "sd15.safetensors",
        category = "checkpoints",
        criticality = "flexible",  # substitutable
        status = "resolved",
        nodes = [
            {node_id = "4", node_type = "CheckpointLoaderSimple", widget_idx = 0, widget_value = "sd15.safetensors"}
        ]
    },

    # Unresolved model (developer doesn't have)
    {
        filename = "detail_lora.safetensors",
        category = "loras",
        criticality = "optional",  # workflow works without it
        status = "unresolved",
        nodes = [
            {node_id = "8", node_type = "LoraLoader", widget_idx = 0, widget_value = "detail_lora.safetensors"}
        ]
    }
]

# Global models table (only resolved models with hashes)
[tool.comfydock.models]
"abc123hash" = {
    filename = "sd15.safetensors",
    size = 4200000000,
    relative_path = "checkpoints/sd15.safetensors",
    category = "checkpoints",
    sources = ["https://civitai.com/..."]  # Optional download URLs
}
```

### Criticality Levels

- **`required`**: Workflow breaks without this exact model (e.g., trained ControlNet)
- **`flexible`**: Any model in this category works (e.g., checkpoints, VAEs)
- **`optional`**: Workflow functions without it (e.g., optional upscaler, style LoRA)

### Resolution Status

- **`resolved`**: Model file found in index, hash stored
- **`unresolved`**: Model file not available, no hash

## Developer Flow: Workflow Commit

### Scenario

Developer creates a workflow in ComfyUI with 10 model references:
- 5 models auto-resolve (found in index)
- 1 model is ambiguous (multiple matches)
- 4 models are missing (not in index)

### Command: `comfydock workflow resolve <workflow_name>`

```bash
$ comfydock workflow resolve my_anime_workflow

Resolving models for workflow: my_anime_workflow
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✓ 5 models auto-resolved

Ambiguous Models (1)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. realistic_vision_v5.safetensors (checkpoint)
   Multiple matches found:

   [1] checkpoints/realistic_vision_v5.safetensors (4.2 GB)
       Hash: abc123...

   [2] checkpoints/backup/realistic_vision_v5.safetensors (4.2 GB)
       Hash: abc123... (same file)

   [3] checkpoints/test/realistic_vision_v5.safetensors (2.1 GB)
       Hash: def456... (different file!)

   Choice [1-3] or (s)kip: 1
   → Saved to manifest ✓

Unresolved Models (4)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

2. anime_style_lora.safetensors (lora)
   Not found in model index
   Used by node #5 (LoraLoader)

   🔍 Searching for 'anime_style_lora'...
   No matches found

   [o] Mark as optional
   [r] Refine search
   [s] Skip

   Choice [o]/r/s: o
   ℹ  Marked as optional - end users can skip
   → Saved to manifest ✓

3. trained_controlnet.safetensors (controlnet)
   Not found in model index
   Used by node #12 (ControlNetLoader)

   🔍 Searching for 'trained_controlnet'...
   Found 5 matches:

   [1] trained_controlnet.safetensors (1.4 GB)
       controlnet/trained_controlnet.safetensors
   [2] controlnet_anime.safetensors (1.3 GB)
       controlnet/anime/controlnet_anime.safetensors
   [3] control_v11p_sd15_canny.pth (1.4 GB)
       controlnet/control_v11p_sd15_canny.pth

   [1-3] Select  [r] Refine  [o] Optional  [s] Skip
   Choice [1]/r/o/s: 1
   → Saved to manifest ✓

4. detail_tweaker.safetensors (lora)
   Not found in model index
   Used by node #8 (LoraLoader)

   🔍 Searching for 'detail_tweaker'...
   No matches found

   [u] Download  [r] Refine  [o] Optional  [s] Skip
   Choice [u]/r/o/s: u

   Enter download URL: https://civitai.com/.../detail_tweaker.safetensors

   Model will be downloaded to:
     /models/loras/detail_tweaker.safetensors

   [Y] Continue  [m] Change path  [b] Back
   Choice [Y]/m/b: m

   Enter path: loras/custom/

   Model will be downloaded to:
     /models/loras/custom/detail_tweaker.safetensors

   [Y] Continue  [m] Change path  [b] Back
   Choice [Y]/m/b: y

   Downloading... 100%
   ✓ Downloaded and indexed
   → Saved to manifest ✓

Resolution Summary
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✓ 7 models resolved
⚠ 2 models marked optional
○ 1 model skipped

Next steps:
  • Run 'comfydock status' to verify
  • Run 'comfydock workflow resolve my_anime_workflow' again to fix skipped
  • Run 'comfydock commit' --allow-issues to save current state
```

### Model Resolution Flow

**When model not found in index:**
1. System auto-searches using workflow filename (fast path for 80% case)
2. If matches found, show results (top 9)
3. User options:
   - **[1-9]** Select model from results
   - **[r]** Refine search with custom pattern (user types new query)
   - **[u]** Download from URL (enter direct download link)
   - **[o]** Mark as optional (workflow works without it)
   - **[s]** Skip (leave unresolved, fix later)

**Download from URL flow:**
- For known nodes (CheckpointLoader, LoraLoader): Shows default path like `checkpoints/model.safetensors`
- For unknown nodes: User enters path immediately
- Confirmation prompt: `[Y] Continue  [m] Change path  [b] Back to menu`
- Path entry allows any subdirectory (e.g., `loras/custom/`, `checkpoints/SD15/`)
- After path change, returns to same confirmation prompt (can adjust multiple times)
- Downloads to global models directory, indexes automatically, resolves to manifest

**Design notes:**
- All models must be in global models directory (enforced constraint)
- Auto-search tries workflow filename first (handles most cases)
- Refinement loop handles renamed files (user knows better than system)
- Download URL completes the resolution flow (no deadlocks)
- Progressive writes ensure Ctrl+C safety
- Shows top 9 results only (no pagination - forces better search queries)

**End User Import Context:**

Options vary based on whether download URL is available in manifest:

**With download URL (developer provided source):**
1. Download from URL
2. Search your index (for substitution)
3. Skip

**Without download URL (developer didn't provide source):**
1. Search your index
2. Skip

### Progressive Writes

Each resolution is **saved immediately** to pyproject.toml:
- Enables Ctrl+C safety (partial progress preserved)
- Next run reuses previous resolutions (no re-prompting)
- Skipped models can be resolved later

### Auto-Resolution Logic

**Skip prompts when:**
1. Exact hash match found (previously resolved)
2. Single filename match in expected category directory
3. Model was resolved in previous commit (reuse mapping)

**Prompt when:**
1. Multiple files with same name
2. File not found in index
3. Ambiguous category (e.g., checkpoint in loras/ folder)

## End User Flow: Workflow Import

### Scenario

User imports a workflow bundle with 10 model references:
- 6 models resolved in manifest (have hashes)
- 2 models marked optional (no hashes)
- User's local index has 3 of the 6 resolved models

### Command: `comfydock import anime_workflow.tar.gz`

```bash
$ comfydock import anime_workflow.tar.gz --env imported

Importing bundle: anime_workflow.tar.gz
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Extracting bundle...
✓ Workflows: 1
✓ Models in manifest: 6 resolved, 2 optional
✓ Custom nodes: 3

Checking local models...
✓ 3 models found locally (by hash)
⚠ 3 models need resolution

Model Resolution
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. realistic_vision_v5.safetensors (checkpoint, 4.2 GB)
   Developer used: checkpoints/realistic_vision_v5.safetensors
   Not found locally

   You have 12 compatible checkpoints:
   [1] Use your: dreamshaper_8.safetensors (4.1 GB)
   [2] Use your: sd15_base.safetensors (4.0 GB)
   [3] Download original (4.2 GB)
   [4] Skip

   Choice [1-4]: 1
   → Using your model: dreamshaper_8.safetensors ✓

2. trained_controlnet.safetensors (controlnet, 1.4 GB)
   [REQUIRED] Workflow needs this exact model
   Not found locally
   Download URL available: https://civitai.com/api/download/models/123456

   [1] Download from URL (1.4 GB)
   [2] Search your index
   [3] Skip (workflow will break)

   Choice [1-3]: 1
   → Downloading... ████████████ 100% (1.4 GB)
   → Saved to: models/controlnet/trained_controlnet.safetensors ✓
   → Indexed with hash: xyz789... ✓

3. anime_style_lora.safetensors (lora, optional)
   Developer marked as optional
   No download URL available

   🔍 Searching for 'anime_style_lora'...
   Found 5 matches:

   [1] anime_style_lora_v2.safetensors (144 MB)
   [2] anime_general.safetensors (156 MB)
   [3] anime_character_lora.safetensors (122 MB)

   [1-3] Select  [r] Refine  [s] Skip
   Choice [1]/r/s: 1
   → Using your model ✓

Updating workflow paths...
✓ Remapped 3 model references to local paths
✓ Updated workflow JSON

Installing custom nodes...
✓ comfyui-impact-pack (from cache)
✓ comfyui-animatediff (downloading)

Setup Complete
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✓ Environment ready: imported
✓ 9 models resolved (1 substituted, 1 skipped)
✓ All required nodes installed

Run with: comfydock run -e imported
```

### Category-Based Substitution

**Always allow substitution:**
- `checkpoints` → Any checkpoint works
- `vae` → Any VAE works

**Warn before substitution:**
- `loras` → "Results may differ from original"
- `upscale_models` → "Different model may affect quality"

**Require exact match:**
- Models marked `criticality = "required"`
- Models with no category match (fallback to exact)

### Workflow Path Rewriting

After resolution, workflow JSON is updated:
```json
// Before (developer's paths)
"inputs": {
    "ckpt_name": "checkpoints/realistic_vision_v5.safetensors"
}

// After (user's paths)
"inputs": {
    "ckpt_name": "checkpoints/dreamshaper_8.safetensors"
}
```

This ensures ComfyUI loads the correct local models.

## Status Command

### `comfydock status`

Shows pending resolution issues:

```bash
$ comfydock status

Environment: dev
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Workflows:
  ⚠ my_workflow (3 unresolved models)
  ✓ simple_workflow

Models:
  ✓ 15 resolved
  ⚠ 3 unresolved
  ○ 2 optional

Custom Nodes:
  ✓ 5 installed

Next steps:
  • Run 'comfydock workflow resolve my_workflow' to fix issues
  • Run 'comfydock commit' when ready
```

## Implementation Notes

### Data Layer (models/manifest.py)

```python
@dataclass
class ManifestWorkflowModel:
    """Model entry in workflow manifest."""
    filename: str
    category: str
    criticality: str  # "required" | "flexible" | "optional"
    status: str  # "resolved" | "unresolved"
    nodes: list[WorkflowNodeWidgetRef]

    # Optional (only if resolved)
    hash: str | None = None
    size: int | None = None
    relative_path: str | None = None
    sources: list[str] = field(default_factory=list)
```

### Manager Layer (managers/workflow_manager.py)

```python
def resolve_workflow_models(
    self,
    workflow_name: str,
    auto_resolve: bool = True
) -> ResolutionResult:
    """Interactive model resolution with progressive writes."""
    # 1. Parse workflow JSON → extract model refs
    # 2. For each ref:
    #    - Check if previously resolved (reuse)
    #    - Try auto-resolve (single match)
    #    - Prompt user if ambiguous/missing
    #    - Write immediately to manifest
    # 3. Return summary
```

### Auto-Resolution Strategy

```python
def auto_resolve_model(
    ref: WorkflowNodeWidgetRef,
    index: ModelIndex
) -> ModelWithLocation | None:
    """Attempt automatic resolution without prompts."""

    # 1. Check cache (previously resolved)
    if cached := get_cached_resolution(ref):
        return cached

    # 2. Exact filename + category match
    category = get_category_for_node_type(ref.node_type)
    matches = index.find_in_category(ref.widget_value, category)

    if len(matches) == 1:
        return matches[0]  # Unambiguous

    # 3. Multiple matches or none → needs user input
    return None
```

## Edge Cases

### Model Deleted After Resolution
- Hash mapping remains in manifest
- Next analysis detects missing file
- User must re-index or re-resolve

### Ambiguous Hash Collisions
- Multiple files with same quick hash
- Prompt user to select correct file
- Store full hash for verification

## Summary

**Developer Experience:**
- Auto-resolve when possible
- Interactive prompts for ambiguity
- Mark missing models as optional
- Progressive writes (Ctrl+C safe)

**End User Experience:**
- Category-aware substitution
- Download only required models
- Skip optional models
- Workflow paths auto-updated

**Key Innovation:**
- Single unified model list (resolved + unresolved)
- Criticality orthogonal to resolution status
- No artificial split between "required" and "optional" tables
