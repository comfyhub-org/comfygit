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

    # Model management subcommands
    model_parser = subparsers.add_parser("model", help="Manage model index")
    model_subparsers = model_parser.add_subparsers(dest="model_command", help="Model commands")

    # model index subcommands
    model_index_parser = model_subparsers.add_parser("index", help="Model index operations")
    model_index_subparsers = model_index_parser.add_subparsers(dest="model_index_command", help="Model index commands")

    # model index find
    model_index_find_parser = model_index_subparsers.add_parser("find", help="Find models by hash or filename")
    model_index_find_parser.add_argument("query", help="Search query (hash prefix or filename)")
    model_index_find_parser.set_defaults(func=global_cmds.model_index_find)

    # model index list
    model_index_list_parser = model_index_subparsers.add_parser("list", help="List all indexed models")
    model_index_list_parser.set_defaults(func=global_cmds.model_index_list)

    # model index status
    model_index_status_parser = model_index_subparsers.add_parser("status", help="Show models directory and index status")
    model_index_status_parser.set_defaults(func=global_cmds.model_index_status)

    # model index sync
    model_index_sync_parser = model_index_subparsers.add_parser("sync", help="Scan models directory and update index")
    model_index_sync_parser.set_defaults(func=global_cmds.model_index_sync)

    # model index dir
    model_index_dir_parser = model_index_subparsers.add_parser("dir", help="Set global models directory to index")
    model_index_dir_parser.add_argument("path", type=Path, help="Path to models directory")
    model_index_dir_parser.set_defaults(func=global_cmds.model_dir_add)

    # model download
    model_download_parser = model_subparsers.add_parser("download", help="Download model from URL")
    model_download_parser.add_argument("url", help="Model download URL (Civitai, HuggingFace, or direct)")
    model_download_parser.add_argument("--path", type=str, help="Target path relative to models directory (e.g., checkpoints/model.safetensors)")
    model_download_parser.add_argument("-c", "--category", type=str, help="Model category for auto-path (e.g., checkpoints, loras, vae)")
    model_download_parser.add_argument("-y", "--yes", action="store_true", help="Skip path confirmation prompt")
    model_download_parser.set_defaults(func=global_cmds.model_download)

    # model add-source
    model_add_source_parser = model_subparsers.add_parser("add-source", help="Add download source URL to model(s)")
    model_add_source_parser.add_argument("model", nargs="?", help="Model filename or hash (omit for interactive mode)")
    model_add_source_parser.add_argument("url", nargs="?", help="Download URL")
    model_add_source_parser.set_defaults(func=global_cmds.model_add_source)

    # Registry management subcommands
    registry_parser = subparsers.add_parser("registry", help="Manage node registry cache")
    registry_subparsers = registry_parser.add_subparsers(dest="registry_command", help="Registry commands")

    # registry status
    registry_status_parser = registry_subparsers.add_parser("status", help="Show registry cache status")
    registry_status_parser.set_defaults(func=global_cmds.registry_status)

    # registry update
    registry_update_parser = registry_subparsers.add_parser("update", help="Update registry data from GitHub")
    registry_update_parser.set_defaults(func=global_cmds.registry_update)

    # Config management
    config_parser = subparsers.add_parser("config", help="Manage configuration settings")
    config_parser.add_argument("--civitai-key", type=str, help="Set Civitai API key (use empty string to clear)")
    config_parser.add_argument("--show", action="store_true", help="Show current configuration")
    config_parser.set_defaults(func=global_cmds.config)


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

    # repair - Repair environment drift (manual edits or git operations)
    repair_parser = subparsers.add_parser("repair", help="Repair environment to match pyproject.toml")
    repair_parser.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")
    repair_parser.set_defaults(func=env_cmds.repair)

    # commit - Commit unsaved changes
    commit_parser = subparsers.add_parser("commit", help="Commit unsaved changes to pyproject.toml (or uv.lock)")
    commit_parser.add_argument("-m", "--message", help="Commit message (auto-generated if not provided)")
    commit_parser.add_argument("--auto", action="store_true", help="Auto-resolve issues without interaction")
    commit_parser.add_argument("--allow-issues", action="store_true", help="Allow committing workflows with unresolved issues")
    commit_parser.set_defaults(func=env_cmds.commit)

    # log - Show commit history
    log_parser = subparsers.add_parser("log", help="Show commit history")
    log_parser.add_argument("-v", "--verbose", action="store_true", help="Show full details")
    log_parser.set_defaults(func=env_cmds.log)

    # rollback - Revert changes
    rollback_parser = subparsers.add_parser("rollback", help="Rollback to a previous version or discard uncommitted changes")
    rollback_parser.add_argument("target", nargs="?", help="Version to rollback to (e.g., 'v1', 'v2') - leave empty to discard uncommitted changes")
    rollback_parser.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")
    rollback_parser.add_argument("--force", action="store_true", help="Force rollback, discarding uncommitted changes without error")
    rollback_parser.set_defaults(func=env_cmds.rollback)

    # Node management subcommands
    node_parser = subparsers.add_parser("node", help="Manage custom nodes")
    node_subparsers = node_parser.add_subparsers(dest="node_command", help="Node commands")

    # node add
    node_add_parser = node_subparsers.add_parser("add", help="Add custom node")
    node_add_parser.add_argument("node_name", help="Node directory name or registry ID")
    node_add_parser.add_argument("--dev", action="store_true", help="Track existing local development node")
    node_add_parser.add_argument("--no-test", action="store_true", help="Don't test resolution")
    node_add_parser.add_argument("--force", action="store_true", help="Force overwrite existing directory")
    node_add_parser.set_defaults(func=env_cmds.node_add)

    # node remove
    node_remove_parser = node_subparsers.add_parser("remove", help="Remove custom node")
    node_remove_parser.add_argument("node_name", help="Node registry ID or name")
    node_remove_parser.add_argument("--dev", action="store_true", help="Remove development node specifically")
    node_remove_parser.set_defaults(func=env_cmds.node_remove)

    # node list
    node_list_parser = node_subparsers.add_parser("list", help="List custom nodes")
    node_list_parser.set_defaults(func=env_cmds.node_list)

    # node update
    node_update_parser = node_subparsers.add_parser("update", help="Update custom node")
    node_update_parser.add_argument("node_name", help="Node identifier or name to update")
    node_update_parser.add_argument("-y", "--yes", action="store_true", help="Auto-confirm updates (skip prompts)")
    node_update_parser.add_argument("--no-test", action="store_true", help="Don't test resolution")
    node_update_parser.set_defaults(func=env_cmds.node_update)

    # Workflow management subcommands
    workflow_parser = subparsers.add_parser("workflow", help="Manage workflows")
    workflow_subparsers = workflow_parser.add_subparsers(dest="workflow_command", help="Workflow commands")

    # workflow list
    workflow_list_parser = workflow_subparsers.add_parser("list", help="List all workflows with sync status")
    workflow_list_parser.set_defaults(func=env_cmds.workflow_list)

    # workflow resolve
    workflow_resolve_parser = workflow_subparsers.add_parser("resolve", help="Resolve workflow dependencies (nodes & models)")
    workflow_resolve_parser.add_argument("name", help="Workflow name to resolve")
    workflow_resolve_parser.add_argument("--auto", action="store_true", help="Auto-resolve without interaction")
    workflow_resolve_parser.add_argument("--install", action="store_true", help="Auto-install missing nodes without prompting")
    workflow_resolve_parser.add_argument("--no-install", action="store_true", help="Skip node installation prompt")
    workflow_resolve_parser.set_defaults(func=env_cmds.workflow_resolve)

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
