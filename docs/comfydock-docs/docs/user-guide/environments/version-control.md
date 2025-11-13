# Version Control

> Use git-based version control to track, commit, and rollback changes to your environment configuration. Every environment is a git repository.

## Overview

ComfyGit gives each environment its own git repository in the `.cec/` directory. This tracks:

* **Custom nodes** — Which nodes are installed and their versions
* **Python dependencies** — Packages from `pyproject.toml`
* **Workflows** — Workflow JSON files you've created or modified
* **Model references** — Model download URLs and importance settings
* **Constraints** — Version pins and dependency constraints

Changes are tracked automatically — you just commit when ready.

## The .cec directory

Each environment has a `.cec/` directory:

```
~/comfygit/environments/my-env/.cec/
├── .git/                   # Git repository
├── pyproject.toml          # Dependencies and nodes
├── uv.lock                 # Locked dependency versions
├── workflows/              # Tracked workflow files
└── .python-version         # Python version pin
```

This entire directory is version controlled. When you commit, you're committing changes to these files.

## Checking for changes

See what's changed since your last commit:

```bash
cg status
```

**Clean environment:**

```
Environment: my-env ✓

✓ No workflows
✓ No uncommitted changes
```

**With uncommitted changes:**

```
Environment: my-env

⚠ Uncommitted changes:

  Custom Nodes:
    + comfyui-impact-pack

  Python Packages:
    + ultralytics (any)

💡 Next:
  Commit changes: cg commit -m "<message>"
```

## Committing changes

### Basic commit

Save your current environment state:

```bash
cg commit -m "Added impact pack for face detailing"
```

**Output:**

```
📋 Analyzing workflows...
✅ Commit successful: Added impact pack for face detailing
  • Added 1 workflow(s)
```

### Auto-generated commit message

Let ComfyGit generate a message:

```bash
cg commit
```

Generates messages like:

* "Update workflows"
* "Add custom nodes"
* "Update dependencies"

!!! tip "Descriptive messages"
    Use descriptive commit messages for easier version navigation:
    ```bash
    cg commit -m "Added IPAdapter nodes for style transfer"
    cg commit -m "Pinned torch to 2.4.1 for stability"
    cg commit -m "Removed unused video nodes"
    ```

### What gets committed

A commit captures:

1. **Node changes** — Additions, removals, updates
2. **Dependency changes** — Python packages added/removed/updated
3. **Workflow changes** — New, modified, or deleted workflow files
4. **Constraint changes** — Version pins added/removed
5. **Model metadata** — Download URLs and importance settings

**Example commit:**

```bash
# Add a node
cg node add comfyui-impact-pack

# Check status
cg status
# Shows: + comfyui-impact-pack under Custom Nodes

# Commit
cg commit -m "Added impact pack"
```

### Workflow issues and commits

ComfyGit blocks commits if workflows have unresolved issues:

**Blocked commit:**

```bash
cg commit -m "Update workflow"
```

**Output:**

```
📋 Analyzing workflows...

⚠ Cannot commit - workflows have unresolved issues:

  • portrait.json: 2 nodes unresolved, 1 models not found

💡 Options:
  1. Resolve issues: cg workflow resolve "portrait"
  2. Force commit: cg commit -m 'msg' --allow-issues
```

**Option 1: Resolve first (recommended)**

```bash
# Fix the issues
cg workflow resolve portrait

# Then commit
cg commit -m "Updated portrait workflow"
```

**Option 2: Force commit**

```bash
# Commit anyway (not recommended)
cg commit -m "WIP: portrait workflow" --allow-issues
```

!!! warning "Allow issues flag"
    Using `--allow-issues` commits broken workflows. Only use this for work-in-progress commits. Fix issues before sharing the environment.

## Viewing commit history

### Compact format (default)

```bash
cg commit log
```

**Output:**

```
Version history for environment 'my-env':

v3: Removed unused video nodes
v2: Added IPAdapter for style transfer
v1: Added impact pack for face detailing

Use 'cg rollback <version>' to restore to a specific version
```

### Verbose format

See full details:

```bash
cg commit log --verbose
```

**Output:**

```
Version history for environment 'my-env':

Version: v3
Message: Removed unused video nodes
Date:    2025-11-03 14:23:45
Commit:  a1b2c3d4


Version: v2
Message: Added IPAdapter for style transfer
Date:    2025-11-03 12:10:33
Commit:  e5f6g7h8


Version: v1
Message: Added impact pack for face detailing
Date:    2025-11-03 09:15:22
Commit:  i9j0k1l2

Use 'cg rollback <version>' to restore to a specific version
```

## Rolling back changes

### Discard uncommitted changes

Undo all changes since last commit:

```bash
cg rollback
```

**Confirmation prompt:**

```
⏮ Discarding uncommitted changes in environment 'my-env'

This will discard all changes since your last commit:
  • Custom nodes added/removed
  • Dependencies changed
  • Workflows modified

Continue? (y/N):
```

Type `y` and press Enter.

**Output:**

```
✓ Rollback complete

Uncommitted changes have been discarded
• Environment is now clean and matches the last commit
• Run 'cg commit log' to see version history
```

**Skip confirmation:**

```bash
cg rollback --yes
```

### Rollback to specific version

Restore environment to a previous commit:

```bash
# Rollback to v2
cg rollback v2
```

**Confirmation prompt:**

```
⏮ Rolling back environment 'my-env' to v2

This will:
  • Restore pyproject.toml to v2
  • Reset workflows to v2 state
  • Update environment to match v2 dependencies

Current state will be lost unless committed first.

Continue? (y/N):
```

**Output:**

```
✓ Rollback complete

Environment is now at version v2
• Run 'cg commit -m "message"' to save any new changes
• Run 'cg commit log' to see version history
```

**What happens:**

1. Git checks out the specified version in `.cec/`
2. `pyproject.toml` is restored to that version
3. Workflows are restored to that version
4. Environment is auto-repaired to match the restored configuration

**Skip confirmation:**

```bash
cg rollback v2 --yes
```

## Pushing to remotes

Share your environment with others via git remotes.

### Adding a remote

```bash
# Add a remote repository
cg remote add origin https://github.com/username/my-env.git
```

### Pushing commits

```bash
cg push origin
```

**Pre-flight checks:**

```
✗ You have uncommitted changes

💡 Commit first:
   cg commit -m 'your message'
```

After committing:

```bash
cg push origin
```

**Output:**

```
📤 Pushing to origin...
   ✓ Pushed commits to origin

💾 Remote: https://github.com/username/my-env.git
```

### Force push

Overwrite remote history (use with caution):

```bash
cg push origin --force
```

!!! warning "Force push"
    Only force push if you're sure. This rewrites history and can cause issues for collaborators.

## Pulling from remotes

Update your environment from a remote repository.

### Basic pull

```bash
cg pull origin
```

**Pre-flight checks:**

```
✗ You have uncommitted changes

💡 Options:
  • Commit: cg commit -m 'message'
  • Discard: cg rollback
  • Force: cg pull origin --force
```

After committing or discarding:

```bash
cg pull origin
```

**Output:**

```
📥 Pulling from origin...
  [1/2] Installing comfyui-controlnet-aux... ✓
  [2/2] Installing comfyui-ipadapter-plus... ✓

✓ Pulled changes from origin
   • Installed 2 node(s)

⚙️  Environment synced successfully
```

**What happens:**

1. Pulls latest commits from remote
2. Merges changes into `.cec/`
3. Automatically runs `cg repair` to sync environment
4. Installs missing nodes
5. Downloads missing models (if configured)

### Force pull

Discard local changes and pull:

```bash
cg pull origin --force
```

### Handling merge conflicts

If both you and a remote have changes:

```
✗ Merge conflict detected

💡 To resolve:
   1. cd ~/comfygit/environments/my-env/.cec
   2. git status  # See conflicted files
   3. Edit conflicts and resolve
   4. git add <resolved-files>
   5. git commit
   6. cg repair  # Sync environment
```

**Resolution steps:**

```bash
# Navigate to .cec
cd ~/comfygit/environments/my-env/.cec

# See conflicts
git status

# Edit conflicted files (usually pyproject.toml)
# Look for conflict markers: <<<<<<<, =======, >>>>>>>
# Keep the changes you want

# Stage resolved files
git add pyproject.toml

# Commit the merge
git commit -m "Merged remote changes"

# Return to workspace
cd ~/comfydock

# Sync environment
cg repair
```

## Repairing environments

Sync environment filesystem to match `pyproject.toml`:

```bash
cg repair
```

**When to use:**

* After manual edits to `pyproject.toml`
* After `git pull` or `rollback`
* When nodes aren't loading
* After resolving git conflicts

**Example:**

```bash
# Manually edit .cec/pyproject.toml
# Add a dependency or change a node URL

# Sync environment
cg repair
```

**Output:**

```
🔧 Syncing environment to pyproject.toml...

Preview:
  Nodes to install:
    + comfyui-manager

  Python packages to install:
    + requests (>=2.31.0)

Continue? (y/N): y

  [1/1] Installing comfyui-manager... ✓

✅ Environment synced successfully
   • Installed 1 node(s)
   • Installed 1 package(s)
```

**Skip confirmation:**

```bash
cg repair --yes
```

## Common workflows

### Experiment and commit

```bash
# Make changes
cg node add experimental-node

# Test it
cg run
# Try it out...

# Good? Commit
cg commit -m "Added experimental node - works great"

# Bad? Rollback
cg rollback
```

### Feature branch workflow

```bash
# Create environment for feature
cg create feature-xyz --use

# Make changes
cg node add new-feature-node
cg commit -m "Added feature node"

# More changes
cg node add another-node
cg commit -m "Added supporting node"

# Test
cg run

# Good? Push
cg remote add origin https://github.com/me/feature-xyz.git
cg push origin

# Share link with team
```

### Safe experimentation

```bash
# Current state
cg commit -m "Stable state before experiment"

# Try something risky
cg node add untested-node
cg run
# Doesn't work...

# Rollback
cg rollback

# Back to stable state
```

### Team collaboration

**Team member 1:**

```bash
# Create environment
cg create project-x

# Add nodes
cg node add comfyui-ipadapter-plus
cg commit -m "Initial setup with IPAdapter"

# Push
cg remote add origin https://github.com/team/project-x.git
cg push origin
```

**Team member 2:**

```bash
# Import from git
cg import https://github.com/team/project-x.git --name project-x

# Make changes
cg node add comfyui-controlnet-aux
cg commit -m "Added ControlNet support"

# Push
cg push origin
```

**Team member 1:**

```bash
# Pull changes
cg pull origin

# Nodes are auto-installed
# Continue working...
```

## Version control best practices

### Commit early and often

```bash
# After each logical change
cg node add some-node
cg commit -m "Added some-node for X feature"

# Not after 10 changes
cg node add node1
cg node add node2
# ... 8 more changes
cg commit -m "Updated everything"  # Bad!
```

### Use descriptive messages

**Good:**

* "Added ComfyUI-Manager for node management"
* "Pinned PyTorch to 2.4.1 for CUDA 12.8 compatibility"
* "Removed deprecated ControlNet nodes"
* "Updated portrait workflow with better face detailing"

**Bad:**

* "Update"
* "Changes"
* "WIP"
* "asdf"

### Test before committing

```bash
# Make changes
cg node add new-node

# Test
cg run
# Verify it works...

# Good? Commit
cg commit -m "Added new-node"

# Bad? Fix first or rollback
```

### Commit workflow changes separately

```bash
# Bad: mixing concerns
cg node add ipadapter
# Edit workflow in ComfyUI...
cg commit -m "Updated everything"

# Good: separate commits
cg node add ipadapter
cg commit -m "Added IPAdapter node"
# Edit workflow...
cg commit -m "Updated portrait workflow to use IPAdapter"
```

## Troubleshooting

### Can't commit - no changes detected

**Symptom:** `✓ No changes to commit`

**Cause:** Nothing has changed in `.cec/` since last commit

**Check:**

```bash
cg status
# Should show uncommitted changes if any exist
```

### Rollback doesn't work

**Symptom:** Rollback command fails or doesn't restore properly

**Solutions:**

```bash
# Check git status manually
cd ~/comfygit/environments/my-env/.cec
git status

# Force clean
git reset --hard HEAD

# Return and repair
cd ~/comfydock
cg repair
```

### Push rejected

**Symptom:** Remote rejects push

**Cause:** Remote has commits you don't have locally

**Solution:**

```bash
# Pull first
cg pull origin

# Resolve conflicts if any
# Then push
cg push origin
```

### Lost changes after rollback

**Symptom:** Rolled back but want changes back

**Solution:**

```bash
# Git never forgets - find your commit
cd ~/comfygit/environments/my-env/.cec
git reflog

# Find the commit hash
# Restore it
git checkout <commit-hash>

# Or cherry-pick specific changes
git cherry-pick <commit-hash>

# Return to comfydock
cd ~/comfydock
cg repair
```

## Next steps

Master version control, then explore:

* **[Custom Nodes](../custom-nodes/adding-nodes.md)** — Install and manage extensions
* **[Workflows](../workflows/workflow-resolution.md)** — Resolve dependencies automatically
* **[Collaboration](../collaboration/git-remotes.md)** — Share environments with team

## See also

* [Git Remotes](../collaboration/git-remotes.md) — Detailed remote management
* [Export & Import](../collaboration/export-import.md) — Tarball-based sharing
* [CLI Reference](../../cli-reference/environment-commands.md) — Complete command docs
