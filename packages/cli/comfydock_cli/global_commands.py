"""Global workspace-level commands for ComfyDock CLI - Simplified."""

import sys
from functools import cached_property
from pathlib import Path

from comfydock_core.core.workspace import Workspace
from comfydock_core.factories.workspace_factory import WorkspaceFactory

from .logging.logging_config import get_logger
from .logging.environment_logger import WorkspaceLogger, with_workspace_logging
from .cli_utils import get_workspace_or_exit
from .utils import paginate, create_progress_callback, show_download_stats, show_civitai_auth_help

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
        """Import a ComfyDock environment from a package."""
        print("⚠️  Import/export functionality is not yet implemented in this MVP")
        print("\nThis feature will allow you to:")
        print("  - Import environments from .tar.gz packages")
        print("  - Include pyproject.toml, uv.lock, and custom nodes")
        print("  - Share environments between systems")
        return 0

    @with_workspace_logging("export")
    def export_env(self, args):
        """Export a ComfyDock environment to a package."""
        print("⚠️  Import/export functionality is not yet implemented in this MVP")
        print("\nThis feature will allow you to:")
        print("  - Export environments to .tar.gz packages")
        print("  - Include pyproject.toml, uv.lock, and custom nodes")
        print("  - Share environments between systems")
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
