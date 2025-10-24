"""Environment-specific commands for ComfyDock CLI - Simplified."""
from __future__ import annotations

import sys
from functools import cached_property
from typing import TYPE_CHECKING

from comfydock_core.models.exceptions import CDEnvironmentError, CDNodeConflictError, UVCommandError
from comfydock_core.utils.uv_error_handler import handle_uv_error

from .formatters.error_formatter import NodeErrorFormatter
from .strategies.interactive import InteractiveModelStrategy, InteractiveNodeStrategy

if TYPE_CHECKING:
    from comfydock_core.core.environment import Environment
    from comfydock_core.core.workspace import Workspace
    from comfydock_core.models.environment import EnvironmentStatus
    from comfydock_core.models.workflow import WorkflowAnalysisStatus

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
            except Exception:
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
        print("   This will download PyTorch and dependencies (may take a few minutes)...")
        print()

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
        from comfydock_cli.utils.progress import create_model_sync_progress

        try:
            progress = create_model_sync_progress()
            self.workspace.set_active_environment(args.name, progress=progress)
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
        # Check that environment exists (don't require active environment)
        env_path = self.workspace.paths.environments / args.name
        if not env_path.exists():
            print(f"✗ Environment '{args.name}' not found")
            print("\nAvailable environments:")
            for env in self.workspace.list_environments():
                print(f"  • {env.name}")
            sys.exit(1)

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

        status = env.status()

        # Clean state - everything is good
        if status.is_synced and not status.git.has_changes and status.workflow.sync_status.total_count == 0:
            print(f"Environment: {env.name} ✓")
            print("\n✓ No workflows")
            print("✓ No uncommitted changes")
            return

        # Show environment name
        print(f"Environment: {env.name}")

        # Workflows section - consolidated with issues
        if status.workflow.sync_status.total_count > 0 or status.workflow.sync_status.has_changes:
            print("\n📋 Workflows:")

            # Group workflows by state and show with issues inline
            all_workflows = {}

            # Build workflow map with their analysis
            for wf_analysis in status.workflow.analyzed_workflows:
                all_workflows[wf_analysis.name] = {
                    'state': wf_analysis.sync_state,
                    'has_issues': wf_analysis.has_issues,
                    'analysis': wf_analysis
                }

            # Show workflows with inline issue details
            for name in status.workflow.sync_status.synced:
                if name in all_workflows:
                    wf = all_workflows[name]['analysis']
                    # Show warning if has issues OR path sync needed
                    if wf.has_issues or wf.has_path_sync_issues:
                        print(f"  ⚠️  {name} (synced)")
                        self._print_workflow_issues(wf)
                    else:
                        print(f"  ✓ {name}")

            for name in status.workflow.sync_status.new:
                if name in all_workflows:
                    wf = all_workflows[name]['analysis']
                    # Show warning if has issues OR path sync needed
                    if wf.has_issues or wf.has_path_sync_issues:
                        print(f"  ⚠️  {name} (new)")
                        self._print_workflow_issues(wf)
                    else:
                        print(f"  🆕 {name} (new, ready to commit)")

            for name in status.workflow.sync_status.modified:
                if name in all_workflows:
                    wf = all_workflows[name]['analysis']
                    # Check if workflow has missing models
                    missing_for_wf = [m for m in status.missing_models if name in m.workflow_names]

                    # Show warning if has issues OR path sync needed
                    if wf.has_issues or wf.has_path_sync_issues:
                        print(f"  ⚠️  {name} (modified)")
                        self._print_workflow_issues(wf)
                    elif missing_for_wf:
                        print(f"  ⬇️  {name} (modified, missing models)")
                        print(f"      {len(missing_for_wf)} model(s) need downloading")
                    else:
                        print(f"  📝 {name} (modified)")

            for name in status.workflow.sync_status.deleted:
                print(f"  🗑️  {name} (deleted)")

        # Environment drift (manual edits)
        if not status.comparison.is_synced:
            print("\n⚠️  Environment needs repair:")

            if status.comparison.missing_nodes:
                print(f"  • {len(status.comparison.missing_nodes)} nodes in pyproject.toml not installed")

            if status.comparison.extra_nodes:
                print(f"  • {len(status.comparison.extra_nodes)} extra nodes on filesystem")

            if status.comparison.version_mismatches:
                print(f"  • {len(status.comparison.version_mismatches)} version mismatches")

            if not status.comparison.packages_in_sync:
                print("  • Python packages out of sync")

        # Git changes
        if status.git.has_changes:
            has_specific_changes = (
                status.git.nodes_added or
                status.git.nodes_removed or
                status.git.workflow_changes
            )

            if has_specific_changes:
                print("\n📦 Uncommitted changes:")
                if status.git.nodes_added:
                    for node in status.git.nodes_added[:3]:
                        name = node['name'] if isinstance(node, dict) else node
                        print(f"  • Added node: {name}")
                    if len(status.git.nodes_added) > 3:
                        print(f"  • ... and {len(status.git.nodes_added) - 3} more nodes")

                if status.git.nodes_removed:
                    for node in status.git.nodes_removed[:3]:
                        name = node['name'] if isinstance(node, dict) else node
                        print(f"  • Removed node: {name}")
                    if len(status.git.nodes_removed) > 3:
                        print(f"  • ... and {len(status.git.nodes_removed) - 3} more nodes")

                if status.git.workflow_changes:
                    count = len(status.git.workflow_changes)
                    print(f"  • {count} workflow(s) changed")
            else:
                # Generic message for other changes (e.g., model resolutions)
                print("\n📦 Uncommitted changes:")
                print("  • Configuration updated")

        # Dev node drift (requirements changed)
        dev_drift = env.check_development_node_drift()
        if dev_drift:
            print("\n🔧 Dev node updates available:")
            for node_name in list(dev_drift.keys())[:3]:
                print(f"  • {node_name}")
            if len(dev_drift) > 3:
                print(f"  • ... and {len(dev_drift) - 3} more")

        # Suggested actions - smart and contextual
        self._show_smart_suggestions(status, dev_drift)

    # Removed: _has_uninstalled_packages - this logic is now in core's WorkflowAnalysisStatus

    def _print_workflow_issues(self, wf_analysis: WorkflowAnalysisStatus):
        """Print compact workflow issues summary using model properties only."""
        # Build compact summary using WorkflowAnalysisStatus properties (no pyproject access!)
        parts = []

        # Path sync warnings (FIRST - most actionable fix)
        if wf_analysis.models_needing_path_sync_count > 0:
            parts.append(f"{wf_analysis.models_needing_path_sync_count} model paths need syncing")

        # Use the uninstalled_count property (populated by core)
        if wf_analysis.uninstalled_count > 0:
            parts.append(f"{wf_analysis.uninstalled_count} packages needed for installation")

        # Resolution issues
        if wf_analysis.resolution.nodes_unresolved:
            parts.append(f"{len(wf_analysis.resolution.nodes_unresolved)} nodes couldn't be resolved")
        if wf_analysis.resolution.models_unresolved:
            parts.append(f"{len(wf_analysis.resolution.models_unresolved)} models not found")
        if wf_analysis.resolution.models_ambiguous:
            parts.append(f"{len(wf_analysis.resolution.models_ambiguous)} ambiguous models")

        # Show download intents as pending work (not blocking but needs attention)
        download_intents = [m for m in wf_analysis.resolution.models_resolved if m.match_type == "download_intent"]
        if download_intents:
            parts.append(f"{len(download_intents)} models queued for download")

        # Print compact issue line
        if parts:
            print(f"      {', '.join(parts)}")

    def _show_smart_suggestions(self, status, dev_drift):
        """Show contextual suggestions based on current state."""
        env = self._get_env(type('Args', (), {'target_env': None})())  # Get current env
        suggestions = []

        # Differentiate workflow-related nodes from orphan nodes
        uninstalled_workflow_nodes = set()
        for wf in status.workflow.analyzed_workflows:
            uninstalled_workflow_nodes.update(env.get_uninstalled_nodes(wf.name))

        orphan_missing_nodes = set(status.comparison.missing_nodes) - uninstalled_workflow_nodes
        has_orphan_nodes = bool(orphan_missing_nodes or status.comparison.extra_nodes)

        # Missing models + environment drift: check if repair needed first
        if status.missing_models and has_orphan_nodes:
            suggestions.append("Install missing nodes: comfydock repair")

            # Group workflows with missing models
            workflows_with_missing = {}
            for missing_info in status.missing_models:
                for wf_name in missing_info.workflow_names:
                    if wf_name not in workflows_with_missing:
                        workflows_with_missing[wf_name] = []
                    workflows_with_missing[wf_name].append(missing_info)

            if len(workflows_with_missing) == 1:
                wf_name = list(workflows_with_missing.keys())[0]
                suggestions.append(f"Then resolve workflow: comfydock workflow resolve \"{wf_name}\"")
            else:
                suggestions.append("Then resolve workflow (pick one):")
                for wf_name in list(workflows_with_missing.keys())[:2]:
                    suggestions.append(f"  comfydock workflow resolve \"{wf_name}\"")

            print("\n💡 Next:")
            for s in suggestions:
                print(f"  {s}")
            return

        # Missing models only (no orphan nodes) - workflow resolve handles everything
        if status.missing_models:
            workflows_with_missing = {}
            for missing_info in status.missing_models:
                for wf_name in missing_info.workflow_names:
                    if wf_name not in workflows_with_missing:
                        workflows_with_missing[wf_name] = []
                    workflows_with_missing[wf_name].append(missing_info)

            if len(workflows_with_missing) == 1:
                wf_name = list(workflows_with_missing.keys())[0]
                suggestions.append(f"Resolve workflow: comfydock workflow resolve \"{wf_name}\"")
            else:
                suggestions.append("Resolve workflows with missing models (pick one):")
                for wf_name in list(workflows_with_missing.keys())[:3]:
                    suggestions.append(f"  comfydock workflow resolve \"{wf_name}\"")
                if len(workflows_with_missing) > 3:
                    suggestions.append(f"  ... and {len(workflows_with_missing) - 3} more")

            print("\n💡 Next:")
            for s in suggestions:
                print(f"  {s}")
            return

        # Environment drift only (no workflow issues)
        if not status.comparison.is_synced:
            suggestions.append("Run: comfydock repair")
            print("\n💡 Next:")
            for s in suggestions:
                print(f"  {s}")
            return

        # Path sync warnings (prioritize - quick fix!)
        workflows_needing_sync = [
            w for w in status.workflow.analyzed_workflows
            if w.has_path_sync_issues
        ]

        if workflows_needing_sync:
            workflow_names = [w.name for w in workflows_needing_sync]
            if len(workflow_names) == 1:
                suggestions.append(f"Sync model paths: comfydock workflow resolve \"{workflow_names[0]}\"")
            else:
                suggestions.append(f"Sync model paths in {len(workflow_names)} workflows: comfydock workflow resolve \"<name>\"")

        # Check for workflows with download intents
        workflows_with_downloads = []
        for wf in status.workflow.analyzed_workflows:
            download_intents = [m for m in wf.resolution.models_resolved if m.match_type == "download_intent"]
            if download_intents:
                workflows_with_downloads.append(wf.name)

        # Workflows with issues (unresolved/ambiguous)
        workflows_with_issues = [w.name for w in status.workflow.workflows_with_issues]
        if workflows_with_issues:
            if len(workflows_with_issues) == 1:
                suggestions.append(f"Fix issues: comfydock workflow resolve \"{workflows_with_issues[0]}\"")
            else:
                suggestions.append("Fix workflows (pick one):")
                for wf_name in workflows_with_issues[:3]:
                    suggestions.append(f"  comfydock workflow resolve \"{wf_name}\"")
                if len(workflows_with_issues) > 3:
                    suggestions.append(f"  ... and {len(workflows_with_issues) - 3} more")

            # Only suggest committing if there are uncommitted changes
            if status.git.has_changes:
                suggestions.append("Or commit anyway: comfydock commit -m \"...\" --allow-issues")

        # Workflows with queued downloads (no other issues)
        elif workflows_with_downloads:
            if len(workflows_with_downloads) == 1:
                suggestions.append(f"Complete downloads: comfydock workflow resolve \"{workflows_with_downloads[0]}\"")
            else:
                suggestions.append("Complete downloads (pick one):")
                for wf_name in workflows_with_downloads[:3]:
                    suggestions.append(f"  comfydock workflow resolve \"{wf_name}\"")

        # Ready to commit (workflow changes OR git changes)
        elif status.workflow.sync_status.has_changes and status.workflow.is_commit_safe:
            suggestions.append("Commit workflows: comfydock commit -m \"<message>\"")
        elif status.git.has_changes:
            # Uncommitted pyproject changes without workflow issues
            suggestions.append("Commit changes: comfydock commit -m \"<message>\"")

        # Dev node updates
        if dev_drift:
            for node_name in list(dev_drift.keys())[:1]:
                suggestions.append(f"Update dev node: comfydock node update {node_name}")

        # Show suggestions if any
        if suggestions:
            print("\n💡 Next:")
            for s in suggestions:
                print(f"  {s}")

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

        # Workflow tracking no longer needed - all workflows are automatically managed

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
        """Add custom node(s) - directly modifies pyproject.toml."""
        env = self._get_env(args)

        # Batch mode: multiple nodes
        if len(args.node_names) > 1:
            print(f"📦 Adding {len(args.node_names)} nodes...")

            # Create callbacks for progress display
            def on_node_start(node_id, idx, total):
                print(f"  [{idx}/{total}] Installing {node_id}...", end=" ", flush=True)

            def on_node_complete(node_id, success, error):
                if success:
                    print("✓")
                else:
                    print(f"✗ ({error})")

            from comfydock_core.models.workflow import NodeInstallCallbacks
            callbacks = NodeInstallCallbacks(
                on_node_start=on_node_start,
                on_node_complete=on_node_complete
            )

            # Install nodes with progress feedback
            installed_count, failed_nodes = env.install_nodes_with_progress(
                args.node_names,
                callbacks=callbacks
            )

            if installed_count > 0:
                print(f"\n✅ Installed {installed_count}/{len(args.node_names)} nodes")

            if failed_nodes:
                print(f"\n⚠️  Failed to install {len(failed_nodes)} nodes:")
                for node_id, error in failed_nodes:
                    print(f"  • {node_id}: {error}")

            print(f"\nRun 'comfydock -e {env.name} env status' to review changes")
            return

        # Single node mode (original behavior)
        node_name = args.node_names[0]

        if args.dev:
            print(f"📦 Adding development node: {node_name}")
        else:
            print(f"📦 Adding node: {node_name}")

        # Directly add the node
        try:
            node_info = env.add_node(node_name, is_development=args.dev, no_test=args.no_test, force=args.force)
        except CDNodeConflictError as e:
            # Use formatter to render error with CLI commands
            formatted = NodeErrorFormatter.format_conflict_error(e)
            if logger:
                logger.error(f"Node conflict for '{node_name}': {e}", exc_info=True)
            print(f"✗ Cannot add node '{node_name}'", file=sys.stderr)
            print(formatted, file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            if logger:
                logger.error(f"Node add failed for '{node_name}': {e}", exc_info=True)
            print(f"✗ Failed to add node '{node_name}'", file=sys.stderr)
            print(f"   {e}", file=sys.stderr)
            sys.exit(1)

        if args.dev:
            print(f"✓ Development node '{node_info.name}' added and tracked")
        else:
            print(f"✓ Node '{node_info.name}' added to pyproject.toml")

        print(f"\nRun 'comfydock -e {env.name} env status' to review changes")

    @with_env_logging("env node remove")
    def node_remove(self, args, logger=None):
        """Remove custom node(s) - handles filesystem immediately."""
        env = self._get_env(args)

        # Batch mode: multiple nodes
        if len(args.node_names) > 1:
            print(f"🗑 Removing {len(args.node_names)} nodes...")

            # Create callbacks for progress display
            def on_node_start(node_id, idx, total):
                print(f"  [{idx}/{total}] Removing {node_id}...", end=" ", flush=True)

            def on_node_complete(node_id, success, error):
                if success:
                    print("✓")
                else:
                    print(f"✗ ({error})")

            from comfydock_core.models.workflow import NodeInstallCallbacks
            callbacks = NodeInstallCallbacks(
                on_node_start=on_node_start,
                on_node_complete=on_node_complete
            )

            # Remove nodes with progress feedback
            removed_count, failed_nodes = env.remove_nodes_with_progress(
                args.node_names,
                callbacks=callbacks
            )

            if removed_count > 0:
                print(f"\n✅ Removed {removed_count}/{len(args.node_names)} nodes")

            if failed_nodes:
                print(f"\n⚠️  Failed to remove {len(failed_nodes)} nodes:")
                for node_id, error in failed_nodes:
                    print(f"  • {node_id}: {error}")

            print(f"\nRun 'comfydock -e {env.name} env status' to review changes")
            return

        # Single node mode (original behavior)
        node_name = args.node_names[0]

        print(f"🗑 Removing node: {node_name}")

        # Remove the node (handles filesystem imperatively)
        try:
            result = env.remove_node(node_name)
        except Exception as e:
            if logger:
                logger.error(f"Node remove failed for '{node_name}': {e}", exc_info=True)
            print(f"✗ Failed to remove node '{node_name}'", file=sys.stderr)
            print(f"   {e}", file=sys.stderr)
            sys.exit(1)

        # Render result based on node type and action
        if result.source == "development":
            if result.filesystem_action == "disabled":
                print(f"ℹ️  Development node '{result.name}' removed from tracking")
                print(f"   Files preserved at: custom_nodes/{result.name}.disabled/")
            else:
                print(f"✓ Development node '{result.name}' removed from tracking")
        else:
            print(f"✓ Node '{result.name}' removed from environment")
            if result.filesystem_action == "deleted":
                print("   (cached globally, can reinstall)")

        print(f"\nRun 'comfydock -e {env.name} env status' to review changes")

    @with_env_logging("env node list")
    def node_list(self, args):
        """List custom nodes in the environment."""
        env = self._get_env(args)

        nodes = env.list_nodes()

        if not nodes:
            print("No custom nodes installed")
            return

        print(f"Custom nodes in '{env.name}':")
        for node in nodes:
            print(f"  • {node.registry_id or node.name} ({node.source})")

    @with_env_logging("env node update")
    def node_update(self, args, logger=None):
        """Update a custom node."""
        from comfydock_core.strategies.confirmation import (
            AutoConfirmStrategy,
            InteractiveConfirmStrategy,
        )

        env = self._get_env(args)

        print(f"🔄 Updating node: {args.node_name}")

        # Choose confirmation strategy
        strategy = AutoConfirmStrategy() if args.yes else InteractiveConfirmStrategy()

        try:
            result = env.update_node(
                args.node_name,
                confirmation_strategy=strategy,
                no_test=args.no_test
            )

            if result.changed:
                print(f"✓ {result.message}")

                if result.source == 'development':
                    if result.requirements_added:
                        print("  Added dependencies:")
                        for dep in result.requirements_added:
                            print(f"    + {dep}")
                    if result.requirements_removed:
                        print("  Removed dependencies:")
                        for dep in result.requirements_removed:
                            print(f"    - {dep}")

                print("\nRun 'comfydock status' to review changes")
            else:
                print(f"ℹ️  {result.message}")

        except Exception as e:
            if logger:
                logger.error(f"Node update failed for '{args.node_name}': {e}", exc_info=True)
            print(f"✗ Failed to update node '{args.node_name}'", file=sys.stderr)
            print(f"   {e}", file=sys.stderr)
            sys.exit(1)

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

    @with_env_logging("env repair")
    def repair(self, args, logger=None):
        """Repair environment to match pyproject.toml (for manual edits or git operations)."""
        env = self._get_env(args)

        # Get status first
        status = env.status()

        if status.is_synced:
            print("✓ No changes to apply")
            return

        # Confirm unless --yes
        if not args.yes:
            preview = status.get_sync_preview()

            # Check if there are actually any changes to show
            has_changes = (
                preview['nodes_to_install'] or
                preview['nodes_to_remove'] or
                preview['nodes_to_update'] or
                preview['packages_to_sync'] or
                preview['workflows_to_add'] or
                preview['workflows_to_update'] or
                preview['workflows_to_remove'] or
                preview.get('models_downloadable') or
                preview.get('models_unavailable')
            )

            if not has_changes:
                print("✓ No changes to apply (environment is synced)")
                return

            print("This will apply the following changes:")

            if preview['nodes_to_install']:
                print(f"  • Install {len(preview['nodes_to_install'])} missing nodes:")
                for node in preview['nodes_to_install']:
                    print(f"    - {node}")

            if preview['nodes_to_remove']:
                print(f"  • Remove {len(preview['nodes_to_remove'])} extra nodes:")
                for node in preview['nodes_to_remove']:
                    print(f"    - {node}")

            if preview['nodes_to_update']:
                print(f"  • Update {len(preview['nodes_to_update'])} nodes to correct versions:")
                for mismatch in preview['nodes_to_update']:
                    print(f"    - {mismatch['name']}: {mismatch['actual']} → {mismatch['expected']}")

            if preview['packages_to_sync']:
                print("  • Sync Python packages")

            # Show workflow changes categorized by operation
            if preview['workflows_to_add']:
                print(f"  • Add {len(preview['workflows_to_add'])} new workflow(s) to ComfyUI:")
                for workflow_name in preview['workflows_to_add']:
                    print(f"    - {workflow_name}")

            if preview['workflows_to_update']:
                print(f"  • Update {len(preview['workflows_to_update'])} workflow(s) in ComfyUI:")
                for workflow_name in preview['workflows_to_update']:
                    print(f"    - {workflow_name}")

            if preview['workflows_to_remove']:
                print(f"  • Remove {len(preview['workflows_to_remove'])} workflow(s) from ComfyUI:")
                for workflow_name in preview['workflows_to_remove']:
                    print(f"    - {workflow_name}")

            # Show model download preview with URLs and paths
            if preview.get('models_downloadable'):
                print(f"\n  Models:")
                count = len(preview['models_downloadable'])
                print(f"    • Download {count} missing model(s):\n")
                for idx, missing_info in enumerate(preview['models_downloadable'][:5], 1):
                    print(f"      [{idx}/{min(count, 5)}] {missing_info.model.filename} ({missing_info.criticality})")
                    # Show source URL
                    if missing_info.model.sources:
                        source_url = missing_info.model.sources[0]
                        # Truncate long URLs
                        if len(source_url) > 70:
                            display_url = source_url[:67] + "..."
                        else:
                            display_url = source_url
                        print(f"         From: {display_url}")
                    # Show target path
                    print(f"           To: {missing_info.model.relative_path}")
                if count > 5:
                    print(f"\n      ... and {count - 5} more")

            if preview.get('models_unavailable'):
                print(f"\n  ⚠️  Models unavailable:")
                for missing_info in preview['models_unavailable'][:3]:
                    print(f"      - {missing_info.model.filename} (no sources)")

            response = input("\nContinue? (y/N): ")
            if response.lower() != 'y':
                print("Cancelled")
                return

        print(f"⚙️ Applying changes to: {env.name}")

        # Create callbacks for node and model progress
        from comfydock_core.models.workflow import BatchDownloadCallbacks, NodeInstallCallbacks
        from .utils.progress import create_progress_callback

        # Node installation callbacks
        def on_node_start(node_id, idx, total):
            print(f"  [{idx}/{total}] Installing {node_id}...", end=" ", flush=True)

        def on_node_complete(node_id, success, error):
            if success:
                print("✓")
            else:
                print(f"✗ ({error})")

        node_callbacks = NodeInstallCallbacks(
            on_node_start=on_node_start,
            on_node_complete=on_node_complete
        )

        # Model download callbacks
        def on_file_start(filename, idx, total):
            print(f"   [{idx}/{total}] Downloading {filename}...")

        def on_file_complete(filename, success, error):
            print()  # New line after progress bar
            if success:
                print(f"   ✓ {filename}")
            else:
                print(f"   ✗ {filename}: {error}")

        model_callbacks = BatchDownloadCallbacks(
            on_file_start=on_file_start,
            on_file_progress=create_progress_callback(),
            on_file_complete=on_file_complete
        )

        # Apply changes with node and model callbacks
        try:
            # Show header if nodes to install
            if preview['nodes_to_install']:
                print("\n⬇️  Installing nodes...")

            model_strategy = getattr(args, 'models', 'all')
            sync_result = env.sync(
                model_strategy=model_strategy,
                model_callbacks=model_callbacks,
                node_callbacks=node_callbacks
            )

            # Show completion message if nodes were installed
            if preview['nodes_to_install']:
                print()  # Blank line after node installation

            # Check for errors
            if not sync_result.success:
                for error in sync_result.errors:
                    print(f"⚠️  {error}", file=sys.stderr)

            # Show model download summary
            if sync_result.models_downloaded:
                print(f"\n✓ Downloaded {len(sync_result.models_downloaded)} model(s)")

            if sync_result.models_failed:
                print(f"\n⚠️  {len(sync_result.models_failed)} model(s) failed:")
                for filename, error in sync_result.models_failed[:3]:
                    print(f"   • {filename}: {error}")

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
        from .strategies.rollback import AutoRollbackStrategy, InteractiveRollbackStrategy

        env = self._get_env(args)

        try:
            if args.target:
                print(f"⏮ Rolling back environment '{env.name}' to {args.target}")
            else:
                print(f"⏮ Discarding uncommitted changes in environment '{env.name}'")

            # Choose strategy based on --yes flag
            if getattr(args, 'yes', False) or getattr(args, 'force', False):
                strategy = AutoRollbackStrategy()
            else:
                strategy = InteractiveRollbackStrategy()

            # Execute rollback with strategy
            env.rollback(
                target=args.target,
                force=getattr(args, 'force', False),
                strategy=strategy
            )

            print("✓ Rollback complete")

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
        except CDEnvironmentError as e:
            print(f"✗ {e}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            if logger:
                logger.error(f"Rollback failed for environment '{env.name}': {e}", exc_info=True)
            print(f"✗ Rollback failed: {e}", file=sys.stderr)
            sys.exit(1)

    @with_env_logging("env commit")
    def commit(self, args, logger=None):
        """Commit workflows with optional issue resolution."""
        env = self._get_env(args)

        print("📋 Analyzing workflows...")

        # Get workflow status (read-only analysis)
        try:
            workflow_status = env.workflow_manager.get_workflow_status()

            if logger:
                logger.debug(f"Workflow status: {workflow_status.sync_status}")

            # Check if there are ANY committable changes (workflows OR git)
            if not env.has_committable_changes():
                print("✓ No changes to commit")
                return

        except Exception as e:
            if logger:
                logger.error(f"Workflow analysis failed: {e}", exc_info=True)
            print(f"✗ Failed to analyze workflows: {e}", file=sys.stderr)
            sys.exit(1)

        # Check commit safety
        if not workflow_status.is_commit_safe and not getattr(args, 'allow_issues', False):
            print("\n⚠ Cannot commit - workflows have unresolved issues:\n")
            for wf in workflow_status.workflows_with_issues:
                print(f"  • {wf.name}: {wf.issue_summary}")

            print("\n💡 Options:")
            print("  1. Resolve issues: comfydock workflow resolve \"<name>\"")
            print("  2. Force commit: comfydock commit -m 'msg' --allow-issues")
            sys.exit(1)

        # Execute commit with chosen strategies
        try:
            env.execute_commit(
                workflow_status=workflow_status,
                message=args.message,
                allow_issues=getattr(args, 'allow_issues', False)
            )
        except Exception as e:
            if logger:
                logger.error(f"Commit failed for environment '{env.name}': {e}", exc_info=True)
            print(f"✗ Commit failed: {e}", file=sys.stderr)
            sys.exit(1)

        # Display results on success
        print(f"✅ Commit successful: {args.message if args.message else 'Update workflows'}")

        # Show what was done
        new_count = len(workflow_status.sync_status.new)
        modified_count = len(workflow_status.sync_status.modified)
        deleted_count = len(workflow_status.sync_status.deleted)

        if new_count > 0:
            print(f"  • Added {new_count} workflow(s)")
        if modified_count > 0:
            print(f"  • Updated {modified_count} workflow(s)")
        if deleted_count > 0:
            print(f"  • Deleted {deleted_count} workflow(s)")

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

    @with_env_logging("workflow list", get_env_name=lambda self, args: self._get_env(args).name)
    def workflow_list(self, args):
        """List all workflows with their sync status."""
        env = self._get_env(args)

        workflows = env.list_workflows()

        if workflows.total_count == 0:
            print("No workflows found")
            return

        print(f"Workflows in '{env.name}':")

        if workflows.synced:
            print("\n✓ Synced (up to date):")
            for name in workflows.synced:
                print(f"  📋 {name}")

        if workflows.modified:
            print("\n⚠ Modified (changed since last commit):")
            for name in workflows.modified:
                print(f"  📝 {name}")

        if workflows.new:
            print("\n🆕 New (not committed yet):")
            for name in workflows.new:
                print(f"  ➕ {name}")

        if workflows.deleted:
            print("\n🗑 Deleted (removed from ComfyUI):")
            for name in workflows.deleted:
                print(f"  ➖ {name}")

        # Show commit suggestion if there are changes
        if workflows.has_changes:
            print("\nRun 'comfydock commit' to save current state")

    @with_env_logging("workflow resolve", get_env_name=lambda self, args: self._get_env(args).name)
    def workflow_resolve(self, args, logger=None):
        """Resolve workflow dependencies interactively."""
        env = self._get_env(args)

        # Choose strategy
        if args.auto:
            from comfydock_core.strategies.auto import AutoModelStrategy, AutoNodeStrategy
            node_strategy = AutoNodeStrategy()
            model_strategy = AutoModelStrategy()
        else:
            node_strategy = InteractiveNodeStrategy()
            model_strategy = InteractiveModelStrategy()

        # Phase 1: Resolve dependencies (updates pyproject.toml)
        print("\n🔧 Resolving dependencies...")
        try:
            from comfydock_cli.utils.progress import create_batch_download_callbacks

            result = env.resolve_workflow(
                name=args.name,
                node_strategy=node_strategy,
                model_strategy=model_strategy,
                download_callbacks=create_batch_download_callbacks()
            )
        except FileNotFoundError as e:
            if logger:
                logger.error(f"Resolution failed for '{args.name}': {e}", exc_info=True)
            workflow_path = env.workflow_manager.comfyui_workflows / f"{args.name}.json"
            print(f"✗ Workflow '{args.name}' not found at {workflow_path}")
            sys.exit(1)
        except Exception as e:
            if logger:
                logger.error(f"Resolution failed for '{args.name}': {e}", exc_info=True)
            print(f"✗ Failed to resolve dependencies: {e}", file=sys.stderr)
            sys.exit(1)

        # Phase 2: Check for uninstalled nodes and prompt for installation
        uninstalled_nodes = env.get_uninstalled_nodes(workflow_name=args.name)

        if uninstalled_nodes:
            print(f"\n📦 Found {len(uninstalled_nodes)} missing node packs:")
            for node_id in uninstalled_nodes:
                print(f"  • {node_id}")

            # Determine if we should install
            should_install = False

            if hasattr(args, 'install') and args.install:
                # Auto-install mode
                should_install = True
            elif hasattr(args, 'no_install') and args.no_install:
                # Skip install mode
                should_install = False
            else:
                # Interactive prompt (default)
                try:
                    response = input("\nInstall missing nodes? (Y/n): ").strip().lower()
                    should_install = response in ['', 'y', 'yes']
                except KeyboardInterrupt:
                    print("\nSkipped node installation")
                    should_install = False

            if should_install:
                from comfydock_core.models.workflow import NodeInstallCallbacks

                print("\n⬇️  Installing nodes...")

                # Create callbacks for progress display
                def on_node_start(node_id, idx, total):
                    print(f"  [{idx}/{total}] Installing {node_id}...", end=" ", flush=True)

                def on_node_complete(node_id, success, error):
                    if success:
                        print("✓")
                    else:
                        # Handle UV-specific errors
                        if "UVCommandError" in str(error) and logger:
                            from comfydock_core.integrations.uv_command import UVCommandError
                            try:
                                # Try to extract meaningful error
                                user_msg = error.split(":", 1)[1].strip() if ":" in error else error
                                print(f"✗ ({user_msg})")
                            except:
                                print(f"✗ ({error})")
                        else:
                            print(f"✗ ({error})")

                callbacks = NodeInstallCallbacks(
                    on_node_start=on_node_start,
                    on_node_complete=on_node_complete
                )

                # Install nodes with progress feedback
                installed_count, failed_nodes = env.install_nodes_with_progress(
                    uninstalled_nodes,
                    callbacks=callbacks
                )

                if installed_count > 0:
                    print(f"\n✅ Installed {installed_count}/{len(uninstalled_nodes)} nodes")

                if failed_nodes:
                    print(f"\n⚠️  Failed to install {len(failed_nodes)} nodes:")
                    for node_id, error in failed_nodes:
                        print(f"  • {node_id}")
                    print("\n💡 For detailed error information:")
                    print(f"   {self.workspace.path}/logs/{env.name}.log")
                    print("\nYou can try installing them manually:")
                    print("  comfydock node add <node-id>")
            else:
                print("\nℹ️  Skipped node installation. To install later:")
                print(f"  • Re-run: comfydock workflow resolve \"{args.name}\"")
                print("  • Or install individually: comfydock node add <node-id>")

        # Display final results - check issues first
        uninstalled = env.get_uninstalled_nodes(workflow_name=args.name)

        if result.has_issues or uninstalled:
            print("\n⚠️  Partial resolution - issues remain:")

            # Show what was resolved
            if result.models_resolved:
                print(f"  ✓ Resolved {len(result.models_resolved)} models")
            if result.nodes_resolved:
                print(f"  ✓ Resolved {len(result.nodes_resolved)} nodes")

            # Show what's still broken
            if result.nodes_unresolved:
                print(f"  ✗ {len(result.nodes_unresolved)} nodes couldn't be resolved")
            if result.models_unresolved:
                print(f"  ✗ {len(result.models_unresolved)} models not found")
            if result.models_ambiguous:
                print(f"  ✗ {len(result.models_ambiguous)} ambiguous models")
            if uninstalled:
                print(f"  ✗ {len(uninstalled)} packages need installation")

            print("\n💡 Next:")
            print(f"  Re-run: comfydock workflow resolve \"{args.name}\"")
            print("  Or commit with issues: comfydock commit -m \"...\" --allow-issues")

        elif result.models_resolved or result.nodes_resolved:
            # Check for failed download intents by querying current state (not stale result)
            # Downloads execute AFTER result is created, so we need fresh state
            current_models = env.pyproject.workflows.get_workflow_models(args.name)
            failed_downloads = [
                m for m in current_models
                if m.status == 'unresolved' and m.sources  # Has download intent but still unresolved
            ]

            if failed_downloads:
                print("\n⚠️  Resolution partially complete:")
                # Count successful resolutions (not download intents or successful downloads)
                successful_models = [
                    m for m in result.models_resolved
                    if m.match_type != 'download_intent' or m.resolved_model is not None
                ]
                if successful_models:
                    print(f"  ✓ Resolved {len(successful_models)} models")
                if result.nodes_resolved:
                    print(f"  ✓ Resolved {len(result.nodes_resolved)} nodes")

                print(f"  ⚠️  {len(failed_downloads)} model(s) queued for download (failed to fetch)")
                for m in failed_downloads:
                    print(f"      • {m.filename}")

                print("\n💡 Next:")
                print("  Add Civitai API key: comfydock config --civitai-key <your-token>")
                print(f"  Try again: comfydock workflow resolve \"{args.name}\"")
                print("  Or commit anyway: comfydock commit -m \"...\" --allow-issues")
            else:
                print("\n✅ Resolution complete!")
                if result.models_resolved:
                    print(f"  • Resolved {len(result.models_resolved)} models")
                if result.nodes_resolved:
                    print(f"  • Resolved {len(result.nodes_resolved)} nodes")
                print("\n💡 Next:")
                print(f"  Commit workflows: comfydock commit -m \"Resolved {args.name}\"")
        else:
            print("✓ No changes needed - all dependencies already resolved")
