"""Environment-specific commands for ComfyDock CLI - Simplified."""
from __future__ import annotations

import sys
from functools import cached_property
from typing import TYPE_CHECKING

from comfydock_core.models.environment import UserAction
from comfydock_cli.interactive.model_resolver import InteractiveModelResolver

if TYPE_CHECKING:
    from comfydock_core.models.environment import EnvironmentStatus
    from comfydock_core.core.environment import Environment
    from comfydock_core.core.workspace import Workspace

from .cli_utils import get_workspace_or_exit
from .logging.environment_logger import with_env_logging
from .logging.logging_config import get_logger

logger = get_logger(__name__)


class EnvironmentCommands:
    """Handler for environment-specific commands - simplified for MVP."""

    def __init__(self):
        """Initialize environment commands handler."""
        pass

    @cached_property
    def workspace(self) -> Workspace:
        return get_workspace_or_exit()

    def _get_env(self, args) -> Environment:
        """Get environment from global -e flag or active environment.

        Args:
            args: Parsed command line arguments

        Returns:
            Environment instance

        Raises:
            SystemExit if no environment specified
        """
        # Check global -e flag first
        if hasattr(args, 'target_env') and args.target_env:
            try:
                env = self.workspace.get_environment(args.target_env)
                return env
            except Exception as e:
                print(f"✗ Unknown environment: {args.target_env}")
                print("Available environments:")
                for e in self.workspace.list_environments():
                    print(f"  • {e.name}")
                sys.exit(1)

        # Fall back to active environment
        active = self.workspace.get_active_environment()
        if not active:
            print("✗ No environment specified. Either:")
            print("  • Use -e flag: comfydock -e my-env <command>")
            print("  • Set active: comfydock use <name>")
            sys.exit(1)
        return active

    # === Commands that operate ON environments ===

    @with_env_logging("env create")
    def create(self, args, logger=None):
        """Create a new environment."""
        print(f"🚀 Creating environment: {args.name}")

        try:
            self.workspace.create_environment(
                name=args.name,
                comfyui_version=args.comfyui,
                python_version=args.python,
                template_path=args.template
            )
        except Exception as e:
            if logger:
                logger.error(f"Environment creation failed for '{args.name}': {e}", exc_info=True)
            print(f"✗ Failed to create environment: {e}", file=sys.stderr)
            sys.exit(1)

        if args.use:
            try:
                self.workspace.set_active_environment(args.name)

            except Exception as e:
                if logger:
                    logger.error(f"Failed to set active environment '{args.name}': {e}", exc_info=True)
                print(f"✗ Failed to set active environment: {e}", file=sys.stderr)
                sys.exit(1)

        print(f"✓ Environment created: {args.name}")
        if args.use:
            print(f"✓ Active environment set to: {args.name}")
            print("\nNext steps:")
            print("  • Run ComfyUI: comfydock run")
            print("  • Add nodes: comfydock node add <node-name>")
        else:
            print("\nNext steps:")
            print(f"  • Run ComfyUI: comfydock -e {args.name} run")
            print(f"  • Add nodes: comfydock -e {args.name} node add <node-name>")
            print(f"  • Set as active: comfydock use {args.name}")


    @with_env_logging("env use")
    def use(self, args, logger=None):
        """Set the active environment."""
        try:
            self.workspace.set_active_environment(args.name)
        except Exception as e:
            if logger:
                logger.error(f"Failed to set active environment '{args.name}': {e}", exc_info=True)
            print(f"✗ Failed to set active environment: {e}", file=sys.stderr)
            sys.exit(1)

        print(f"✓ Active environment set to: {args.name}")
        print("You can now run commands without the -e flag")


    @with_env_logging("env delete")
    def delete(self, args, logger=None):
        """Delete an environment."""
        # Check that environment exists
        self._get_env(args)

        # Confirm deletion unless --yes is specified
        if not args.yes:
            response = input(f"Delete environment '{args.name}'? This cannot be undone. (y/N): ")
            if response.lower() != 'y':
                print("Cancelled")
                return

        print(f"🗑 Deleting environment: {args.name}")

        try:
            self.workspace.delete_environment(args.name)
        except Exception as e:
            if logger:
                logger.error(f"Environment deletion failed for '{args.name}': {e}", exc_info=True)
            print(f"✗ Failed to delete environment: {e}", file=sys.stderr)
            sys.exit(1)

        print(f"✓ Environment deleted: {args.name}")

    # === Commands that operate IN environments ===

    @with_env_logging("env run")
    def run(self, args):
        """Run ComfyUI in the specified environment."""
        env = self._get_env(args)
        comfyui_args = args.args if hasattr(args, 'args') else []

        # Handle sync if needed
        if not args.no_sync:
            print("🔁 Syncing environment...")
            # from comfydock_cli.interactive.model_resolver import SilentResolver
            # Use silent resolver for run command to avoid interrupting startup
            sync_result = env.sync(model_resolver=InteractiveModelResolver())
            if not sync_result.success:
                for error in sync_result.errors:
                    print(f"⚠️  {error}", file=sys.stderr)

        print(f"🎮 Starting ComfyUI in environment: {env.name}")
        if comfyui_args:
            print(f"   Arguments: {' '.join(comfyui_args)}")

        # Run ComfyUI
        result = env.run(comfyui_args)

        # Exit with ComfyUI's exit code
        sys.exit(result.returncode)

    @with_env_logging("env status")
    def status(self, args):
        """Show environment status using semantic methods."""
        env = self._get_env(args)

        print(f"Environment: {env.name}")
        print(f"Path: {env.path}")

        status = env.status()

        # Show sync status
        if not status.is_synced:
            print('\n===================================================')
            print("🔁 Sync Status: ✗ Out of sync")
            print('===================================================')

            # Show missing/extra nodes
            if status.comparison.missing_nodes:
                print(f"  Missing nodes ({len(status.comparison.missing_nodes)}):")
                for node in status.comparison.missing_nodes:
                    print(f"    - {node}")

            if status.comparison.extra_nodes:
                print(f"  Extra nodes ({len(status.comparison.extra_nodes)}):")
                for node in status.comparison.extra_nodes:
                    print(f"    + {node}")

            if status.comparison.version_mismatches:
                print(f"  Version mismatches ({len(status.comparison.version_mismatches)}):")
                for mismatch in status.comparison.version_mismatches:
                    print(f"    ~ {mismatch['name']}: {mismatch['actual']} → {mismatch['expected']}")

            if not status.comparison.packages_in_sync:
                print(f"  {status.comparison.package_sync_message}")

            # Show workflow sync actions using semantic methods
            workflow_actions = status.get_workflow_sync_actions()
            if workflow_actions:
                print(f"  Workflows ({len(workflow_actions)}):")
                for action in workflow_actions:
                    print(f"    {action.icon} {action.name} ({action.description})")

            print("\n  Run 'comfydock sync' to update tracked files")
        else:
            print('\n===================================================')
            print("🔁 Sync Status: ✓ In sync")
            print('===================================================')

        # Show git status using semantic methods
        if not status.git.has_changes:
            print('\n===================================================')
            print("📦 Git Status: ✓ Clean")
            print('===================================================')
        else:
            changes_summary = status.get_changes_summary()
            print('\n===================================================')
            print(f"📦 Git Status: ~ {changes_summary.get_headline()}")
            print('===================================================')

            # Show detailed changes with consistent formatting
            self._show_git_changes(status)

            # Show recommended action
            action = status.get_recommended_action()
            if action == UserAction.COMMIT_REQUIRED:
                print("\n  Run 'comfydock commit -m \"message\"' to save changes")

            # Show full diff if verbose
            if hasattr(args, 'verbose') and args.verbose and status.git.diff:
                print("\n" + "=" * 60)
                print("Full diff:")
                print("=" * 60)
                print(status.git.diff)

    def _show_git_changes(self, status: EnvironmentStatus):
        """Helper method to show git changes in a structured way."""
        # Show node changes
        if status.git.nodes_added or status.git.nodes_removed:
            print("\n  Custom Nodes:")
            for node in status.git.nodes_added:
                if isinstance(node, dict):
                    name = node['name']
                    suffix = ' (development)' if node.get('is_development') else ''
                    print(f"    + {name}{suffix}")
                else:
                    # Backwards compatibility for string format
                    print(f"    + {node}")
            for node in status.git.nodes_removed:
                if isinstance(node, dict):
                    name = node['name']
                    suffix = ' (development)' if node.get('is_development') else ''
                    print(f"    - {name}{suffix}")
                else:
                    # Backwards compatibility for string format
                    print(f"    - {node}")

        # Show dependency changes
        if status.git.dependencies_added or status.git.dependencies_removed or status.git.dependencies_updated:
            print("\n  Python Packages:")
            for dep in status.git.dependencies_added:
                version = dep.get('version', 'any')
                source = dep.get('source', '')
                if source:
                    print(f"    + {dep['name']} ({version}) [{source}]")
                else:
                    print(f"    + {dep['name']} ({version})")
            for dep in status.git.dependencies_removed:
                version = dep.get('version', 'any')
                print(f"    - {dep['name']} ({version})")
            for dep in status.git.dependencies_updated:
                old = dep.get('old_version', 'any')
                new = dep.get('new_version', 'any')
                print(f"    ~ {dep['name']}: {old} → {new}")

        # Show constraint changes
        if status.git.constraints_added or status.git.constraints_removed:
            print("\n  Constraint Dependencies:")
            for constraint in status.git.constraints_added:
                print(f"    + {constraint}")
            for constraint in status.git.constraints_removed:
                print(f"    - {constraint}")

        # Show workflow changes (tracking and content)
        workflow_changes_shown = False

        # Show tracking changes
        if status.git.workflows_tracked or status.git.workflows_untracked:
            if not workflow_changes_shown:
                print("\n  Workflows:")
                workflow_changes_shown = True
            for name in status.git.workflows_tracked:
                print(f"    📋 {name} (now tracked)")
            for name in status.git.workflows_untracked:
                print(f"    ❌ {name} (untracked)")

        # Show workflow file changes
        if status.git.workflow_changes:
            if not workflow_changes_shown:
                print("\n  Workflows:")
                workflow_changes_shown = True
            for workflow_name, git_status in status.git.workflow_changes.items():
                if git_status == "modified":
                    print(f"    ~ {workflow_name}.json")
                elif git_status == "added":
                    print(f"    + {workflow_name}.json")
                elif git_status == "deleted":
                    print(f"    - {workflow_name}.json")

    @with_env_logging("env log")
    def log(self, args, logger=None):
        """Show environment version history with simple identifiers."""
        env = self._get_env(args)

        try:
            versions = env.get_versions(limit=20)

            if not versions:
                print("No version history yet")
                print("\nTip: Run 'comfydock sync' to create your first version")
                return

            print(f"Version history for environment '{env.name}':\n")

            if not args.verbose:
                # Compact format
                for version in reversed(versions):  # Show newest first
                    print(f"{version['version']}: {version['message']}")
                print()
            else:
                # Detailed format
                for version in reversed(versions):  # Show newest first
                    print(f"Version: {version['version']}")
                    print(f"Message: {version['message']}")
                    print(f"Date:    {version['date'][:19]}")  # Trim timezone for readability
                    print(f"Commit:  {version['hash'][:8]}")
                    print('\n')

            print("Use 'comfydock rollback <version>' to restore to a specific version")

        except Exception as e:
            if logger:
                logger.error(f"Failed to read version history for environment '{env.name}': {e}", exc_info=True)
            print(f"✗ Could not read version history: {e}", file=sys.stderr)
            sys.exit(1)

    # === Node management ===

    @with_env_logging("env node add")
    def node_add(self, args, logger=None):
        """Add a custom node - directly modifies pyproject.toml."""
        env = self._get_env(args)

        if args.dev:
            print(f"🔍 Searching for development node: {args.node_name}")
        else:
            print(f"📦 Adding node: {args.node_name}")

        # Directly add the node
        try:
            env.add_node(args.node_name, is_development=args.dev, no_test=args.no_test)
        except Exception as e:
            if logger:
                logger.error(f"Node add failed for '{args.node_name}': {e}", exc_info=True)
            print(f"✗ Failed to add node '{args.node_name}'", file=sys.stderr)
            print(f"   {e}", file=sys.stderr)
            sys.exit(1)

        print(f"✓ Node '{args.node_name}' added to pyproject.toml")

        # Now try to sync environment:
        if not env.status().is_synced:
            print("🔁 Syncing environment...")
            sync_result = env.sync(model_resolver=InteractiveModelResolver())
            if sync_result.has_unresolved_models:
                print("⚠️  Some workflow models remain unresolved")

        # if result.resolution_success is not None:
        #     if result.conflict_message:
        #         print(result.conflict_message)
        print(f"\nRun 'comfydock -e {env.name} env status' to review changes")
        # print(f"Run 'comfydock -e {env.name} env sync' to apply changes")


    @with_env_logging("env node remove")
    def node_remove(self, args, logger=None):
        """Remove a custom node - directly modifies pyproject.toml."""
        env = self._get_env(args)

        node_type = "development" if hasattr(args, 'dev') and args.dev else ""
        type_msg = f" {node_type}" if node_type else ""
        print(f"🗑 Removing{type_msg} node: {args.node_name}")

        # Directly remove the node
        try:
            env.remove_node(args.node_name)
        except Exception as e:
            if logger:
                logger.error(f"Node remove failed for '{args.node_name}': {e}", exc_info=True)
            print(f"✗ Failed to remove node '{args.node_name}'", file=sys.stderr)
            print(f"   {e}", file=sys.stderr)
            sys.exit(1)

        print(f"✓ Node '{args.node_name}' removed from pyproject.toml")

        # Now try to sync environment:
        if not env.status().is_synced:
            print("🔁 Syncing environment...")
            from comfydock_cli.interactive.model_resolver import InteractiveModelResolver
            sync_result = env.sync(model_resolver=InteractiveModelResolver())
            if sync_result.has_unresolved_models:
                print("⚠️  Some workflow models remain unresolved")

        print(f"\nRun 'comfydock -e {env.name} env status' to review changes")
        # print(f"Run 'comfydock -e {env.name} env sync' to apply changes")

    @with_env_logging("env node list")
    def node_list(self, args):
        """List custom nodes in the environment."""
        env = self._get_env(args)

        # Load pyproject.toml and list nodes
        config = env.pyproject.load()
        nodes = config.get('tool', {}).get('comfydock', {}).get('nodes', {})

        if not nodes:
            print("No custom nodes installed")
            return

        print(f"Custom nodes in '{env.name}':")

        # List regular nodes
        for node_name, info in nodes.items():
            if node_name == 'development':
                continue  # Skip development section
            source = info.get('source', 'unknown')
            print(f"  • {node_name} ({source})")

        # List development nodes
        dev_nodes = nodes.get('development', {})
        for dev_name, _dev_info in dev_nodes.items():
            print(f"  • {dev_name} (development)")

    # === Constraint management ===

    @with_env_logging("env constraint add")
    def constraint_add(self, args, logger=None):
        """Add constraint dependencies to [tool.uv]."""
        env = self._get_env(args)

        print(f"📦 Adding constraints: {' '.join(args.packages)}")

        # Add each constraint
        try:
            for package in args.packages:
                env.add_constraint(package)
        except Exception as e:
            if logger:
                logger.error(f"Constraint add failed: {e}", exc_info=True)
            print("✗ Failed to add constraints", file=sys.stderr)
            print(f"   {e}", file=sys.stderr)
            sys.exit(1)

        print(f"✓ Added {len(args.packages)} constraint(s) to pyproject.toml")
        print(f"\nRun 'comfydock -e {env.name} constraint list' to view all constraints")

    @with_env_logging("env constraint list")
    def constraint_list(self, args):
        """List constraint dependencies from [tool.uv]."""
        env = self._get_env(args)

        # Get constraints from pyproject.toml
        constraints = env.list_constraints()

        if not constraints:
            print("No constraint dependencies configured")
            return

        print(f"Constraint dependencies in '{env.name}':")
        for constraint in constraints:
            print(f"  • {constraint}")

    @with_env_logging("env constraint remove")
    def constraint_remove(self, args, logger=None):
        """Remove constraint dependencies from [tool.uv]."""
        env = self._get_env(args)

        print(f"🗑 Removing constraints: {' '.join(args.packages)}")

        # Remove each constraint
        removed_count = 0
        try:
            for package in args.packages:
                if env.remove_constraint(package):
                    removed_count += 1
                else:
                    print(f"   Warning: constraint '{package}' not found")
        except Exception as e:
            if logger:
                logger.error(f"Constraint remove failed: {e}", exc_info=True)
            print("✗ Failed to remove constraints", file=sys.stderr)
            print(f"   {e}", file=sys.stderr)
            sys.exit(1)

        if removed_count > 0:
            print(f"✓ Removed {removed_count} constraint(s) from pyproject.toml")
        else:
            print("No constraints were removed")

        print(f"\nRun 'comfydock -e {env.name} constraint list' to view remaining constraints")

    # === Git-based operations ===

    @with_env_logging("env sync")
    def sync(self, args, logger=None):
        """Apply changes: commit pyproject.toml and run uv sync."""
        env = self._get_env(args)

        # Get status first
        status = env.status()

        if status.is_synced and status.workflow.in_sync:
            print("✓ No changes to apply")
            return

        # Confirm unless --yes
        if not args.yes:
            preview = status.get_sync_preview()
            print("This will apply the following changes:")

            if preview.nodes_to_install:
                print(f"  • Install {len(preview.nodes_to_install)} missing nodes:")
                for node in preview.nodes_to_install:
                    print(f"    - {node}")

            if preview.nodes_to_remove:
                print(f"  • Remove {len(preview.nodes_to_remove)} extra nodes:")
                for node in preview.nodes_to_remove:
                    print(f"    - {node}")

            if preview.nodes_to_update:
                print(f"  • Update {len(preview.nodes_to_update)} nodes to correct versions:")
                for mismatch in preview.nodes_to_update:
                    print(f"    - {mismatch['name']}: {mismatch['actual']} → {mismatch['expected']}")

            if preview.packages_to_sync:
                print("  • Sync Python packages")

            if preview.workflows_to_sync:
                print(f"  • Sync {len(preview.workflows_to_sync)} workflows:")
                for action in preview.workflows_to_sync:
                    print(f"    - {action.name} ({action.description})")

            response = input("\nContinue? (y/N): ")
            if response.lower() != 'y':
                print("Cancelled")
                return

        print(f"⚙️ Applying changes to: {env.name}")

        # Apply changes with interactive model resolver
        try:
            sync_result = env.sync(model_resolver=InteractiveModelResolver())

            # Check for errors
            if not sync_result.success:
                for error in sync_result.errors:
                    print(f"⚠️  {error}", file=sys.stderr)

            # Show unresolved models warning if any
            if sync_result.has_unresolved_models:
                print("\n⚠️  Some workflow models remain unresolved")
                print("   Update model paths in ComfyUI to resolve")

        except Exception as e:
            if logger:
                logger.error(f"Sync failed for environment '{env.name}': {e}", exc_info=True)
            print(f"✗ Failed to apply changes: {e}", file=sys.stderr)
            sys.exit(1)

        print("✓ Changes applied successfully!")
        print(f"\nEnvironment '{env.name}' is ready to use")

    @with_env_logging("env rollback")
    def rollback(self, args, logger=None):
        """Rollback to previous state or discard uncommitted changes."""
        env = self._get_env(args)

        try:
            # Discard uncommitted changes (with confirmation)
            from comfydock_core.utils.git import get_uncommitted_changes
            uncommitted_files = get_uncommitted_changes(env.cec_path)

            if not args.target and not uncommitted_files:
                print("✓ No uncommitted changes to rollback")
                return

            if uncommitted_files:
                print(f"⚠️  This will discard all uncommitted changes in environment '{env.name}':")
                for file in uncommitted_files[:5]:  # Show first 5 files
                    print(f"    • {file}")
                if len(uncommitted_files) > 5:
                    print(f"    ... and {len(uncommitted_files) - 5} more files")

                if not getattr(args, 'yes', False):
                    response = input("\nAre you sure? This cannot be undone. (y/N): ")
                    if response.lower() != 'y':
                        print("Rollback cancelled")
                        return

            if args.target:
                print(f"⏮ Rolling back environment '{env.name}' to {args.target}")
            else:
                print(f"⏮ Discarding uncommitted changes in environment '{env.name}'")

            env.rollback(target=args.target)
            print("✓ Successfully rolled back")

            # Now try to sync environment:
            if not env.status().is_synced:
                print("🔁 Syncing environment...")
                sync_result = env.sync(model_resolver=InteractiveModelResolver())
                if sync_result.has_unresolved_models:
                    print("⚠️  Some workflow models remain unresolved")

            if args.target:
                print(f"\nEnvironment is now at version {args.target}")
                print("• Run 'comfydock commit -m \"message\"' to save any new changes")
                print("• Run 'comfydock log' to see version history")
            else:
                print("\nUncommitted changes have been discarded")
                print("• Environment is now clean and matches the last commit")
                print("• Run 'comfydock log' to see version history")

        except ValueError as e:
            print(f"✗ {e}", file=sys.stderr)
            print("\nTip: Run 'comfydock log' to see available versions")
            sys.exit(1)
        except Exception as e:
            if logger:
                logger.error(f"Rollback failed for environment '{env.name}': {e}", exc_info=True)
            print(f"✗ Rollback failed: {e}", file=sys.stderr)
            sys.exit(1)

    @with_env_logging("env commit")
    def commit(self, args, logger=None):
        """Commit current state without applying (git commit only)."""
        env = self._get_env(args)

        # Get or generate commit message
        if args.message:
            message = args.message
        else:
            # Auto-generate message based on changes
            status = env.status()
            if not status.git.has_changes:
                print("✓ No changes to commit")
                return

            message = status.generate_commit_message()
            print(f"Auto-generated message: {message}")

        # Commit changes
        from comfydock_core.utils.git import git_commit

        try:
            git_commit(env.cec_path, message)
            print(f"✓ Committed changes: {message}")
        except Exception as e:
            if logger:
                logger.error(f"Commit failed for environment '{env.name}': {e}", exc_info=True)
            print(f"✗ Commit failed: {e}", file=sys.stderr)
            sys.exit(1)


    @with_env_logging("env reset")
    def reset(self, args):
        """Reset uncommitted changes in pyproject.toml."""
        env = self._get_env(args)

        print(f"🔄 Resetting changes for: {env.name}")

        # Git checkout to reset changes
        import subprocess
        cmd = ["git", "checkout", "HEAD", "--", "pyproject.toml"]
        result = subprocess.run(cmd, cwd=env.cec_path, capture_output=True)

        if result.returncode == 0:
            print("✓ Changes reset")
        else:
            print("✗ Reset failed", file=sys.stderr)
            sys.exit(1)

    # === Workflow management ===

    @with_env_logging("workflow list")
    def workflow_list(self, args):
        """List workflow tracking status."""
        env = self._get_env(args)

        workflows = env.scan_workflows()

        if not workflows:
            print("No workflows found")
            return

        print(f"Workflows in '{env.name}':")
        for name, info in workflows.items():
            state_icon = "📋" if info.state == "tracked" else "👁️"
            print(f"  {state_icon} {name} [{info.state}]")

    @with_env_logging("workflow track")
    def workflow_track(self, args, logger=None):
        """Start tracking a workflow with smart model resolution."""
        env = self._get_env(args)

        if args.all:
            # Track all untracked workflows
            workflows = env.scan_workflows()
            untracked = [name for name, info in workflows.items() if info.state == "watched"]

            if not untracked:
                print("No untracked workflows found")
                return

            print(f"Tracking {len(untracked)} workflows...")
            for name in untracked:
                try:
                    # Use new resolution system for each workflow
                    self._track_single_workflow_enhanced(env, name, getattr(args, 'skip_disambiguation', False))
                    print(f"  ✓ {name}")
                except Exception as e:
                    print(f"  ✗ {name}: {e}")
        elif args.name:
            # Track single workflow with new resolution system
            try:
                self._track_single_workflow_enhanced(env, args.name, getattr(args, 'skip_disambiguation', False))
                print(f"✓ Started tracking workflow '{args.name}'")
            except Exception as e:
                if logger:
                    logger.error(f"Workflow track failed for '{args.name}': {e}", exc_info=True)
                print(f"✗ Failed to track workflow '{args.name}': {e}", file=sys.stderr)
                sys.exit(1)
        else:
            print("✗ Either provide a workflow name or use --all", file=sys.stderr)
            sys.exit(1)

    def _track_single_workflow_enhanced(self, env, name: str, skip_disambiguation: bool = False):
        """Track single workflow with enhanced model resolution"""
        # Analyze workflow with new resolution system
        print(f"Analyzing workflow '{name}'...")
        results, existing_metadata = env.workflow_manager.analyze_workflow_models(name)

        # Show resolution summary
        resolver = InteractiveModelResolver()
        resolver.show_summary(results)

        # Handle ambiguous models
        resolutions = None
        ambiguous = [r for r in results if r.resolution_type == "ambiguous"]
        if ambiguous and not skip_disambiguation:
            resolutions = resolver.resolve_ambiguous(results)

        # Track with resolutions
        resolved_count, unresolved_count = env.workflow_manager.track_workflow_with_resolutions(
            name,
            resolutions
        )

        print(f"   {resolved_count} models resolved")
        if unresolved_count > 0:
            print(f"   ⚠️  {unresolved_count} models unresolved")
            print("   Update paths in ComfyUI to resolve")

    @with_env_logging("workflow untrack")
    def workflow_untrack(self, args, logger=None):
        """Stop tracking a workflow."""
        env = self._get_env(args)

        try:
            env.untrack_workflow(args.name)
            print(f"✓ Stopped tracking workflow '{args.name}' (ComfyUI copy preserved)")
        except Exception as e:
            if logger:
                logger.error(f"Workflow untrack failed for '{args.name}': {e}", exc_info=True)
            print(f"✗ Failed to untrack workflow '{args.name}': {e}", file=sys.stderr)
            sys.exit(1)


    @with_env_logging("workflow sync")
    def workflow_sync(self, args):
        """Sync workflows and update metadata"""
        env = self._get_env(args)

        # Sync files with model resolution
        sync_result = env.sync(model_resolver=InteractiveModelResolver())

        # Report results
        if sync_result.workflows_synced:
            any_changed = False
            for name, action in sync_result.workflows_synced.items():
                if action != "in_sync":
                    print(f"Synced '{name}': {action}")
                    any_changed = True

            if not any_changed:
                print("All workflows are in sync")

            # Report model resolution results
            for resolution in sync_result.workflow_resolutions:
                if resolution.unresolved_count > 0:
                    print(f"  ⚠️  '{resolution.name}': {resolution.unresolved_count} models unresolved")
                elif resolution.resolved_count > 0:
                    print(f"  ✅ '{resolution.name}': {resolution.resolved_count} models resolved")
        else:
            print("No workflows to sync")

    # === Environment Model Commands ===

    @with_env_logging("model add")
    def model_add(self, args, logger=None):
        """Add model to environment manifest."""
        env = self._get_env(args)
        workspace = self.workspace

        identifier = args.identifier
        category = 'optional' if args.optional else 'required'

        # if identifier.startswith('http'):
        #     # Download from URL
        #     print(f"📥 Downloading model from {identifier}...")
        #     try:
        #         from ..managers.model_download_manager import ModelDownloadManager
        #         download_manager = ModelDownloadManager(workspace.model_manager)
        #         model = download_manager.download_from_url(identifier)
        #     except Exception as e:
        #         print(f"✗ Failed to download model: {e}", file=sys.stderr)
        #         sys.exit(1)
        # else:
        # Look up in workspace index by hash or filename
        print(f"🔍 Searching for model: {identifier}")
        matches = workspace.search_models(identifier)

        if not matches:
            print(f"✗ Model not found: {identifier}")
            print("Try one of:")
            print("  • Use full or partial hash from 'comfydock model index find'")
            print("  • Use filename from 'comfydock model index list'")
            print("  • Download with URL: comfydock model add https://...")
            sys.exit(1)
        elif len(matches) > 1:
            # Interactive selection
            print(f"Found {len(matches)} models:")
            for i, m in enumerate(matches):
                print(f"  {i+1}. {m.filename} [{m.hash[:8]}...] ({m.relative_path})")

            try:
                choice = input("Select model [1]: ").strip() or "1"
                model_idx = int(choice) - 1
                if 0 <= model_idx < len(matches):
                    model = matches[model_idx]
                else:
                    print("✗ Invalid selection")
                    sys.exit(1)
            except (ValueError, KeyboardInterrupt):
                print("✗ Invalid selection")
                sys.exit(1)
        else:
            model = matches[0]

        # Add to manifest
        try:
            env.pyproject.models.add_model(
                model_hash=model.hash,
                filename=model.filename,
                file_size=model.file_size,
                category=category
            )

            # Link to workflow if specified
            if args.workflow:
                workflow_config = env.pyproject.workflows.get_tracked().get(args.workflow)
                if workflow_config:
                    # Add model to workflow requirements
                    if 'requires' not in workflow_config:
                        workflow_config['requires'] = {}
                    if 'models' not in workflow_config['requires']:
                        workflow_config['requires']['models'] = []

                    if model.hash not in workflow_config['requires']['models']:
                        workflow_config['requires']['models'].append(model.hash)
                        env.pyproject.save()
                        print(f"✓ Linked model to workflow '{args.workflow}'")
                else:
                    print(f"Warning: Workflow '{args.workflow}' not found")

        except Exception as e:
            if logger:
                logger.error(f"Model add failed: {e}", exc_info=True)
            print(f"✗ Failed to add model to manifest: {e}", file=sys.stderr)
            sys.exit(1)

        print(f"✓ Added {category} model: {model.filename}")
        print(f"  Hash: {model.hash[:12]}...")
        print(f"  Path: {model.relative_path}")

    @with_env_logging("model remove")
    def model_remove(self, args, logger=None):
        """Remove model from environment manifest."""
        env = self._get_env(args)

        model_hash = args.hash

        # Find and remove from manifest
        try:
            removed = env.pyproject.models.remove_model(model_hash)
            if not removed:
                print(f"✗ Model not in manifest: {model_hash}")
                print("Use 'comfydock model list' to see current models")
                sys.exit(1)

        except Exception as e:
            if logger:
                logger.error(f"Model remove failed: {e}", exc_info=True)
            print(f"✗ Failed to remove model: {e}", file=sys.stderr)
            sys.exit(1)

        print(f"✓ Removed model: {model_hash[:12]}...")

    @with_env_logging("model list")
    def model_list(self, args, logger=None):
        """List models in environment manifest."""
        env = self._get_env(args)
        workspace = self.workspace

        try:
            manifest = env.pyproject.models.get_all()
        except Exception as e:
            if logger:
                logger.error(f"Model list failed: {e}", exc_info=True)
            print(f"✗ Failed to read model manifest: {e}", file=sys.stderr)
            sys.exit(1)

        required_models = manifest.get('required', {})
        optional_models = manifest.get('optional', {})

        if not required_models and not optional_models:
            print("No models in environment manifest")
            print("\nAdd models with:")
            print("  • comfydock model add <hash|url>")
            print("  • comfydock model add <hash|url> --optional")
            return

        # Check which models are available locally
        print(f"Models in environment '{env.name}':")

        if required_models:
            print("\nRequired Models:")
            for hash, spec in required_models.items():
                local_models = workspace.model_index_manager.find_model_by_hash(hash)
                status = "✓" if local_models else "✗"
                print(f"  {status} {spec['filename']} [{hash[:8]}...]")
                print(f"      Size: {self._format_size(spec['size'])}")

                if not local_models:
                    # Check if we have sources for re-downloading
                    sources = workspace.model_index_manager.get_sources(hash)
                    if sources:
                        print(f"      Available from: {sources[0]['type']}")
                    else:
                        print("      No download sources available")

        if optional_models:
            print("\nOptional Models:")
            for hash, spec in optional_models.items():
                local_models = workspace.model_index_manager.find_model_by_hash(hash)
                status = "✓" if local_models else "○"
                print(f"  {status} {spec['filename']} [{hash[:8]}...]")
                print(f"      Type: {spec['type']} | Size: {self._format_size(spec['size'])}")

                if not local_models:
                    sources = workspace.model_index_manager.get_sources(hash)
                    if sources:
                        print(f"      Available from: {sources[0]['type']}")

        # Summary
        total_required = len(required_models)
        total_optional = len(optional_models)
        available_required = sum(1 for hash in required_models.keys()
                               if workspace.model_index_manager.find_model_by_hash(hash))
        available_optional = sum(1 for hash in optional_models.keys()
                               if workspace.model_index_manager.find_model_by_hash(hash))

        print("\nSummary:")
        print(f"  Required: {available_required}/{total_required} available")
        print(f"  Optional: {available_optional}/{total_optional} available")

        if available_required < total_required:
            print(f"\n⚠️  {total_required - available_required} required models are missing!")

    def _format_size(self, size_bytes: int) -> str:
        """Format file size in human readable form."""
        size = float(size_bytes)
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"
