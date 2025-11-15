"""Environment-specific commands for ComfyDock CLI - Simplified."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from functools import cached_property
from typing import TYPE_CHECKING, Any

from comfygit_core.models.exceptions import CDDependencyConflictError, CDEnvironmentError, CDNodeConflictError, CDRegistryDataError, UVCommandError
from comfygit_core.utils.uv_error_handler import handle_uv_error

from .formatters.error_formatter import NodeErrorFormatter
from .strategies.interactive import InteractiveModelStrategy, InteractiveNodeStrategy

if TYPE_CHECKING:
    from comfygit_core.core.environment import Environment
    from comfygit_core.core.workspace import Workspace
    from comfygit_core.models.environment import EnvironmentStatus
    from comfygit_core.models.workflow import WorkflowAnalysisStatus

from .cli_utils import get_workspace_or_exit
from .logging.environment_logger import with_env_logging
from .logging.logging_config import get_logger

logger = get_logger(__name__)


class EnvironmentCommands:
    """Handler for environment-specific commands - simplified for MVP."""

    def __init__(self) -> None:
        """Initialize environment commands handler."""
        pass

    @cached_property
    def workspace(self) -> Workspace:
        return get_workspace_or_exit()

    def _get_or_create_workspace(self, args: argparse.Namespace) -> Workspace:
        """Get existing workspace or initialize a new one with user confirmation.

        This is a delegation to GlobalCommands._get_or_create_workspace to avoid duplication.
        We import and use GlobalCommands here for the shared logic.

        Args:
            args: Command arguments, must have 'yes' attribute for non-interactive mode

        Returns:
            Workspace instance (existing or newly created)
        """
        from .global_commands import GlobalCommands

        global_cmds = GlobalCommands()
        return global_cmds._get_or_create_workspace(args)

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
            print("  • Use -e flag: cg -e my-env <command>")
            print("  • Set active: cg use <name>")
            sys.exit(1)
        return active

    # === Commands that operate ON environments ===

    @with_env_logging("env create")
    def create(self, args: argparse.Namespace, logger=None) -> None:
        """Create a new environment."""
        # Ensure workspace exists, creating it if necessary
        workspace = self._get_or_create_workspace(args)

        print(f"🚀 Creating environment: {args.name}")
        print("   This will download PyTorch and dependencies (may take a few minutes)...")
        print()

        try:
            workspace.create_environment(
                name=args.name,
                comfyui_version=args.comfyui,
                python_version=args.python,
                template_path=args.template,
                torch_backend=args.torch_backend,
            )
        except Exception as e:
            if logger:
                logger.error(f"Environment creation failed for '{args.name}': {e}", exc_info=True)
            print(f"✗ Failed to create environment: {e}", file=sys.stderr)
            sys.exit(1)

        if args.use:
            try:
                workspace.set_active_environment(args.name)

            except Exception as e:
                if logger:
                    logger.error(f"Failed to set active environment '{args.name}': {e}", exc_info=True)
                print(f"✗ Failed to set active environment: {e}", file=sys.stderr)
                sys.exit(1)

        print(f"✓ Environment created: {args.name}")
        if args.use:
            print(f"✓ Active environment set to: {args.name}")
            print("\nNext steps:")
            print("  • Run ComfyUI: cg run")
            print("  • Add nodes: cg node add <node-name>")
        else:
            print("\nNext steps:")
            print(f"  • Run ComfyUI: cg -e {args.name} run")
            print(f"  • Add nodes: cg -e {args.name} node add <node-name>")
            print(f"  • Set as active: cg use {args.name}")

    @with_env_logging("env use")
    def use(self, args: argparse.Namespace, logger=None) -> None:
        """Set the active environment."""
        from comfygit_cli.utils.progress import create_model_sync_progress

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
    def delete(self, args: argparse.Namespace, logger=None) -> None:
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
    def run(self, args: argparse.Namespace) -> None:
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

    def manifest(self, args: argparse.Namespace) -> None:
        """Show environment manifest (pyproject.toml configuration)."""
        env = self._get_env(args)

        import tomlkit
        import yaml

        # Load raw TOML config
        config = env.pyproject.load()

        # Handle section filtering if requested
        if hasattr(args, 'section') and args.section:
            # Navigate to requested section using dot notation
            keys = args.section.split('.')
            current = config
            try:
                for key in keys:
                    current = current[key]
                config = {args.section: current}
            except (KeyError, TypeError):
                print(f"✗ Section not found: {args.section}")
                print("\nAvailable sections:")
                print("  • project")
                print("  • tool.comfygit")
                print("  • tool.comfygit.nodes")
                print("  • tool.comfygit.workflows")
                print("  • tool.comfygit.models")
                print("  • tool.uv")
                print("  • dependency-groups")
                sys.exit(1)

        # Output format
        if hasattr(args, 'pretty') and args.pretty:
            # Convert tomlkit objects to plain Python types recursively
            def to_plain(obj):
                """Recursively convert tomlkit objects to plain Python types."""
                if isinstance(obj, dict):
                    return {k: to_plain(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [to_plain(item) for item in obj]
                elif hasattr(obj, 'unwrap'):  # tomlkit items have unwrap()
                    return to_plain(obj.unwrap())
                else:
                    return obj

            plain_dict = to_plain(config)
            print(yaml.dump(plain_dict, default_flow_style=False, sort_keys=False))
        else:
            # Default: raw TOML (exact file representation)
            print(tomlkit.dumps(config))

    @with_env_logging("env status")
    def status(self, args: argparse.Namespace) -> None:
        """Show environment status using semantic methods."""
        env = self._get_env(args)

        status = env.status()

        # Format branch info
        if status.git.current_branch:
            branch_info = f" (on {status.git.current_branch})"
        else:
            branch_info = ""  # Detached HEAD - show warning separately

        # Clean state - everything is good
        if status.is_synced and not status.git.has_changes and status.workflow.sync_status.total_count == 0:
            print(f"Environment: {env.name}{branch_info} ✓")
            print("\n✓ No workflows")
            print("✓ No uncommitted changes")
            return

        # Show environment name with branch
        print(f"Environment: {env.name}{branch_info}")

        # Detached HEAD warning (shown prominently at top)
        if status.git.current_branch is None:
            print("⚠️  Detached HEAD - commits will not be saved to any branch!")
            print("   Create a branch with: cg checkout -b <branch-name>")

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

                # Show other changes if present
                if status.git.has_other_changes:
                    print("  • Other files modified in .cec/")
            else:
                # Generic message for other changes (e.g., model resolutions)
                print("\n📦 Uncommitted changes:")
                if status.git.has_other_changes:
                    print("  • Other files modified in .cec/")
                else:
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

    def _print_workflow_issues(self, wf_analysis: WorkflowAnalysisStatus) -> None:
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

    def _show_smart_suggestions(self, status: EnvironmentStatus, dev_drift) -> None:
        """Show contextual suggestions based on current state."""
        suggestions = []

        # Differentiate workflow-related nodes from orphan nodes
        uninstalled_workflow_nodes = set()
        for wf in status.workflow.analyzed_workflows:
            uninstalled_workflow_nodes.update(wf.uninstalled_nodes)

        orphan_missing_nodes = set(status.comparison.missing_nodes) - uninstalled_workflow_nodes
        has_orphan_nodes = bool(orphan_missing_nodes or status.comparison.extra_nodes)

        # Missing models + environment drift: check if repair needed first
        if status.missing_models and has_orphan_nodes:
            suggestions.append("Install missing nodes: cg repair")

            # Group workflows with missing models
            workflows_with_missing = {}
            for missing_info in status.missing_models:
                for wf_name in missing_info.workflow_names:
                    if wf_name not in workflows_with_missing:
                        workflows_with_missing[wf_name] = []
                    workflows_with_missing[wf_name].append(missing_info)

            if len(workflows_with_missing) == 1:
                wf_name = list(workflows_with_missing.keys())[0]
                suggestions.append(f"Then resolve workflow: cg workflow resolve \"{wf_name}\"")
            else:
                suggestions.append("Then resolve workflow (pick one):")
                for wf_name in list(workflows_with_missing.keys())[:2]:
                    suggestions.append(f"  cg workflow resolve \"{wf_name}\"")

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
                suggestions.append(f"Resolve workflow: cg workflow resolve \"{wf_name}\"")
            else:
                suggestions.append("Resolve workflows with missing models (pick one):")
                for wf_name in list(workflows_with_missing.keys())[:3]:
                    suggestions.append(f"  cg workflow resolve \"{wf_name}\"")
                if len(workflows_with_missing) > 3:
                    suggestions.append(f"  ... and {len(workflows_with_missing) - 3} more")

            print("\n💡 Next:")
            for s in suggestions:
                print(f"  {s}")
            return

        # Environment drift only (no workflow issues)
        if not status.comparison.is_synced:
            suggestions.append("Run: cg repair")
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
                suggestions.append(f"Sync model paths: cg workflow resolve \"{workflow_names[0]}\"")
            else:
                suggestions.append(f"Sync model paths in {len(workflow_names)} workflows: cg workflow resolve \"<name>\"")

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
                suggestions.append(f"Fix issues: cg workflow resolve \"{workflows_with_issues[0]}\"")
            else:
                suggestions.append("Fix workflows (pick one):")
                for wf_name in workflows_with_issues[:3]:
                    suggestions.append(f"  cg workflow resolve \"{wf_name}\"")
                if len(workflows_with_issues) > 3:
                    suggestions.append(f"  ... and {len(workflows_with_issues) - 3} more")

            # Only suggest committing if there are uncommitted changes
            if status.git.has_changes:
                suggestions.append("Or commit anyway: cg commit -m \"...\" --allow-issues")

        # Workflows with queued downloads (no other issues)
        elif workflows_with_downloads:
            if len(workflows_with_downloads) == 1:
                suggestions.append(f"Complete downloads: cg workflow resolve \"{workflows_with_downloads[0]}\"")
            else:
                suggestions.append("Complete downloads (pick one):")
                for wf_name in workflows_with_downloads[:3]:
                    suggestions.append(f"  cg workflow resolve \"{wf_name}\"")

        # Ready to commit (workflow changes OR git changes)
        elif status.workflow.sync_status.has_changes and status.workflow.is_commit_safe:
            suggestions.append("Commit workflows: cg commit -m \"<message>\"")
        elif status.git.has_changes:
            # Uncommitted pyproject changes without workflow issues
            suggestions.append("Commit changes: cg commit -m \"<message>\"")

        # Dev node updates
        if dev_drift:
            for node_name in list(dev_drift.keys())[:1]:
                suggestions.append(f"Update dev node: cg node update {node_name}")

        # Show suggestions if any
        if suggestions:
            print("\n💡 Next:")
            for s in suggestions:
                print(f"  {s}")

    def _show_git_changes(self, status: EnvironmentStatus) -> None:
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

    @with_env_logging("log")
    def log(self, args: argparse.Namespace, logger=None) -> None:
        """Show environment version history with simple identifiers."""
        env = self._get_env(args)

        try:
            versions = env.get_versions(limit=20)

            if not versions:
                print("No version history yet")
                print("\nTip: Run 'cg commit' to create your first version")
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

            print("Use 'cg rollback <version>' to restore to a specific version")

        except Exception as e:
            if logger:
                logger.error(f"Failed to read version history for environment '{env.name}': {e}", exc_info=True)
            print(f"✗ Could not read version history: {e}", file=sys.stderr)
            sys.exit(1)

    # === Node management ===

    @with_env_logging("env node add")
    def node_add(self, args: argparse.Namespace, logger=None) -> None:
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

            from comfygit_core.models.workflow import NodeInstallCallbacks
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

            print(f"\nRun 'cg -e {env.name} env status' to review changes")
            return

        # Single node mode (original behavior)
        node_name = args.node_names[0]

        if args.dev:
            print(f"📦 Adding development node: {node_name}")
        else:
            print(f"📦 Adding node: {node_name}")

        # Create confirmation strategy for dev node replacement
        from comfygit_core.strategies.confirmation import InteractiveConfirmStrategy
        confirmation_strategy = InteractiveConfirmStrategy()

        # Directly add the node
        try:
            node_info = env.add_node(
                node_name,
                is_development=args.dev,
                no_test=args.no_test,
                force=args.force,
                confirmation_strategy=confirmation_strategy
            )
        except CDRegistryDataError as e:
            # Registry data unavailable
            formatted = NodeErrorFormatter.format_registry_error(e)
            if logger:
                logger.error(f"Registry data unavailable for node add: {e}", exc_info=True)
            print(f"✗ Cannot add node - registry data unavailable", file=sys.stderr)
            print(formatted, file=sys.stderr)
            sys.exit(1)
        except CDDependencyConflictError as e:
            # Dependency conflict with enhanced formatting
            formatted = NodeErrorFormatter.format_dependency_conflict_error(e, verbose=args.verbose)
            if logger:
                logger.error(f"Dependency conflict for '{node_name}': {e}", exc_info=True)
            print(formatted, file=sys.stderr)
            sys.exit(1)
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

        print(f"\nRun 'cg -e {env.name} env status' to review changes")

    @with_env_logging("env node remove")
    def node_remove(self, args: argparse.Namespace, logger=None) -> None:
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

            from comfygit_core.models.workflow import NodeInstallCallbacks
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

            print(f"\nRun 'cg -e {env.name} env status' to review changes")
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

        print(f"\nRun 'cg -e {env.name} env status' to review changes")

    @with_env_logging("env node prune")
    def node_prune(self, args: argparse.Namespace, logger=None) -> None:
        """Remove unused custom nodes from environment."""
        env = self._get_env(args)

        # Get unused nodes
        exclude = args.exclude if hasattr(args, 'exclude') and args.exclude else None
        try:
            unused = env.get_unused_nodes(exclude=exclude)
        except Exception as e:
            if logger:
                logger.error(f"Failed to get unused nodes: {e}", exc_info=True)
            print(f"✗ Failed to get unused nodes: {e}", file=sys.stderr)
            sys.exit(1)

        if not unused:
            print("✓ No unused nodes found")
            return

        # Display table
        print(f"\nFound {len(unused)} unused node(s):\n")
        for node in unused:
            node_id = node.registry_id or node.name
            print(f"  • {node_id}")

        # Confirm unless --yes flag
        if not args.yes:
            try:
                confirm = input(f"\nRemove {len(unused)} node(s)? [y/N]: ")
                if confirm.lower() != 'y':
                    print("Cancelled")
                    return
            except (EOFError, KeyboardInterrupt):
                print("\nCancelled")
                return

        # Remove with progress
        print(f"\n🗑 Pruning {len(unused)} unused nodes...")

        def on_node_start(node_id, idx, total):
            print(f"  [{idx}/{total}] Removing {node_id}...", end=" ", flush=True)

        def on_node_complete(node_id, success, error):
            if success:
                print("✓")
            else:
                print(f"✗ ({error})")

        from comfygit_core.models.workflow import NodeInstallCallbacks
        callbacks = NodeInstallCallbacks(
            on_node_start=on_node_start,
            on_node_complete=on_node_complete
        )

        try:
            success_count, failed = env.prune_unused_nodes(exclude=exclude, callbacks=callbacks)
        except Exception as e:
            if logger:
                logger.error(f"Prune failed: {e}", exc_info=True)
            print(f"\n✗ Prune failed: {e}", file=sys.stderr)
            sys.exit(1)

        print(f"\n✓ Removed {success_count} node(s)")
        if failed:
            print(f"✗ Failed to remove {len(failed)} node(s):")
            for node_id, error in failed:
                print(f"  • {node_id}: {error}")
            sys.exit(1)

    @with_env_logging("env node list")
    def node_list(self, args: argparse.Namespace) -> None:
        """List custom nodes in the environment."""
        env = self._get_env(args)

        nodes = env.list_nodes()

        if not nodes:
            print("No custom nodes installed")
            return

        print(f"Custom nodes in '{env.name}':")
        for node in nodes:
            # Format version display based on source type
            version_suffix = ""
            if node.version:
                if node.source == "git":
                    version_suffix = f" @ {node.version[:8]}"
                elif node.source == "registry":
                    version_suffix = f" v{node.version}"
                elif node.source == "development":
                    version_suffix = " (dev)"

            print(f"  • {node.registry_id or node.name} ({node.source}){version_suffix}")

    @with_env_logging("env node update")
    def node_update(self, args: argparse.Namespace, logger=None) -> None:
        """Update a custom node."""
        from comfygit_core.strategies.confirmation import (
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

                print("\nRun 'cg status' to review changes")
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
    def constraint_add(self, args: argparse.Namespace, logger=None) -> None:
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
        print(f"\nRun 'cg -e {env.name} constraint list' to view all constraints")

    @with_env_logging("env constraint list")
    def constraint_list(self, args: argparse.Namespace) -> None:
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
    def constraint_remove(self, args: argparse.Namespace, logger=None) -> None:
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

        print(f"\nRun 'cg -e {env.name} constraint list' to view remaining constraints")

    # === Python dependency management ===

    @with_env_logging("env py add")
    def py_add(self, args: argparse.Namespace, logger=None) -> None:
        """Add Python dependencies to the environment."""
        env = self._get_env(args)

        # Validate arguments: must provide either packages or requirements file
        if not args.packages and not args.requirements:
            print("✗ Error: Must specify packages or use -r/--requirements", file=sys.stderr)
            print("Examples:", file=sys.stderr)
            print("  cg py add requests pillow", file=sys.stderr)
            print("  cg py add -r requirements.txt", file=sys.stderr)
            sys.exit(1)

        if args.packages and args.requirements:
            print("✗ Error: Cannot specify both packages and -r/--requirements", file=sys.stderr)
            sys.exit(1)

        # Resolve requirements file path to absolute path (UV runs in .cec directory)
        requirements_file = None
        if args.requirements:
            requirements_file = args.requirements.resolve()
            if not requirements_file.exists():
                print(f"✗ Error: Requirements file not found: {args.requirements}", file=sys.stderr)
                sys.exit(1)

        # Display what we're doing
        upgrade_text = " (with upgrade)" if args.upgrade else ""
        if requirements_file:
            print(f"📦 Adding packages from {args.requirements}{upgrade_text}...")
        else:
            print(f"📦 Adding {len(args.packages)} package(s){upgrade_text}...")

        try:
            env.add_dependencies(
                packages=args.packages or None,
                requirements_file=requirements_file,
                upgrade=args.upgrade,
                group=getattr(args, 'group', None),
                dev=getattr(args, 'dev', False),
                editable=getattr(args, 'editable', False),
                bounds=getattr(args, 'bounds', None)
            )
        except UVCommandError as e:
            if logger:
                logger.error(f"Failed to add dependencies: {e}", exc_info=True)
                if e.stderr:
                    logger.error(f"UV stderr:\n{e.stderr}")
            print(f"✗ Failed to add packages", file=sys.stderr)
            if e.stderr:
                print(f"\n{e.stderr}", file=sys.stderr)
            else:
                print(f"   {e}", file=sys.stderr)
            sys.exit(1)

        if requirements_file:
            print(f"\n✓ Added packages from {args.requirements}")
        else:
            print(f"\n✓ Added {len(args.packages)} package(s) to dependencies")
        print(f"\nRun 'cg -e {env.name} status' to review changes")

    @with_env_logging("env py remove")
    def py_remove(self, args: argparse.Namespace, logger=None) -> None:
        """Remove Python dependencies from the environment."""
        env = self._get_env(args)

        # Handle --group flag (remove from dependency group)
        if hasattr(args, 'group') and args.group:
            group_name = args.group
            print(f"🗑 Removing {len(args.packages)} package(s) from group '{group_name}'...")

            try:
                result = env.pyproject.dependencies.remove_from_group(group_name, args.packages)
            except ValueError as e:
                print(f"✗ {e}", file=sys.stderr)
                sys.exit(1)

            # Show results
            if not result['removed']:
                if len(result['skipped']) == 1:
                    print(f"\nℹ️  Package '{result['skipped'][0]}' is not in group '{group_name}'")
                else:
                    print(f"\nℹ️  None of the specified packages are in group '{group_name}':")
                    for pkg in result['skipped']:
                        print(f"  • {pkg}")
                return

            print(f"\n✓ Removed {len(result['removed'])} package(s) from group '{group_name}'")

            if result['skipped']:
                print(f"\nℹ️  Skipped {len(result['skipped'])} package(s) not in group:")
                for pkg in result['skipped']:
                    print(f"  • {pkg}")

            print(f"\nRun 'cg -e {env.name} py list --all' to view remaining groups")
            return

        # Default behavior: remove from main dependencies
        print(f"🗑 Removing {len(args.packages)} package(s)...")

        try:
            result = env.remove_dependencies(args.packages)
        except UVCommandError as e:
            if logger:
                logger.error(f"Failed to remove dependencies: {e}", exc_info=True)
                if e.stderr:
                    logger.error(f"UV stderr:\n{e.stderr}")
            print(f"✗ Failed to remove packages", file=sys.stderr)
            if e.stderr:
                print(f"\n{e.stderr}", file=sys.stderr)
            else:
                print(f"   {e}", file=sys.stderr)
            sys.exit(1)

        # If nothing was removed, show appropriate message
        if not result['removed']:
            if len(result['skipped']) == 1:
                print(f"\nℹ️  Package '{result['skipped'][0]}' is not in dependencies (already removed or never added)")
            else:
                print(f"\nℹ️  None of the specified packages are in dependencies:")
                for pkg in result['skipped']:
                    print(f"  • {pkg}")
            return

        # Show successful removals
        print(f"\n✓ Removed {len(result['removed'])} package(s) from dependencies")

        # Show skipped packages if any
        if result['skipped']:
            print(f"\nℹ️  Skipped {len(result['skipped'])} package(s) not in dependencies:")
            for pkg in result['skipped']:
                print(f"  • {pkg}")

        print(f"\nRun 'cg -e {env.name} status' to review changes")

    @with_env_logging("env py remove-group")
    def py_remove_group(self, args: argparse.Namespace, logger=None) -> None:
        """Remove an entire dependency group."""
        env = self._get_env(args)
        group_name = args.group

        print(f"🗑 Removing dependency group: {group_name}")

        try:
            env.pyproject.dependencies.remove_group(group_name)
        except ValueError as e:
            print(f"✗ {e}", file=sys.stderr)
            sys.exit(1)

        print(f"\n✓ Removed dependency group '{group_name}'")
        print(f"\nRun 'cg -e {env.name} py list --all' to view remaining groups")

    @with_env_logging("env py uv")
    def py_uv(self, args: argparse.Namespace, logger=None) -> None:
        """Direct UV command passthrough for advanced users."""
        env = self._get_env(args)

        if not args.uv_args:
            # Show helpful usage message
            print("Usage: cg py uv <uv-command> [uv-args...]")
            print("Example: cg py uv add --group optional-cuda sageattention")
            print("\nThis is direct UV access. See 'uv --help' for options.")
            sys.exit(1)

        # Build UV command with environment context
        cmd = [env.uv_manager.uv._binary] + args.uv_args

        # Execute with environment context (cwd and env vars)
        result = subprocess.run(
            cmd,
            cwd=env.cec_path,
            env={
                **os.environ,
                "UV_PROJECT_ENVIRONMENT": str(env.venv_path),
                "UV_CACHE_DIR": str(env.workspace_paths.cache / "uv_cache"),
            }
        )
        sys.exit(result.returncode)

    @with_env_logging("env py list")
    def py_list(self, args: argparse.Namespace) -> None:
        """List Python dependencies."""
        env = self._get_env(args)

        all_deps = env.list_dependencies(all=args.all)

        # Check if there are any dependencies at all
        total_count = sum(len(deps) for deps in all_deps.values())
        if total_count == 0:
            print("No project dependencies or dependency groups")
            return

        # Display dependencies grouped by section
        first_group = True
        for group_name, group_deps in all_deps.items():
            if not group_deps:
                continue

            if not first_group:
                print()  # Blank line between groups
            first_group = False

            # Format the header
            if group_name == "dependencies":
                print(f"Dependencies ({len(group_deps)}):")
                for dep in group_deps:
                    print(f"  • {dep}")
            else:
                print(f"{group_name} ({len(group_deps)}):")
                for dep in group_deps:
                    print(f"  • {dep}")

        # Show tip if not showing all groups
        if not args.all and len(all_deps) == 1:
            print("\nTip: Use --all to see dependency groups")

    # === Git-based operations ===

    @with_env_logging("env repair")
    def repair(self, args: argparse.Namespace, logger=None) -> None:
        """Repair environment to match pyproject.toml (for manual edits or git operations)."""
        env = self._get_env(args)

        # Get status first
        status = env.status()

        if status.is_synced:
            print("✓ No changes to apply")
            return

        # Get preview for display and later use
        preview: dict[str, Any] = status.get_sync_preview()

        # Confirm unless --yes
        if not args.yes:

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
        from comfygit_core.models.workflow import BatchDownloadCallbacks, NodeInstallCallbacks
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

    @with_env_logging("env checkout")
    def checkout(self, args: argparse.Namespace, logger=None) -> None:
        """Checkout commits, branches, or files."""
        from .strategies.rollback import AutoRollbackStrategy, InteractiveRollbackStrategy

        env = self._get_env(args)

        try:
            if args.branch:
                # Create new branch and switch
                # If ref is None, create_branch defaults to HEAD
                start_point = args.ref if args.ref is not None else "HEAD"
                print(f"Creating and switching to branch '{args.branch}'...")
                env.create_branch(args.branch, start_point=start_point)
                env.switch_branch(args.branch)
                print(f"✓ Switched to new branch '{args.branch}'")
            else:
                # Just checkout ref - ref is required when not using -b
                if args.ref is None:
                    print("✗ Error: ref argument is required when not using -b", file=sys.stderr)
                    sys.exit(1)

                print(f"Checking out '{args.ref}'...")

                # Choose strategy
                strategy = AutoRollbackStrategy() if args.yes or args.force else InteractiveRollbackStrategy()

                env.checkout(args.ref, strategy=strategy, force=args.force)

                # Check if detached HEAD
                current_branch = env.get_current_branch()
                if current_branch is None:
                    print(f"✓ HEAD is now at {args.ref} (detached)")
                    print("  You are in 'detached HEAD' state. To keep changes:")
                    print(f"    cg checkout -b <new-branch-name>")
                else:
                    print(f"✓ Switched to branch '{current_branch}'")
        except Exception as e:
            if logger:
                logger.error(f"Checkout failed: {e}", exc_info=True)
            print(f"✗ Checkout failed: {e}", file=sys.stderr)
            sys.exit(1)

    @with_env_logging("env branch")
    def branch(self, args: argparse.Namespace, logger=None) -> None:
        """Manage branches."""
        env = self._get_env(args)

        try:
            if args.name is None:
                # List branches
                branches = env.list_branches()
                if not branches:
                    print("No branches found")
                    return

                print("Branches:")
                for name, is_current in branches:
                    marker = "* " if is_current else "  "
                    print(f"{marker}{name}")
            elif args.delete or args.force_delete:
                # Delete branch
                force = args.force_delete
                print(f"Deleting branch '{args.name}'...")
                env.delete_branch(args.name, force=force)
                print(f"✓ Deleted branch '{args.name}'")
            else:
                # Create branch (don't switch)
                print(f"Creating branch '{args.name}'...")
                env.create_branch(args.name)
                print(f"✓ Created branch '{args.name}'")
        except Exception as e:
            if logger:
                logger.error(f"Branch operation failed: {e}", exc_info=True)
            print(f"✗ Branch operation failed: {e}", file=sys.stderr)
            sys.exit(1)

    @with_env_logging("env switch")
    def switch(self, args: argparse.Namespace, logger=None) -> None:
        """Switch to branch."""
        env = self._get_env(args)

        try:
            print(f"Switching to branch '{args.branch}'...")
            env.switch_branch(args.branch, create=args.create)
            print(f"✓ Switched to branch '{args.branch}'")
        except Exception as e:
            if logger:
                logger.error(f"Switch failed: {e}", exc_info=True)
            print(f"✗ Switch failed: {e}", file=sys.stderr)
            sys.exit(1)

    @with_env_logging("env reset")
    def reset_git(self, args: argparse.Namespace, logger=None) -> None:
        """Reset HEAD to ref (git-native reset)."""
        from .strategies.rollback import InteractiveRollbackStrategy

        env = self._get_env(args)

        # Determine mode
        if args.hard:
            mode = "hard"
        elif args.soft:
            mode = "soft"
        else:
            mode = "mixed"  # default

        try:
            # Choose strategy for hard mode
            strategy = None
            if mode == "hard" and not args.yes:
                strategy = InteractiveRollbackStrategy()

            print(f"Resetting to '{args.ref}' (mode: {mode})...")
            env.reset(args.ref, mode=mode, strategy=strategy, force=args.yes)
            print(f"✓ Reset to '{args.ref}'")
        except Exception as e:
            if logger:
                logger.error(f"Reset failed: {e}", exc_info=True)
            print(f"✗ Reset failed: {e}", file=sys.stderr)
            sys.exit(1)

    @with_env_logging("env merge")
    def merge(self, args: argparse.Namespace, logger=None) -> None:
        """Merge branch into current."""
        env = self._get_env(args)

        try:
            current = env.get_current_branch()
            if current is None:
                print("✗ Cannot merge while in detached HEAD state")
                sys.exit(1)

            print(f"Merging '{args.branch}' into '{current}'...")
            env.merge_branch(args.branch, message=args.message)
            print(f"✓ Merged '{args.branch}' into '{current}'")
        except Exception as e:
            if logger:
                logger.error(f"Merge failed: {e}", exc_info=True)
            print(f"✗ Merge failed: {e}", file=sys.stderr)
            sys.exit(1)

    @with_env_logging("env revert")
    def revert(self, args: argparse.Namespace, logger=None) -> None:
        """Revert a commit."""
        env = self._get_env(args)

        try:
            print(f"Reverting commit '{args.commit}'...")
            env.revert_commit(args.commit)
            print(f"✓ Reverted commit '{args.commit}'")
        except Exception as e:
            if logger:
                logger.error(f"Revert failed: {e}", exc_info=True)
            print(f"✗ Revert failed: {e}", file=sys.stderr)
            sys.exit(1)

    @with_env_logging("env commit")
    def commit(self, args: argparse.Namespace, logger=None) -> None:
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
            print("  1. Resolve issues: cg workflow resolve \"<name>\"")
            print("  2. Force commit: cg commit -m 'msg' --allow-issues")
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


    # === Git remote operations ===

    @with_env_logging("env pull")
    def pull(self, args: argparse.Namespace, logger=None) -> None:
        """Pull from remote and repair environment."""
        env = self._get_env(args)

        # Check for uncommitted changes first
        if env.has_committable_changes() and not getattr(args, 'force', False):
            print("⚠️  You have uncommitted changes")
            print()
            print("💡 Options:")
            print("  • Commit: cg commit -m 'message'")
            print("  • Discard: cg rollback")
            print("  • Force: cg pull origin --force")
            sys.exit(1)

        # Check remote exists
        if not env.git_manager.has_remote(args.remote):
            print(f"✗ Remote '{args.remote}' not configured")
            print()
            print("💡 Set up a remote first:")
            print(f"   cg remote add {args.remote} <url>")
            sys.exit(1)

        try:
            print(f"📥 Pulling from {args.remote}...")

            # Create callbacks for node and model progress (reuse repair command patterns)
            from comfygit_core.models.workflow import BatchDownloadCallbacks, NodeInstallCallbacks
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

            # Pull and repair with progress callbacks
            result = env.pull_and_repair(
                remote=args.remote,
                model_strategy=getattr(args, 'models', 'all'),
                model_callbacks=model_callbacks,
                node_callbacks=node_callbacks
            )

            # Extract sync result for summary
            sync_result = result.get('sync_result')

            print(f"\n✓ Pulled changes from {args.remote}")

            # Show summary of what was synced (like repair command)
            if sync_result:
                summary_items = []
                if sync_result.nodes_installed:
                    summary_items.append(f"Installed {len(sync_result.nodes_installed)} node(s)")
                if sync_result.nodes_removed:
                    summary_items.append(f"Removed {len(sync_result.nodes_removed)} node(s)")
                if sync_result.models_downloaded:
                    summary_items.append(f"Downloaded {len(sync_result.models_downloaded)} model(s)")

                if summary_items:
                    for item in summary_items:
                        print(f"   • {item}")

            print("\n⚙️  Environment synced successfully")

        except KeyboardInterrupt:
            # User pressed Ctrl+C - git changes already rolled back by core
            if logger:
                logger.warning("Pull interrupted by user")
            print("\n⚠️  Pull interrupted - git changes rolled back", file=sys.stderr)
            sys.exit(1)
        except ValueError as e:
            # Merge conflicts
            if logger:
                logger.error(f"Pull failed: {e}", exc_info=True)

            # Check if it's a merge conflict
            error_str = str(e)
            if "Merge conflict" in error_str or "conflict" in error_str.lower():
                print(f"\n✗ Merge conflict detected", file=sys.stderr)
                print()
                print("💡 To resolve:")
                print(f"   1. cd {env.cec_path}")
                print("   2. git status  # See conflicted files")
                print("   3. Edit conflicts and resolve")
                print("   4. git add <resolved-files>")
                print("   5. git commit")
                print("   6. cg repair  # Sync environment")
            else:
                print(f"✗ Pull failed: {e}", file=sys.stderr)
            sys.exit(1)
        except OSError as e:
            # Network, auth, or other git errors
            if logger:
                logger.error(f"Pull failed: {e}", exc_info=True)

            # Check if it's a merge conflict (OSError from git_merge)
            error_str = str(e)
            if "Merge conflict" in error_str or "conflict" in error_str.lower():
                print(f"\n✗ Merge conflict detected", file=sys.stderr)
                print()
                print("💡 To resolve:")
                print(f"   1. cd {env.cec_path}")
                print("   2. git status  # See conflicted files")
                print("   3. Edit conflicts and resolve")
                print("   4. git add <resolved-files>")
                print("   5. git commit")
                print("   6. cg repair  # Sync environment")
            else:
                print(f"✗ Pull failed: {e}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            if logger:
                logger.error(f"Pull failed: {e}", exc_info=True)
            print(f"✗ Pull failed: {e}", file=sys.stderr)
            sys.exit(1)

    @with_env_logging("env push")
    def push(self, args: argparse.Namespace, logger=None) -> None:
        """Push commits to remote."""
        env = self._get_env(args)

        # Check for uncommitted changes
        if env.has_committable_changes():
            print("⚠️  You have uncommitted changes")
            print()
            print("💡 Commit first:")
            print("   cg commit -m 'your message'")
            sys.exit(1)

        # Check remote exists
        if not env.git_manager.has_remote(args.remote):
            print(f"✗ Remote '{args.remote}' not configured")
            print()
            print("💡 Set up a remote first:")
            print(f"   cg remote add {args.remote} <url>")
            sys.exit(1)

        try:
            force = getattr(args, 'force', False)

            if force:
                print(f"📤 Force pushing to {args.remote}...")
            else:
                print(f"📤 Pushing to {args.remote}...")

            # Push (with force flag if specified)
            push_output = env.push_commits(remote=args.remote, force=force)

            if force:
                print(f"   ✓ Force pushed commits to {args.remote}")
            else:
                print(f"   ✓ Pushed commits to {args.remote}")

            # Show remote URL
            from comfygit_core.utils.git import git_remote_get_url
            remote_url = git_remote_get_url(env.cec_path, args.remote)
            if remote_url:
                print()
                print(f"💾 Remote: {remote_url}")

        except ValueError as e:
            # No remote or workflow issues
            if logger:
                logger.error(f"Push failed: {e}", exc_info=True)
            print(f"✗ Push failed: {e}", file=sys.stderr)
            sys.exit(1)
        except OSError as e:
            # Network, auth, or git errors
            if logger:
                logger.error(f"Push failed: {e}", exc_info=True)
            print(f"✗ Push failed: {e}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            if logger:
                logger.error(f"Push failed: {e}", exc_info=True)
            print(f"✗ Push failed: {e}", file=sys.stderr)
            sys.exit(1)

    @with_env_logging("env remote")
    def remote(self, args: argparse.Namespace, logger=None) -> None:
        """Manage git remotes."""
        env = self._get_env(args)

        subcommand = args.remote_command

        try:
            if subcommand == "add":
                # Add remote
                if not args.name or not args.url:
                    print("✗ Usage: cg remote add <name> <url>")
                    sys.exit(1)

                env.git_manager.add_remote(args.name, args.url)
                print(f"✓ Added remote '{args.name}': {args.url}")

            elif subcommand == "remove":
                # Remove remote
                if not args.name:
                    print("✗ Usage: cg remote remove <name>")
                    sys.exit(1)

                env.git_manager.remove_remote(args.name)
                print(f"✓ Removed remote '{args.name}'")

            elif subcommand == "list":
                # List remotes
                remotes = env.git_manager.list_remotes()

                if not remotes:
                    print("No remotes configured")
                    print()
                    print("💡 Add a remote:")
                    print("   cg remote add origin <url>")
                else:
                    print("Remotes:")
                    for name, url, remote_type in remotes:
                        print(f"  {name}\t{url} ({remote_type})")

            else:
                print(f"✗ Unknown remote command: {subcommand}")
                print("   Usage: cg remote [add|remove|list]")
                sys.exit(1)

        except ValueError as e:
            print(f"✗ {e}", file=sys.stderr)
            sys.exit(1)
        except OSError as e:
            if logger:
                logger.error(f"Remote operation failed: {e}", exc_info=True)
            print(f"✗ {e}", file=sys.stderr)
            sys.exit(1)

    # === Workflow management ===

    @with_env_logging("workflow list", get_env_name=lambda self, args: self._get_env(args).name)
    def workflow_list(self, args: argparse.Namespace) -> None:
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
            print("\nRun 'cg commit' to save current state")

    @with_env_logging("workflow model importance", get_env_name=lambda self, args: self._get_env(args).name)
    def workflow_model_importance(self, args: argparse.Namespace, logger=None) -> None:
        """Update model importance (criticality) for workflow models."""
        env = self._get_env(args)

        # Determine workflow name (direct or interactive)
        if hasattr(args, 'workflow_name') and args.workflow_name:
            workflow_name = args.workflow_name
        else:
            # Interactive: select workflow
            workflow_name = self._select_workflow_interactive(env)
            if not workflow_name:
                print("✗ No workflow selected")
                return

        # Get workflow models
        models = env.pyproject.workflows.get_workflow_models(workflow_name)
        if not models:
            print(f"✗ No models found in workflow '{workflow_name}'")
            return

        # Determine model (direct or interactive)
        if hasattr(args, 'model_identifier') and args.model_identifier:
            # Direct mode: update single model
            model_identifier = args.model_identifier
            new_importance = args.importance

            success = env.workflow_manager.update_model_criticality(
                workflow_name=workflow_name,
                model_identifier=model_identifier,
                new_criticality=new_importance
            )

            if success:
                print(f"✓ Updated '{model_identifier}' importance to: {new_importance}")
            else:
                print(f"✗ Model '{model_identifier}' not found in workflow '{workflow_name}'")
                sys.exit(1)
        else:
            # Interactive: loop over all models
            print(f"\n📋 Setting model importance for workflow: {workflow_name}")
            print(f"   Found {len(models)} model(s)\n")

            updated_count = 0
            for model in models:
                current_importance = model.criticality
                display_name = model.filename
                if model.hash:
                    display_name += f" ({model.hash[:8]}...)"

                print(f"\nModel: {display_name}")
                print(f"  Current: {current_importance}")
                print(f"  Options: [r]equired, [f]lexible, [o]ptional, [s]kip")

                # Prompt for new importance
                try:
                    choice = input("  Choice: ").strip().lower()
                except (KeyboardInterrupt, EOFError):
                    print("\n✗ Cancelled")
                    return

                # Map choice to importance level
                importance_map = {
                    'r': 'required',
                    'f': 'flexible',
                    'o': 'optional',
                    's': None  # Skip
                }

                new_importance = importance_map.get(choice)
                if new_importance is None:
                    if choice == 's':
                        print("  → Skipped")
                        continue
                    else:
                        print(f"  → Invalid choice, skipping")
                        continue

                # Update model importance
                identifier = model.hash if model.hash else model.filename
                success = env.workflow_manager.update_model_criticality(
                    workflow_name=workflow_name,
                    model_identifier=identifier,
                    new_criticality=new_importance
                )

                if success:
                    print(f"  ✓ Updated to: {new_importance}")
                    updated_count += 1
                else:
                    print(f"  ✗ Failed to update")

            print(f"\n✓ Updated {updated_count}/{len(models)} model(s)")

    def _select_workflow_interactive(self, env) -> str | None:
        """Interactive workflow selection from available workflows.

        Returns:
            Selected workflow name or None if cancelled
        """
        status = env.workflow_manager.get_workflow_sync_status()
        all_workflows = status.new + status.modified + status.synced

        if not all_workflows:
            print("✗ No workflows found")
            return None

        print("\n📋 Available workflows:")
        for i, name in enumerate(all_workflows, 1):
            # Show sync state
            if name in status.new:
                state = "new"
            elif name in status.modified:
                state = "modified"
            else:
                state = "synced"
            print(f"  {i}. {name} ({state})")

        print()
        try:
            choice = input("Select workflow (number or name): ").strip()
        except (KeyboardInterrupt, EOFError):
            return None

        # Try to parse as number
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(all_workflows):
                return all_workflows[idx]
        except ValueError:
            # Try as name
            if choice in all_workflows:
                return choice

        print(f"✗ Invalid selection: {choice}")
        return None

    @with_env_logging("workflow resolve", get_env_name=lambda self, args: self._get_env(args).name)
    def workflow_resolve(self, args: argparse.Namespace, logger=None) -> None:
        """Resolve workflow dependencies interactively."""
        env = self._get_env(args)

        # Choose strategy
        if args.auto:
            from comfygit_core.strategies.auto import AutoModelStrategy, AutoNodeStrategy
            node_strategy = AutoNodeStrategy()
            model_strategy = AutoModelStrategy()
        else:
            node_strategy = InteractiveNodeStrategy()
            model_strategy = InteractiveModelStrategy()

        # Phase 1: Resolve dependencies (updates pyproject.toml)
        print("\n🔧 Resolving dependencies...")
        try:
            from comfygit_cli.utils.progress import create_batch_download_callbacks

            result = env.resolve_workflow(
                name=args.name,
                node_strategy=node_strategy,
                model_strategy=model_strategy,
                download_callbacks=create_batch_download_callbacks()
            )
        except CDRegistryDataError as e:
            # Registry data unavailable
            formatted = NodeErrorFormatter.format_registry_error(e)
            if logger:
                logger.error(f"Registry data unavailable for workflow resolve: {e}", exc_info=True)
            print(f"✗ Cannot resolve workflow - registry data unavailable", file=sys.stderr)
            print(formatted, file=sys.stderr)
            sys.exit(1)
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
                from comfygit_core.models.workflow import NodeInstallCallbacks

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
                            from comfygit_core.integrations.uv_command import UVCommandError
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
                    log_file = self.workspace.paths.logs / env.name / "full.log"
                    print(f"   {log_file}")
                    print("\nYou can try installing them manually:")
                    print("  cg node add <node-id>")
            else:
                print("\nℹ️  Skipped node installation")
                # print("\nℹ️  Skipped node installation. To install later:")
                # print(f"  • Re-run: cg workflow resolve \"{args.name}\"")
                # print("  • Or install individually: cg node add <node-id>")

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
            print(f"  Re-run: cg workflow resolve \"{args.name}\"")
            print("  Or commit with issues: cg commit -m \"...\" --allow-issues")

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
                print("  Add Civitai API key: cg config --civitai-key <your-token>")
                print(f"  Try again: cg workflow resolve \"{args.name}\"")
                print("  Or commit anyway: cg commit -m \"...\" --allow-issues")
            else:
                print("\n✅ Resolution complete!")
                if result.models_resolved:
                    print(f"  • Resolved {len(result.models_resolved)} models")
                if result.nodes_resolved:
                    print(f"  • Resolved {len(result.nodes_resolved)} nodes")
                print("\n💡 Next:")
                print(f"  Commit workflows: cg commit -m \"Resolved {args.name}\"")
        else:
            print("✓ No changes needed - all dependencies already resolved")
