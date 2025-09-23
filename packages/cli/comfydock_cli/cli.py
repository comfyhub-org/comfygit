"""ComfyDock MVP CLI - Workspace and Environment Management."""

import argparse
import sys
from pathlib import Path

from .env_commands import EnvironmentCommands
from .global_commands import GlobalCommands
from .logging.logging_config import setup_logging


def main():
    """Main entry point for ComfyDock CLI."""
    # Initialize logging system with minimal console output
    # Environment commands will add file handlers as needed
    setup_logging(level="INFO", simple_format=True, console_level="CRITICAL")

    # Special handling for 'run' command to pass through ComfyUI args
    parser = create_parser()
    if 'run' in sys.argv:
        # Parse known args, pass unknown to ComfyUI
        args, unknown = parser.parse_known_args()
        if getattr(args, 'command', None) == 'run':
            args.args = unknown
        else:
            # Not actually the run command, do normal parsing
            args = parser.parse_args()
    else:
        # Normal parsing for all other commands
        args = parser.parse_args()

    if not hasattr(args, 'func'):
        parser.print_help()
        sys.exit(1)

    try:
        # Execute the command
        args.func(args)
    except KeyboardInterrupt:
        print("\n✗ Interrupted")
        sys.exit(130)
    except Exception as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        sys.exit(1)


def create_parser():
    """Create the argument parser with hierarchical command structure."""
    parser = argparse.ArgumentParser(
        description="ComfyDock - Manage ComfyUI workspaces and environments",
        prog="comfydock"
    )

    # Global options
    parser.add_argument(
        '-e', '--env',
        help='Target environment (uses active if not specified)',
        dest='target_env'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Verbose output'
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Add all commands (workspace and environment)
    _add_global_commands(subparsers)
    _add_env_commands(subparsers)

    return parser


def _add_global_commands(subparsers):
    """Add global workspace-level commands."""
    global_cmds = GlobalCommands()

    # init - Initialize workspace
    init_parser = subparsers.add_parser("init", help="Initialize ComfyDock workspace")
    init_parser.add_argument("path", type=Path, nargs="?", help="Workspace directory (default: ~/comfydock)")
    init_parser.set_defaults(func=global_cmds.init)

    # list - List all environments
    list_parser = subparsers.add_parser("list", help="List all environments")
    list_parser.set_defaults(func=global_cmds.list_envs)

    # migrate - Import existing ComfyUI
    migrate_parser = subparsers.add_parser("migrate", help="Scan and import existing ComfyUI instance")
    migrate_parser.add_argument("source_path", type=Path, help="Path to existing ComfyUI")
    migrate_parser.add_argument("env_name", help="New environment name")
    migrate_parser.add_argument("--scan-only", action="store_true", help="Only scan, don't import")
    migrate_parser.set_defaults(func=global_cmds.migrate)

    # import - Import ComfyDock environment
    import_parser = subparsers.add_parser("import", help="Import ComfyDock environment (packed in .tar.gz usually)")
    import_parser.add_argument("path", type=Path, nargs="?", help="Path to input file")
    import_parser.set_defaults(func=global_cmds.import_env)

    # export - Export ComfyDock environment
    export_parser = subparsers.add_parser("export", help="Export ComfyDock environment (include relevant files from .cec)")
    export_parser.add_argument("path", type=Path, nargs="?", help="Path to output file")
    export_parser.set_defaults(func=global_cmds.export_env)

    # Index management subcommands
    index_parser = subparsers.add_parser("index", help="Manage workspace indexes")
    index_subparsers = index_parser.add_subparsers(dest="index_command", help="Index commands")

    # index model subcommands
    index_model_parser = index_subparsers.add_parser("model", help="Model index operations")
    index_model_subparsers = index_model_parser.add_subparsers(dest="index_model_command", help="Model index commands")

    # index model find
    index_model_find_parser = index_model_subparsers.add_parser("find", help="Find models by hash or filename")
    index_model_find_parser.add_argument("query", help="Search query (hash prefix or filename)")
    index_model_find_parser.set_defaults(func=global_cmds.model_index_find)

    # index model list
    index_model_list_parser = index_model_subparsers.add_parser("list", help="List all indexed models")
    index_model_list_parser.set_defaults(func=global_cmds.model_index_list)

    # index model status
    index_model_status_parser = index_model_subparsers.add_parser("status", help="Show models directory and index status")
    index_model_status_parser.set_defaults(func=global_cmds.model_index_status)

    # index model sync
    index_model_sync_parser = index_model_subparsers.add_parser("sync", help="Scan models directory and update index")
    index_model_sync_parser.set_defaults(func=global_cmds.model_index_sync)

    # index model dir subcommands
    index_model_dir_parser = index_model_subparsers.add_parser("dir", help="Model directory management")
    index_model_dir_subparsers = index_model_dir_parser.add_subparsers(dest="index_model_dir_command", help="Directory commands")

    # index model dir add
    index_model_dir_add_parser = index_model_dir_subparsers.add_parser("add", help="Set global models directory")
    index_model_dir_add_parser.add_argument("path", type=Path, help="Path to models directory")
    index_model_dir_add_parser.set_defaults(func=global_cmds.model_dir_add)

    # index registry subcommands
    index_registry_parser = index_subparsers.add_parser("registry", help="Node registry cache operations")
    index_registry_subparsers = index_registry_parser.add_subparsers(dest="index_registry_command", help="Registry commands")

    # index registry status
    index_registry_status_parser = index_registry_subparsers.add_parser("status", help="Show registry cache status")
    index_registry_status_parser.set_defaults(func=global_cmds.registry_status)

    # index registry update
    index_registry_update_parser = index_registry_subparsers.add_parser("update", help="Update registry data from GitHub")
    index_registry_update_parser.set_defaults(func=global_cmds.registry_update)


def _add_env_commands(subparsers):
    """Add environment-specific commands."""
    env_cmds = EnvironmentCommands()

    # Environment Management Commands (operate ON environments)

    # create - Create new environment
    create_parser = subparsers.add_parser("create", help="Create new environment")
    create_parser.add_argument("name", help="Environment name")
    create_parser.add_argument("--template", type=Path, help="Template manifest")
    create_parser.add_argument("--python", default="3.11", help="Python version")
    create_parser.add_argument("--comfyui", help="ComfyUI version")
    create_parser.add_argument("--use", action="store_true", help="Set active environment after creation")
    create_parser.set_defaults(func=env_cmds.create)

    # use - Set active environment
    use_parser = subparsers.add_parser("use", help="Set active environment")
    use_parser.add_argument("name", help="Environment name")
    use_parser.set_defaults(func=env_cmds.use)

    # delete - Delete environment
    delete_parser = subparsers.add_parser("delete", help="Delete environment")
    delete_parser.add_argument("name", help="Environment name")
    delete_parser.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")
    delete_parser.set_defaults(func=env_cmds.delete)

    # Environment Operation Commands (operate IN environments, require -e or active)

    # run - Run ComfyUI (special handling for ComfyUI args)
    run_parser = subparsers.add_parser("run", help="Run ComfyUI")
    run_parser.add_argument("--no-sync", action="store_true", help="Skip environment sync before running")
    run_parser.set_defaults(func=env_cmds.run, args=[])

    # status - Show environment status
    status_parser = subparsers.add_parser("status", help="Show status (both sync and git status)")
    status_parser.add_argument("-v", "--verbose", action="store_true", help="Show full details")
    status_parser.set_defaults(func=env_cmds.status)

    # sync - Apply changes from pyproject.toml
    sync_parser = subparsers.add_parser("sync", help="Apply changes from pyproject.toml to current environment")
    sync_parser.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")
    sync_parser.set_defaults(func=env_cmds.sync)

    # commit - Commit unsaved changes
    commit_parser = subparsers.add_parser("commit", help="Commit unsaved changes to pyproject.toml (or uv.lock)")
    commit_parser.add_argument("-m", "--message", help="Commit message (auto-generated if not provided)")
    commit_parser.set_defaults(func=env_cmds.commit)

    # log - Show commit history
    log_parser = subparsers.add_parser("log", help="Show commit history")
    log_parser.add_argument("-v", "--verbose", action="store_true", help="Show full details")
    log_parser.set_defaults(func=env_cmds.log)

    # rollback - Revert changes
    rollback_parser = subparsers.add_parser("rollback", help="Rollback to a previous version or discard uncommitted changes")
    rollback_parser.add_argument("target", nargs="?", help="Version to rollback to (e.g., 'v1', 'v2') - leave empty to discard uncommitted changes")
    rollback_parser.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")
    rollback_parser.set_defaults(func=env_cmds.rollback)

    # Node management subcommands
    node_parser = subparsers.add_parser("node", help="Manage custom nodes")
    node_subparsers = node_parser.add_subparsers(dest="node_command", help="Node commands")

    # node add
    node_add_parser = node_subparsers.add_parser("add", help="Add custom node")
    node_add_parser.add_argument("node_name", help="Node directory name or registry ID")
    node_add_parser.add_argument("--dev", action="store_true", help="Track existing local development node")
    node_add_parser.add_argument("--no-test", action="store_true", help="Don't test resolution")
    node_add_parser.set_defaults(func=env_cmds.node_add)

    # node remove
    node_remove_parser = node_subparsers.add_parser("remove", help="Remove custom node")
    node_remove_parser.add_argument("node_name", help="Node registry ID or name")
    node_remove_parser.add_argument("--dev", action="store_true", help="Remove development node specifically")
    node_remove_parser.set_defaults(func=env_cmds.node_remove)

    # node list
    node_list_parser = node_subparsers.add_parser("list", help="List custom nodes")
    node_list_parser.set_defaults(func=env_cmds.node_list)

    # Workflow management subcommands
    workflow_parser = subparsers.add_parser("workflow", help="Manage workflows")
    workflow_subparsers = workflow_parser.add_subparsers(dest="workflow_command", help="Workflow commands")

    # workflow track
    workflow_track_parser = workflow_subparsers.add_parser("track", help="Start tracking workflow(s)")
    workflow_track_parser.add_argument("name", nargs="?", help="Workflow name to track")
    workflow_track_parser.add_argument("--all", action="store_true", help="Track all untracked workflows")
    workflow_track_parser.add_argument(
        "--install-mode",
        choices=["auto", "manual", "skip"],
        default="auto",
        help="How to handle missing nodes: auto (default), manual, or skip"
    )
    workflow_track_parser.set_defaults(func=env_cmds.workflow_track)

    # workflow untrack
    workflow_untrack_parser = workflow_subparsers.add_parser("untrack", help="Stop tracking workflow")
    workflow_untrack_parser.add_argument("name", help="Workflow name to untrack")
    workflow_untrack_parser.set_defaults(func=env_cmds.workflow_untrack)

    # workflow list
    workflow_list_parser = workflow_subparsers.add_parser("list", help="List workflow tracking status")
    workflow_list_parser.set_defaults(func=env_cmds.workflow_list)

    # Environment Model management subcommands
    env_model_parser = subparsers.add_parser("model", help="Manage environment model requirements")
    env_model_subparsers = env_model_parser.add_subparsers(dest="env_model_command", help="Environment model commands")

    # model add
    env_model_add_parser = env_model_subparsers.add_parser("add", help="Add model to environment manifest")
    env_model_add_parser.add_argument("identifier", help="Model hash or URL")
    env_model_add_parser.add_argument("--optional", action="store_true", help="Add as optional model")
    env_model_add_parser.add_argument("--workflow", help="Link to specific workflow")
    env_model_add_parser.set_defaults(func=env_cmds.model_add)

    # model remove
    env_model_remove_parser = env_model_subparsers.add_parser("remove", help="Remove model from environment manifest")
    env_model_remove_parser.add_argument("hash", help="Model hash to remove")
    env_model_remove_parser.set_defaults(func=env_cmds.model_remove)

    # model list
    env_model_list_parser = env_model_subparsers.add_parser("list", help="List models in environment manifest")
    env_model_list_parser.set_defaults(func=env_cmds.model_list)

    # Constraint management subcommands
    constraint_parser = subparsers.add_parser("constraint", help="Manage UV constraint dependencies")
    constraint_subparsers = constraint_parser.add_subparsers(dest="constraint_command", help="Constraint commands")

    # constraint add
    constraint_add_parser = constraint_subparsers.add_parser("add", help="Add constraint dependencies")
    constraint_add_parser.add_argument("packages", nargs="+", help="Package specifications (e.g., torch==2.4.1)")
    constraint_add_parser.set_defaults(func=env_cmds.constraint_add)

    # constraint list
    constraint_list_parser = constraint_subparsers.add_parser("list", help="List constraint dependencies")
    constraint_list_parser.set_defaults(func=env_cmds.constraint_list)

    # constraint remove
    constraint_remove_parser = constraint_subparsers.add_parser("remove", help="Remove constraint dependencies")
    constraint_remove_parser.add_argument("packages", nargs="+", help="Package names to remove")
    constraint_remove_parser.set_defaults(func=env_cmds.constraint_remove)

if __name__ == "__main__":
    main()
