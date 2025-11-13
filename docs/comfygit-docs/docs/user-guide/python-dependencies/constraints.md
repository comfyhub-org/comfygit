# Dependency Constraints

> Override and control package versions globally across your environment using UV constraint dependencies.

## Overview

Constraints are global version restrictions that override what versions UV can choose when resolving dependencies:

- **Pin specific versions** - Lock PyTorch, NumPy, or other critical packages
- **Prevent updates** - Keep packages within a major version range
- **Resolve conflicts** - Force compatible versions when nodes disagree
- **Establish baselines** - Set version requirements before adding nodes

Constraints are stored in `[tool.uv.constraint-dependencies]` in your `.cec/pyproject.toml` and apply to **all** dependencies in the environment.

!!! note "Constraints vs regular dependencies"
    - **Regular dependencies** (`cg py add`) - Packages you explicitly need installed
    - **Constraints** (`cg constraint add`) - Version restrictions without installation

    Constraints don't install packages—they control what versions can be installed by other dependencies.

## Before you begin

Make sure you have:

- An active environment — `cg use <name>` or use `-e <name>` flag
- Understanding of version specifiers (`==`, `>=`, `<`, etc.)

## Understanding constraints

### What are constraints?

Think of constraints as **meta-dependencies**—they don't install packages themselves, but they restrict what versions UV can choose when resolving other dependencies.

**Example scenario:**

```bash
# Without constraints
cg node add node-a  # Installs torch==2.0.0
cg node add node-b  # Error! Requires torch>=2.1.0

# With constraints
cg constraint add "torch==2.1.0"  # Set version requirement
cg node add node-a  # Uses torch==2.1.0 (constraint overrides node's requirement)
cg node add node-b  # Uses torch==2.1.0 (satisfied)
```

The constraint forces both nodes to use PyTorch 2.1.0, even though `node-a` requested 2.0.0.

### How constraints work

When UV resolves dependencies:

1. **Reads constraints** from `[tool.uv.constraint-dependencies]`
2. **Applies restrictions** to all package resolution
3. **Rejects incompatible versions** even if requested by dependencies
4. **Succeeds only if** all constraints can be satisfied simultaneously

**In pyproject.toml:**

```toml
[tool.uv.constraint-dependencies]
torch = "==2.1.0"
numpy = ">=1.24.0"
pillow = ">=9.0.0,<10.0.0"
```

These constraints apply to:
- Packages added with `cg py add`
- Dependencies from custom nodes (`cg node add`)
- Transitive dependencies (dependencies of dependencies)

## Adding constraints

Add version restrictions to your environment:

```bash
cg constraint add "torch==2.1.0"
```

**What happens:**

1. **Updates pyproject.toml** - Adds to `[tool.uv.constraint-dependencies]`
2. **No immediate installation** - Constraints don't install packages
3. **Applied on next resolution** - Takes effect when you add/update packages

**Example output:**

```
📦 Adding constraints: torch==2.1.0

✓ Added 1 constraint(s) to pyproject.toml

Run 'cg -e my-env constraint list' to view all constraints
```

### Adding multiple constraints

Add several constraints at once:

```bash
cg constraint add "torch==2.1.0" "numpy>=1.24.0" "pillow<10.0"
```

All constraints are added together.

### Common constraint patterns

#### Pin to exact version

Lock a package to a specific version:

```bash
cg constraint add "torch==2.1.0"
```

**Result:** `torch = "==2.1.0"`

**Use when:** You need reproducibility or a specific feature version.

#### Minimum version requirement

Ensure at least a certain version:

```bash
cg constraint add "numpy>=1.24.0"
```

**Result:** `numpy = ">=1.24.0"`

**Use when:** You need modern features or bug fixes.

#### Major version cap

Allow minor/patch updates but prevent major version changes:

```bash
cg constraint add "pillow>=9.0.0,<10.0.0"
```

**Result:** `pillow = ">=9.0.0,<10.0.0"`

**Use when:** You want updates but need API stability.

#### Minor version cap

Lock to a specific minor version series:

```bash
cg constraint add "transformers>=4.30.0,<4.31.0"
```

**Result:** `transformers = ">=4.30.0,<4.31.0"`

**Use when:** You need patch updates but want to avoid feature changes.

#### PyTorch with CUDA version

Pin PyTorch to a specific CUDA build:

```bash
cg constraint add "torch==2.1.0+cu121"
```

**Result:** `torch = "==2.1.0+cu121"`

**Use when:** You need a specific CUDA version for GPU compatibility.

!!! tip "Quoting version specifiers"
    Always quote constraints with special characters:
    ```bash
    cg constraint add "numpy>=1.24"  # ✓ Correct
    cg constraint add numpy>=1.24    # ✗ Shell interprets >
    ```

### Updating existing constraints

Adding a constraint for an existing package updates it:

```bash
# First time
cg constraint add "torch==2.0.0"

# Update to newer version
cg constraint add "torch==2.1.0"
```

The second command replaces the first constraint. No duplicates are created.

## Listing constraints

View all active constraints in your environment:

```bash
cg constraint list
```

**Example output:**

```
Constraint dependencies in 'my-project':
  • torch==2.1.0+cu121
  • numpy>=1.24.0
  • pillow>=9.0.0,<10.0.0
  • opencv-python>=4.8.0
```

### When no constraints exist

```bash
cg constraint list
```

**Output:**

```
No constraint dependencies configured
```

This is normal—most environments start without constraints and add them as needed.

## Removing constraints

Remove version restrictions you no longer need:

```bash
cg constraint remove torch
```

**What happens:**

1. **Removes from pyproject.toml** - Deletes from `[tool.uv.constraint-dependencies]`
2. **Package stays installed** - Doesn't uninstall the package
3. **Next resolution is unconstrained** - Future updates can choose any version

**Example output:**

```
🗑 Removing constraints: torch

✓ Removed 1 constraint(s) from pyproject.toml
```

### Removing multiple constraints

Remove several constraints at once:

```bash
cg constraint remove torch numpy pillow
```

### Removing non-existent constraints

ComfyGit safely handles constraints that don't exist:

```bash
cg constraint remove nonexistent
```

**Output:**

```
🗑 Removing constraints: nonexistent
   Warning: constraint 'nonexistent' not found

✓ Removed 0 constraint(s) from pyproject.toml
```

No error—the operation is idempotent.

## Common use cases

### Resolving node conflicts

Two nodes require incompatible package versions:

```bash
# Check what's conflicting
cg node add node-b

# Output:
# ✗ Dependency conflict:
#   torch==2.0.0 (required by node-a)
#   conflicts with torch>=2.1.0 (required by node-b)

# Add constraint to force compatible version
cg constraint add "torch==2.1.0"

# Now both nodes can install
cg node add node-b --yes
```

See [Resolving Node Conflicts](../custom-nodes/node-conflicts.md) for detailed conflict resolution strategies.

### Establishing a compatibility baseline

Set constraints before adding nodes to prevent conflicts:

```bash
# Set your environment's foundation
cg constraint add "torch==2.1.0+cu121"
cg constraint add "numpy>=1.24.0,<2.0.0"
cg constraint add "pillow>=9.0.0,<10.0.0"

# Now add nodes—they'll all use compatible versions
cg node add comfyui-impact-pack
cg node add comfyui-controlnet-aux
cg node add comfyui-animatediff
```

This prevents conflicts by establishing version requirements upfront.

### Locking PyTorch backend

Pin PyTorch to a specific CUDA version for your GPU:

```bash
# CUDA 12.1
cg constraint add "torch==2.1.0+cu121"
cg constraint add "torchvision==0.16.0+cu121"
cg constraint add "torchaudio==2.1.0+cu121"

# Or CUDA 11.8
cg constraint add "torch==2.1.0+cu118"
cg constraint add "torchvision==0.16.0+cu118"
cg constraint add "torchaudio==2.1.0+cu118"

# Or CPU-only
cg constraint add "torch==2.1.0+cpu"
cg constraint add "torchvision==0.16.0+cpu"
cg constraint add "torchaudio==2.1.0+cpu"
```

Ensures all nodes use the same PyTorch backend.

### Preventing unwanted upgrades

Keep packages stable while allowing patch updates:

```bash
# Lock to transformers 4.30.x
cg constraint add "transformers>=4.30.0,<4.31.0"

# Lock to diffusers 0.21.x
cg constraint add "diffusers>=0.21.0,<0.22.0"
```

Useful when newer versions have breaking changes or regressions.

### Forcing modern package versions

Ensure all dependencies use recent versions:

```bash
# Require Python 3.10+ features
cg constraint add "numpy>=1.24.0"
cg constraint add "scipy>=1.11.0"
cg constraint add "pillow>=10.0.0"
```

Prevents nodes from dragging in old dependencies.

### Working with local package indexes

Combine with custom indexes for air-gapped environments:

```bash
# Add constraint for package from custom index
cg constraint add "internal-package>=1.0.0"

# The constraint applies when installing from custom index
cg py add internal-package
```

## Advanced patterns

### Constraints from file

Create a constraints file for reusable baselines:

**constraints.txt:**

```txt
torch==2.1.0+cu121
torchvision==0.16.0+cu121
torchaudio==2.1.0+cu121
numpy>=1.24.0,<2.0.0
pillow>=9.0.0,<10.0.0
opencv-python>=4.8.0
transformers>=4.30.0,<5.0.0
diffusers>=0.21.0,<1.0.0
```

**Apply all constraints:**

```bash
# Read file and add each constraint
while IFS= read -r constraint; do
  [[ "$constraint" =~ ^#.*$ || -z "$constraint" ]] && continue
  cg constraint add "$constraint"
done < constraints.txt
```

Or add manually:

```bash
cg constraint add \
  "torch==2.1.0+cu121" \
  "numpy>=1.24.0,<2.0.0" \
  "pillow>=9.0.0,<10.0.0"
```

### Environment-specific constraints

Different environments with different GPU capabilities:

```bash
# Development machine (CUDA 12.1)
cg -e dev-env constraint add "torch==2.1.0+cu121"

# Production server (CUDA 11.8)
cg -e prod-env constraint add "torch==2.1.0+cu118"

# CPU-only testing
cg -e test-env constraint add "torch==2.1.0+cpu"
```

### Temporary constraints for testing

Test if a version works before committing:

```bash
# Add constraint
cg constraint add "experimental-pkg==0.1.0-beta"

# Test installation
cg node add test-node

# If it doesn't work, remove constraint
cg constraint remove experimental-pkg

# Try different version
cg constraint add "experimental-pkg==0.0.9"
```

### Constraints with node installation

Apply constraint only for specific node installation:

```bash
# Add constraint before node
cg constraint add "torch>=2.1.0"
cg node add cuda-heavy-node

# Remove constraint after (if not needed globally)
cg constraint remove torch
```

## Troubleshooting

### Constraint blocks all installations

**Error:**

```
✗ Failed to add node
   No version of 'torch' satisfies constraint torch==2.0.0
   and requirement torch>=2.1.0 (from node-b)
```

**Cause:** Constraint is too restrictive for a dependency.

**Solution:**

1. **Check constraint:**
   ```bash
   cg constraint list
   ```

2. **Remove or relax constraint:**
   ```bash
   cg constraint remove torch
   # Or relax to range:
   cg constraint add "torch>=2.0.0,<3.0.0"
   ```

3. **Retry installation:**
   ```bash
   cg node add node-b
   ```

### Package still uses old version

**Scenario:** You added a constraint but package version didn't change.

**Cause:** Constraints don't trigger reinstallation—they only affect future resolutions.

**Solution:**

Force re-resolution with repair:

```bash
# View current state
cg status

# Apply constraints by syncing environment
cg repair --yes
```

This will sync packages to satisfy the new constraints.

### Conflicting constraints

**Error:**

```
✗ Failed to resolve dependencies
   torch==2.0.0 conflicts with torch==2.1.0
```

**Cause:** You have multiple constraints for the same package with incompatible versions.

**Solution:**

1. **List constraints:**
   ```bash
   cg constraint list
   ```

2. **Identify duplicates or conflicts** (shouldn't happen normally, but check)

3. **Remove and re-add with correct version:**
   ```bash
   cg constraint remove torch
   cg constraint add "torch==2.1.0"
   ```

### Constraint not taking effect

**Scenario:** Added constraint but node still installs different version.

**Cause:** Constraint syntax might be incorrect or package name mismatch.

**Solution:**

1. **Verify constraint was added:**
   ```bash
   cg constraint list
   ```

2. **Check package name spelling:**
   ```bash
   # Wrong:
   cg constraint add "pytorch==2.1.0"

   # Correct:
   cg constraint add "torch==2.1.0"
   ```

3. **Check version specifier syntax:**
   ```bash
   # Valid:
   cg constraint add "numpy>=1.24.0"     # ✓
   cg constraint add "pillow>=9.0,<10.0"  # ✓

   # Invalid:
   cg constraint add "numpy>1.24"        # Missing .0
   cg constraint add "pillow=>9.0"       # Wrong operator
   ```

### Repair fails after adding constraint

**Error:**

```
✗ Failed to repair environment
   Could not resolve dependencies
```

**Cause:** Constraint is incompatible with existing dependencies.

**Solution:**

1. **Check what's installed:**
   ```bash
   cg py list --all
   ```

2. **Remove conflicting constraint:**
   ```bash
   cg constraint remove problematic-package
   ```

3. **Try repair again:**
   ```bash
   cg repair --yes
   ```

4. **If still fails, check node conflicts:**
   ```bash
   cg status
   ```

See [Node Conflicts](../custom-nodes/node-conflicts.md#troubleshooting-common-scenarios) for detailed resolution steps.

## How it works

### Behind the scenes

When you run `cg constraint add`:

1. **Reads pyproject.toml** - Loads current configuration
2. **Updates or adds constraint** - Modifies `[tool.uv.constraint-dependencies]`
3. **Writes to disk** - Saves changes to `.cec/pyproject.toml`
4. **Tracks in git** - Changes ready to commit

**Example pyproject.toml:**

```toml
[tool.uv.constraint-dependencies]
torch = "==2.1.0+cu121"
numpy = ">=1.24.0,<2.0.0"
pillow = ">=9.0.0,<10.0.0"
```

### Constraints vs dependencies

**Dependencies** (`[project.dependencies]`):
- Install packages in your environment
- Show up in `cg py list`
- Required for your code to run
- Added with `cg py add`

**Constraints** (`[tool.uv.constraint-dependencies]`):
- Restrict versions during resolution
- Don't install anything themselves
- Applied to all dependencies
- Added with `cg constraint add`

**Example showing both:**

```toml
[project.dependencies]
# These packages ARE installed
requests = ">=2.28.0"

[tool.uv.constraint-dependencies]
# These are version restrictions applied during resolution
urllib3 = ">=1.26.0,<2.0.0"  # Constrains requests' dependency
```

Even though you didn't explicitly add `urllib3` as a dependency, the constraint affects what version `requests` can use for its `urllib3` dependency.

### UV resolution with constraints

UV's resolution algorithm:

1. **Collects requirements** from:
   - `[project.dependencies]`
   - Node groups (`[project.optional-dependencies]`)
   - Transitive dependencies

2. **Applies constraints** from `[tool.uv.constraint-dependencies]`

3. **Finds compatible versions** that satisfy all requirements + constraints

4. **Fails if impossible** to satisfy everything simultaneously

**Example:**

```toml
[project.dependencies]
node-a-dep = "*"  # Wants torch>=2.0.0

[project.optional-dependencies]
"node/node-b" = ["torch>=2.1.0"]

[tool.uv.constraint-dependencies]
torch = "==2.1.0"
```

**Resolution:**
- `node-a-dep` wants `torch>=2.0.0` → `2.1.0` satisfies
- `node-b` wants `torch>=2.1.0` → `2.1.0` satisfies
- Constraint forces `torch==2.1.0` → Final version: `2.1.0` ✓

### Relationship to repair

The `cg repair` command re-syncs your environment to match `pyproject.toml`:

```bash
# Add constraint
cg constraint add "torch==2.1.0"

# Constraint is in pyproject.toml but not applied yet

# Apply constraint by repairing
cg repair --yes
```

This triggers UV to re-resolve with the new constraint and install the correct versions.

## Best practices

### Start broad, narrow as needed

Begin with minimal constraints:

```bash
# Start with no constraints
cg node add node-a node-b node-c

# Only add constraints when conflicts arise
# (ComfyGit will tell you if there's a conflict)
```

Add constraints reactively rather than preemptively.

### Use version ranges over exact pins

Prefer ranges for flexibility:

```bash
# More flexible (allows patch updates)
cg constraint add "numpy>=1.24.0,<2.0.0"

# Less flexible (locked to exact version)
cg constraint add "numpy==1.24.3"
```

Use exact pins only when necessary (PyTorch CUDA versions, known bugs).

### Document your constraints

Add comments to your pyproject.toml explaining why:

```toml
[tool.uv.constraint-dependencies]
# Pin PyTorch for CUDA 12.1 compatibility with RTX 4090
torch = "==2.1.0+cu121"

# Prevent numpy 2.0 due to breaking changes in node-x
numpy = ">=1.24.0,<2.0.0"

# Lock pillow to v9 due to regression in v10 loading certain formats
pillow = ">=9.5.0,<10.0.0"
```

Helps future you understand the reasoning.

### Keep constraints in version control

Commit constraint changes with descriptive messages:

```bash
# Add constraint
cg constraint add "torch==2.1.0+cu121"

# Commit with context
cg commit -m "Pin PyTorch to 2.1.0+cu121 for CUDA 12.1 support"
```

### Review constraints periodically

Constraints can become outdated:

```bash
# List all constraints
cg constraint list

# Remove ones that are no longer needed
cg constraint remove old-package

# Update versions to more recent ranges
cg constraint add "numpy>=1.26.0,<2.0.0"
```

### Test after changing constraints

Verify environment still works:

```bash
# Change constraint
cg constraint add "torch==2.2.0"

# Apply changes
cg repair --yes

# Test ComfyUI starts
cg run
```

Catch issues early before committing.

## Next steps

- **[Py Commands](py-commands.md)** - Manage Python dependencies
- **[Node Conflicts](../custom-nodes/node-conflicts.md)** - Resolve conflicts between custom nodes
- **[Version Control](../environments/version-control.md)** - Commit and track constraint changes
- **[Environment Repair](../environments/version-control.md#repairing-environments)** - Apply constraints with repair
