# Migrating from ComfyDock v0.x

> Important information for users of the old Docker-based ComfyDock (v0.1.x - v0.3.x).

!!! warning "Breaking Changes"
    ComfyDock v1.0+ is a complete rewrite with a fundamentally different architecture. The Docker-based v0.x and UV-based v1.x **cannot coexist** — they are separate tools with different commands and workflows.

## What changed?

### v0.x (Docker-based)

* **Architecture**: Docker containers + GUI
* **Command**: `comfydock`
* **Storage**: `~/.comfydock/`
* **Environments**: Docker images with mounted volumes
* **Management**: Web GUI with environment cards
* **Sharing**: Commit containers to Docker Hub

### v1.0+ (UV-based)

* **Architecture**: UV virtual environments + CLI
* **Command**: `cg`
* **Storage**: `~/comfygit/` (configurable)
* **Environments**: Native Python environments with git
* **Management**: Command-line interface
* **Sharing**: Export tarballs or Git remotes

## Why the rewrite?

**Problems with Docker approach:**

* Large Docker images (5-10GB+ per environment)
* Complex volume mounting configurations
* Performance overhead from containerization
* Limited sharing options (Docker Hub only)
* GUI locked users into specific workflow

**Benefits of UV approach:**

* Smaller environments (PyTorch shared, only custom nodes differ)
* Native filesystem performance
* Standard Python tooling (pyproject.toml, pip-compatible)
* Multiple sharing options (tarballs, GitHub, GitLab)
* CLI enables scripting and automation
* Git-based version control built-in

## Migration strategy

There is **no automatic migration** from v0.x to v1.x. You need to recreate your environments manually.

### Recommended approach

For each Docker-based environment:

1. **Document your setup**:
   ```bash
   # In v0.x, list your custom nodes
   docker exec <container> ls /app/ComfyUI/custom_nodes
   ```

2. **Export workflows**: Save your workflow JSON files

3. **Note your models**: Record which models you were using

4. **Create new v1.x environment**:
   ```bash
   # Install v1.x
   uv tool install comfygit

   # Initialize
   cg init

   # Create environment
   cg create my-project --use
   ```

5. **Add custom nodes**:
   ```bash
   # Add each node from your v0.x environment
   cg node add comfyui-depthflow-nodes
   cg node add comfyui-impact-pack
   # ... etc
   ```

   !!! warning "Skip ComfyUI-Manager"
       Don't install `comfyui-manager` in v1.x - ComfyDock replaces its functionality with `cg node add`.

6. **Load workflows**:
   ```bash
   # Copy workflow files to ComfyUI directory
   cp workflows/*.json ~/comfygit/environments/my-project/ComfyUI/user/default/workflows/

   # Resolve dependencies
   cg workflow resolve my-workflow.json
   ```

7. **Index your models**:
   ```bash
   # Point to your existing models directory
   cg model index dir /path/to/models
   cg model index sync
   ```

## Coexistence

v0.x and v1.x use different directories and commands, so they can technically coexist:

| Aspect | v0.x | v1.x |
|--------|------|------|
| Command | `comfydock` | `cg` |
| Storage | `~/.comfydock/` | `~/comfygit/` |
| Technology | Docker | UV + Python venvs |

However, there's no integration between them. Choose one and stick with it.

## Deprecation timeline

* **v0.x status**: No longer actively developed
* **v0.x support**: Community support only, no new features
* **v1.x status**: Active development, all new features

!!! info "Legacy documentation"
    Old Docker-based documentation is available under [Legacy Docs (v0.x)](../legacy/index.md) for reference.

## Frequently asked questions

??? question "Can I convert a Docker image to a v1.x environment?"
    No automatic conversion exists. You need to manually recreate the environment by:

    1. Listing custom nodes in the Docker container
    2. Creating a new v1.x environment
    3. Adding the same nodes via `cg node add`

??? question "Will my old workflows work in v1.x?"
    Yes! Workflow JSON files are compatible. ComfyDock v1.x can resolve dependencies from workflow files using `cg workflow resolve`.

??? question "What about my models?"
    Models are just files—they work in both versions. Point v1.x to your existing models directory:
    ```bash
    cg model index dir /path/to/old/models
    ```

??? question "Can I still use v0.x?"
    Yes, but it's no longer maintained. Install the old version:
    ```bash
    pip install comfydock==0.1.6
    ```

??? question "I prefer the GUI. Does v1.x have one?"
    No. ComfyDock v1.x is CLI-only by design. The CLI enables:

    * Scripting and automation
    * Integration with CI/CD
    * Better team collaboration via Git
    * Faster, more flexible workflows

??? question "What about my Docker-based environments?"
    They're unaffected. v1.x doesn't touch Docker containers. You can keep using them or delete them when ready to switch.

## Example migration

Here's a real-world migration example:

**Old v0.x environment "production":**

* ComfyUI v0.2.0
* Custom nodes: Impact-Pack, ControlNet-Aux, Depthflow-Nodes
* Models: SD1.5, Deliberate v2, various LoRAs
* Workflows: 10 JSON files

**Migration steps:**

```bash
# 1. Install v1.x
uv tool install comfygit

# 2. Initialize workspace
cg init ~/comfydock

# 3. Create equivalent environment
cg create production --use

# 4. Add custom nodes
cg node add comfyui-depthflow-nodes
cg node add comfyui-impact-pack
cg node add comfyui-controlnet-aux

# 5. Index existing models
cg model index dir /home/user/models
cg model index sync

# 6. Copy workflows
cp ~/.comfydock/production/workflows/*.json \
   ~/comfygit/environments/production/ComfyUI/user/default/workflows/

# 7. Commit the setup
cg commit -m "Migrated from v0.x Docker environment"

# 8. Test
cg run
```

**Result:**

* Smaller disk usage (no Docker image overhead)
* Git-based version control
* Same custom nodes and workflows
* Native filesystem performance

## Need help?

If you're stuck during migration:

* Ask on [GitHub Discussions](https://github.com/comfyhub-org/comfygit/discussions)
* Check [troubleshooting guide](../troubleshooting/common-issues.md)
* Report issues on [GitHub Issues](https://github.com/comfyhub-org/comfygit/issues)

## Next steps

After migrating:

* Read the [Quickstart guide](quickstart.md) to learn v1.x workflows
* Understand [Core Concepts](concepts.md) like .cec and git-based versioning
* Explore [Version Control](../user-guide/environments/version-control.md) features
