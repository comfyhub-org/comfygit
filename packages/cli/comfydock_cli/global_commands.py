"""Global workspace-level commands for ComfyDock CLI - Simplified."""

import sys
from functools import cached_property
from pathlib import Path

from comfydock_core.core.workspace import Workspace
from comfydock_core.factories.workspace_factory import WorkspaceFactory
from comfydock_core.models.protocols import ExportCallbacks, ImportCallbacks

from .cli_utils import get_workspace_or_exit
from .logging.environment_logger import WorkspaceLogger, with_workspace_logging
from .logging.logging_config import get_logger
from .utils import create_progress_callback, paginate, show_civitai_auth_help, show_download_stats

logger = get_logger(__name__)


class GlobalCommands:
    """Handler for global workspace commands."""

    def __init__(self):
        """Initialize global commands handler."""
        pass

    @cached_property
    def workspace(self) -> "Workspace":
        return get_workspace_or_exit()

    def init(self, args):
        """Initialize a new ComfyDock workspace.

        Creates:
        - ~/comfydock/ (or custom path)
        - .metadata/ for workspace state
        - uv_cache/ for package management
        - environments/ for ComfyUI environments
        """
        # Determine workspace path
        path = args.path if (hasattr(args, "path") and args.path) else None

        workspace_paths = WorkspaceFactory.get_paths(path)

        print(f"🎯 Initializing ComfyDock workspace at: {workspace_paths.root}")

        try:
            # Create workspace
            workspace = WorkspaceFactory.create(workspace_paths.root)

            # Set workspace path for logging after creation
            WorkspaceLogger.set_workspace_path(workspace.path)

            # Now log this command with the workspace logger
            with WorkspaceLogger.log_command("init", arg_path=path if path else "default"):
                logger.info(f"Workspace initialized at {workspace.path}")

                # Fetch registry data for the new workspace
                print("📦 Fetching latest registry data...")
                success = workspace.update_registry_data()
                if success:
                    print("✓ Registry data downloaded")
                    logger.info("Registry data downloaded successfully")
                else:
                    print("⚠️  Could not fetch registry data (will retry when needed)")
                    logger.warning("Failed to fetch initial registry data")

            print(f"✓ Workspace initialized at {workspace.path}")

            # Show default models directory
            try:
                models_dir = workspace.get_models_directory()
                print(f"✓ Default models directory: {models_dir}")
                print("   (Change with: comfydock model index dir <path>)")
            except Exception:
                # Should not happen with new auto-creation, but handle gracefully
                pass

            print("\nNext steps:")
            print("  1. Create an environment: comfydock create <name>")
            print("  2. Add custom nodes: comfydock -e <name> node add <node>")
            print("  3. Run ComfyUI: comfydock -e <name> run")
        except Exception as e:
            print(f"✗ Failed to initialize workspace: {e}", file=sys.stderr)
            sys.exit(1)

    @with_workspace_logging("list")
    def list_envs(self, args):
        """List all environments in the workspace."""
        logger.info("Listing environments in workspace")

        try:
            environments = self.workspace.list_environments()
            active_env = self.workspace.get_active_environment()
            active_name = active_env.name if active_env else None

            logger.info(f"Found {len(environments)} environments, active: {active_name or 'none'}")

            if not environments:
                print("No environments found.")
                print("Create one with: comfydock create <name>")
                return

            print("Environments:")
            for env in environments:
                marker = "✓" if env.name == active_name else " "
                status = "(active)" if env.name == active_name else ""
                print(f"  {marker} {env.name:15} {status}")

        except Exception as e:
            logger.error(f"Failed to list environments: {e}")
            print(f"✗ Failed to list environments: {e}", file=sys.stderr)
            sys.exit(1)

    @with_workspace_logging("migrate")
    def migrate(self, args):
        """Migrate an existing ComfyUI installation (not implemented in MVP)."""
        print("⚠️  Migration is not yet implemented in this MVP")
        print("\nFor now, you can:")
        print("  1. Create a new environment: comfydock create <name>")
        print("  2. Manually add your custom nodes:")
        print("     comfydock -e <name> node add <node-name-or-url>")
        print("  3. Apply changes: comfydock -e <name> sync")

        # Still do a basic scan if requested
        if args.scan_only:
            source_path = Path(args.source_path)
            if source_path.exists():
                print(f"\n📋 Basic scan of: {source_path}")

                # Check for ComfyUI
                if (source_path / "main.py").exists():
                    print("  ✓ ComfyUI detected")

                # Check for custom nodes
                custom_nodes = source_path / "custom_nodes"
                if custom_nodes.exists():
                    node_count = len([d for d in custom_nodes.iterdir() if d.is_dir()])
                    print(f"  ✓ Found {node_count} custom nodes")

                # Check for models
                models = source_path / "models"
                if models.exists():
                    print("  ✓ Models directory found")
            else:
                print(f"✗ Path not found: {source_path}")

        return 0

    @with_workspace_logging("import")
    def import_env(self, args):
        """Import a ComfyDock environment from a tarball or git repository."""
        from pathlib import Path

        from comfydock_core.utils.git import is_git_url

        if not args.path:
            print("✗ Please specify path to import tarball or git URL")
            print("  Usage: comfydock import <path.tar.gz|git-url>")
            return 1

        # Detect if this is a git URL or local tarball
        is_git = is_git_url(args.path)

        if is_git:
            print("📦 Importing environment from git repository")
            print(f"   URL: {args.path}")
            if hasattr(args, 'branch') and args.branch:
                print(f"   Branch/Tag: {args.branch}")
            print()
        else:
            tarball_path = Path(args.path)
            if not tarball_path.exists():
                print(f"✗ File not found: {tarball_path}")
                return 1
            print(f"📦 Importing environment from {tarball_path.name}")
            print()

        # Get environment name from args or prompt
        if hasattr(args, 'name') and args.name:
            env_name = args.name
        else:
            env_name = input("Environment name: ").strip()
            if not env_name:
                print("✗ Environment name required")
                return 1

        # Ask for model download strategy
        print("\nModel download strategy:")
        print("  1. all      - Download all models with sources")
        print("  2. required - Download only required models")
        print("  3. skip     - Skip all downloads (can resolve later)")
        strategy_choice = input("Choice (1-3) [1]: ").strip() or "1"

        strategy_map = {"1": "all", "2": "required", "3": "skip"}
        strategy = strategy_map.get(strategy_choice, "all")

        # CLI callbacks for progress updates
        class CLIImportCallbacks(ImportCallbacks):
            def __init__(self):
                self.manifest = None

            def on_phase(self, phase: str, description: str):
                # Add emojis based on phase
                emoji_map = {
                    "clone_repo": "📥",
                    "clone_comfyui": "🔧",
                    "restore_comfyui": "🔧",
                    "install_deps": "🔧",
                    "init_git": "🔧",
                    "copy_workflows": "📝",
                    "sync_nodes": "📦",
                    "resolve_models": "🔄"
                }

                # First phase shows initialization header
                if phase == "clone_repo":
                    print(f"\n📥 {description}")
                elif phase in ["clone_comfyui", "restore_comfyui"]:
                    print("\n🔧 Initializing environment...")
                    print(f"   {description}")
                elif phase in ["install_deps", "init_git"]:
                    print(f"   {description}")
                elif phase == "copy_workflows":
                    print("\n📝 Setting up workflows...")
                elif phase == "sync_nodes":
                    print("\n📦 Syncing custom nodes...")
                elif phase == "resolve_models":
                    print(f"\n🔄 {description}")
                else:
                    emoji = emoji_map.get(phase, "")
                    print(f"\n{emoji} {description}" if emoji else f"\n{description}")

            def on_workflow_copied(self, workflow_name: str):
                print(f"   Copied: {workflow_name}")

            def on_node_installed(self, node_name: str):
                print(f"   Installed: {node_name}")

            def on_workflow_resolved(self, workflow_name: str, downloads: int):
                print(f"   • {workflow_name}", end="")
                if downloads:
                    print(f" (downloaded {downloads} models)")
                else:
                    print()

            def on_error(self, error: str):
                print(f"   ⚠️  {error}")

            def on_download_failures(self, failures: list[tuple[str, str]]):
                if not failures:
                    return

                print(f"\n⚠️  {len(failures)} model(s) failed to download:")
                for workflow_name, model_name in failures:
                    print(f"   • {model_name} (from {workflow_name})")

                print("\nModels are saved as download intents - you can download them later with:")
                print("   comfydock workflow resolve <workflow>")
                print("\nIf you see 401 Unauthorized errors, add your Civitai API key:")
                print("   comfydock config --civitai-key <your-token>")

        try:
            if is_git:
                env = self.workspace.import_from_git(
                    git_url=args.path,
                    name=env_name,
                    model_strategy=strategy,
                    branch=getattr(args, 'branch', None),
                    callbacks=CLIImportCallbacks()
                )
            else:
                env = self.workspace.import_environment(
                    tarball_path=Path(args.path),
                    name=env_name,
                    model_strategy=strategy,
                    callbacks=CLIImportCallbacks()
                )

            print(f"\n✅ Import complete: {env.name}")
            print("   Environment ready to use!")

            # Set as active if --use flag provided
            if hasattr(args, 'use') and args.use:
                self.workspace.set_active_environment(env.name)
                print(f"   '{env.name}' set as active environment")
            else:
                print(f"\nActivate with: comfydock use {env_name}")

        except Exception as e:
            print(f"\n✗ Import failed: {e}")
            return 1

        return 0

    @with_workspace_logging("export")
    def export_env(self, args):
        """Export a ComfyDock environment to a package."""
        from datetime import datetime
        from pathlib import Path

        # Get active environment or from -e flag
        try:
            if hasattr(args, 'target_env') and args.target_env:
                env = self.workspace.get_environment(args.target_env)
            else:
                env = self.workspace.get_active_environment()
                if not env:
                    print("✗ No active environment. Use: comfydock use <name>")
                    print("   Or specify with: comfydock -e <name> export")
                    return 1
        except Exception as e:
            print(f"✗ Error getting environment: {e}")
            return 1

        # Determine output path
        if args.path:
            output_path = Path(args.path)
        else:
            # Default: <env_name>_export_<date>.tar.gz in current directory
            timestamp = datetime.now().strftime("%Y%m%d")
            output_path = Path.cwd() / f"{env.name}_export_{timestamp}.tar.gz"

        print(f"📦 Exporting environment: {env.name}")
        print()

        # Export callbacks
        class CLIExportCallbacks(ExportCallbacks):
            def __init__(self):
                self.models_without_sources = []

            def on_models_without_sources(self, models: list):
                self.models_without_sources = models

        callbacks = CLIExportCallbacks()

        try:
            tarball_path = env.export_environment(output_path, callbacks=callbacks)

            # Check if we need user confirmation
            if callbacks.models_without_sources and not args.allow_issues:
                print("⚠️  Export validation:")
                print(f"\n{len(callbacks.models_without_sources)} model(s) have no source URLs.\n")

                # Show first 3 models initially
                shown_all = len(callbacks.models_without_sources) <= 3

                def show_models(show_all=False):
                    if show_all or len(callbacks.models_without_sources) <= 3:
                        for model_info in callbacks.models_without_sources:
                            print(f"  • {model_info.filename}")
                            workflows_str = ", ".join(model_info.workflows)
                            print(f"    Used by: {workflows_str}")
                    else:
                        for model_info in callbacks.models_without_sources[:3]:
                            print(f"  • {model_info.filename}")
                            workflows_str = ", ".join(model_info.workflows)
                            print(f"    Used by: {workflows_str}")
                        remaining = len(callbacks.models_without_sources) - 3
                        print(f"\n  ... and {remaining} more")

                show_models()

                print("\n⚠️  Recipients won't be able to download these models automatically.")
                print("   Add sources: comfydock model add-source")

                # Single confirmation loop
                while True:
                    if shown_all or len(callbacks.models_without_sources) <= 3:
                        response = input("\nContinue export? (y/N): ").strip().lower()
                    else:
                        response = input("\nContinue export? (y/N) or (s)how all models: ").strip().lower()

                    if response == 's' and not shown_all:
                        print()
                        show_models(show_all=True)
                        shown_all = True
                        print("\n⚠️  Recipients won't be able to download these models automatically.")
                        print("   Add sources: comfydock model add-source")
                        continue
                    elif response == 'y':
                        break
                    else:
                        print("\n✗ Export cancelled")
                        print("   Fix with: comfydock model add-source")
                        # Clean up the created tarball
                        if tarball_path.exists():
                            tarball_path.unlink()
                        return 1

            size_mb = tarball_path.stat().st_size / (1024 * 1024)
            print(f"\n✅ Export complete: {tarball_path.name} ({size_mb:.1f} MB)")
            print("\nShare this file to distribute your complete environment!")

        except ValueError as e:
            print(f"✗ Export validation failed: {e}")
            return 1
        except Exception as e:
            print(f"✗ Export failed: {e}")
            return 1

        return 0

    # === Model Management Commands ===

    @with_workspace_logging("model index list")
    def model_index_list(self, args):
        """List all indexed models."""
        from comfydock_core.utils.common import format_size

        logger.info("Listing all indexed models")

        try:
            # Get all models from the index
            models = self.workspace.list_models()

            logger.info(f"Retrieved {len(models)} models from index")

            if not models:
                print("📦 All indexed models:")
                print("   No models found")
                print("   Run 'comfydock model index dir <path>' to set your models directory")
                return

            # Get stats for header
            stats = self.workspace.get_model_stats()
            total_models = stats.get('total_models', 0)
            total_locations = stats.get('total_locations', 0)

            # Define how to render a single model
            def render_model(model):
                size_str = format_size(model.file_size)
                print(f"\n   {model.filename}")
                print(f"   Size: {size_str}")
                print(f"   Hash: {model.hash[:12]}...")
                print(f"   Path: {model.relative_path}")

            # Use pagination for results
            header = f"📦 All indexed models ({total_models} unique, {total_locations} files):"
            paginate(models, render_model, page_size=5, header=header)

        except Exception as e:
            logger.error(f"Failed to list models: {e}")
            print(f"✗ Failed to list models: {e}", file=sys.stderr)
            sys.exit(1)

    @with_workspace_logging("model index find")
    def model_index_find(self, args):
        """Search for models by hash or filename."""
        from comfydock_core.utils.common import format_size

        query = args.query
        logger.info(f"Searching models for query: '{query}'")

        try:
            # Search for models
            results = self.workspace.search_models(query)

            logger.info(f"Found {len(results)} models matching query")

            if not results:
                print(f"No models found matching: {query}")
                return

            # Define how to render a single model
            def render_model(model):
                size_str = format_size(model.file_size)
                print(f"\n   {model.filename}")
                print(f"   Size: {size_str}")
                print(f"   Hash: {model.hash}")
                print(f"   Path: {model.relative_path}")

            # Use pagination for results
            header = f"🔍 Found {len(results)} model(s) matching '{query}':"
            paginate(results, render_model, page_size=5, header=header)

        except Exception as e:
            logger.error(f"Model search failed for query '{query}': {e}")
            print(f"✗ Search failed: {e}", file=sys.stderr)
            sys.exit(1)

    @with_workspace_logging("model index show")
    def model_index_show(self, args):
        """Show detailed information about a specific model."""
        from datetime import datetime

        from comfydock_core.utils.common import format_size

        identifier = args.identifier
        logger.info(f"Showing details for model: '{identifier}'")

        try:
            details = self.workspace.get_model_details(identifier)
            model = details.model
            sources = details.sources
            locations = details.all_locations

            # Display detailed information
            print(f"📦 Model Details: {model.filename}\n")

            # Core identification
            print(f"  Hash:           {model.hash}")
            print(f"  Blake3:         {model.blake3_hash or 'Not computed'}")
            print(f"  SHA256:         {model.sha256_hash or 'Not computed'}")
            print(f"  Size:           {format_size(model.file_size)}")
            print(f"  Category:       {model.category}")

            # Timestamps
            first_seen = datetime.fromtimestamp(model.last_seen).strftime("%Y-%m-%d %H:%M:%S")
            print(f"  Last Seen:      {first_seen}")

            # Locations
            print(f"\n  Locations ({len(locations)}):")
            for loc in locations:
                mtime = datetime.fromtimestamp(loc['mtime']).strftime("%Y-%m-%d %H:%M:%S")
                print(f"    • {loc['relative_path']}")
                print(f"      Modified: {mtime}")

            # Sources
            if sources:
                print(f"\n  Sources ({len(sources)}):")
                for source in sources:
                    print(f"    • {source['type'].title()}")
                    print(f"      URL: {source['url']}")
                    if source['metadata']:
                        for key, value in source['metadata'].items():
                            print(f"      {key}: {value}")
                    added = datetime.fromtimestamp(source['added_time']).strftime("%Y-%m-%d %H:%M:%S")
                    print(f"      Added: {added}")
            else:
                print("\n  Sources: None")
                print(f"    Add with: comfydock model add-source {model.hash[:12]}")

            # Metadata (if any)
            if model.metadata:
                print("\n  Metadata:")
                for key, value in model.metadata.items():
                    print(f"    {key}: {value}")

        except KeyError:
            print(f"No model found matching: {identifier}")
        except ValueError:
            # Handle ambiguous matches
            results = self.workspace.search_models(identifier)
            print(f"Multiple models found matching '{identifier}':\n")
            for idx, model in enumerate(results, 1):
                print(f"  {idx}. {model.relative_path} ({model.hash[:12]}...)")
            print("\nUse more specific identifier:")
            print(f"  Full hash: comfydock model index show {results[0].hash}")
            print(f"  Full path: comfydock model index show {results[0].relative_path}")
        except Exception as e:
            logger.error(f"Failed to show model details for '{identifier}': {e}")
            print(f"✗ Failed to show model: {e}", file=sys.stderr)
            sys.exit(1)

    # === Model Directory Commands ===

    # === Registry Commands ===

    @with_workspace_logging("registry status")
    def registry_status(self, args):
        """Show registry cache status."""
        try:
            info = self.workspace.get_registry_info()

            if not info['exists']:
                print("✗ No registry data cached")
                print("   Run 'comfydock index registry update' to fetch")
                return

            print("📦 Registry Cache Status:")
            print(f"   Path: {info['path']}")
            print(f"   Age: {info['age_hours']} hours")
            print(f"   Stale: {'Yes' if info['stale'] else 'No'} (>24 hours)")
            if info['version']:
                print(f"   Version: {info['version']}")

        except Exception as e:
            logger.error(f"Failed to get registry status: {e}")
            print(f"✗ Failed to get registry status: {e}", file=sys.stderr)
            sys.exit(1)

    @with_workspace_logging("registry update")
    def registry_update(self, args):
        """Update registry data from GitHub."""
        try:
            print("🔄 Updating registry data from GitHub...")

            success = self.workspace.update_registry_data()

            if success:
                info = self.workspace.get_registry_info()
                print("✓ Registry data updated successfully")
                if info['version']:
                    print(f"   Version: {info['version']}")
            else:
                print("✗ Failed to update registry data")
                print("   Using existing cache if available")

        except Exception as e:
            logger.error(f"Failed to update registry: {e}")
            print(f"✗ Failed to update registry: {e}", file=sys.stderr)
            sys.exit(1)

    @with_workspace_logging("model index dir")
    def model_dir_add(self, args):
        """Set the global models directory."""
        directory_path = args.path.resolve()
        logger.info(f"Setting models directory: {directory_path}")

        try:
            print(f"📁 Setting global models directory: {directory_path}")

            if not directory_path.exists():
                print(f"✗ Directory does not exist: {directory_path}")
                sys.exit(1)

            if not directory_path.is_dir():
                print(f"✗ Path is not a directory: {directory_path}")
                sys.exit(1)

            print("   Performing initial scan...")

            # Set the models directory and perform initial scan
            self.workspace.set_models_directory(directory_path)

            print(f"\n✓ Models directory set successfully: {directory_path}")
            print("   Use 'comfydock index model sync' to rescan when models change")

        except Exception as e:
            logger.error(f"Failed to set models directory '{directory_path}': {e}")
            print(f"✗ Failed to set models directory: {e}", file=sys.stderr)
            sys.exit(1)

    @with_workspace_logging("model index sync")
    def model_index_sync(self, args):
        """Scan models directory and update index."""
        logger.info("Syncing models directory")

        try:
            print("🔄 Scanning models directory...")

            result = self.workspace.sync_model_directory()

            if result is None:
                print("✗ No models directory configured")
                print("   Run 'comfydock model index dir <path>' to set your models directory")
                return

            total_changes = result
            print(f"\n✓ Sync complete: {total_changes} changes")

        except Exception as e:
            logger.error(f"Failed to sync models: {e}")
            print(f"✗ Failed to sync: {e}", file=sys.stderr)
            sys.exit(1)

    @with_workspace_logging("model index status")
    def model_index_status(self, args):
        """Show model index status and statistics."""
        logger.info("Getting model status")

        try:
            # Get models directory info
            models_dir = self.workspace.get_models_directory()

            # Get stats
            stats = self.workspace.get_model_stats()

            print("📊 Model Index Status:")
            print()

            if models_dir:
                exists = "✓" if models_dir.exists() else "✗"
                print(f"   Models Directory: {exists} {models_dir}")
            else:
                print("   Models Directory: Not configured")
                print("   Run 'comfydock model index dir <path>' to set your models directory")
                return

            total_models = stats.get('total_models', 0)
            total_locations = stats.get('total_locations', 0)
            print(f"   Total Models: {total_models} unique models")
            print(f"   Total Files: {total_locations} files indexed")

            if total_locations > total_models:
                duplicates = total_locations - total_models
                print(f"   Duplicates: {duplicates} duplicate files detected")

        except Exception as e:
            logger.error(f"Failed to get status: {e}")
            print(f"✗ Failed to get status: {e}", file=sys.stderr)
            sys.exit(1)

    @with_workspace_logging("model download")
    def model_download(self, args):
        """Download model from URL with interactive path confirmation."""
        from comfydock_core.services.model_downloader import DownloadRequest

        url = args.url
        logger.info(f"Downloading model from: {url}")

        try:
            # Get models directory
            models_dir = self.workspace.get_models_directory()
            downloader = self.workspace.model_downloader

            # Determine target path
            if args.path:
                # User specified explicit path
                suggested_path = Path(args.path)
            elif args.category:
                # User specified category - extract filename from URL
                filename = downloader._extract_filename(url, None)
                suggested_path = Path(args.category) / filename
            else:
                # Auto-suggest based on URL/filename
                suggested_path = downloader.suggest_path(url, node_type=None, filename_hint=None)

            # Path confirmation (unless --yes)
            if not args.yes:
                print(f"\n📥 Downloading from: {url}")
                print(f"   Model will be saved to: {suggested_path}")
                print("\n   [Y] Continue  [m] Change path  [c] Cancel")

                choice = input("Choice [Y]/m/c: ").strip().lower()

                if choice == 'c':
                    print("✗ Download cancelled")
                    return
                elif choice == 'm':
                    new_path = input("\nEnter path (relative to models dir): ").strip()
                    if new_path:
                        suggested_path = Path(new_path)
                    else:
                        print("✗ Download cancelled")
                        return

            # Create download request
            target_path = models_dir / suggested_path
            request = DownloadRequest(
                url=url,
                target_path=target_path,
                workflow_name=None
            )

            # Download with progress callback
            print(f"\n📥 Downloading to: {suggested_path}")
            progress_callback = create_progress_callback()
            result = downloader.download(request, progress_callback=progress_callback)
            print()  # New line after progress

            # Handle result
            if not result.success:
                print(f"✗ Download failed: {result.error}")

                # Show Civitai auth help if needed
                if "civitai.com" in url.lower() and result.error and (
                    "401" in str(result.error) or "unauthorized" in str(result.error).lower()
                ):
                    show_civitai_auth_help()

                sys.exit(1)

            # Success - show stats
            if result.model:
                print()
                show_download_stats(result.model)
                logger.info(f"Successfully downloaded model to {result.model.relative_path}")
            else:
                print("✓ Download complete")

        except Exception as e:
            logger.error(f"Model download failed: {e}")
            print(f"✗ Download failed: {e}", file=sys.stderr)
            sys.exit(1)

    # === Model Source Management ===

    @with_workspace_logging("model add-source")
    def model_add_source(self, args):
        """Add download source URLs to models."""
        env = self.workspace.get_active_environment()

        # Mode detection: direct vs interactive
        if args.model and args.url:
            # Direct mode
            self._add_source_direct(env, args.model, args.url)
        else:
            # Interactive mode
            self._add_source_interactive(env)

    def _add_source_direct(self, env, identifier: str, url: str):
        """Direct mode: add source to specific model."""
        result = env.add_model_source(identifier, url)

        if result.success:
            print(f"✓ Added source to {result.model.filename}")
            print(f"  {url}")
        else:
            # Handle errors
            if result.error == "model_not_found":
                print(f"✗ Model not found: {identifier}", file=sys.stderr)
                print("\nHint: Use hash prefix or exact filename", file=sys.stderr)
                sys.exit(1)

            elif result.error == "ambiguous_filename":
                print(f"✗ Multiple models match '{identifier}':", file=sys.stderr)
                for match in result.matches:
                    print(f"  • {match.relative_path} ({match.hash[:8]}...)", file=sys.stderr)
                print(f"\nUse full hash: comfydock model add-source <hash> {url}", file=sys.stderr)
                sys.exit(1)

            elif result.error == "url_exists":
                print(f"✗ URL already exists for {result.model.filename}", file=sys.stderr)
                sys.exit(1)

    def _add_source_interactive(self, env):
        """Interactive mode: go through all models without sources."""
        statuses = env.get_models_without_sources()

        if not statuses:
            print("✓ All models have download sources!")
            return

        print("\n📦 Add Model Sources\n")
        print(f"Found {len(statuses)} model(s) without download sources\n")

        added_count = 0
        skipped_count = 0

        for idx, status in enumerate(statuses, 1):
            model = status.model
            available = status.available_locally

            # Show model info
            print(f"[{idx}/{len(statuses)}] {model.filename}")
            print(f"  Hash: {model.hash[:16]}...")
            print(f"  Path: {model.relative_path}")

            # Show availability status
            if available:
                print("  Status: ✓ Available locally")
            else:
                print("  Status: ✗ Not in local index (phantom reference)")

            # Prompt for URL
            url = input("\n  URL (or 's' to skip, 'q' to quit): ").strip()
            print()

            if url.lower() == 'q':
                print("⊗ Cancelled\n")
                break
            elif url.lower() == 's' or not url:
                skipped_count += 1
                continue
            else:
                # Add source
                result = env.add_model_source(model.hash, url)

                if result.success:
                    print("  ✓ Added source\n")
                    added_count += 1
                else:
                    # Should not happen in this flow, but handle gracefully
                    print(f"  ✗ Failed to add source: {result.error}\n", file=sys.stderr)

        # Summary
        print(f"✅ Complete: {added_count}/{len(statuses)} source(s) added")

        if added_count > 0:
            print("\nYour environment is now more shareable!")
            print("  Run 'comfydock export' to bundle and distribute")

    # === Config Management ===

    @with_workspace_logging("config")
    def config(self, args):
        """Manage ComfyDock configuration settings."""
        # Flag mode - direct operations
        if hasattr(args, 'civitai_key') and args.civitai_key is not None:
            self._set_civitai_key(args.civitai_key)
            return

        if hasattr(args, 'show') and args.show:
            self._show_config()
            return

        # Interactive mode - no flags provided
        self._interactive_config()

    def _set_civitai_key(self, key: str):
        """Set Civitai API key."""
        if key == "":
            self.workspace.workspace_config_manager.set_civitai_token(None)
            print("✓ Civitai API key cleared")
        else:
            self.workspace.workspace_config_manager.set_civitai_token(key)
            print("✓ Civitai API key saved")

    def _show_config(self):
        """Display current configuration."""
        print("ComfyDock Configuration:\n")

        # Civitai API Key
        token = self.workspace.workspace_config_manager.get_civitai_token()
        if token:
            # Mask key showing last 4 chars
            masked = f"••••••••{token[-4:]}" if len(token) > 4 else "••••"
            print(f"  Civitai API Key: {masked}")
        else:
            print("  Civitai API Key: Not set")

        # Registry cache preference
        prefer_cache = self.workspace.workspace_config_manager.get_prefer_registry_cache()
        print(f"  Registry Cache:  {'Enabled' if prefer_cache else 'Disabled'}")

    def _interactive_config(self):
        """Interactive configuration menu."""
        while True:
            # Get current config
            civitai_token = self.workspace.workspace_config_manager.get_civitai_token()
            prefer_cache = self.workspace.workspace_config_manager.get_prefer_registry_cache()

            # Display menu
            print("\nComfyDock Configuration\n")

            # Civitai key status
            if civitai_token:
                masked = f"••••••••{civitai_token[-4:]}" if len(civitai_token) > 4 else "••••"
                print(f"  1. Civitai API Key: {masked}")
            else:
                print("  1. Civitai API Key: Not set")

            # Registry cache
            cache_status = "Enabled" if prefer_cache else "Disabled"
            print(f"  2. Registry Cache:  {cache_status}")

            # Options
            print("\n  [1-2] Change setting  [c] Clear a setting  [q] Quit")
            choice = input("Choice: ").strip().lower()

            if choice == 'q':
                break
            elif choice == '1':
                self._interactive_set_civitai_key()
            elif choice == '2':
                self._interactive_toggle_registry_cache()
            elif choice == 'c':
                self._interactive_clear_setting()
            else:
                print("  Invalid choice")

    def _interactive_set_civitai_key(self):
        """Interactive Civitai API key setup."""
        print("\n🔑 Civitai API Key Setup")
        print("   Get your key from: https://civitai.com/user/account")

        key = input("\nEnter API key (or blank to cancel): ").strip()
        if not key:
            print("  Cancelled")
            return

        self.workspace.workspace_config_manager.set_civitai_token(key)
        print("✓ API key saved")

    def _interactive_toggle_registry_cache(self):
        """Toggle registry cache preference."""
        current = self.workspace.workspace_config_manager.get_prefer_registry_cache()
        new_value = not current

        self.workspace.workspace_config_manager.set_prefer_registry_cache(new_value)
        status = "enabled" if new_value else "disabled"
        print(f"✓ Registry cache {status}")

    def _interactive_clear_setting(self):
        """Clear a configuration setting."""
        print("\nClear which setting?")
        print("  1. Civitai API Key")
        print("\n  [1] Clear setting  [c] Cancel")

        choice = input("Choice: ").strip().lower()

        if choice == "1":
            self.workspace.workspace_config_manager.set_civitai_token(None)
            print("✓ Civitai API key cleared")
        elif choice == "c" or choice == "":
            print("  Cancelled")
        else:
            print("  Invalid choice")
