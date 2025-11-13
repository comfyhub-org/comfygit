# Team Workflows

Best practices and patterns for collaborating on ComfyUI environments with your team.

## Overview

ComfyGit supports multiple collaboration patterns to fit different team structures and workflows. Choose the approach that matches your needs:

- **Tarball Distribution**: One-time sharing via export/import
- **Git Collaboration**: Continuous sync via push/pull
- **Git Import**: Template-based distribution from repositories
- **Hybrid**: Combine approaches for different use cases

This guide provides proven patterns for each scenario.

---

## Choosing a Collaboration Method

### When to Use Tarball Export/Import

**Best for:**

- One-time environment sharing
- Offline environments (no internet access)
- Client deliverables
- Archival and backups
- CI/CD artifacts

**Advantages:**

- Works offline
- No git repository needed
- Self-contained package
- Simple distribution (email, file share, etc.)

**Limitations:**

- No version history
- Manual updates required
- Recipients must re-import for updates

**Pattern:**

```
Creator → Export → .tar.gz → Distribute → Recipients → Import
```

See [Export and Import](export-import.md) for details.

---

### When to Use Git Remotes

**Best for:**

- Active team development
- Continuous collaboration
- Version-controlled workflows
- Branch-based development

**Advantages:**

- Full git history
- Automatic synchronization
- Conflict resolution
- Branch workflows

**Limitations:**

- Requires git repository
- Network access needed
- More complex setup

**Pattern:**

```
Team Member A → Push → Remote → Pull ← Team Member B
```

See [Git Remotes](git-remotes.md) for details.

---

### When to Use Git Import

**Best for:**

- Public workflow templates
- Starter environments
- Reproducible research
- Community distributions

**Advantages:**

- Direct URL import
- Version pinning (branches/tags)
- GitHub/GitLab integration
- Subdirectory support

**Limitations:**

- Read-only (no push back)
- Requires public repository
- One-way distribution

**Pattern:**

```
Public Repo → Import URL → User's Environment
```

See [Export and Import](export-import.md#import-from-git-repository) for details.

---

## Pattern 1: Single Maintainer Distribution

**Scenario:** One person creates and maintains an environment, distributes to team/clients.

### Workflow

**1. Maintainer: Create and Configure**

```bash
# Create environment
cg create production-workflow

# Add custom nodes
cg -e production-workflow node add rgthree-comfy
cg -e production-workflow node add was-node-suite-comfyui

# Add workflows
# ... create workflows in ComfyUI ...

# Commit state
cg -e production-workflow commit -m "Initial production setup"
```

**2. Maintainer: Add Model Sources**

Ensure all models have download URLs:

```bash
# Interactive mode - add sources for all models
cg -e production-workflow model add-source
```

This allows recipients to auto-download models.

**3. Maintainer: Export**

```bash
cg -e production-workflow export production-v1.0.tar.gz
```

**4. Maintainer: Distribute**

Share the tarball via:

- Email attachment
- Cloud storage (Dropbox, Google Drive)
- Internal file share
- CDN for public distribution

**5. Recipients: Import**

```bash
cg import production-v1.0.tar.gz --name production
```

Models download automatically if sources were added.

**6. Updates: New Version**

When updates are needed:

```bash
# Maintainer makes changes
cg -e production-workflow commit -m "v1.1: Add new workflows"
cg -e production-workflow export production-v1.1.tar.gz

# Recipients import new version
cg delete production
cg import production-v1.1.tar.gz --name production
```

---

### Advantages

- Simple mental model (one source of truth)
- No merge conflicts
- Controlled distribution
- Works offline

### Best Practices

1. **Version your exports**: Use clear version numbers in filenames
   ```
   production-v1.0.tar.gz
   production-v1.1.tar.gz
   production-v2.0.tar.gz
   ```

2. **Add model sources**: Always add sources before exporting
   ```bash
   cg model add-source
   ```

3. **Document changes**: Include a CHANGELOG with each export
   ```
   v1.1 (2025-01-09):
   - Added ControlNet workflow
   - Updated ComfyUI to v0.2.7
   - Added IPAdapter nodes
   ```

4. **Test the export**: Import locally to verify completeness
   ```bash
   cg import test.tar.gz --name test-import
   ```

---

## Pattern 2: Active Team Development

**Scenario:** Multiple developers actively collaborating on a shared environment.

### Initial Setup

**1. Team Lead: Create Environment**

```bash
# Create environment
cg create team-env

# Configure environment
cg -e team-env node add rgthree-comfy
cg -e team-env commit -m "Initial setup"
```

**2. Team Lead: Create Git Repository**

Create a repository on GitHub/GitLab/Bitbucket:

```bash
# On GitHub/GitLab, create an empty repository: team-env
```

**3. Team Lead: Push Initial State**

```bash
# Add remote
cg -e team-env remote add origin git@github.com:company/team-env.git

# Push
cg -e team-env push
```

**4. Team Members: Join**

Option A - Import from git:

```bash
cg import git@github.com:company/team-env.git --name team-env
```

Option B - Clone + pull:

```bash
# Create environment
cg create team-env

# Add remote
cg -e team-env remote add origin git@github.com:company/team-env.git

# Pull
cg -e team-env pull
```

---

### Daily Workflow

**Morning: Pull Latest Changes**

Start each day by pulling updates:

```bash
cg -e team-env pull
```

This syncs your environment with the team's latest changes.

**During Day: Work and Commit**

Make changes and commit frequently:

```bash
# Add a node
cg -e team-env node add custom-node

# Create/modify workflows
# ... work in ComfyUI ...

# Commit
cg -e team-env commit -m "Add feature X workflow"
```

**End of Day: Push Changes**

Share your work with the team:

```bash
# Pull first (in case others pushed)
cg -e team-env pull

# Push your commits
cg -e team-env push
```

---

### Handling Conflicts

**1. Pull Rejects with Conflicts**

```
✗ Pull failed: Merge conflict in pyproject.toml
```

**2. Resolve Manually**

```bash
# Navigate to environment
cd ~/comfygit/environments/team-env/.cec

# Check conflict
git status

# Edit conflicted file
nano pyproject.toml

# Stage resolution
git add pyproject.toml

# Commit merge
git commit -m "Merge remote changes"

# Sync environment
cd -
cg -e team-env sync
```

**3. Push Resolution**

```bash
cg -e team-env push
```

---

### Best Practices

1. **Pull before push**: Always pull latest changes before pushing
   ```bash
   cg -e team-env pull && cg -e team-env push
   ```

2. **Small, focused commits**: Easier to review and merge
   ```bash
   cg -e team-env commit -m "Add SDXL workflow"
   cg -e team-env commit -m "Update ControlNet node"
   ```

3. **Descriptive messages**: Help team understand changes
   ```
   ✅ "Add img2img workflow with IPAdapter"
   ❌ "Updates"
   ```

4. **Communicate major changes**: Discuss before:
   - Removing nodes others might use
   - Changing ComfyUI version
   - Restructuring workflows

5. **Use branches for experiments**:
   ```bash
   cd ~/comfygit/environments/team-env/.cec
   git checkout -b experiment-feature
   # ... make changes ...
   git checkout main
   git merge experiment-feature
   ```

---

## Pattern 3: Template Distribution

**Scenario:** Distributing starter environments to the community or across teams.

### Creating a Template

**1. Create Clean Template**

```bash
# Create template environment
cg create comfyui-template

# Add commonly-used nodes
cg -e comfyui-template node add rgthree-comfy
cg -e comfyui-template node add was-node-suite-comfyui
cg -e comfyui-template node add comfyui-controlnet-aux

# Add starter workflows
# ... create basic workflows ...

# Commit
cg -e comfyui-template commit -m "Template v1.0"
```

**2. Add Model Sources**

Critical for templates - users must be able to download models:

```bash
cg -e comfyui-template model add-source
```

**3. Push to Public Repository**

```bash
# Create public GitHub repo
cg -e comfyui-template remote add origin git@github.com:user/comfyui-template.git
cg -e comfyui-template push

# Tag releases
cd ~/comfygit/environments/comfyui-template/.cec
git tag v1.0
git push origin v1.0
```

---

### Using a Template

**Import Specific Version**

```bash
# Import latest
cg import https://github.com/user/comfyui-template --name my-project

# Import specific version
cg import https://github.com/user/comfyui-template --branch v1.0 --name my-project
```

**Customize After Import**

```bash
# Add your own nodes
cg -e my-project node add custom-node

# Create your workflows
# ...

# Commit your changes
cg -e my-project commit -m "Customize for my project"
```

---

### Template Best Practices

1. **Comprehensive model sources**: Every model should have a download URL

2. **Include documentation**: Add README in the repo
   ```markdown
   # ComfyUI Template

   Starter environment with commonly-used nodes.

   ## Included Workflows
   - txt2img: Basic SDXL text-to-image
   - img2img: Image-to-image with ControlNet

   ## Usage
   cg import https://github.com/user/comfyui-template --name my-env
   ```

3. **Version releases**: Use git tags for stable versions
   ```bash
   git tag -a v1.0 -m "Release v1.0"
   git push origin v1.0
   ```

4. **Keep it minimal**: Only include universally-useful components

5. **Test imports**: Verify template imports work in a fresh workspace

---

## Pattern 4: Hybrid Approach

**Scenario:** Different distribution methods for different audiences.

### Example Setup

**Internal Team: Git Collaboration**

```bash
# Team uses git remotes for active development
cg -e project remote add origin git@github.com:company/project-internal.git
cg -e project push
```

**Client Delivery: Tarball Export**

```bash
# Export stable version for client
cg -e project export client-delivery-v1.0.tar.gz
```

**Public Showcase: Git Import**

```bash
# Push to public repo for community
cg -e project remote add public https://github.com/company/project-public.git
cg -e project push -r public
```

---

### Advantages

- **Flexibility**: Use the right tool for each audience
- **Security**: Keep internal development private
- **Convenience**: Git for team, tarball for clients

---

## Model Management Strategies

Models are often the largest component of environments. Choose a strategy that fits your team's needs.

### Strategy 1: Centralized Model Library

**Setup:**

One shared models directory on a network drive or cloud storage.

```bash
# All team members point to shared directory
cg model index dir /mnt/shared/models
```

**Advantages:**

- No duplicate downloads
- Consistent model versions
- Saves disk space and bandwidth

**Limitations:**

- Requires network access
- Single point of failure
- Slower access over network

---

### Strategy 2: Individual Model Libraries

**Setup:**

Each team member maintains their own models directory.

```bash
# Each member has local models
cg model index dir ~/ComfyUI/models
```

**Advantages:**

- No network dependency
- Fast local access
- Works offline

**Limitations:**

- Duplicate downloads across team
- Potential version inconsistencies

---

### Strategy 3: Hybrid

**Setup:**

Shared directory for large/common models, local for experiments.

```bash
# Symlink common models from shared location
ln -s /mnt/shared/models/checkpoints ~/comfygit/models/checkpoints

# Keep local models for experiments
cg model index dir ~/comfygit/models
```

**Advantages:**

- Balance of speed and efficiency
- Flexibility for team members

**Limitations:**

- More complex setup
- Requires coordination

---

## Communication and Coordination

### Establish Team Conventions

Document team practices:

**Commit Messages:**

```
Format: <type>: <description>

Examples:
- feat: Add SDXL upscaling workflow
- fix: Resolve ControlNet version conflict
- update: Upgrade ComfyUI to v0.2.7
- docs: Add workflow usage instructions
```

**Branch Naming:**

```
feature/<name>    - New features
fix/<name>        - Bug fixes
experiment/<name> - Experimental work
```

**Node Management:**

```
- Test new nodes in branches before merging
- Communicate before removing nodes
- Document node dependencies in commits
```

---

### Regular Sync Meetings

Schedule regular check-ins:

- **Daily standups**: Share what you're working on
- **Weekly syncs**: Review environment changes
- **Release planning**: Coordinate major updates

---

### Communication Channels

Use dedicated channels for environment collaboration:

- **Slack/Discord**: Quick updates and questions
- **GitHub Issues**: Track environment issues and feature requests
- **Wiki/Docs**: Document workflows and best practices

---

## Troubleshooting Team Issues

### Issue: Frequent Merge Conflicts

**Symptoms:** Team members constantly get conflicts when pulling.

**Solutions:**

1. **Pull more frequently**: Reduce time between syncs
   ```bash
   # Pull every hour or before starting work
   cg -e team-env pull
   ```

2. **Use branches**: Isolate experimental work
   ```bash
   git checkout -b my-feature
   ```

3. **Coordinate changes**: Communicate before major edits
   ```
   "I'm updating ControlNet nodes, please don't modify them for 30min"
   ```

---

### Issue: Push Rejected (Someone Pushed First)

**Symptoms:**

```
✗ Push failed: Updates were rejected
```

**Solution:**

```bash
# Pull to merge their changes
cg -e team-env pull

# Resolve any conflicts
# ...

# Push again
cg -e team-env push
```

---

### Issue: Models Missing After Pull

**Symptoms:** Workflows break because models weren't downloaded.

**Solutions:**

1. **Use pull with model strategy**:
   ```bash
   cg -e team-env pull --models all
   ```

2. **Resolve manually after pull**:
   ```bash
   cg -e team-env workflow resolve --all
   ```

3. **Check model sources**:
   ```bash
   cg -e team-env model index show <model-name>
   ```

---

### Issue: Inconsistent Python Environments

**Symptoms:** Different team members have different package versions.

**Causes:**

- Not pulling latest `uv.lock`
- Manual package installations

**Solutions:**

1. **Pull regularly** to sync `uv.lock`:
   ```bash
   cg -e team-env pull
   ```

2. **Never manually install packages**: Always use ComfyGit commands
   ```bash
   # ✅ Correct
   cg -e team-env py add requests

   # ❌ Wrong
   cd ~/comfygit/environments/team-env/.venv
   pip install requests
   ```

---

## Security Considerations

### Private Repositories

Use SSH keys for authentication:

```bash
# Add remote with SSH URL
cg -e team-env remote add origin git@github.com:company/private-env.git
```

Configure SSH keys: [GitHub SSH Setup](https://docs.github.com/en/authentication/connecting-to-github-with-ssh)

---

### Access Control

Use repository permissions to control access:

- **Read-only**: Can pull, cannot push
- **Write**: Can pull and push
- **Admin**: Full repository control

Manage via GitHub/GitLab settings.

---

### Secrets Management

**Never commit secrets** to the environment repository:

- API keys
- Passwords
- Authentication tokens

**Instead:**

1. **Use environment variables**:
   ```bash
   export CIVITAI_API_KEY=<your-key>
   ```

2. **Local configuration files**: Add to `.gitignore`

3. **ComfyGit config**: Store separately from environment
   ```bash
   cg config --civitai-key <key>
   ```

---

## Next Steps

- [Export and Import](export-import.md) - Tarball-based sharing
- [Git Remotes](git-remotes.md) - Push/pull collaboration
- [Version Control](../environments/version-control.md) - Commit and rollback
- [Managing Custom Nodes](../custom-nodes/managing-nodes.md) - Node updates and conflicts

---

## Summary

Effective team collaboration requires:

- **Choose the right method**: Tarball, git, or hybrid based on your needs
- **Establish conventions**: Commit messages, branch naming, communication
- **Sync frequently**: Pull before work, push when done
- **Manage models**: Decide on centralized vs individual model libraries
- **Coordinate changes**: Communicate before major updates
- **Handle conflicts**: Pull, resolve, sync, push

Start with simple patterns and evolve as your team grows. The key to successful collaboration is clear communication and consistent practices.
