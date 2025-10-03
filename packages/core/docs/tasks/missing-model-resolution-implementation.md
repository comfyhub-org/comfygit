# Missing Model Resolution Implementation Plan (MVP)

**Status**: Ready to Implement
**Created**: 2025-10-02
**Updated**: 2025-10-02
**Priority**: High
**Scope**: MVP - Fuzzy search and workflow remapping only

---

## Executive Summary

**The Problem**: Users save workflows that reference models with incorrect paths. ComfyDock detects these as "missing" but provides no good way to fix them.

**The Solution**: Interactive fuzzy search against the user's existing model index, allowing them to quickly map missing references to models they already have.

**MVP Scope**:
1. ✅ **Fuzzy search local index** (primary flow - 80% of cases)
2. ✅ **Manual path selection** (from indexed models only)
3. ✅ **Fix manually in ComfyUI** (give user a chance to fix and re-run)
4. ❌ **Download from URL** (deferred - future feature)
5. ❌ **Mark as external** (deferred - future feature)

**Key Principles**:
1. Focus on remapping workflows to use models the user already has in their index
2. **Workflow JSON is NEVER modified** - only pyproject.toml mappings are created
3. Content-addressable design: models keyed by hash, workflows reference by original paths
4. Preserves shareability: workflows can be shared without exposing local paths

---

## User Scenarios (Why This Matters)

### **Scenario 1: Imported Workflow with Wrong Paths (Most Common)**

```bash
# User downloads workflow from CivitAI
# Workflow references: "models/SD/sd15-v1.safetensors"
# User has model at: "checkpoints/stable-diffusion-v1-5.safetensors"

❯ cfd status
📋 Workflows:
  ⚠️  imported_workflow (new)
      Missing model: models/SD/sd15-v1.safetensors

❯ cfd workflow resolve imported_workflow

⚠️  Model not found: models/SD/sd15-v1.safetensors
  in node #4 (CheckpointLoaderSimple)

🔍 Searching your model index...

Found 5 potential matches:
  1. checkpoints/stable-diffusion-v1-5.safetensors (4.27 GB)
  2. SD1.5/v1-5-pruned.ckpt (4.27 GB)
  3. models/sd15-ema.safetensors (4.27 GB)
  4. checkpoints/sd-v1-4.safetensors (4.27 GB)
  5. [Browse all 23 checkpoint models...]

  0. Other options

Choice [1]: 1

✓ Selected: checkpoints/stable-diffusion-v1-5.safetensors
✓ Mapping saved to pyproject.toml (workflow JSON preserved)
✓ Resolved!

❯ cfd status
📋 Workflows:
  🆕 imported_workflow (new, ready to commit)

💡 Next:
  Commit workflows: comfydock commit -m "Add imported workflow"
```

**This is the main use case we're solving.**

### **Scenario 2: Template Workflow Before Testing**

```bash
# User creates workflow in ComfyUI
# Adds checkpoint loader (defaults to some path)
# Saves before running/testing

❯ cfd status
📋 Workflows:
  ⚠️  my_template (new)
      Missing model: example.safetensors

# Same fuzzy search flow, user picks their preferred model
# Workflow updated, ready to commit
```

### **Scenario 3: Model Moved/Renamed Outside ComfyDock**

```bash
# User reorganized their models folder
# Workflow still references old path

# Fuzzy search finds model at new location
# Workflow updated automatically
```

---

## Design: Resolution Flow

### **Entry Point**

```
⚠️  Model not found: v1-5-pruned-emaonly-fp16.safetensors
  in node #4 (CheckpointLoaderSimple)

🔍 Searching your model index for checkpoint models...
```

System automatically:
1. Determines model category from node type ("CheckpointLoaderSimple" → checkpoint)
2. Searches only that category in index
3. Fuzzy matches against missing filename
4. Scores results by similarity

### **Option 1: Fuzzy Search Results (Primary Flow)**

```
Found 5 potential matches:

  1. checkpoints/stable-diffusion-v1-5.safetensors (4.27 GB)
     Hash: abc123... | High confidence match

  2. SD1.5/v1-5-pruned.ckpt (4.27 GB)
     Hash: def456... | Good match

  3. models/sd15-ema-pruned.safetensors (4.27 GB)
     Hash: ghi789... | Possible match

  4. checkpoints/sd-v1-4.safetensors (4.27 GB)
     Hash: jkl012...

  5. [Browse all 23 checkpoint models...]

  0. Other options (manual path, fix in ComfyUI)

Choice [1]:
```

**If user selects 1-4:**
```
Choice: 1

✓ Selected: checkpoints/stable-diffusion-v1-5.safetensors
  Hash: abc123... | Size: 4.27 GB

Saving resolution to pyproject.toml...
✓ Added to model registry
✓ Created mapping: v1-5-pruned-emaonly-fp16.safetensors → hash abc123...
✓ Model resolved!

💡 Next:
  Commit workflows: comfydock commit -m "Add workflow"
```

**If user selects 5 (Browse all):**
```
Choice: 5

All checkpoint models (23 total):

Page 1/3:
  1. checkpoints/stable-diffusion-v1-5.safetensors (4.27 GB)
  2. checkpoints/sd-v2-1.safetensors (5.21 GB)
  3. checkpoints/deliberate-v2.safetensors (4.27 GB)
  4. checkpoints/dreamshaper-8.safetensors (4.27 GB)
  5. checkpoints/realisticVision-v4.safetensors (4.27 GB)
  6. SD1.5/v1-5-pruned.ckpt (4.27 GB)
  7. SD1.5/v1-5-inpainting.ckpt (4.27 GB)
  8. models/protogen-x3.4.safetensors (4.27 GB)
  9. models/sd15-ema.safetensors (4.27 GB)
  10. backup/sd-v1-5.safetensors (4.27 GB)

[N]ext, [P]rev, [F]ilter, or enter number:
```

User can page through, filter by search term, or select by number.

### **Option 2: Manual Path (From Index)**

```
Choice: 0

Other options:
  1. Enter model path (must be in index)
  2. Fix manually in ComfyUI (skip resolution for now)

Choice: 1
```

```
Enter model path or filename: stable-diffusion

Searching index for "stable-diffusion"...

Found 8 matches:
  1. checkpoints/stable-diffusion-v1-5.safetensors
  2. checkpoints/stable-diffusion-v2-1.safetensors
  3. SD1.5/stable-diffusion-inpainting.ckpt
  ...

Choice:
```

**If user enters full path:**
```
Enter model path: checkpoints/stable-diffusion-v1-5.safetensors

Checking index...
✓ Found in index (hash: abc123...)
✓ Workflow updated
✓ Resolved!
```

**If path not in index:**
```
Enter model path: ~/Downloads/my-model.safetensors

Checking index...
✗ Model not found in index

This model needs to be in your workspace models directory and indexed first.

To add this model:
  1. Move/copy to: .comfydock_workspace/models/checkpoints/
  2. Run: comfydock models index
  3. Try resolution again

⚠️  Model stays unresolved
```

**Key point**: We don't index arbitrary files during resolution. User must add to workspace first.

### **Option 3: Fix Manually in ComfyUI**

```
Choice: 2

You can fix this manually:
  1. Run: comfydock run
  2. Open workflow in ComfyUI
  3. Update model path to correct model
  4. Save workflow
  5. Run: comfydock workflow resolve <name> again

⚠️  Model stays unresolved (fix manually and retry)
```

This gives user control - maybe they want to use a different model, maybe they want to test something first.

### **Cancel (Ctrl+C)**

At any point:
```
^C
⚠️  Cancelled - model stays unresolved

You can resolve this later with:
  comfydock workflow resolve <workflow-name>
```

---

## Implementation Details

**Important**: ComfyDock has an existing `ModelConfig` class (`comfydock_core/configs/model_config.py`) that provides all node-to-directory mappings. Use it instead of creating new mappings. Key methods:
- `get_directories_for_node(node_type)` - Returns list of directories (may be multiple!)
- `is_model_loader_node(node_type)` - Checks if node loads models
- `reconstruct_model_path(node_type, widget_value)` - Builds possible paths

### **Phase 1: Fuzzy Search Engine**

**Core Method**:
```python
def find_similar_models(
    missing_ref: str,
    node_type: str,
    limit: int = 5
) -> list[ScoredMatch]:
    """
    Find models similar to missing reference.

    Args:
        missing_ref: "v1-5-pruned-emaonly-fp16.safetensors"
        node_type: "CheckpointLoaderSimple"
        limit: Number of results to return

    Returns:
        List of ScoredMatch objects sorted by confidence
    """
    # 1. Get directories this node type can load from (using ModelConfig)
    directories = self.model_config.get_directories_for_node(node_type)

    if not directories:
        # Unknown node type - default to checkpoints
        directories = ["checkpoints"]

    # 2. Get all models from ANY of those directories
    # (Some node types like CheckpointLoader can load from multiple dirs)
    candidates = []
    for directory in directories:
        candidates.extend(self.model_index.get_by_category(directory))

    # 3. Score each candidate
    scored = []
    missing_name = Path(missing_ref).stem.lower()

    for model in candidates:
        model_name = Path(model.filename).stem.lower()

        # Use Python's difflib for fuzzy matching
        from difflib import SequenceMatcher
        score = SequenceMatcher(None, missing_name, model_name).ratio()

        if score > 0.4:  # Minimum 40% similarity
            scored.append(ScoredMatch(
                model=model,
                score=score,
                confidence="high" if score > 0.8 else "good" if score > 0.6 else "possible"
            ))

    # 4. Sort by score descending
    scored.sort(key=lambda x: x.score, reverse=True)

    return scored[:limit]
```

**Using ModelConfig for Node Type Mapping**:

ComfyDock already has a `ModelConfig` class that provides node-to-directory mappings. Use it instead of hardcoding:

```python
# Available in comfydock_core/configs/model_config.py
from comfydock_core.configs.model_config import ModelConfig

self.model_config = ModelConfig.load()  # Load default config

# Methods to use:
directories = self.model_config.get_directories_for_node("CheckpointLoaderSimple")
# Returns: ["checkpoints"]

directories = self.model_config.get_directories_for_node("CheckpointLoader")
# Returns: ["checkpoints", "configs"]  # ← Multiple directories!

is_loader = self.model_config.is_model_loader_node("LoraLoader")
# Returns: True

possible_paths = self.model_config.reconstruct_model_path(
    node_type="CheckpointLoaderSimple",
    widget_value="sd15.safetensors"
)
# Returns: ["checkpoints/sd15.safetensors"]
```

**Key Insight**: Some node types (like `CheckpointLoader`) can load from **multiple directories**. The fuzzy search must check ALL directories for that node type.

**Dependencies**: None! Use Python's built-in `difflib.SequenceMatcher`.

### **Phase 2: Interactive Selection UI**

**Strategy Method**:
```python
class InteractiveModelStrategy(ModelResolutionStrategy):

    def handle_missing_model(
        self,
        reference: WorkflowNodeWidgetRef
    ) -> tuple[str, str] | None:
        """
        Interactive resolution for missing model.

        Returns:
            ("select", "checkpoints/model.safetensors") - User selected model
            ("skip", None) - User chose to skip/fix manually
            None - Cancelled (Ctrl+C)
        """
        print(f"\n⚠️  Model not found: {reference.widget_value}")
        print(f"  in node #{reference.node_id} ({reference.node_type})")

        # Search index
        print(f"\n🔍 Searching your model index for {node_category} models...")
        matches = self.workflow_manager.find_similar_models(
            missing_ref=reference.widget_value,
            node_type=reference.node_type,
            limit=5
        )

        if not matches:
            print("No similar models found in index")
            return self._show_other_options(reference)

        # Show matches
        print(f"\nFound {len(matches)} potential matches:\n")

        for i, match in enumerate(matches, 1):
            size_gb = match.model.file_size / (1024**3)
            print(f"  {i}. {match.model.relative_path} ({size_gb:.2f} GB)")
            print(f"     Hash: {match.model.hash[:8]}...")

        print(f"\n  5. [Browse all {total_in_category} {node_category} models...]")
        print(f"  0. Other options")

        while True:
            choice = input("\nChoice [1]: ").strip() or "1"

            if choice == "0":
                return self._show_other_options(reference)

            elif choice == "5":
                return self._browse_all_models(node_category)

            elif choice.isdigit() and 1 <= int(choice) <= len(matches):
                selected = matches[int(choice) - 1].model

                print(f"\n✓ Selected: {selected.relative_path}")
                print(f"  Hash: {selected.hash} | Size: {selected.file_size / (1024**3):.2f} GB")

                return ("select", selected.relative_path)

            else:
                print("Invalid choice")

    def _show_other_options(self, reference):
        """Show fallback options."""
        print("\nOther options:")
        print("  1. Enter model path manually")
        print("  2. Fix manually in ComfyUI (skip for now)")

        choice = input("\nChoice: ").strip()

        if choice == "1":
            return self._manual_path_entry()
        elif choice == "2":
            print("\nYou can fix this manually:")
            print("  1. Run: comfydock run")
            print("  2. Open workflow and update model path")
            print("  3. Save and run resolution again")
            return ("skip", None)

        return ("skip", None)

    def _manual_path_entry(self):
        """Handle manual path entry."""
        path = input("\nEnter model path or search term: ").strip()

        # Search index for this path/term
        results = self.model_index.search(path)

        if not results:
            print(f"\n✗ Not found in index")
            print("\nTo add this model:")
            print("  1. Move/copy to workspace models directory")
            print("  2. Run: comfydock models index")
            return ("skip", None)

        if len(results) == 1:
            print(f"✓ Found: {results[0].relative_path}")
            return ("select", results[0].relative_path)

        # Multiple matches - let user pick
        print(f"\nFound {len(results)} matches:")
        for i, model in enumerate(results, 1):
            print(f"  {i}. {model.relative_path}")

        choice = input("\nChoice: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(results):
            selected = results[int(choice) - 1]
            return ("select", selected.relative_path)

        return ("skip", None)
```

### **Phase 3: Core Integration**

**Update `fix_resolution()` in workflow_manager.py**:

```python
# Handle missing models using strategy
if model_strategy:
    for model_ref in resolution.models_unresolved:
        try:
            result = model_strategy.handle_missing_model(model_ref)

            if result is None:
                # Cancelled (Ctrl+C)
                remaining_models_unresolved.append(model_ref)

            elif result[0] == "select":
                # User selected a model from index
                selected_path = result[1]
                original_ref = model_ref.widget_value

                # Get model from index
                model_info = self.model_index.find_by_path(selected_path)

                # Add to model registry (if not already there)
                if not self.pyproject.models.has_model(model_info.hash):
                    self.pyproject.models.add_model(
                        model_hash=model_info.hash,
                        filename=model_info.filename,
                        file_size=model_info.file_size,
                        category="required",
                        relative_path=model_info.relative_path
                    )

                # Add workflow mapping (preserve original reference!)
                self._add_workflow_model_mapping(
                    workflow_name=workflow_name,
                    workflow_reference=original_ref,  # Original path from workflow
                    model_hash=model_info.hash,
                    node_id=model_ref.node_id,
                    widget_idx=model_ref.widget_idx
                )

                logger.info(f"Mapped: {original_ref} → hash {model_info.hash[:8]}...")
                # Don't add to remaining_unresolved - it's resolved!

            elif result[0] == "skip":
                # User chose to fix manually or skip
                remaining_models_unresolved.append(model_ref)
                logger.info(f"Skipped: {model_ref.widget_value}")

        except KeyboardInterrupt:
            print("\n⚠️  Cancelled - model stays unresolved")
            remaining_models_unresolved.append(model_ref)
            break  # Don't process more models

else:
    remaining_models_unresolved = list(resolution.models_unresolved)
```

### **Phase 4: CRITICAL - Workflow JSON is NOT Modified**

**Important Design Principle**: During local resolution, workflow JSON files are **NEVER** modified. Here's why:

**What Happens**:
- User selects model from index
- Mapping saved to `pyproject.toml`
- Workflow JSON remains **unchanged** with original reference

**Why This Matters**:
1. ✅ **Shareability**: Workflow can be shared as-is without local paths leaking
2. ✅ **Content-addressable**: Hash mappings are universal across users
3. ✅ **Import-ready**: Original references preserved for mapping on import
4. ✅ **Git-friendly**: No local-specific changes in workflow files

**When IS Workflow JSON Modified?**

**ONLY during import** (future feature):
```python
# Import flow (not MVP):
def import_workflow(bundle: Path):
    # 1. Read workflow JSON from bundle
    workflow_data = bundle.read_workflow("my_workflow.json")
    # Original ref: "models/SD/sd15-v1.safetensors"

    # 2. Get hash mapping from bundle
    mappings = bundle.get_model_mappings("my_workflow")
    # "models/SD/sd15-v1.safetensors" → hash 48835672...

    # 3. Check if we have this model
    model_hash = mappings["models/SD/sd15-v1.safetensors"]["hash"]
    local_model = model_index.find_by_hash(model_hash)
    # User has it at: "checkpoints/sd15.safetensors"

    # 4. Rewrite workflow JSON with local path
    workflow_data = replace_model_references(
        workflow_data,
        old_ref="models/SD/sd15-v1.safetensors",
        new_ref="checkpoints/sd15.safetensors"
    )

    # 5. Save to ComfyUI directory with local paths
    save_workflow(workflow_data, "my_workflow.json")
```

**Key Insight**:
- **Local resolution**: Maps workflow refs → hashes in pyproject.toml
- **Import**: Rewrites workflow JSON to use local paths

This is why the content-addressable design works!

---

## pyproject.toml Schema & Persistence ⭐ CRITICAL

### **Why This Matters**

Without persisting resolutions to pyproject.toml, the resolution is lost. Running `status` again shows the same missing models, creating an infinite loop.

### **Design: Content-Addressed Model Registry**

**Key Principle**: Models are stored in a universal registry keyed by **content hash** (universal identifier). Workflows reference models by their original paths, with mappings to the actual model hashes.

### **Schema Structure**

```toml
[tool.comfydock.models.required]
# Universal model registry - keyed by fast hash
48835672f5450d120620917e9d38ed7ff399310437274355c855760573deac85 = {
  filename = "v1-5-pruned-emaonly.safetensors",
  size = 4265146304,
  relative_path = "checkpoints/SD1.5/v1-5-pruned-emaonly.safetensors"
}
911dec51edd2b0256398271b748dd8b44dec09b1f91297f2f640813bc341a097 = {
  filename = "photon_v1.safetensors",
  size = 2132625918,
  relative_path = "checkpoints/SD1.5/photon_v1.safetensors"
}

[tool.comfydock.workflows.imported_workflow.models]
# Map workflow references → actual model hashes
"models/SD/sd15-v1.safetensors" = {  # What workflow originally asked for
  hash = "48835672f5450d120620917e9d38ed7ff399310437274355c855760573deac85",
  nodes = [
    {node_id = "4", widget_idx = 0},      # First node using this model
    {node_id = "7", widget_idx = 1}       # Second node using same model
  ]
}
"some-lora.safetensors" = {
  hash = "911dec51edd2b0256398271b748dd8b44dec09b1f91297f2f640813bc341a097",
  nodes = [
    {node_id = "5", widget_idx = 2}
  ]
}
```

### **Why This Design**

1. ✅ **Content-addressable**: Hash is universal ID across all users
2. ✅ **Import-friendly**: Recipients see "need hash X" and map to their files
3. ✅ **Preserves originals**: Workflow JSON stays unchanged
4. ✅ **Clear resolution**: "Workflow says X → hash Y → stored at Z"
5. ✅ **Multi-node support**: One model used by multiple nodes tracked cleanly
6. ✅ **Exportable**: Registry includes all metadata for bundle creation

### **Resolution Flow**

**Before resolution:**
```toml
[tool.comfydock.models.required]
# Empty or has other models

[tool.comfydock.workflows.imported_workflow.models]
# Empty - no resolutions yet
```

Workflow JSON: `"widgets_values": ["models/SD/sd15-v1.safetensors"]`
Status: ⚠️ Missing model

**User runs resolution:**
```bash
❯ cfd workflow resolve imported_workflow

⚠️  Model not found: models/SD/sd15-v1.safetensors
  in node #4 (CheckpointLoaderSimple)

🔍 Searching...

Found 5 matches:
  1. checkpoints/stable-diffusion-v1-5.safetensors (4.27 GB)

Choice: 1
```

**After resolution:**
```toml
[tool.comfydock.models.required]
# Model added to registry
48835672f5450d120620917e9d38ed7ff399310437274355c855760573deac85 = {
  filename = "stable-diffusion-v1-5.safetensors",
  size = 4470000000,
  relative_path = "checkpoints/stable-diffusion-v1-5.safetensors"
}

[tool.comfydock.workflows.imported_workflow.models]
# Mapping created
"models/SD/sd15-v1.safetensors" = {
  hash = "48835672f5450d120620917e9d38ed7ff399310437274355c855760573deac85",
  nodes = [{node_id = "4", widget_idx = 0}]
}
```

Workflow JSON: **UNCHANGED** - still `"models/SD/sd15-v1.safetensors"`
Status: ✓ Resolved (mapping found in pyproject)

### **Implementation**

**Update fix_resolution() to save to pyproject:**

```python
# In workflow_manager.py fix_resolution():
if result[0] == "select":
    selected_path = result[1]
    original_ref = model_ref.widget_value

    # Get model from index
    model_info = self.model_index.find_by_path(selected_path)

    # Error handling: Model no longer in index (file deleted since selection)
    if not model_info:
        print(f"\n✗ Model not found in index: {selected_path}")
        print("  It may have been moved or deleted.")
        print("  Run: comfydock models index")
        remaining_models_unresolved.append(model_ref)
        continue

    # ✅ STEP 1: Add to model registry (if not already there)
    if not self.pyproject.models.has_model(model_info.hash):
        self.pyproject.models.add_model(
            model_hash=model_info.hash,
            filename=model_info.filename,
            file_size=model_info.file_size,
            category="required",
            relative_path=model_info.relative_path
        )

    # ✅ STEP 2: Add workflow mapping
    self._add_workflow_model_mapping(
        workflow_name=workflow_name,
        workflow_reference=original_ref,
        model_hash=model_info.hash,
        node_id=model_ref.node_id,
        widget_idx=model_ref.widget_idx
    )

    logger.info(f"Resolved: {original_ref} → hash {model_info.hash[:8]}...")
    # Model now resolved - will be found in next analysis!
```

**Add helper method:**

```python
def _add_workflow_model_mapping(
    self,
    workflow_name: str,
    workflow_reference: str,
    model_hash: str,
    node_id: str,
    widget_idx: int
):
    """Add or update workflow model mapping in pyproject."""
    # Get existing mappings
    current_mappings = self.pyproject.workflows.get_model_resolutions(workflow_name)

    # Build/update mapping
    if workflow_reference in current_mappings:
        # Update existing - add node if not already there
        mapping = current_mappings[workflow_reference]
        nodes = mapping.get("nodes", [])

        node_ref = {"node_id": str(node_id), "widget_idx": int(widget_idx)}
        if node_ref not in nodes:
            nodes.append(node_ref)

        current_mappings[workflow_reference]["nodes"] = nodes
    else:
        # Create new mapping
        current_mappings[workflow_reference] = {
            "hash": model_hash,
            "nodes": [{"node_id": str(node_id), "widget_idx": int(widget_idx)}]
        }

    # Save updated mappings
    self.pyproject.workflows.set_model_resolutions(workflow_name, current_mappings)
```

**Update WorkflowHandler.set_model_resolutions() for new schema:**

```python
def set_model_resolutions(self, name: str, model_resolutions: dict) -> None:
    """Set model resolutions for a workflow.

    Args:
        name: Workflow name
        model_resolutions: Dict mapping workflow reference to {hash, nodes}
            Format: {
                "models/SD/sd15.safetensors": {
                    "hash": "48835672...",
                    "nodes": [{"node_id": "4", "widget_idx": 0}]
                }
            }
    """
    config = self.load()
    self.ensure_section(config, 'tool', 'comfydock', 'workflows', name)

    models_table = tomlkit.table()

    for workflow_ref, resolution_data in model_resolutions.items():
        model_entry = tomlkit.table()
        model_entry['hash'] = resolution_data['hash']

        # Nodes as array of inline tables
        nodes_list = []
        for node_ref in resolution_data.get('nodes', []):
            node_inline = tomlkit.inline_table()
            node_inline['node_id'] = str(node_ref['node_id'])
            node_inline['widget_idx'] = int(node_ref['widget_idx'])
            nodes_list.append(node_inline)

        model_entry['nodes'] = nodes_list
        models_table[workflow_ref] = model_entry

    config['tool']['comfydock']['workflows'][name]['models'] = models_table
    self.save(config)
```

### **Analysis Flow Updates**

**Update workflow analysis to check pyproject first:**

```python
def get_model_resolution_for_workflow(
    self,
    workflow_name: str,
    workflow: Workflow
) -> ResolutionResult:
    """Analyze models, checking pyproject mappings first."""

    # Load saved resolutions
    workflow_mappings = self.pyproject.workflows.get_model_resolutions(workflow_name)
    # Returns: {"models/SD/sd15.safetensors": {hash: "...", nodes: [...]}, ...}

    # Load model registry
    model_registry = self.pyproject.models.get_category("required")
    # Returns: {"hash1": {filename, size, relative_path}, ...}

    resolved_models = []
    unresolved_models = []
    ambiguous_models = []

    for model_ref in workflow.model_references:
        reference_str = model_ref.widget_value

        # Check if we have a saved resolution
        if reference_str in workflow_mappings:
            model_hash = workflow_mappings[reference_str]["hash"]

            # Verify model exists in registry
            if model_hash in model_registry:
                model_data = model_registry[model_hash]

                # Verify file exists in index
                index_result = self.model_index.find_by_hash(model_hash)
                if index_result:
                    resolved_models.append(model_ref)
                    continue
                else:
                    # Mapping exists but file deleted
                    unresolved_models.append(model_ref)
                    continue

        # No mapping, search index directly
        matches = self.model_index.search(reference_str)

        if len(matches) == 0:
            unresolved_models.append(model_ref)
        elif len(matches) == 1:
            # Auto-resolve and save!
            self._auto_resolve_and_save(workflow_name, model_ref, matches[0])
            resolved_models.append(model_ref)
        else:
            ambiguous_models.append((model_ref, matches))

    return ResolutionResult(...)
```

**Auto-resolution helper method:**

```python
def _auto_resolve_and_save(
    self,
    workflow_name: str,
    model_ref: WorkflowNodeWidgetRef,
    model_info: ModelInfo
) -> None:
    """Auto-resolve a model with exactly 1 match and save to pyproject.

    Called when index search finds exactly one match - we can safely auto-resolve it.
    """
    # Add to model registry (if not already there)
    if not self.pyproject.models.has_model(model_info.hash):
        self.pyproject.models.add_model(
            model_hash=model_info.hash,
            filename=model_info.filename,
            file_size=model_info.file_size,
            category="required",
            relative_path=model_info.relative_path
        )

    # Add workflow mapping
    self._add_workflow_model_mapping(
        workflow_name=workflow_name,
        workflow_reference=model_ref.widget_value,
        model_hash=model_info.hash,
        node_id=model_ref.node_id,
        widget_idx=model_ref.widget_idx
    )

    logger.info(f"Auto-resolved: {model_ref.widget_value} → hash {model_info.hash[:8]}...")
```

### **Benefits**

- ✅ `status` shows correct state after `workflow resolve`
- ✅ `commit` sees resolved models
- ✅ Resolution survives git operations
- ✅ Export includes full model metadata
- ✅ Import can map hashes to user's files
- ✅ No re-prompting for same models
- ✅ Workflow JSON preserved (shareable as-is)

---

## Partial Resolutions & Edge Cases

### **Partial Resolution Behavior**

**Key Principle**: Each model is saved individually to pyproject.toml as it's resolved. Resolutions are incremental, not all-or-nothing.

**Example flow:**
```bash
❯ cfd workflow resolve my_workflow

Workflow has 4 models: A, B, C, D

⚠️  Model not found: model_A.safetensors
# User selects from fuzzy search
✓ Resolved: model_A

⚠️  Model not found: model_B.safetensors
# User selects from fuzzy search
✓ Resolved: model_B

⚠️  Model not found: model_C.safetensors
# User presses Ctrl+C
^C
⚠️  Cancelled - remaining models stay unresolved

❯ cfd status
📋 Workflows:
  ⚠️  my_workflow (new)
      Missing model: model_C.safetensors
      Missing model: model_D.safetensors
```

**What happened:**
- Models A and B were saved to pyproject.toml ✓
- Models C and D remain unresolved
- Running `cfd workflow resolve my_workflow` again will only prompt for C and D
- Already-resolved models are remembered

### **Edge Case 1: Model Deleted After Resolution**

**Scenario:** User resolves model, then deletes the file from disk.

**pyproject.toml has:**
```toml
[tool.comfydock.models.required]
48835672... = {filename = "sd15.safetensors", relative_path = "checkpoints/sd15.safetensors"}

[tool.comfydock.workflows.my_workflow.models]
"models/SD/sd15.safetensors" = {hash = "48835672...", nodes = [...]}
```

**Analysis flow detects:**
```python
# Mapping exists
if reference_str in workflow_mappings:
    model_hash = workflow_mappings[reference_str]["hash"]

    # Check if file still exists in index
    index_result = self.model_index.find_by_hash(model_hash)
    if not index_result:
        # Mapping exists but file deleted!
        unresolved_models.append(model_ref)
```

**User experience:**
```bash
❯ cfd status
📋 Workflows:
  ⚠️  my_workflow (new)
      Missing model: models/SD/sd15.safetensors (was resolved but file missing)

💡 Next:
  Re-index models: comfydock models index
  Or resolve again: comfydock workflow resolve my_workflow
```

### **Edge Case 2: Re-indexing Models**

**Scenario:** User runs `cfd models index` after resolving workflows.

**Impact:** None! Mappings stay valid because they're keyed by **content hash**.

**What stays the same:**
- Model hash (content-based, doesn't change)
- Mappings in pyproject.toml (reference hash, not path)

**What might change:**
- Model's `relative_path` in index (if file moved)
- But pyproject.toml still references by hash, so resolution still works

**Example:**
```bash
# Before move
Index: checkpoints/sd15.safetensors → hash 48835672...
pyproject: "models/SD/sd15.safetensors" → hash 48835672...
Status: ✓ Resolved

# User moves file
$ mv checkpoints/sd15.safetensors models/SD1.5/sd15-moved.safetensors

# Re-index
❯ cfd models index

# After move
Index: models/SD1.5/sd15-moved.safetensors → hash 48835672... (same hash!)
pyproject: "models/SD/sd15.safetensors" → hash 48835672... (unchanged)
Status: ✓ Still resolved (hash mapping intact)
```

### **Edge Case 3: Multiple Workflows, Same Model**

**Scenario:** Two workflows reference the same model (by content) but with different paths.

**pyproject.toml:**
```toml
[tool.comfydock.models.required]
# Model stored ONCE
48835672... = {filename = "sd15.safetensors", relative_path = "checkpoints/sd15.safetensors"}

[tool.comfydock.workflows.workflow_a.models]
# Original reference: "sd15.safetensors"
"sd15.safetensors" = {hash = "48835672...", nodes = [...]}

[tool.comfydock.workflows.workflow_b.models]
# Original reference: "models/SD/sd15-v1.safetensors" (different path!)
"models/SD/sd15-v1.safetensors" = {hash = "48835672...", nodes = [...]}
```

**Benefit: Deduplication**
- Model data stored once in registry (4.2 GB saved on disk: 0 bytes extra)
- Both workflows reference same hash
- Export bundles include hash once, mappings show both workflows need it
- On import, recipient maps hash to their local file (whatever path they have)

### **Edge Case 4: Same Model Path, Different Versions**

**Scenario:** Workflow references "sd15.safetensors" but user has two different SD 1.5 models.

**Index has:**
```
checkpoints/sd15-v1.0.safetensors → hash 48835672...
checkpoints/sd15-v1.5.safetensors → hash 911dec51...
```

**Resolution:**
```bash
⚠️  Model not found: sd15.safetensors

🔍 Searching...
Found 2 potential matches:
  1. checkpoints/sd15-v1.0.safetensors (4.27 GB)
  2. checkpoints/sd15-v1.5.safetensors (4.27 GB)

Choice: 1
✓ Mapped: sd15.safetensors → hash 48835672...
```

**Result:** User explicitly chooses which version, mapping saved by hash.

---

## Model Index Integration

### **Requirement: Model Index Search**

The model index needs to support:

```python
class ModelIndex:

    def get_by_category(self, category: str) -> list[ModelInfo]:
        """Get all models of a specific category."""
        # Query SQLite: SELECT * FROM models WHERE category = ?

    def search(self, term: str) -> list[ModelInfo]:
        """Search for models by filename or path."""
        # Query SQLite: SELECT * FROM models WHERE filename LIKE ? OR relative_path LIKE ?

    def find_by_path(self, relative_path: str) -> ModelInfo | None:
        """Find model by exact relative path."""
        # Query SQLite: SELECT * FROM models WHERE relative_path = ?
```

**If model index doesn't have category yet**, add it during indexing:

```python
def index_model(self, file_path: Path) -> ModelInfo:
    """Index a model file."""
    # Existing logic...

    # Infer category from path
    relative_path = file_path.relative_to(workspace.models_path)
    category = relative_path.parts[0] if len(relative_path.parts) > 1 else "other"
    # e.g., "checkpoints/model.safetensors" → category = "checkpoints"

    model_info.category = category
    # Store in DB
```

---

## Testing Strategy

### **Integration Tests to Keep**

From `test_missing_model_resolution.py`, **KEEP**:

```python
class TestFuzzySearchResolution:
    """NEW: Test fuzzy search flow."""

    def test_fuzzy_search_finds_similar_models(self):
        """Search finds models with similar names."""

    def test_user_selects_from_fuzzy_results(self):
        """User can select from search results."""

    def test_pyproject_mapping_created_after_selection(self):
        """Model mapping added to pyproject.toml (workflow JSON unchanged)."""

class TestManualPathResolution:
    """Test manual path entry (from index)."""

    def test_manual_path_finds_model_in_index(self):
        """User enters path, model found in index."""

    def test_manual_path_not_in_index_warns_user(self):
        """Path not in index shows helpful message."""

class TestResolutionSkip:
    """Test skip/cancel behavior."""

    def test_skip_resolution(self):
        """User skips, model stays unresolved."""

    def test_ctrl_c_cancels_resolution(self):
        """Ctrl+C cancels gracefully."""
```

### **Integration Tests to REMOVE/DEFER**

From `test_missing_model_resolution.py`, **REMOVE** (not MVP):

```python
class TestLocateExistingFile:
    # Remove - we don't index arbitrary files during resolution

class TestMarkAsExternal:
    # Remove - not MVP feature

class TestDownloadFromURL:
    # Remove - not MVP feature
```

### **Manual Testing Flow**

```bash
# Setup
❯ cfd create test_resolve
❯ cd test_resolve

# Add some models to index
❯ cfd models index

# Create workflow with wrong model path
# (manually edit workflow JSON to reference non-existent model)

# Test resolution
❯ cfd workflow resolve test_workflow

# Should see:
# - Fuzzy search results
# - Can select a model
# - Workflow updated
# - Can commit

❯ cfd status
# Should show workflow as resolved

❯ cfd commit -m "Add workflow"
# Should succeed
```

---

## Success Criteria

### **User Experience**

✅ User with imported workflow can resolve model in <30 seconds
✅ Fuzzy search shows relevant models first (high confidence at top)
✅ Workflow JSON automatically updated with selected model
✅ Clear guidance when model not in index
✅ Ctrl+C works at any point

### **Technical**

✅ No external dependencies (use built-in difflib)
✅ Fast search (query index, not filesystem)
✅ Workflow updates preserve formatting
✅ Multiple models in same workflow can be resolved
✅ All resolution paths tested

---

## Out of Scope (Future Work)

The following are explicitly **NOT** in this MVP:

❌ **Download from URL**
- Requires HTTP client, progress bars, error handling
- Adds significant complexity
- Defer until import implementation needs it

❌ **Mark as external**
- Requires pyproject.toml schema extension
- Adds "external" model type to track
- Defer until export/import is further along

❌ **Index arbitrary files**
- Manual path only selects from existing index
- User must add to workspace and run `models index` first
- Keeps separation of concerns clean

❌ **Advanced search features**
- Fuzzy matching by tags/metadata
- Multi-criteria scoring
- Search result filtering/sorting
- Keep it simple for MVP

❌ **Resume/retry for failed operations**
- Just let user try again
- Keep error handling minimal

---

## Implementation Order

### **Week 1: Core Search**
1. Add category field to model index schema
2. Implement `find_similar_models()` with difflib
3. Add node type → category mapping
4. Unit tests for search scoring

### **Week 1: Interactive UI**
5. Update `InteractiveModelStrategy` with new flow
6. Display fuzzy search results
7. Handle user selection
8. Add browse/pagination UI

### **Week 1: Integration**
9. Update `fix_resolution()` to handle new return values
10. Implement `update_workflow_model_reference()`
11. Integration tests
12. Manual testing

### **Week 2: Polish**
13. Error handling and edge cases
14. Manual path entry flow
15. "Fix in ComfyUI" messaging
16. Documentation updates

---

## Files to Modify

| File | Changes | Priority |
|------|---------|----------|
| `src/comfydock_core/managers/workflow_manager.py` | Add `find_similar_models()` using ModelConfig, `_add_workflow_model_mapping()` | High |
| `src/comfydock_core/managers/workflow_manager.py` | Update `fix_resolution()` to save to pyproject.toml | High |
| `src/comfydock_core/managers/pyproject_manager.py` | Add model registry methods, workflow mapping methods | High |
| `packages/cli/comfydock_cli/strategies/interactive.py` | New resolution UI with fuzzy search | High |
| `src/comfydock_core/indexing/model_index.py` | Add category field, search methods | Medium |
| `tests/integration/test_missing_model_resolution.py` | **Rewrite** to match new design | High |

**Estimated effort**: 2-3 days for implementation + testing

**Key Design Points**:
- Use existing `ModelConfig` class for node-to-directory mappings (no hardcoded mappings!)
- Handle multi-directory node types (e.g., CheckpointLoader searches both "checkpoints" and "configs")
- No modifications to workflow JSON files during local resolution - only pyproject.toml mappings!

---

## Related Documents

- `/docs/prd.md` - Overall product requirements
