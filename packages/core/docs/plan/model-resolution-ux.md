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

   [1] Search index
   [2] Mark as optional
   [3] Skip (fix later)

   Choice [1-3]: 2
   ℹ  Marked as optional - end users can skip
   → Saved to manifest ✓

3. trained_controlnet.safetensors (controlnet)
   Not found in model index
   Used by node #12 (ControlNetLoader)

   [1] Search index
   [2] Mark as optional
   [3] Skip (fix later)

   Choice [1-3]: 1

   Search for model (filename): controlnet

   Found 8 matches (showing 5):
   [1] trained_controlnet.safetensors (1.4 GB) - controlnet/trained_controlnet.safetensors
   [2] controlnet_anime.safetensors (1.3 GB) - controlnet/controlnet_anime.safetensors
   [3] control_v11p_sd15_canny.pth (1.4 GB) - controlnet/control_v11p_sd15_canny.pth
   [4] control_v11f1e_sd15_tile.pth (1.4 GB) - controlnet/control_v11f1e_sd15_tile.pth
   [5] control_sd15_depth.pth (1.4 GB) - controlnet/control_sd15_depth.pth

   (n)ext page, (r)efine search, or select [1-5]: 1
   → Got Hash: xyz789...
   → Saved to manifest ✓

4. detail_tweaker.safetensors (lora)
   Not found in model index
   Used by node #8 (LoraLoader)

   [1] Search index
   [2] Mark as optional
   [3] Skip (fix later)

   Choice [1-3]: 3
   ℹ  Skipped - workflow remains unresolved

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

### Resolution Options by Context

**MVP Options (Developer resolving unresolved models):**
1. **Search index**: Interactive index filename search with paginated results
   - User enters search term
   - System shows top 5 matches at a time
   - Options: (n)ext page, (r)efine search, select [1-5]
   - On selection: save to manifest
2. **Mark as optional**: Mark model as optional in manifest
   - No hash stored
   - End users can skip during import
3. **Skip**: Leave unresolved for later
   - Workflow remains in unresolved state
   - Can run resolve again to fix

**Post-MVP Options (will be added later):**
- **Download via URL**: User provides download URL
  - Downloads to correct category directory in global models path
  - Indexes with hash computation + provided source URL
  - Saves to manifest as resolved
  - Use case: Developer has download link but file not local yet

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

   [1] Search your index
   [2] Skip

   Choice [1-2]: 1

   Search for model (filename): anime

   Found 15 matches (showing 5):
   [1] anime_style_lora_v2.safetensors (144 MB) - loras/anime_style_lora_v2.safetensors
   [2] anime_general.safetensors (156 MB) - loras/anime_general.safetensors
   [3] anime_character_lora.safetensors (122 MB) - loras/anime_character_lora.safetensors
   [4] realistic_anime_mix.safetensors (144 MB) - loras/realistic_anime_mix.safetensors
   [5] anime_background_lora.safetensors (98 MB) - loras/anime_background_lora.safetensors

   (n)ext page, (r)efine search, (b)ack to menu, or select [1-5]: 1
   → Using your model: anime_style_lora_v2.safetensors ✓
   → Updated workflow mapping ✓

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
