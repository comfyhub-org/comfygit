# Workflow Tracking

> Automatic workflow discovery, sync tracking, and version control integration.

## Overview

ComfyGit automatically tracks all workflows in your environment:

- **Zero configuration** - Save workflows in ComfyUI, they're tracked automatically
- **Sync states** - New, modified, synced, or deleted
- **Git integration** - Workflows committed to `.cec` directory
- **Change detection** - BLAKE3 content hashing for precise tracking
- **Subgraph support** - Full ComfyUI v1.24.3+ compatibility

No manual registration needed - just save workflows in ComfyUI and ComfyGit handles the rest.

## Workflow discovery

### Where workflows live

**ComfyUI directory:**

```
~/comfygit/environments/my-env/ComfyUI/user/default/workflows/
├── portrait-generation.json
├── anime-style.json
└── sdxl-upscale.json
```

This is where ComfyUI saves workflows when you click "Save" in the frontend.

**ComfyGit tracking directory:**

```
~/comfygit/environments/my-env/.cec/workflows/
├── portrait-generation.json
├── anime-style.json
└── sdxl-upscale.json
```

Committed copies stored in `.cec` for version control.

### Automatic detection

ComfyGit discovers workflows in real-time:

```bash
# Save a new workflow in ComfyUI, then:
cg workflow list
```

Output shows immediately:

```
Workflows in 'my-env':

🆕 New (not committed yet):
  ➕ my-new-workflow
```

No explicit "add workflow" command needed.

## Workflow sync states

ComfyGit tracks four sync states:

### New

**Workflow exists in ComfyUI but not in `.cec`**

```bash
cg workflow list
```

```
🆕 New (not committed yet):
  ➕ my-new-workflow
```

**What it means:**

- You saved this workflow in ComfyUI
- Not yet committed to version control
- Will be copied to `.cec` on next `cg commit`

**Next step:**

```bash
cg commit -m "Add my-new-workflow"
```

### Modified

**Workflow exists in both places but content differs**

```bash
cg workflow list
```

```
⚠ Modified (changed since last commit):
  📝 portrait-generation
```

**What it means:**

- You edited the workflow in ComfyUI
- Committed copy in `.cec` is out of date
- Content hash differs (BLAKE3)

**Common causes:**

- Changed node connections
- Modified widget values
- Added/removed nodes
- Adjusted model paths

**Next step:**

```bash
cg commit -m "Update portrait-generation workflow"
```

### Synced

**Workflow identical in both places**

```bash
cg workflow list
```

```
✓ Synced (up to date):
  📋 portrait-generation
  📋 anime-style
```

**What it means:**

- ComfyUI version matches `.cec` version
- No uncommitted changes
- Safe to share or pull

**No action needed** - Everything in sync.

### Deleted

**Workflow exists in `.cec` but not in ComfyUI**

```bash
cg workflow list
```

```
🗑 Deleted (removed from ComfyUI):
  ➖ old-workflow
```

**What it means:**

- You deleted the workflow file from ComfyUI
- Committed copy still in `.cec`
- Will be removed from `.cec` on next commit

**Next step:**

```bash
cg commit -m "Remove old-workflow"
```

## Workflow metadata

Workflow metadata stored in `.cec/pyproject.toml`:

```toml
[tool.comfygit.workflows.portrait-generation]
nodes = [
    "rgthree-comfy",
    "comfyui_controlnet_aux"
]

[tool.comfygit.workflows.portrait-generation.custom_node_map]
CR_AspectRatioSD15 = "comfyui_controlnet_aux"

[[tool.comfygit.workflows.portrait-generation.models]]
hash = "f6e5d4c3b2a1..."
filename = "sd_xl_base_1.0.safetensors"
category = "checkpoints"
criticality = "flexible"
status = "resolved"
nodes = [
    {node_id = "3", node_type = "CheckpointLoaderSimple", widget_index = 0, widget_value = "sd_xl_base_1.0.safetensors"}
]
```

**Sections:**

- `nodes` - Required node packages (resolved from workflow)
- `custom_node_map` - User-confirmed node type → package mappings
- `models` - Model references with resolution details

**Updated automatically during:**

- `cg workflow resolve` - Interactive or auto resolution
- `cg commit` - Auto-resolution before commit
- `cg workflow model importance` - Criticality updates

## Workflow structure

ComfyGit parses standard ComfyUI workflow JSON:

### Basic structure

```json
{
  "id": "workflow-id",
  "revision": 5,
  "version": 0.4,
  "nodes": [
    {
      "id": 3,
      "type": "CheckpointLoaderSimple",
      "widgets_values": ["sd_xl_base_1.0.safetensors"]
    },
    {
      "id": 5,
      "type": "KSampler",
      "widgets_values": [123456, "fixed", 20, 8.0]
    }
  ],
  "links": [[1, 3, 0, 5, 0, "MODEL"]],
  "groups": [],
  "config": {},
  "extra": {}
}
```

**What ComfyGit extracts:**

- **Node types** - `CheckpointLoaderSimple`, `KSampler`, etc.
- **Model references** - Widget values containing model filenames
- **Node connections** - Links between nodes (preserved but not analyzed)

### Subgraph structure (ComfyUI v1.24.3+)

Workflows can contain reusable subgraphs:

```json
{
  "nodes": [
    {
      "id": 10,
      "type": "0a58ac1f-cb15-4e01-aab3-26292addb965",
      "outputs": [{"name": "IMAGE", "type": "IMAGE"}]
    }
  ],
  "definitions": {
    "subgraphs": [
      {
        "id": "0a58ac1f-cb15-4e01-aab3-26292addb965",
        "name": "Text2Img",
        "nodes": [
          {"id": 3, "type": "KSampler"},
          {"id": 10, "type": "CheckpointLoaderSimple"}
        ]
      }
    ]
  }
}
```

**How ComfyGit handles subgraphs:**

1. **Flattening** - Extracts all nodes from subgraph definitions
2. **Scoped IDs** - Preserves node identity (e.g., `uuid:3`)
3. **UUID filtering** - Removes subgraph reference nodes (they're placeholders)
4. **Lossless serialization** - Preserves all 14 subgraph fields
5. **Round-trip safety** - Rebuilds exact original structure on save

**What you need to know:**

- ✅ Subgraphs fully supported since ComfyGit v1.0.7
- ✅ Node/model resolution works inside subgraphs
- ✅ Model paths updated correctly in subgraph nodes
- ✅ No special commands needed - just works

## Listing workflows

### Basic list

```bash
cg workflow list
```

Shows all workflows grouped by sync state:

```
Workflows in 'my-env':

✓ Synced (up to date):
  📋 portrait-generation
  📋 anime-style

⚠ Modified (changed since last commit):
  📝 sdxl-upscale

🆕 New (not committed yet):
  ➕ experimental-flow

Run 'cg commit' to save current state
```

### Status integration

Workflows appear in `cg status` with resolution details:

```bash
cg status
```

```
Environment: my-env

📋 Workflows:
  ⚠️  portrait-generation (synced)
      2 unresolved nodes
      1 missing model
      → Run: cg workflow resolve portrait-generation

  ✓ anime-style (modified)
      All dependencies resolved

  🆕 experimental-flow (new)
      Not yet analyzed
      → Commit to analyze dependencies
```

## Workflow commit flow

### Standard commit

Committing automatically handles workflow updates:

```bash
cg commit -m "Update workflows"
```

**What happens:**

1. **Copy workflows** - ComfyUI → `.cec` directory
2. **Auto-resolve all** - Analyze and resolve dependencies
3. **Update metadata** - Write resolutions to `pyproject.toml`
4. **Path sync** - Update model paths in workflow JSON
5. **Cleanup deleted** - Remove deleted workflows from pyproject
6. **Cleanup orphans** - Remove unused models from global table
7. **Git commit** - Commit `.cec` directory changes

**Files committed:**

```
.cec/workflows/my-workflow.json         # Workflow JSON
.cec/pyproject.toml                      # Metadata + resolutions
.cec/comfyui.json                        # ComfyUI version
.cec/environment.json                    # Environment metadata
```

### Blocked commits

Commit blocks if workflows have unresolved issues:

```bash
cg commit
```

```
✗ Cannot commit with unresolved issues

Workflow 'portrait-generation':
  • 2 unresolved nodes: CR_AspectRatioSD15, CustomUpscaler
  • 1 missing model: anime-style-xl.safetensors

Fix with: cg workflow resolve portrait-generation

Or force commit: cg commit --allow-issues
```

**Why blocking?**

Unresolved workflows won't work on other machines:

- Missing nodes → workflow fails to load
- Missing models → generation fails
- No sources → can't download models

**Forcing commit (not recommended):**

```bash
cg commit --allow-issues -m "WIP workflow"
```

Use only for work-in-progress or experimental workflows.

### Workflow-only commits

No other changes? Commit is optimized:

```bash
# Only workflows modified
cg commit -m "Add new workflow"
```

Skips unnecessary git operations, only commits workflow changes.

## Workflow change detection

ComfyGit uses content hashing to detect changes:

### Normalization

Before hashing, workflows are normalized:

**Removed (volatile fields):**

- `extra.ds` - UI pan/zoom state
- `frontend_version` - ComfyUI frontend version
- `revision` - Auto-increment counter
- Random seeds when `randomize: true`

**Why normalize?**

Prevents false positives:

```json
// These are considered identical:
{"nodes": [...], "extra": {"ds": {"offset": [100, 200]}}}
{"nodes": [...], "extra": {"ds": {"offset": [150, 250]}}}
```

Panning/zooming doesn't create "modified" state.

### BLAKE3 hashing

**Fast cryptographic hash:**

- 10-50x faster than SHA256
- Detects even single character changes
- Prevents accidental overwrites

**Example:**

```bash
# Modify workflow in ComfyUI (change single widget value)
cg workflow list
```

Immediately shows:

```
⚠ Modified (changed since last commit):
  📝 my-workflow
```

## Workflow organization

### Naming conventions

ComfyUI saves workflows with the name you provide:

```
Save workflow as: portrait-generation
→ Creates: portrait-generation.json
```

**Best practices:**

- Use kebab-case: `anime-style-xl`
- Be descriptive: `sdxl-portrait-upscale`
- Avoid spaces: Use dashes instead
- Lowercase preferred: `my-workflow` not `My-Workflow`

**Why it matters:**

- CLI commands use workflow names: `cg workflow resolve my-workflow`
- Names appear in `pyproject.toml` keys
- Git filenames should be portable

### Workflow subdirectories

ComfyUI doesn't support subdirectories in workflows folder:

❌ **Not supported:**

```
workflows/
├── portraits/
│   └── my-workflow.json
└── anime/
    └── another-workflow.json
```

✅ **Use naming instead:**

```
workflows/
├── portrait-my-workflow.json
├── portrait-upscale.json
├── anime-style-v1.json
└── anime-style-v2.json
```

ComfyGit tracks all `.json` files in workflows directory (flat structure only).

## Workflow lifecycle

### Creating a workflow

1. **Design in ComfyUI** - Build your workflow
2. **Save** - Click "Save" in ComfyUI, provide name
3. **Check status** - `cg workflow list` (shows as "new")
4. **Resolve** - `cg workflow resolve my-workflow` (optional, commit does this)
5. **Commit** - `cg commit -m "Add my-workflow"`

### Updating a workflow

1. **Edit in ComfyUI** - Modify nodes, connections, values
2. **Save** - Save in ComfyUI (overwrites file)
3. **Check changes** - `cg workflow list` (shows as "modified")
4. **Re-resolve if needed** - `cg workflow resolve my-workflow`
5. **Commit** - `cg commit -m "Update my-workflow"`

### Sharing a workflow

1. **Ensure resolved** - `cg workflow resolve my-workflow`
2. **Set model importance** - `cg workflow model importance my-workflow`
3. **Add model sources** - `cg model add-source <model>` for each model
4. **Commit** - `cg commit -m "Prepare my-workflow for sharing"`
5. **Push** - `cg push`

Or export:

```bash
cg export my-env-export.tar.gz
```

### Deleting a workflow

1. **Delete file** - Remove from ComfyUI workflows folder
2. **Check status** - `cg workflow list` (shows as "deleted")
3. **Commit** - `cg commit -m "Remove old-workflow"`

Metadata automatically cleaned up from `pyproject.toml`.

## Workflow caching

ComfyGit caches workflow analysis for performance:

### Cache structure

**Location:** `~/comfygit/cache/workflows.db` (SQLite)

**Cached data:**

- Workflow dependencies (nodes + model references)
- Resolution results (node packages + model matches)
- Analysis timestamps

**Cache keys:**

- Environment name
- Workflow name
- Content hash (BLAKE3)
- Resolution context hash

### Cache invalidation

**Automatic invalidation:**

- Workflow content changes (hash differs)
- Pyproject modified (if workflow-relevant sections change)
- Model index updated (if workflow's models affected)
- ComfyGit version changes

**Manual invalidation:**

```bash
# Force cache miss by touching workflow
touch ~/comfygit/environments/my-env/ComfyUI/user/default/workflows/my-workflow.json
```

Or delete cache entirely:

```bash
rm -rf ~/comfygit/cache/workflows.db
```

### Cache benefits

**Without cache:**

```bash
time cg workflow resolve my-workflow
# → 2.5 seconds
```

**With cache (hit):**

```bash
time cg workflow resolve my-workflow
# → 0.05 seconds (50x faster)
```

Critical for:

- Large workflows (100+ nodes)
- Frequent commits
- Status checks

## Workflow-to-environment binding

Workflows are environment-specific:

```
~/comfygit/environments/
├── env-a/
│   ├── ComfyUI/user/default/workflows/
│   │   └── workflow-a.json
│   └── .cec/
│       ├── workflows/workflow-a.json
│       └── pyproject.toml (resolutions for env-a)
└── env-b/
    ├── ComfyUI/user/default/workflows/
    │   └── workflow-b.json
    └── .cec/
        ├── workflows/workflow-b.json
        └── pyproject.toml (resolutions for env-b)
```

**Why separate?**

Different environments may:

- Use different model paths
- Have different nodes installed
- Target different ComfyUI versions
- Have different model collections

**Sharing workflows across environments:**

Copy workflow JSON manually or use export/import:

```bash
# Export from env-a
cg -e env-a export env-a-export.tar.gz

# Import to env-b
cg import env-a-export.tar.gz --name env-b-copy
```

## Best practices

!!! success "Recommended"
    - **Commit frequently** - Don't accumulate many workflow changes
    - **Descriptive names** - Use clear, specific workflow names
    - **Resolve before commit** - Catch dependency issues early
    - **Test after load** - Open workflow in ComfyUI to verify model paths
    - **Track work-in-progress** - Even experimental workflows benefit from commits

!!! warning "Avoid"
    - **Manual .cec edits** - Let ComfyGit manage `.cec/workflows/`
    - **Spaces in names** - Use dashes instead
    - **Committing broken workflows** - Resolve dependencies first
    - **Ignoring "modified" state** - Commit or discard changes explicitly
    - **Deleting .cec directory** - This is your version control!

## Troubleshooting

### Workflow shows as modified but I haven't changed it

**Problem:** Workflow marked modified after opening in ComfyUI

**Possible causes:**

1. **Model path changed** - ComfyUI updated paths when loading
2. **Revision incremented** - ComfyUI auto-increments revision on save
3. **Extra fields added** - ComfyUI added frontend metadata

**Solution 1: Commit the changes**

```bash
cg commit -m "ComfyUI metadata updates"
```

Normalization means most metadata changes won't trigger "modified" state, but some might.

**Solution 2: Discard changes**

```bash
# Copy .cec version back to ComfyUI
cp .cec/workflows/my-workflow.json ComfyUI/user/default/workflows/my-workflow.json
```

### New workflow not detected

**Problem:** Saved workflow in ComfyUI but `cg workflow list` doesn't show it

**Check location:**

```bash
ls ~/comfygit/environments/my-env/ComfyUI/user/default/workflows/
```

Workflow must be in this exact directory.

**Check filename:**

Must have `.json` extension.

**Solution:** Move file to correct location:

```bash
mv ~/Downloads/my-workflow.json ~/comfygit/environments/my-env/ComfyUI/user/default/workflows/
```

### Deleted workflow still in .cec

**Problem:** Deleted workflow from ComfyUI but still in `.cec/workflows/`

**Expected behavior:** Shows as "deleted" in `cg workflow list`

**Solution:** Commit to remove:

```bash
cg commit -m "Remove deleted workflow"
```

ComfyGit cleans up `.cec/workflows/` and `pyproject.toml` entries.

### Workflow won't commit due to unresolved issues

**Problem:** `cg commit` blocked by workflow dependency issues

**Solution 1: Resolve dependencies**

```bash
cg workflow resolve my-workflow
```

Interactive mode helps fix issues.

**Solution 2: Mark nodes/models optional**

During resolution, choose `[o]` optional for non-essential dependencies.

**Solution 3: Force commit (use sparingly)**

```bash
cg commit --allow-issues -m "WIP: experimental workflow"
```

## Next steps

- [Workflow resolution](workflow-resolution.md) - Resolve workflow dependencies
- [Model importance](workflow-model-importance.md) - Mark models as required/flexible/optional
- [Version control](../environments/version-control.md) - Git integration for environments
