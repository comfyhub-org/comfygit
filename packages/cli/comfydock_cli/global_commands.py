"""Global workspace-level commands for ComfyDock CLI - Simplified."""

import sys
from functools import cached_property
from pathlib import Path

from comfydock_core.core.workspace import Workspace
from comfydock_core.factories.workspace_factory import WorkspaceFactory

from .logging.logging_config import get_logger
from .logging.environment_logger import WorkspaceLogger, with_workspace_logging
from .cli_utils import get_workspace_or_exit

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
        from .pagination import paginate

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
        from .pagination import paginate

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

    # def model_find(self, args):
    #     """Find models by hash or filename (renamed from model_search)."""
    #     return self.model_search(args)
