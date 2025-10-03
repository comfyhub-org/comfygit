# Missing Model Resolution - Complete Implementation Plan

**Status**: Ready to Implement
**Priority**: High
**Estimated Effort**: 1-2 days

---

## Executive Summary

This document provides a **complete, step-by-step implementation plan** for the content-addressable model resolution system. It fills critical gaps identified in the original design documents and provides concrete code examples for all components.

### What This Document Provides

✅ Missing repository methods with full implementations (NO schema changes needed!)
✅ Corrected pyproject.toml schema aligned with design
✅ Strategy protocol clarification
✅ Complete end-to-end implementation flow
✅ Integration examples

### Key Simplification

**The existing database schema already supports everything we need!** The `relative_path` field contains the category information (e.g., `"checkpoints/model.safetensors"`), so we can extract categories on-the-fly without schema migrations.

---

## Critical Design Decisions

### 1. Hash Strategy (ALREADY IMPLEMENTED ✅)

**Quick Hash Calculation Already Exists!**

The `ModelRepository.calculate_short_hash()` method (lines 535-579) already implements the quick hash strategy:
- Samples 5MB from start, middle, end of file + file size
- Uses Blake3 for fast hashing
- ~200ms vs 30-60s for full hash
- Stored in `hash` field (PRIMARY KEY)

**Full Hashes: For export/import only (future)**
- `blake3_hash` and `sha256_hash` fields already exist
- Methods `compute_blake3()` and `compute_sha256()` already implemented
- Not needed for MVP resolution feature
- Will be used for export verification later

**Decision**: Use existing `hash` field (quick hash) as content address - already working!

### 2. pyproject.toml Schema (CORRECTED)

**Current Implementation (WRONG):**
```toml
[tool.comfydock.workflows.my_workflow]
models = {
  "abc123hash" = { nodes = [...] }  # Hash as key - loses original reference!
}
```

**Correct Implementation (Content-Addressable):**
```toml
[tool.comfydock.workflows.my_workflow.models]
# Original workflow reference → hash mapping
"sd15-missing.safetensors" = {
  hash = "abc123...",
  nodes = [{node_id = "1", widget_idx = 0}]
}
```

**Why This Matters:**
- Preserves original workflow reference (shareability)
- Maps workflow-specific names to universal hashes
- Multiple workflows can reference same hash with different names
- Import can remap hashes to local paths

### 3. Strategy Protocol (RESOLVED)

**Current Protocol (needs update):**
```python
def handle_missing_model(self, reference: WorkflowNodeWidgetRef) -> Optional[str]:
    """Returns: Download URL or None to skip"""
```

**New Protocol:**
```python
def handle_missing_model(self, reference: WorkflowNodeWidgetRef) -> tuple[str, str] | None:
    """Returns: ("action", "data") tuple or None to skip

    Actions:
    - ("select", "path/to/model.safetensors") - User selected from index
    - ("skip", None) - User chose to skip

    Returns None on cancel/interrupt
    """
```

---

## Phase 1: Add Missing Repository Methods

**NO SCHEMA CHANGES NEEDED!** The existing `relative_path` field already contains category information (e.g., `"checkpoints/sd15.safetensors"`). We can extract categories on-the-fly using SQL LIKE patterns.

### 1.1 Understanding the Existing Schema

**Current schema (v7):**
```sql
CREATE TABLE model_locations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_hash TEXT NOT NULL,
    relative_path TEXT NOT NULL,  -- e.g., "checkpoints/sd15.safetensors"
    filename TEXT NOT NULL,        -- e.g., "sd15.safetensors"
    mtime REAL NOT NULL,
    last_seen INTEGER NOT NULL,
    UNIQUE(relative_path)
)
```

**Key insight**: `relative_path` already contains the category as the first path segment!
- `"checkpoints/model.safetensors"` → category is `"checkpoints"`
- `"loras/mylora.safetensors"` → category is `"loras"`
- `"SD1.5/photon_v1.safetensors"` → category is `"SD1.5"`

### 1.2 Add Three Missing Methods

**File**: `packages/core/src/comfydock_core/repositories/model_repository.py`

**Method 1: Get models by category (extracts from relative_path)**
```python
def get_by_category(self, category: str) -> list[ModelWithLocation]:
    """Get all models in a specific category by filtering relative_path.

    Args:
        category: Category name (e.g., "checkpoints", "loras", "vae")

    Returns:
        List of ModelWithLocation objects in that category

    Examples:
        >>> repo.get_by_category("checkpoints")
        # Returns models where relative_path starts with "checkpoints/"
    """
    query = """
    SELECT m.hash, m.file_size, m.blake3_hash, m.sha256_hash, m.metadata,
           l.relative_path, l.filename, l.mtime, l.last_seen
    FROM models m
    JOIN model_locations l ON m.hash = l.model_hash
    WHERE l.relative_path LIKE ?
    ORDER BY l.filename
    """

    # Match paths starting with category/ (e.g., "checkpoints/%")
    search_pattern = f"{category}/%"
    results = self.sqlite.execute_query(query, (search_pattern,))

    models = []
    for row in results:
        metadata = json.loads(row['metadata']) if row['metadata'] else {}
        model = ModelWithLocation(
            hash=row['hash'],
            file_size=row['file_size'],
            blake3_hash=row['blake3_hash'],
            sha256_hash=row['sha256_hash'],
            relative_path=row['relative_path'],
            filename=row['filename'],
            mtime=row['mtime'],
            last_seen=row['last_seen'],
            metadata=metadata
        )
        models.append(model)

    return models
```

**Method 2: Find by exact path (simple WHERE clause)**
```python
def find_by_exact_path(self, relative_path: str) -> ModelWithLocation | None:
    """Find model by exact relative path.

    Args:
        relative_path: Exact relative path to match (e.g., "checkpoints/sd15.safetensors")

    Returns:
        ModelWithLocation or None if not found

    Examples:
        >>> repo.find_by_exact_path("checkpoints/sd15.safetensors")
        # Returns exact match or None
    """
    query = """
    SELECT m.hash, m.file_size, m.blake3_hash, m.sha256_hash, m.metadata,
           l.relative_path, l.filename, l.mtime, l.last_seen
    FROM models m
    JOIN model_locations l ON m.hash = l.model_hash
    WHERE l.relative_path = ?
    LIMIT 1
    """

    results = self.sqlite.execute_query(query, (relative_path,))
    if not results:
        return None

    row = results[0]
    metadata = json.loads(row['metadata']) if row['metadata'] else {}

    return ModelWithLocation(
        hash=row['hash'],
        file_size=row['file_size'],
        blake3_hash=row['blake3_hash'],
        sha256_hash=row['sha256_hash'],
        relative_path=row['relative_path'],
        filename=row['filename'],
        mtime=row['mtime'],
        last_seen=row['last_seen'],
        metadata=metadata
    )
```

**Method 3: Enhanced search (filename OR path - extends existing)**
```python
def search(self, term: str) -> list[ModelWithLocation]:
    """Search for models by filename or path.

    This extends the existing find_by_filename() to also search relative_path.

    Args:
        term: Search term to match against filename or path

    Returns:
        List of matching ModelWithLocation objects

    Examples:
        >>> repo.search("sd15")
        # Returns models where filename OR relative_path contains "sd15"
        # Matches: "checkpoints/sd15.safetensors", "SD1.5/model.safetensors"
    """
    query = """
    SELECT m.hash, m.file_size, m.blake3_hash, m.sha256_hash, m.metadata,
           l.relative_path, l.filename, l.mtime, l.last_seen
    FROM models m
    JOIN model_locations l ON m.hash = l.model_hash
    WHERE l.filename LIKE ? OR l.relative_path LIKE ?
    ORDER BY l.filename
    """

    search_pattern = f"%{term}%"
    results = self.sqlite.execute_query(query, (search_pattern, search_pattern))

    models = []
    for row in results:
        metadata = json.loads(row['metadata']) if row['metadata'] else {}
        model = ModelWithLocation(
            hash=row['hash'],
            file_size=row['file_size'],
            blake3_hash=row['blake3_hash'],
            sha256_hash=row['sha256_hash'],
            relative_path=row['relative_path'],
            filename=row['filename'],
            mtime=row['mtime'],
            last_seen=row['last_seen'],
            metadata=metadata
        )
        models.append(model)

    return models
```

**Note**: The existing `find_by_filename()` only searches the `filename` field. This new `search()` method searches BOTH `filename` AND `relative_path`, making it more comprehensive.

---

## Phase 2: pyproject.toml Schema Fix

### 2.1 Update WorkflowHandler Schema

**File**: `packages/core/src/comfydock_core/managers/pyproject_manager.py`

**Replace `set_model_resolutions()` method:**

```python
def set_model_resolutions(self, name: str, model_resolutions: dict) -> None:
    """Set model resolutions for a workflow.

    Args:
        name: Workflow name
        model_resolutions: Dict mapping workflow reference to {hash, nodes}
            Format: {
                "original/workflow/ref.safetensors": {
                    "hash": "abc123...",
                    "nodes": [{"node_id": "4", "widget_idx": 0}]
                }
            }
    """
    config = self.load()
    self.ensure_section(config, 'tool', 'comfydock', 'workflows', name)

    # Create models table
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
    logger.info(f"Set model resolutions for workflow: {name}")
```

**Update `get_model_resolutions()` to match:**

```python
def get_model_resolutions(self, name: str) -> dict:
    """Get model resolutions for a specific workflow.

    Returns:
        Dict mapping workflow reference to {hash, nodes}
    """
    try:
        config = self.load()
        workflow_data = config.get('tool', {}).get('comfydock', {}).get('workflows', {}).get(name, {})
        return workflow_data.get('models', {})
    except Exception:
        return {}
```

### 2.2 Update ModelHandler to Store relative_path

**Add relative_path parameter:**

```python
def add_model(
    self,
    model_hash: str,
    filename: str,
    file_size: int,
    relative_path: str,  # NEW: Required for lookups
    category: str = "required",
    **metadata,
) -> None:
    """Add a model to the manifest.

    Args:
        model_hash: Model hash (quick hash used as key)
        filename: Model filename
        file_size: File size in bytes
        relative_path: Relative path in models directory
        category: 'required' or 'optional'
        **metadata: Additional metadata (blake3, sha256, sources, etc.)
    """
    config = self.load()
    self.ensure_section(config, "tool", "comfydock", "models", category)

    model_entry = tomlkit.inline_table()
    model_entry["filename"] = filename
    model_entry["size"] = file_size
    model_entry["relative_path"] = relative_path  # NEW

    for key, value in metadata.items():
        model_entry[key] = value

    config["tool"]["comfydock"]["models"][category][model_hash] = model_entry
    self.save(config)
    logger.info(f"Added {category} model: {filename} ({model_hash[:8]}...)")
```

---

## Phase 3: Fuzzy Search Implementation

### 3.1 Create ScoredMatch Data Class

**File**: `packages/core/src/comfydock_core/models/workflow.py`

```python
from dataclasses import dataclass
from .shared import ModelWithLocation

@dataclass
class ScoredMatch:
    """Model match with similarity score."""
    model: ModelWithLocation
    score: float
    confidence: str  # "high", "good", "possible"
```

### 3.2 Add find_similar_models to WorkflowManager

**File**: `packages/core/src/comfydock_core/managers/workflow_manager.py`

**Add imports:**
```python
from difflib import SequenceMatcher
from pathlib import Path
from ..configs.model_config import ModelConfig
from ..models.workflow import ScoredMatch
```

**Add method:**
```python
def find_similar_models(
    self,
    missing_ref: str,
    node_type: str,
    limit: int = 5
) -> list[ScoredMatch]:
    """Find models similar to missing reference using fuzzy search.

    Args:
        missing_ref: The missing model reference from workflow
        node_type: ComfyUI node type (e.g., "CheckpointLoaderSimple")
        limit: Maximum number of results to return

    Returns:
        List of ScoredMatch objects sorted by confidence (highest first)
    """
    # Load model config for node type mappings
    model_config = ModelConfig.load()

    # Get directories this node type can load from
    directories = model_config.get_directories_for_node(node_type)

    if not directories:
        # Unknown node type - default to checkpoints
        directories = ["checkpoints"]
        logger.warning(f"Unknown node type '{node_type}', defaulting to checkpoints")

    # Get all models from ANY of those directories
    candidates = []
    for directory in directories:
        models = self.model_repository.get_by_category(directory)
        candidates.extend(models)

    if not candidates:
        logger.info(f"No models found in categories: {directories}")
        return []

    # Score each candidate
    scored = []
    missing_name = Path(missing_ref).stem.lower()

    for model in candidates:
        model_name = Path(model.filename).stem.lower()

        # Use Python's difflib for fuzzy matching
        score = SequenceMatcher(None, missing_name, model_name).ratio()

        if score > 0.4:  # Minimum 40% similarity
            confidence = "high" if score > 0.8 else "good" if score > 0.6 else "possible"
            scored.append(ScoredMatch(
                model=model,
                score=score,
                confidence=confidence
            ))

    # Sort by score descending
    scored.sort(key=lambda x: x.score, reverse=True)

    return scored[:limit]
```

---

## Phase 4: Strategy Protocol Update

### 4.1 Update Protocol Definition

**File**: `packages/core/src/comfydock_core/models/protocols.py`

```python
class ModelResolutionStrategy(Protocol):
    """Protocol for resolving model references."""

    def resolve_ambiguous_model(
        self, reference: WorkflowNodeWidgetRef, candidates: List[ModelWithLocation]
    ) -> Optional[ModelWithLocation]:
        """Choose from multiple model matches."""
        ...

    def handle_missing_model(
        self, reference: WorkflowNodeWidgetRef
    ) -> tuple[str, str] | None:  # UPDATED
        """Handle completely missing model.

        Args:
            reference: The model reference that couldn't be found

        Returns:
            Tuple of ("action", "data") or None
            - ("select", "path/to/model.safetensors"): User selected model from index
            - ("skip", ""): User chose to skip resolution
            - None: Cancelled (Ctrl+C)
        """
        ...
```

### 4.2 Update InteractiveModelStrategy

**File**: `packages/cli/comfydock_cli/strategies/interactive.py`

```python
def handle_missing_model(
    self, reference: WorkflowNodeWidgetRef
) -> tuple[str, str] | None:
    """Prompt user for missing model with fuzzy search.

    Returns:
        ("select", path) if user selects a model
        ("skip", "") if user skips
        None if cancelled
    """
    print(f"\n⚠️  Model not found: {reference.widget_value}")
    print(f"  in node #{reference.node_id} ({reference.node_type})")

    # Note: Fuzzy search would be called here by WorkflowManager
    # This strategy just handles the UI

    print("\nOptions:")
    print("  1. Search model index")
    print("  2. Enter path manually")
    print("  3. Skip (resolve later)")

    while True:
        choice = input("\nChoice [1]: ").strip() or "1"

        if choice == "1":
            # This will trigger fuzzy search in fix_resolution
            return ("search", "")
        elif choice == "2":
            path = input("Enter model path: ").strip()
            if path:
                return ("select", path)
            return ("skip", "")
        elif choice == "3":
            return ("skip", "")
        else:
            print("  Invalid choice, try again")
```

---

## Phase 5: Integration - fix_resolution() Update

### 5.1 Complete fix_resolution Implementation

**File**: `packages/core/src/comfydock_core/managers/workflow_manager.py`

```python
def fix_resolution(
    self,
    resolution: ResolutionResult,
    node_strategy: NodeResolutionStrategy | None = None,
    model_strategy: ModelResolutionStrategy | None = None,
) -> ResolutionResult:
    """Fix unresolved dependencies using strategies.

    Args:
        resolution: Initial resolution result with issues
        node_strategy: Strategy for resolving nodes
        model_strategy: Strategy for resolving models

    Returns:
        Updated ResolutionResult with resolved items
    """
    # ... existing node resolution code ...

    # Handle missing models using strategy
    remaining_models_unresolved = []
    models_to_add = []

    if model_strategy:
        for model_ref in resolution.models_unresolved:
            try:
                result = model_strategy.handle_missing_model(model_ref)

                if result is None:
                    # Cancelled (Ctrl+C)
                    remaining_models_unresolved.append(model_ref)
                    continue

                action, data = result

                if action == "search":
                    # Perform fuzzy search
                    similar = self.find_similar_models(
                        missing_ref=model_ref.widget_value,
                        node_type=model_ref.node_type,
                        limit=10
                    )

                    if not similar:
                        print("  No similar models found in index")
                        remaining_models_unresolved.append(model_ref)
                        continue

                    # Show fuzzy search results
                    print(f"\nFound {len(similar)} potential matches:\n")
                    for i, match in enumerate(similar[:5], 1):
                        size_gb = match.model.file_size / (1024**3)
                        print(f"  {i}. {match.model.relative_path} ({size_gb:.2f} GB)")
                        print(f"     Confidence: {match.confidence}")

                    if len(similar) > 5:
                        print(f"\n  ... and {len(similar) - 5} more")

                    choice = input("\nSelect [1-5] or (s)kip: ").strip()

                    if choice.lower() == 's':
                        remaining_models_unresolved.append(model_ref)
                        continue

                    if choice.isdigit() and 1 <= int(choice) <= min(5, len(similar)):
                        selected_model = similar[int(choice) - 1].model
                        models_to_add.append(selected_model)
                        logger.info(f"Resolved via fuzzy search: {model_ref.widget_value} → {selected_model.relative_path}")
                    else:
                        print("  Invalid choice")
                        remaining_models_unresolved.append(model_ref)

                elif action == "select":
                    # User provided explicit path
                    path = data

                    # Look up in index by exact path
                    model = self.model_repository.find_by_exact_path(path)

                    if model:
                        models_to_add.append(model)
                        logger.info(f"Resolved: {model_ref.widget_value} → {path}")
                    else:
                        print(f"  ✗ Model not found in index: {path}")
                        print("  Run 'comfydock models index' if the file exists")
                        remaining_models_unresolved.append(model_ref)

                elif action == "skip":
                    remaining_models_unresolved.append(model_ref)
                    logger.info(f"Skipped: {model_ref.widget_value}")

            except KeyboardInterrupt:
                print("\n⚠️  Cancelled - model stays unresolved")
                remaining_models_unresolved.append(model_ref)
                break
    else:
        remaining_models_unresolved = list(resolution.models_unresolved)

    return ResolutionResult(
        nodes_resolved=resolution.nodes_resolved,
        nodes_unresolved=remaining_nodes_unresolved,
        nodes_ambiguous=remaining_nodes_ambiguous,
        models_resolved=list(resolution.models_resolved) + models_to_add,
        models_unresolved=remaining_models_unresolved,
        models_ambiguous=remaining_models_ambiguous,
    )
```

---

## Phase 6: Persistence - apply_resolution() Update

### 6.1 Helper Method for Workflow Mappings

**File**: `packages/core/src/comfydock_core/managers/workflow_manager.py`

```python
def _add_workflow_model_mapping(
    self,
    workflow_name: str,
    workflow_reference: str,
    model_hash: str,
    node_id: str,
    widget_idx: int
) -> None:
    """Add or update workflow model mapping in pyproject.

    Args:
        workflow_name: Name of the workflow
        workflow_reference: Original reference from workflow JSON
        model_hash: Hash of the resolved model
        node_id: Node ID that uses this model
        widget_idx: Widget index containing the model path
    """
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
    logger.info(f"Mapped: {workflow_reference} → hash {model_hash[:8]}...")
```

### 6.2 Update _apply_resolution_to_pyproject

**File**: `packages/core/src/comfydock_core/managers/workflow_manager.py`

```python
def _apply_resolution_to_pyproject(
    self,
    nodes: list,
    models: list[ModelWithLocation],
    workflow_name: str = None,  # NEW: Need workflow context
    model_refs: list[WorkflowNodeWidgetRef] = None  # NEW: Original references
) -> None:
    """Apply resolved nodes and models to pyproject.toml.

    Args:
        nodes: List of resolved node packages
        models: List of resolved ModelWithLocation objects
        workflow_name: Name of workflow being resolved
        model_refs: Original workflow references (for mapping)
    """
    # ... existing node resolution code ...

    # Apply model resolutions
    if models:
        for i, model in enumerate(models):
            # Add to model registry if not already there
            if not self.pyproject.models.has_model(model.hash):
                self.pyproject.models.add_model(
                    model_hash=model.hash,
                    filename=model.filename,
                    file_size=model.file_size,
                    relative_path=model.relative_path,
                    category="required"
                )

            # Add workflow mapping if we have context
            if workflow_name and model_refs and i < len(model_refs):
                ref = model_refs[i]
                self._add_workflow_model_mapping(
                    workflow_name=workflow_name,
                    workflow_reference=ref.widget_value,  # Original reference
                    model_hash=model.hash,
                    node_id=ref.node_id,
                    widget_idx=ref.widget_idx
                )
```

### 6.3 Update apply_resolution Signature

```python
def apply_resolution(
    self,
    resolution: ResolutionResult,
    workflow_name: str = None,  # NEW
    model_refs: list[WorkflowNodeWidgetRef] = None  # NEW
) -> None:
    """Apply resolution to pyproject.toml.

    Args:
        resolution: Resolution result to apply
        workflow_name: Name of workflow (for model mappings)
        model_refs: Original model references (for mapping preservation)
    """
    if not resolution.nodes_resolved and not resolution.models_resolved:
        logger.info("No resolved dependencies to apply")
        return

    self._apply_resolution_to_pyproject(
        resolution.nodes_resolved,
        resolution.models_resolved,
        workflow_name=workflow_name,
        model_refs=model_refs
    )
```

---

## Phase 7: Analysis with Persistence Check

### 7.1 Update get_model_resolution_for_workflow

**File**: `packages/core/src/comfydock_core/managers/workflow_manager.py`

```python
def get_model_resolution_for_workflow(
    self,
    workflow_name: str,
    workflow: Workflow
) -> ResolutionResult:
    """Analyze models, checking pyproject mappings first.

    This implements the persistence check - if a model has been resolved
    before, we reuse that resolution instead of re-prompting.
    """
    # Load saved resolutions from pyproject
    workflow_mappings = self.pyproject.workflows.get_model_resolutions(workflow_name)
    # Returns: {"workflow/ref.safetensors": {hash: "...", nodes: [...]}, ...}

    # Load model registry
    model_registry = self.pyproject.models.get_category("required")
    # Returns: {"hash1": {filename, size, relative_path}, ...}

    resolved_models = []
    unresolved_models = []
    ambiguous_models = []

    for model_ref in workflow.model_references:
        reference_str = model_ref.widget_value

        # STEP 1: Check if we have a saved resolution
        if reference_str in workflow_mappings:
            model_hash = workflow_mappings[reference_str]["hash"]

            # Verify model exists in registry
            if model_hash in model_registry:
                model_data = model_registry[model_hash]

                # Verify file exists in index (detects deleted files)
                index_result = self.model_repository.find_model_by_hash(model_hash)
                if index_result and len(index_result) > 0:
                    # Found! Use cached resolution
                    resolved_models.append(model_ref)
                    logger.debug(f"Using cached resolution: {reference_str} → {model_hash[:8]}")
                    continue
                else:
                    # Mapping exists but file deleted
                    logger.warning(f"Model deleted: {reference_str} (hash {model_hash[:8]})")
                    unresolved_models.append(model_ref)
                    continue

        # STEP 2: No mapping, search index directly
        # Try exact match by reconstructing path
        from ..configs.model_config import ModelConfig
        model_config = ModelConfig.load()
        possible_paths = model_config.reconstruct_model_path(
            model_ref.node_type,
            reference_str
        )

        # Check each possible path
        found = None
        for path in possible_paths:
            found = self.model_repository.find_by_exact_path(path)
            if found:
                break

        if found:
            # Auto-resolve and save
            self._auto_resolve_and_save(workflow_name, model_ref, found)
            resolved_models.append(model_ref)
        else:
            # No exact match - try filename search
            matches = self.model_repository.find_by_filename(reference_str)

            if len(matches) == 0:
                unresolved_models.append(model_ref)
            elif len(matches) == 1:
                # Auto-resolve single match
                self._auto_resolve_and_save(workflow_name, model_ref, matches[0])
                resolved_models.append(model_ref)
            else:
                ambiguous_models.append((model_ref, matches))

    return ResolutionResult(
        nodes_resolved=[],
        nodes_unresolved=[],
        nodes_ambiguous=[],
        models_resolved=resolved_models,
        models_unresolved=unresolved_models,
        models_ambiguous=ambiguous_models
    )
```

### 7.2 Add Auto-Resolution Helper

```python
def _auto_resolve_and_save(
    self,
    workflow_name: str,
    model_ref: WorkflowNodeWidgetRef,
    model: ModelWithLocation
) -> None:
    """Auto-resolve a model with exactly 1 match and save to pyproject.

    Called when index search finds exactly one match - we can safely auto-resolve it.
    """
    # Add to model registry (if not already there)
    if not self.pyproject.models.has_model(model.hash):
        self.pyproject.models.add_model(
            model_hash=model.hash,
            filename=model.filename,
            file_size=model.file_size,
            relative_path=model.relative_path,
            category="required"
        )

    # Add workflow mapping
    self._add_workflow_model_mapping(
        workflow_name=workflow_name,
        workflow_reference=model_ref.widget_value,
        model_hash=model.hash,
        node_id=model_ref.node_id,
        widget_idx=model_ref.widget_idx
    )

    logger.info(f"Auto-resolved: {model_ref.widget_value} → hash {model.hash[:8]}...")
```

---

## Implementation Order

### Day 1: Repository Methods & pyproject Schema (3-4 hours)

**Morning: Repository Methods**
1. ✅ Add get_by_category() method (uses existing relative_path)
2. ✅ Add find_by_exact_path() method (simple WHERE clause)
3. ✅ Add search() method (filename OR path)
4. ✅ Test: Verify methods work with existing data

**Afternoon: pyproject Schema & Fuzzy Search**
1. ✅ Create ScoredMatch dataclass
2. ✅ Update WorkflowHandler.set_model_resolutions() (workflow_ref → hash)
3. ✅ Update ModelHandler.add_model() (add relative_path param)
4. ✅ Implement find_similar_models() in WorkflowManager
5. ✅ Test: Fuzzy search finds similar models

### Day 2: Strategy & Integration (4-5 hours)

**Morning: Strategy Updates**
1. ✅ Update ModelResolutionStrategy protocol (tuple returns)
2. ✅ Update InteractiveModelStrategy
3. ✅ Update fix_resolution() with new flow
4. ✅ Test: Manual resolution flow works

**Afternoon: Persistence**
1. ✅ Add _add_workflow_model_mapping() helper
2. ✅ Update apply_resolution() signature
3. ✅ Update get_model_resolution_for_workflow() (check pyproject first)
4. ✅ Add _auto_resolve_and_save() helper
5. ✅ Update _apply_resolution_to_pyproject()
6. ✅ Test: Resolutions survive status re-run
7. ✅ Test: Deleted files detected

### Day 3: Integration & Testing (2-3 hours)
1. ✅ Run all integration tests
2. ✅ Fix any failures
3. ✅ Test edge cases (partial resolutions, Ctrl+C)
4. ✅ Update CLI commands to use new flow

---

## Testing Checklist

Run these tests to verify implementation:

```bash
# Database tests
uv run pytest tests/integration/test_missing_model_resolution.py::TestFuzzySearchResolution -v

# pyproject schema tests
uv run pytest tests/integration/test_missing_model_resolution.py::TestManualPathResolution -v

# Persistence tests
uv run pytest tests/integration/test_missing_model_resolution.py::TestResolutionPersistence -v

# Deduplication tests
uv run pytest tests/integration/test_missing_model_resolution.py::TestMultipleWorkflowsSameModel -v

# All tests
uv run pytest tests/integration/test_missing_model_resolution.py -v
```

**Success Criteria:** All 10 tests pass

---

## Integration Points

### CLI Integration

**File**: `packages/cli/comfydock_cli/env_commands.py`

Update commit command to provide workflow context:

```python
# In commit command
for analyzed in workflow_status.analyzed_workflows:
    if analyzed.resolution.models_unresolved:
        fixed = env.workflow_manager.fix_resolution(
            resolution=analyzed.resolution,
            node_strategy=None,
            model_strategy=InteractiveModelStrategy()
        )

        # Apply with context for persistence
        env.workflow_manager.apply_resolution(
            resolution=fixed,
            workflow_name=analyzed.name,
            model_refs=analyzed.resolution.models_unresolved
        )
```

---

## Edge Cases Handled

1. ✅ **Model deleted after resolution**: Detected in analysis, marked unresolved
2. ✅ **Multiple workflows, same model**: Hash deduplication works automatically
3. ✅ **Partial resolutions**: Each model saved individually
4. ✅ **Ctrl+C during resolution**: Gracefully handled, already-resolved saved
5. ✅ **Invalid path from user**: Checked in index, helpful error shown
6. ✅ **Unknown node types**: Defaults to checkpoints with warning
7. ✅ **No similar models found**: Shows message, model stays unresolved

---

## Files to Modify

| File | Changes | Lines Changed | Priority |
|------|---------|---------------|----------|
| `repositories/model_repository.py` | Add 3 new methods (get_by_category, find_by_exact_path, search) | ~80 lines | 🔴 Critical |
| `managers/pyproject_manager.py` | Fix workflow schema, add relative_path param | ~40 lines | 🔴 Critical |
| `managers/workflow_manager.py` | Fuzzy search, fix_resolution, persistence helpers | ~200 lines | 🔴 Critical |
| `models/workflow.py` | Add ScoredMatch dataclass | ~10 lines | 🟡 High |
| `models/protocols.py` | Update strategy protocol return type | ~5 lines | 🟡 High |
| `cli/strategies/interactive.py` | Update for tuple returns | ~20 lines | 🟡 High |
| `cli/env_commands.py` | Pass workflow context to apply_resolution | ~10 lines | 🟢 Medium |

**Total estimated changes**: ~365 lines of code

---

## Success Metrics

- ✅ All 10 integration tests pass
- ✅ Fuzzy search finds relevant models (>60% accuracy)
- ✅ Resolutions persist (no re-prompting)
- ✅ Workflow JSON stays unchanged
- ✅ pyproject.toml has correct schema
- ✅ Category filtering works correctly
- ✅ Deleted files detected on re-analysis

---

## Conclusion

This plan provides **complete, executable guidance** for implementing the content-addressable model resolution system. All critical gaps have been identified and filled with concrete solutions.

**An engineer following this plan will:**
1. Know exactly what code to write
2. Understand the data flow end-to-end
3. Have working examples for all components
4. Be able to verify success with integration tests
5. Handle all edge cases correctly

**Key simplifications:**
- ✅ No schema migrations needed (existing schema has everything)
- ✅ No data loss or re-indexing required
- ✅ Quick hash already implemented
- ✅ Just add 3 methods + update integration logic
- ✅ Reduced from 2-3 days to 1-2 days

The implementation is straightforward - the database already supports what we need!
