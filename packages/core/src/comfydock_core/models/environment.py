"""models/environment.py - Environment models for ComfyDock."""

from dataclasses import dataclass, field
from enum import Enum
from typing import List


@dataclass
class PackageSyncStatus:
    """Status of package synchronization."""

    in_sync: bool
    message: str
    details: str | None = None


@dataclass
class GitStatus:
    """Encapsulated git status information."""

    has_changes: bool
    diff: str
    workflow_changes: dict[str, str] = field(default_factory=dict)

    # Git change details (populated by parser if needed)
    nodes_added: list[dict] = field(default_factory=list)  # {"name": str, "is_development": bool}
    nodes_removed: list[dict] = field(default_factory=list)  # {"name": str, "is_development": bool}
    dependencies_added: list[dict] = field(default_factory=list)
    dependencies_removed: list[dict] = field(default_factory=list)
    dependencies_updated: list[dict] = field(default_factory=list)
    constraints_added: list[str] = field(default_factory=list)
    constraints_removed: list[str] = field(default_factory=list)
    workflows_tracked: list[str] = field(default_factory=list)
    workflows_untracked: list[str] = field(default_factory=list)


@dataclass
class WorkflowStatus:
    """Encapsulated workflow status information."""

    in_sync: bool
    sync_status: dict[str, str] = field(default_factory=dict)
    tracked: list[str] = field(default_factory=list)
    watched: list[str] = field(default_factory=list)
    changes_needed: list[dict] = field(default_factory=list)  # {name, status}


@dataclass
class EnvironmentComparison:
    """Comparison between current and expected environment states."""

    missing_nodes: list[str] = field(default_factory=list)
    extra_nodes: list[str] = field(default_factory=list)
    version_mismatches: list[dict] = field(
        default_factory=list
    )  # {name, expected, actual}
    packages_in_sync: bool = True
    package_sync_message: str = ""

    @property
    def is_synced(self) -> bool:
        """Check if environment is fully synced."""
        return (
            not self.missing_nodes
            and not self.extra_nodes
            and not self.version_mismatches
            and self.packages_in_sync
        )


# === Semantic Value Objects ===


class SyncDirection(Enum):
    """Direction for workflow synchronization."""

    UPDATE_COMFYUI = "update_comfyui"
    UPDATE_TRACKED = "update_tracked"
    RESTORE_TO_COMFYUI = "restore"
    UPDATE_TO_CEC = "update_to_cec"


class UserAction(Enum):
    """Recommended user actions."""

    SYNC_REQUIRED = "sync"
    COMMIT_REQUIRED = "commit"
    NO_ACTION_NEEDED = "none"


@dataclass
class WorkflowSyncAction:
    """Semantic workflow sync action."""

    name: str
    action: SyncDirection
    description: str
    icon: str


@dataclass
class ChangesSummary:
    """Summary of changes with semantic meaning."""

    primary_changes: List[str] = field(default_factory=list)
    secondary_changes: List[str] = field(default_factory=list)
    has_breaking_changes: bool = False

    def get_headline(self) -> str:
        """Get a headline summary of changes."""
        if not self.primary_changes and not self.secondary_changes:
            return "No changes"

        if self.has_breaking_changes:
            return "Breaking changes detected"

        if len(self.primary_changes) == 1 and not self.secondary_changes:
            return self.primary_changes[0]

        total = len(self.primary_changes) + len(self.secondary_changes)
        return f"{total} changes"

    def get_commit_message(self) -> str:
        """Generate a commit message from changes."""
        parts = self.primary_changes + self.secondary_changes
        if not parts:
            return "Update environment configuration"
        return "; ".join(parts)


@dataclass
class SyncPreview:
    """Preview of what sync operation will do."""

    nodes_to_install: List[str] = field(default_factory=list)
    nodes_to_remove: List[str] = field(default_factory=list)
    nodes_to_update: List[dict] = field(default_factory=list)
    workflows_to_sync: List[WorkflowSyncAction] = field(default_factory=list)
    packages_to_sync: bool = False

    def has_changes(self) -> bool:
        """Check if sync would make any changes."""
        return bool(
            self.nodes_to_install
            or self.nodes_to_remove
            or self.nodes_to_update
            or self.workflows_to_sync
            or self.packages_to_sync
        )


@dataclass
class EnvironmentStatus:
    """Complete environment status including comparison and git/workflow state."""

    comparison: EnvironmentComparison
    git: GitStatus
    workflow: WorkflowStatus

    @classmethod
    def create(
        cls,
        comparison: EnvironmentComparison,
        git_status: GitStatus,
        workflow_status: WorkflowStatus,
    ) -> "EnvironmentStatus":
        """Factory method to create EnvironmentStatus from components."""
        return cls(comparison=comparison, git=git_status, workflow=workflow_status)

    @property
    def is_synced(self) -> bool:
        """Check if environment is fully synced."""
        return self.comparison.is_synced and self.workflow.in_sync

    # === Semantic Methods ===

    def get_workflow_sync_actions(self) -> List[WorkflowSyncAction]:
        """Convert string-based workflow statuses to semantic actions."""
        actions = []
        for name, status in self.workflow.sync_status.items():
            if status == "comfyui_newer":
                actions.append(
                    WorkflowSyncAction(
                        name=name,
                        action=SyncDirection.UPDATE_TRACKED,
                        description="modified in ComfyUI",
                        icon="✏️",
                    )
                )
            elif status == "tracked_newer":
                actions.append(
                    WorkflowSyncAction(
                        name=name,
                        action=SyncDirection.UPDATE_COMFYUI,
                        description="modified in .cec",
                        icon="📂",
                    )
                )
            elif status == "missing_comfyui":
                actions.append(
                    WorkflowSyncAction(
                        name=name,
                        action=SyncDirection.RESTORE_TO_COMFYUI,
                        description="needs restore to ComfyUI",
                        icon="🔄",
                    )
                )
            elif status == "missing_tracked":
                actions.append(
                    WorkflowSyncAction(
                        name=name,
                        action=SyncDirection.UPDATE_TO_CEC,
                        description="needs update to .cec",
                        icon="📋",
                    )
                )
            else:
                actions.append(
                    WorkflowSyncAction(
                        name=name,
                        action=SyncDirection.UPDATE_TRACKED,
                        description=status,
                        icon="⚠️",
                    )
                )
        return actions

    def get_changes_summary(self) -> ChangesSummary:
        """Analyze and categorize all changes."""
        primary_changes = []
        secondary_changes = []

        # Node changes (most specific)
        if self.git.nodes_added and self.git.nodes_removed:
            primary_changes.append(
                f"Update nodes: +{len(self.git.nodes_added)}, -{len(self.git.nodes_removed)}"
            )
        elif self.git.nodes_added:
            if len(self.git.nodes_added) == 1:
                primary_changes.append(f"Add {self.git.nodes_added[0]}")
            else:
                primary_changes.append(f"Add {len(self.git.nodes_added)} nodes")
        elif self.git.nodes_removed:
            if len(self.git.nodes_removed) == 1:
                primary_changes.append(f"Remove {self.git.nodes_removed[0]}")
            else:
                primary_changes.append(f"Remove {len(self.git.nodes_removed)} nodes")

        # Dependency changes
        if (
            self.git.dependencies_added
            or self.git.dependencies_removed
            or self.git.dependencies_updated
        ):
            dep_count = (
                len(self.git.dependencies_added)
                + len(self.git.dependencies_removed)
                + len(self.git.dependencies_updated)
            )
            secondary_changes.append(f"Update {dep_count} dependencies")

        # Constraint changes
        if self.git.constraints_added or self.git.constraints_removed:
            secondary_changes.append("Update constraints")

        # Workflow tracking changes
        if self.git.workflows_tracked and self.git.workflows_untracked:
            secondary_changes.append(
                f"Update workflow tracking: +{len(self.git.workflows_tracked)}, -{len(self.git.workflows_untracked)}"
            )
        elif self.git.workflows_tracked:
            if len(self.git.workflows_tracked) == 1:
                primary_changes.append(
                    f"Track workflow: {self.git.workflows_tracked[0]}"
                )
            else:
                primary_changes.append(
                    f"Track {len(self.git.workflows_tracked)} workflows"
                )
        elif self.git.workflows_untracked:
            if len(self.git.workflows_untracked) == 1:
                primary_changes.append(
                    f"Untrack workflow: {self.git.workflows_untracked[0]}"
                )
            else:
                primary_changes.append(
                    f"Untrack {len(self.git.workflows_untracked)} workflows"
                )

        # Workflow file changes
        if self.git.workflow_changes:
            workflow_count = len(self.git.workflow_changes)
            if workflow_count == 1:
                workflow_name, workflow_status = list(
                    self.git.workflow_changes.items()
                )[0]
                if workflow_status == "modified":
                    primary_changes.append(f"Update {workflow_name}")
                elif workflow_status == "added":
                    primary_changes.append(f"Add {workflow_name}")
                elif workflow_status == "deleted":
                    primary_changes.append(f"Remove {workflow_name}")
            else:
                primary_changes.append(f"Update {workflow_count} workflows")

        # Detect breaking changes
        has_breaking = bool(
            self.git.nodes_removed
            or self.git.dependencies_removed
            or self.git.constraints_removed
        )

        return ChangesSummary(
            primary_changes=primary_changes,
            secondary_changes=secondary_changes,
            has_breaking_changes=has_breaking,
        )

    def get_recommended_action(self) -> UserAction:
        """Determine what the user should do next."""
        if not self.is_synced:
            return UserAction.SYNC_REQUIRED
        elif self.git.has_changes:
            return UserAction.COMMIT_REQUIRED
        else:
            return UserAction.NO_ACTION_NEEDED

    def generate_commit_message(self) -> str:
        """Generate a semantic commit message."""
        summary = self.get_changes_summary()
        return summary.get_commit_message()

    def get_sync_preview(self) -> SyncPreview:
        """Get preview of what sync operation will do."""
        workflow_actions = self.get_workflow_sync_actions()

        return SyncPreview(
            nodes_to_install=self.comparison.missing_nodes,
            nodes_to_remove=self.comparison.extra_nodes,
            nodes_to_update=self.comparison.version_mismatches,
            workflows_to_sync=workflow_actions,
            packages_to_sync=not self.comparison.packages_in_sync,
        )
