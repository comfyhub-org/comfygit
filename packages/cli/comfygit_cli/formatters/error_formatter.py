# formatters/error_formatter.py

from comfygit_core.models.exceptions import NodeAction, CDNodeConflictError, CDRegistryDataError


class NodeErrorFormatter:
    """Formats core library errors for CLI display."""

    @staticmethod
    def format_registry_error(error: CDRegistryDataError) -> str:
        """Format registry data error with recovery commands."""
        lines = [str(error)]

        if error.cache_path:
            lines.append(f"  Cache location: {error.cache_path}")

        if error.can_retry:
            lines.append("\nTo fix this issue:")
            lines.append("  1. Download registry data:")
            lines.append("     → cg registry update")
            lines.append("")
            lines.append("  2. Check download status:")
            lines.append("     → cg registry status")

        return "\n".join(lines)

    @staticmethod
    def format_node_action(action: NodeAction) -> str:
        """Convert NodeAction to CLI command string."""
        if action.action_type == 'remove_node':
            return f"cg node remove {action.node_identifier}"

        elif action.action_type == 'add_node_dev':
            return f"cg node add {action.node_name} --dev"

        elif action.action_type == 'add_node_force':
            return f"cg node add {action.node_identifier} --force"

        elif action.action_type == 'add_node_version':
            return f"cg node add {action.node_identifier}"

        elif action.action_type == 'rename_directory':
            return f"mv custom_nodes/{action.directory_name} custom_nodes/{action.new_name}"

        elif action.action_type == 'update_node':
            return f"cg node update {action.node_identifier}"

        return f"# Unknown action: {action.action_type}"

    @staticmethod
    def format_conflict_error(error: CDNodeConflictError) -> str:
        """Format a conflict error with suggested actions."""
        if not error.context:
            return str(error)

        lines = [str(error)]

        # Add context details
        ctx = error.context
        if ctx.local_remote_url:
            lines.append(f"  Filesystem: {ctx.local_remote_url}")
        if ctx.expected_remote_url:
            lines.append(f"  Registry:   {ctx.expected_remote_url}")

        # Add suggested actions
        if ctx.suggested_actions:
            lines.append("\nSuggested actions:")
            for i, action in enumerate(ctx.suggested_actions, 1):
                cmd = NodeErrorFormatter.format_node_action(action)
                desc = action.description
                lines.append(f"  {i}. {desc}")
                lines.append(f"     → {cmd}")

        return "\n".join(lines)
