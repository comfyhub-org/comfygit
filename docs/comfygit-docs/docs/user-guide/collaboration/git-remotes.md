# Git Remotes

Collaborate continuously with team members by pushing and pulling environment changes through git remotes.

## Overview

Git remotes enable real-time collaboration by syncing environment versions through a shared git repository. Each environment has its own git repository in the `.cec/` directory that tracks:

- Environment configuration (`pyproject.toml`)
- Python dependencies (`uv.lock`)
- Workflows (`.cec/workflows/*.json`)
- Version history (git commits)

This is ideal for:

- **Team development**: Multiple people working on the same environment
- **Version tracking**: Full git history of environment changes
- **Branch workflows**: Develop features in branches, merge to main
- **Continuous sync**: Push/pull updates as you work

Unlike export/import (which creates one-time snapshots), git remotes enable ongoing collaboration with full version control.

---

## Managing Remotes

Each environment can have multiple git remotes for pushing and pulling changes.

### Adding a Remote

Add a remote repository to your environment:

```bash
cg -e my-env remote add origin https://github.com/user/comfy-env.git
```

**Output:**

```
✓ Added remote 'origin': https://github.com/user/comfy-env.git
```

**Common remote names:**

- `origin`: Primary remote (convention from git)
- `upstream`: Upstream repository for forks
- `backup`: Backup location

!!! note "Environment-Specific"
    Remotes are configured per-environment. Each environment has its own git repository and remote configuration.

### Listing Remotes

View all configured remotes:

```bash
cg -e my-env remote list
```

**Output:**

```
Remotes:
  origin    https://github.com/user/comfy-env.git (fetch)
  origin    https://github.com/user/comfy-env.git (push)
  backup    git@gitlab.com:user/comfy-backup.git (fetch)
  backup    git@gitlab.com:user/comfy-backup.git (push)
```

Each remote shows separate fetch and push URLs (usually the same).

### Removing a Remote

Remove a remote that's no longer needed:

```bash
cg -e my-env remote remove backup
```

**Output:**

```
✓ Removed remote 'backup'
```

---

## Pushing Changes

Push commits to a remote repository to share your environment updates.

### Basic Push

Push to the default remote (`origin`):

```bash
cg -e my-env push
```

**Output:**

```
Pushing to origin/main
✓ Push complete
```

Changes are now visible to anyone with access to the remote repository.

### Push to Specific Remote

Push to a named remote:

```bash
cg -e my-env push -r upstream
```

### Push with Force

Force push when you need to overwrite remote history (use carefully):

```bash
cg -e my-env push --force
```

!!! warning "Force Push Safety"
    Force push uses `--force-with-lease` to prevent overwriting others' changes. It only succeeds if the remote branch hasn't been updated since your last fetch.

---

## Push Requirements

ComfyGit ensures safe pushes by validating your environment state.

### Clean Working Directory

Push requires all changes to be committed:

```bash
cg -e my-env push
```

**If uncommitted changes exist:**

```
✗ Cannot push with uncommitted changes.
  Run: cg commit -m 'message' first
```

**Fix:**

```bash
cg -e my-env commit -m "Add new workflow"
cg -e my-env push
```

This includes both git changes (in `.cec/`) and workflow changes (in `ComfyUI/`).

### Remote Configuration

Push fails if no remote is configured:

```
✗ Push failed: No remote 'origin' configured
```

**Fix:**

```bash
cg -e my-env remote add origin <url>
cg -e my-env push
```

### Authentication

Push may fail with authentication errors:

```
✗ Push failed: Authentication failed for 'https://github.com/user/repo.git'
```

**Solutions:**

1. **Use SSH**: Configure git to use SSH keys
   ```bash
   cg -e my-env remote remove origin
   cg -e my-env remote add origin git@github.com:user/repo.git
   ```

2. **Use credential helper**: Configure git credential storage
   ```bash
   git config --global credential.helper store
   ```

3. **Personal access token**: Use GitHub/GitLab personal access tokens instead of passwords

---

## Pulling Changes

Pull fetches changes from a remote and merges them into your environment.

### Basic Pull

Pull from the default remote (`origin`):

```bash
cg -e my-env pull
```

**Output:**

```
📥 Pulling from origin/main

⬇️  Fetching changes from remote
✓ Merged 3 commits

🔄 Reconciling environment with pulled changes

📦 Installing nodes
  [1/2] Installing rgthree-comfy... ✓
  [2/2] Installing was-node-suite-comfyui... ✓

🔧 Syncing Python packages
✓ Python environment synced

📝 Restoring workflows
✓ Workflows synced to ComfyUI

⏭ Auto-committing post-pull state
✓ Pull complete: environment synced to latest
```

The pull process:

1. **Fetches** changes from remote
2. **Merges** into local branch
3. **Reconciles** nodes (install/remove based on changes)
4. **Syncs** Python packages to match `uv.lock`
5. **Restores** workflows from `.cec` to `ComfyUI/`
6. **Commits** the merged state as a new version

### Pull from Specific Remote

Pull from a named remote:

```bash
cg -e my-env pull -r upstream
```

---

## Pull Reconciliation

Pull doesn't just update git files—it reconciles your entire environment to match the pulled configuration.

### What Gets Reconciled

After merging git changes, ComfyGit updates:

**Custom Nodes:**

- **Added nodes**: Installed automatically from registry/git
- **Removed nodes**: Uninstalled and cleaned up
- **Version changes**: Updated to match new commit

**Python Packages:**

- **Dependencies synced**: Matches `uv.lock` from remote
- **Groups installed**: All dependency groups reconciled

**Workflows:**

- **New workflows**: Copied from `.cec/workflows/` to `ComfyUI/`
- **Updated workflows**: Overwritten with tracked versions
- **Deleted workflows**: Removed from `ComfyUI/`

!!! note "Working Directory Overwrite"
    Pull overwrites `ComfyUI/` workflows with tracked versions from `.cec/`. Uncommitted workflow changes are lost unless you commit first.

### Example: Node Reconciliation

**Scenario:** Remote added `was-node-suite-comfyui` and removed `comfyui-manager`.

**Pull output:**

```
🔄 Reconciling environment with pulled changes

📦 Installing nodes
  [1/1] Installing was-node-suite-comfyui... ✓

🗑️  Removing nodes
  [1/1] Removing comfyui-manager... ✓
```

Your local environment now matches the remote configuration.

---

## Model Download Strategy

Control whether pull downloads new model dependencies.

### Strategy: All (Default)

Downloads all models referenced in pulled workflows:

```bash
cg -e my-env pull
```

Automatically resolves and downloads any new model dependencies.

### Strategy: Required

Downloads only required models:

```bash
cg -e my-env pull --models required
```

Skips optional and flexible models.

### Strategy: Skip

Skips all model downloads:

```bash
cg -e my-env pull --models skip
```

Models are tracked as download intents. Resolve later:

```bash
cg -e my-env workflow resolve --all
```

---

## Pull Requirements

Pull requires a clean working directory to prevent conflicts.

### Clean State Required

Pull fails if you have uncommitted changes:

```bash
cg -e my-env pull
```

**If changes exist:**

```
✗ Cannot pull with uncommitted changes.
Uncommitted changes detected:
  • Git changes in .cec/
  • Workflow changes in ComfyUI

Commit first:
  cg commit -m 'message'
```

**Fix:**

```bash
cg -e my-env commit -m "Save local changes"
cg -e my-env pull
```

### Force Pull

Discard local changes and force pull:

```bash
cg -e my-env pull --force
```

!!! danger "Data Loss Warning"
    Force pull discards ALL uncommitted changes (git and workflows). Use with caution.

---

## Merge Conflicts

Git merge conflicts require manual resolution.

### Detecting Conflicts

Pull fails when conflicts occur:

```
✗ Pull failed: Merge conflict in pyproject.toml
```

### Resolving Conflicts

1. **View conflicts**:
   ```bash
   cd ~/comfygit/environments/my-env/.cec
   git status
   ```

2. **Edit conflicted files** to resolve conflicts:
   ```bash
   nano pyproject.toml
   ```

   Look for conflict markers:
   ```toml
   <<<<<<< HEAD
   [tool.comfygit.nodes]
   "my-node" = { source = "registry" }
   =======
   [tool.comfygit.nodes]
   "other-node" = { source = "registry" }
   >>>>>>> origin/main
   ```

3. **Stage resolved files**:
   ```bash
   git add pyproject.toml
   ```

4. **Commit the merge**:
   ```bash
   git commit -m "Merge remote changes"
   ```

5. **Sync environment**:
   ```bash
   cg -e my-env sync
   ```

!!! tip "Avoiding Conflicts"
    - Pull frequently to stay up-to-date
    - Communicate with team about major changes
    - Use branches for experimental work

---

## Rollback on Failure

If pull fails after merging, ComfyGit automatically rolls back git changes.

### Automatic Rollback

**Scenario:** Pull succeeds in merging, but node installation fails.

**Output:**

```
✗ Pull failed: Could not install rgthree-comfy - network error
Rolling back git changes...
✓ Rollback complete: environment restored to pre-pull state
```

Your environment is restored to exactly how it was before the pull attempt.

### What Gets Rolled Back

- **Git files**: `pyproject.toml`, `uv.lock`, workflows restored
- **Environment state**: Nodes, packages unchanged

This ensures pull is atomic—it either succeeds completely or reverts entirely.

---

## Version History

Each push and pull creates versions in your environment history.

### View Version History

See past versions:

```bash
cg -e my-env commit log
```

**Output:**

```
Recent versions:

  v12 (2025-01-09 10:23:41)
    Merge remote changes
    [abc1234]

  v11 (2025-01-09 09:15:22)
    Add ControlNet workflow
    [def5678]

  v10 (2025-01-08 16:42:10)
    Update node dependencies
    [ghi9012]
```

Each pull creates a new version by auto-committing the merged state.

### Rollback to Version

Restore to a previous version:

```bash
cg -e my-env rollback v10
```

This creates a new version (v13) that matches v10's state. See [Version Control](../environments/version-control.md) for details.

---

## Common Workflows

### Initial Setup (Team Lead)

Create an environment and set up remote:

```bash
# 1. Create environment
cg create team-env

# 2. Configure environment (add nodes, workflows, etc.)
cg -e team-env node add rgthree-comfy
cg -e team-env commit -m "Initial setup"

# 3. Add remote
cg -e team-env remote add origin https://github.com/team/comfy-env.git

# 4. Push to remote
cg -e team-env push
```

Team members can now clone or pull from this remote.

### Daily Workflow (Team Member)

Stay synced with team changes:

```bash
# 1. Pull latest changes
cg -e team-env pull

# 2. Make your changes
cg -e team-env node add custom-node
# ... work on workflows ...

# 3. Commit your changes
cg -e team-env commit -m "Add custom node for feature X"

# 4. Push to share with team
cg -e team-env push
```

### Joining Team (New Member)

Two options for new team members:

**Option 1: Import from git**

```bash
cg import https://github.com/team/comfy-env.git --name team-env
```

**Option 2: Clone manually + pull**

```bash
# Create empty environment
cg create team-env

# Add remote
cg -e team-env remote add origin https://github.com/team/comfy-env.git

# Pull initial state
cg -e team-env pull
```

---

## Troubleshooting

### Push Rejected (Non-Fast-Forward)

**Problem:** Remote has commits you don't have.

```
✗ Push failed: Updates were rejected because the remote contains work that you do not have locally
```

**Solution:** Pull first, then push:

```bash
cg -e my-env pull
cg -e my-env push
```

If conflicts occur during pull, resolve them manually.

---

### Pull Fails: Detached HEAD

**Problem:** Environment is in detached HEAD state.

```
✗ Pull failed: Cannot pull in detached HEAD state
```

**Solution:** Return to a branch:

```bash
cd ~/comfygit/environments/my-env/.cec
git checkout main
cd -
cg -e my-env pull
```

---

### Authentication Repeatedly Prompts

**Problem:** Git keeps asking for credentials.

**Solution:** Configure credential caching:

```bash
# Cache credentials for 1 hour
git config --global credential.helper 'cache --timeout=3600'

# Or store credentials permanently (less secure)
git config --global credential.helper store
```

---

### Remote Already Exists

**Problem:** Trying to add a remote that's already configured.

```
✗ Remote 'origin' already exists
```

**Solution:** Remove first, then re-add:

```bash
cg -e my-env remote remove origin
cg -e my-env remote add origin <new-url>
```

Or update the URL directly in git:

```bash
cd ~/comfygit/environments/my-env/.cec
git remote set-url origin <new-url>
```

---

### Pull Fails: Uncommitted Workflows

**Problem:** You have unsaved workflows in ComfyUI.

```
✗ Cannot pull with uncommitted changes.
Uncommitted changes detected:
  • Workflow changes in ComfyUI
```

**Solutions:**

1. **Commit workflows** (recommended):
   ```bash
   cg -e my-env commit -m "Save current workflows"
   cg -e my-env pull
   ```

2. **Force pull** (discards workflow changes):
   ```bash
   cg -e my-env pull --force
   ```

---

## Best Practices

### Pull Before Push

Always pull before pushing to avoid conflicts:

```bash
cg -e my-env pull
cg -e my-env commit -m "My changes"
cg -e my-env push
```

### Commit Frequently

Small, focused commits make collaboration easier:

```bash
cg -e my-env commit -m "Add ControlNet workflow"
cg -e my-env commit -m "Update node dependencies"
```

Not:

```bash
cg -e my-env commit -m "Lots of changes"
```

### Use Descriptive Messages

Write clear commit messages:

- ✅ "Add SDXL txt2img workflow with ControlNet"
- ✅ "Update IPAdapter to v2.1.0"
- ❌ "Changes"
- ❌ "Update"

### Communicate Major Changes

Before making breaking changes, coordinate with team:

- Removing widely-used nodes
- Changing ComfyUI versions
- Restructuring workflows

### Use Branches for Experiments

Create branches for experimental work:

```bash
cd ~/comfygit/environments/my-env/.cec
git checkout -b experiment-feature
```

Merge to main when ready:

```bash
git checkout main
git merge experiment-feature
cg -e my-env push
```

---

## Next Steps

- [Export and Import](export-import.md) - One-time environment sharing
- [Team Workflows](team-workflows.md) - Collaboration patterns and best practices
- [Version Control](../environments/version-control.md) - Commit and rollback strategies
- [Managing Custom Nodes](../custom-nodes/managing-nodes.md) - Update and remove nodes

---

## Summary

Git remotes enable continuous collaboration:

- **Remotes** connect environments to shared git repositories
- **Push** shares your commits with the team
- **Pull** fetches and merges changes, reconciling your entire environment
- **Requirements** ensure safe operations (clean state, no conflicts)
- **Reconciliation** keeps nodes, packages, and workflows in sync

Use git remotes for active team development with full version history. For one-time sharing, use [Export and Import](export-import.md).
