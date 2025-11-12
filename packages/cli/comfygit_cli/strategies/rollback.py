"""Rollback confirmation strategies for CLI."""


class InteractiveRollbackStrategy:
    """Interactive strategy that prompts user to confirm destructive rollback."""

    def confirm_destructive_rollback(self, git_changes: bool, workflow_changes: bool) -> bool:
        """Prompt user to confirm rollback that will discard changes.

        Args:
            git_changes: Whether there are uncommitted git changes in .cec/
            workflow_changes: Whether there are modified/new/deleted workflows

        Returns:
            True if user confirms, False otherwise
        """
        print("⚠️  This will discard uncommitted changes:")
        if git_changes:
            print("  • Git changes in .cec/")
        if workflow_changes:
            print("  • Workflow modifications in ComfyUI")

        response = input("\nAre you sure? This cannot be undone. (y/N): ")
        return response.lower() == 'y'


class AutoRollbackStrategy:
    """Auto-confirm strategy for --yes flag."""

    def confirm_destructive_rollback(self, git_changes: bool, workflow_changes: bool) -> bool:
        """Always confirm rollback (used with --yes flag).

        Args:
            git_changes: Whether there are uncommitted git changes in .cec/
            workflow_changes: Whether there are modified/new/deleted workflows

        Returns:
            Always True
        """
        return True
