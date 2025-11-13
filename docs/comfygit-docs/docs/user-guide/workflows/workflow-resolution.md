# Workflow Resolution

> Automatically resolve workflow dependencies: custom nodes and models from workflow JSON.

## Overview

ComfyGit analyzes workflow JSON files to determine what custom nodes and models are needed, then resolves them automatically through:

- **Node resolution** - Maps node types to installable packages
- **Model resolution** - Matches model references to your indexed models
- **Interactive fixing** - Prompts for ambiguous or missing dependencies
- **Automatic downloads** - Downloads models when sources are available

Resolution happens in two phases:

1. **Analysis** - Parse workflow JSON, extract dependencies
2. **Resolution** - Match nodes to packages, models to files

Both phases are cached for performance.

## Automatic resolution

Workflows are automatically resolved during `cg commit`:

```bash
cg commit -m "Add new workflow"
```

**What happens:**

1. **Workflow detection** - Finds new/modified workflows
2. **Dependency extraction** - Parses nodes and model references
3. **Resolution** - Matches nodes and models automatically
4. **Path sync** - Updates model paths in workflow JSON
5. **Commit** - Saves resolved state to `.cec/pyproject.toml`

If resolution encounters ambiguous or missing dependencies, commit is blocked:

```
✗ Cannot commit with unresolved issues

Workflow 'portrait-gen' has unresolved dependencies:
  • 2 ambiguous nodes
  • 1 missing model

Run: cg workflow resolve portrait-gen
```

## Manual resolution

Resolve a specific workflow manually:

```bash
cg workflow resolve my-workflow
```

**Interactive mode (default):**

```
🔧 Resolving dependencies...

⚠️  Node not found in registry: CR_AspectRatioSD15
🔍 Searching for: CR_AspectRatioSD15

Results:
  1. comfyui_controlnet_aux (rank #12)
     Contains: 12 nodes including aspect ratio tools

  2. rgthree-comfy (rank #3)
     Contains: 45 nodes including aspect ratio utilities

  [1] Select  [r] Refine search  [m] Manual ID  [o] Optional  [s] Skip
Choice [1]/r/m/o/s: 1

✓ Resolved CR_AspectRatioSD15 → comfyui_controlnet_aux

⚠️  Model not found: anime-style-xl.safetensors
🔍 Searching model index...

No exact match found.

Similar models:
  1. anime-xl-v2.safetensors (confidence: 0.89)
  2. anime-style-lora.safetensors (confidence: 0.76)

  [1] Select  [d] Download URL  [o] Optional  [s] Skip
Choice [1]/d/o/s: d

Enter download URL: https://civitai.com/api/download/models/123456
Enter target path [loras/anime-style-xl.safetensors]:

✓ Download intent saved

📦 Found 1 missing node pack:
  • comfyui_controlnet_aux

Install missing nodes? (Y/n): y

⬇️  Installing nodes...
✓ Installed comfyui_controlnet_aux

📥 Downloading models...
████████████████████████████████████ 2.15 GB / 2.15 GB [100%]

✓ Resolution complete
  • 1 node resolved and installed
  • 1 model downloaded
```

### Auto mode

Skip all prompts and auto-select best matches:

```bash
cg workflow resolve my-workflow --auto
```

Uses scoring system to pick best candidates:

- **Exact matches** - Selects automatically
- **Fuzzy matches** - Picks highest confidence (>0.8)
- **No match** - Leaves unresolved
- **Ambiguous** - Picks highest-ranked package from registry

Good for:

- Known workflows from trusted sources
- Batch processing multiple workflows
- CI/CD environments

## Resolution phases

### Phase 1: Node resolution

Analyzes each node in the workflow:

**Builtin nodes:**

```json
{"id": "3", "type": "KSampler", "widgets_values": [123, "fixed", 20, 8]}
```

Recognized as ComfyUI builtin → No package needed

**Custom nodes:**

```json
{"id": "5", "type": "CR_AspectRatioSD15", "widgets_values": ["1:1"]}
```

Resolution steps:

1. **Check pyproject** - Previous resolution or manual mapping?
2. **Check registry** - Exact node type match in ComfyUI registry
3. **Fuzzy search** - Embedding-based similarity search
4. **Interactive prompt** - Ask user if ambiguous

**Resolution states:**

- **Resolved** - Found package, added to `pyproject.toml`
- **Ambiguous** - Multiple candidates found
- **Unresolved** - Not found anywhere
- **Optional** - User marked as non-essential

### Phase 2: Model resolution

Extracts model references from node widgets:

**Builtin loaders (exact widget detection):**

```json
{"type": "CheckpointLoaderSimple", "widgets_values": ["sd_xl_base_1.0.safetensors"]}
```

Widget index 0 contains checkpoint path (from model config).

**Custom nodes (pattern matching):**

```json
{"type": "CustomLoraLoader", "widgets_values": ["some-lora.safetensors", 0.8]}
```

Scans all widgets for `.safetensors`, `.ckpt`, `.pt` extensions.

**Resolution strategies:**

1. **Exact hash match** - Model filename → BLAKE3 hash in index
2. **Filename search** - Case-insensitive filename lookup
3. **Previous resolution** - Check pyproject for prior download intent
4. **Fuzzy search** - Similarity matching with confidence scores
5. **Download intent** - User provides URL for future download
6. **Optional** - User marks as non-essential

**Resolution states:**

- **Resolved** - Found in model index
- **Download intent** - URL saved, will download on next resolve
- **Ambiguous** - Multiple models with same/similar filename
- **Unresolved** - Not found, no download URL
- **Optional** - User marked as non-essential

## Resolution control flags

### Install missing nodes

**Automatic installation:**

```bash
cg workflow resolve my-workflow --install
```

Skips prompt, automatically installs all resolved node packages.

**Skip installation:**

```bash
cg workflow resolve my-workflow --no-install
```

Only updates pyproject.toml, doesn't install anything. Use when:

- Checking what's needed before installing
- Running in CI without actual installs
- Preparing environment for later installation

**Interactive (default):**

```bash
cg workflow resolve my-workflow
```

Prompts after resolution:

```
📦 Found 3 missing node packs:
  • rgthree-comfy
  • comfyui_controlnet_aux
  • comfyui-impact-pack

Install missing nodes? (Y/n):
```

## Model path synchronization

ComfyGit updates workflow JSON to match resolved model paths.

**Before resolution:**

```json
{
  "type": "CheckpointLoaderSimple",
  "widgets_values": ["sd_xl_base_1.0.safetensors"]
}
```

**After resolution:**

```json
{
  "type": "CheckpointLoaderSimple",
  "widgets_values": ["sd_xl_base_1.0.safetensors"]
}
```

Path updated to match actual location in model index:

- `checkpoints/SD XL/sd_xl_base_1.0.safetensors` (indexed path)
- → `sd_xl_base_1.0.safetensors` (workflow path, base directory stripped)

**Why this matters:**

- ComfyUI frontend expects specific paths in JSON
- Custom nodes may use different base directories
- Path sync ensures workflows load correctly

**What gets synced:**

- ✅ **Builtin nodes only** - Safe, known widget structure
- ❌ **Custom nodes skipped** - Unknown widget layouts, preserved as-is

**When sync happens:**

- During `cg workflow resolve` (after all resolutions)
- During `cg commit` (auto-resolution)
- Batch update to avoid cache invalidation issues

## Subgraph support

ComfyGit fully supports ComfyUI subgraphs (v1.0.7+):

**What are subgraphs?**

Reusable workflow components introduced in ComfyUI v1.24.3. Group nodes into named subgraphs.

**How ComfyGit handles them:**

1. **Flattening** - Extracts nodes from subgraph definitions
2. **Scoped IDs** - Preserves node identity (`uuid:3` for subgraph nodes)
3. **Filtering** - Removes UUID reference nodes (subgraph placeholders)
4. **Lossless round-trip** - Preserves all 14 subgraph fields
5. **Reconstruction** - `to_json()` rebuilds original structure

**Example workflow with subgraph:**

```json
{
  "nodes": [
    {"id": 10, "type": "0a58ac1f-...", "outputs": [{"type": "IMAGE"}]}
  ],
  "definitions": {
    "subgraphs": [{
      "id": "0a58ac1f-...",
      "name": "Text2Img",
      "nodes": [
        {"id": 3, "type": "KSampler"},
        {"id": 10, "type": "CheckpointLoaderSimple"}
      ]
    }]
  }
}
```

**Resolution extracts:**

- `KSampler` (builtin, from subgraph)
- `CheckpointLoaderSimple` (builtin, from subgraph)
- Model reference from checkpoint loader

**Subgraph reference node filtered out:**

- `type: "0a58ac1f-..."` is a UUID, not a real node type

## Resolution caching

ComfyGit aggressively caches resolution for performance.

### Analysis cache

**Cached:** Workflow dependency parsing (nodes + model references)

**Invalidated when:**

- Workflow JSON content changes (BLAKE3 hash)
- ComfyUI version changes
- Normalized workflow differs (ignores pan/zoom, revision)

**Cache location:** SQLite database (`comfygit_cache/workflows.db`)

**Speed improvement:** 50-100x faster on cache hit

### Resolution cache

**Cached:** Node/model resolution results

**Context-aware invalidation:**

- ✅ **Workflow content changed** - Full invalidation
- ✅ **Pyproject modified** - Only if relevant sections changed
- ✅ **Model index changed** - Only if models in workflow affected
- ❌ **Unrelated pyproject changes** - Cache hit!
- ❌ **Unrelated model index changes** - Cache hit!

**Cache validation:**

- Workflow content hash (BLAKE3)
- Pyproject mtime (fast-reject if unchanged)
- Resolution context hash (only workflow-relevant data):
  - Custom node mappings for nodes in this workflow
  - Declared packages for nodes this workflow uses
  - Model entries from pyproject for this workflow
  - Model index subset (only models this workflow references)
  - ComfyGit version

**Manual cache invalidation:**

```bash
# Force re-resolve by modifying workflow
touch ~/comfygit/environments/my-env/ComfyUI/user/default/workflows/my-workflow.json
```

## Progressive writes

Resolution saves changes immediately during interactive mode.

**Why this matters:**

- Ctrl+C safe - Progress not lost
- Can resume after interruption
- No "all-or-nothing" resolution

**What gets written progressively:**

1. **Node resolutions** - Added to `[tool.comfygit.workflows.<name>.nodes]` immediately
2. **Custom node mappings** - Added to `[tool.comfygit.workflows.<name>.custom_node_map]` immediately
3. **Model resolutions** - Added to `[tool.comfygit.workflows.<name>.models]` immediately
4. **Download intents** - Saved with pending download URL
5. **Global model table** - Updated when models resolved

**Batch operations:**

- Model path updates in workflow JSON (all at end)
- Prevents cache invalidation mid-resolution

## Download intents

Models can be resolved with pending download URLs:

**During interactive resolution:**

```
⚠️  Model not found: new-model.safetensors
Enter download URL: https://civitai.com/api/download/models/123456
Enter target path [checkpoints/new-model.safetensors]:
```

**Saved to pyproject:**

```toml
[[tool.comfygit.workflows.my-workflow.models]]
filename = "new-model.safetensors"
category = "checkpoints"
criticality = "required"
status = "unresolved"
sources = ["https://civitai.com/api/download/models/123456"]
relative_path = "checkpoints/new-model.safetensors"
nodes = [{node_id = "5", node_type = "CheckpointLoaderSimple", widget_index = 0}]
```

**Next resolution:**

```bash
cg workflow resolve my-workflow
```

Detects download intent and downloads automatically:

```
📥 Downloading models...
████████████████████████████████████ 2.15 GB / 2.15 GB [100%]

✓ Downloaded new-model.safetensors
```

After download:

- Status changes to `resolved`
- Hash computed and added
- Sources moved to global model table
- Model indexed

## Viewing resolution status

### Quick check

```bash
cg workflow list
```

Shows sync state but not resolution details:

```
Workflows in 'my-env':

✓ Synced (up to date):
  📋 portrait-gen

⚠ Modified (changed since last commit):
  📝 anime-style

🆕 New (not committed yet):
  ➕ sdxl-upscale
```

### Detailed status

```bash
cg status
```

Shows workflows with resolution issues inline:

```
📋 Workflows:
  ⚠️  portrait-gen (synced)
      2 unresolved nodes
      1 missing model

  ✓ anime-style (modified)
      All dependencies resolved
```

### Full resolution report

```bash
cg workflow resolve my-workflow --auto
```

Even in `--auto` mode, shows what was resolved:

```
✓ Resolution complete
  • 3 nodes resolved
  • 2 models resolved (exact hash match)
  • 1 model with download intent
```

## Handling unresolved dependencies

### Unresolved nodes

**Option 1: Mark as optional**

If node isn't essential:

```
⚠️  Node not found: OptionalUpscaler
  [o] Mark as optional
Choice: o
```

Saved to pyproject:

```toml
[tool.comfygit.workflows.my-workflow.custom_node_map]
OptionalUpscaler = false  # false = optional
```

**Option 2: Manual package ID**

If you know the correct package:

```
⚠️  Node not found: MyCustomNode
  [m] Manual package ID
Choice: m
Enter package ID: https://github.com/user/ComfyUI-CustomNodes
```

**Option 3: Skip for now**

Leave unresolved, fix later:

```
  [s] Skip
Choice: s
```

Commit will be blocked until resolved or marked optional.

### Unresolved models

**Option 1: Provide download URL**

```
⚠️  Model not found: my-model.safetensors
  [d] Enter download URL
Choice: d
Enter URL: https://civitai.com/api/download/models/123456
```

Creates download intent - model will download on next resolve.

**Option 2: Mark as optional**

```
  [o] Mark as optional
Choice: o
```

Workflow can run without it.

**Option 3: Skip**

```
  [s] Skip
Choice: s
```

Blocks commit until resolved.

## Best practices

!!! success "Recommended"
    - **Resolve before commit** - Catch issues early
    - **Use --auto for trusted workflows** - Faster for known-good workflows
    - **Mark optional nodes/models** - Improves sharing compatibility
    - **Provide download URLs** - Helps team members get exact models
    - **Let commit auto-resolve** - Default workflow handles most cases

!!! warning "Avoid"
    - **Committing with --allow-issues** - Unresolved deps will break on other machines
    - **Manual pyproject edits** - Use commands for consistency
    - **Skipping model path sync** - Workflows may not load correctly
    - **Ignoring ambiguous warnings** - May resolve to wrong packages

## Troubleshooting

### Resolution fails with cache error

**Problem:** Workflow cache corrupted or stale

**Solution:** Delete and recreate cache:

```bash
rm -rf ~/comfygit/cache/workflows.db
cg workflow resolve my-workflow
```

Cache rebuilds automatically.

### Node resolved to wrong package

**Problem:** Auto-resolution picked incorrect match

**Solution:** Override with custom mapping:

Edit `.cec/pyproject.toml`:

```toml
[tool.comfygit.workflows.my-workflow.custom_node_map]
MyNodeType = "correct-package-id"
```

Or use manual resolution:

```bash
cg workflow resolve my-workflow
# Choose [m] manual when prompted for MyNodeType
```

### Model path not updating in workflow

**Problem:** Workflow JSON still has old path

**Solution:** Ensure resolution completes successfully:

1. Resolve workflow: `cg workflow resolve my-workflow`
2. Commit to save: `cg commit`

Path updates happen during resolution, only for builtin nodes.

### Download intent not executing

**Problem:** Model has download URL but doesn't download

**Solution:** Ensure status is "unresolved" with sources:

```bash
# Check pyproject.toml
cat .cec/pyproject.toml | grep -A 5 "my-model"
```

Should have:

```toml
status = "unresolved"
sources = ["https://..."]
```

If missing, re-resolve:

```bash
cg workflow resolve my-workflow
```

### Commit blocked with resolved deps

**Problem:** All deps resolved but commit still blocked

**Solution:** Check for path sync issues:

```bash
cg status
```

If shows path sync warning, resolve again:

```bash
cg workflow resolve my-workflow
```

## Next steps

- [Workflow tracking](workflow-tracking.md) - How workflows are discovered and managed
- [Model importance](workflow-model-importance.md) - Mark models as required/flexible/optional
- [Model index](../models/model-index.md) - Understanding the model database
