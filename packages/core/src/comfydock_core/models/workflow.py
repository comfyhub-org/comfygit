from __future__ import annotations

from dataclasses import asdict, dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from ..models.node_mapping import (
    GlobalNodePackage,
)

if TYPE_CHECKING:
    from .shared import ModelWithLocation


@dataclass
class Link:
    """Represents a connection between nodes."""
    id: int
    source_node_id: int
    source_slot: int
    target_node_id: int
    target_slot: int
    type: str

    def to_array(self) -> list:
        """Convert to ComfyUI's [id, source_node, source_slot, target_node,
        target_slot, type] format."""
        return [self.id, self.source_node_id, self.source_slot, self.target_node_id, self.target_slot, self.type]

    @classmethod
    def from_array(cls, arr: list) -> Link:
        """Parse from ComfyUI's array format."""
        return cls(arr[0], arr[1], arr[2], arr[3], arr[4], arr[5])

@dataclass
class Group:
    """Represents a visual grouping of nodes."""
    id: int
    title: str
    bounding: tuple[float, float, float, float]  # [x, y, width, height]
    color: str
    font_size: int = 24
    flags: dict[str, Any] = field(default_factory=dict)

@dataclass
class Workflow:
    """Complete parsed workflow representation."""

    # Core data
    nodes: dict[str, WorkflowNode]  # Keep as dict for easier access

    # Graph structure
    links: list[Link] = field(default_factory=list)
    groups: list[Group] = field(default_factory=list)

    # Metadata (exactly as in your examples)
    id: str | None = None
    revision: int = 0
    last_node_id: int | None = None
    last_link_id: int | None = None
    version: float | None = None

    # Flexible containers (don't break these out into separate fields!)
    config: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    @cached_property
    def node_types(self) -> set[str]:
        return {node.type for node in self.nodes.values()}

    @classmethod
    def from_json(cls, data: dict) -> Workflow:
        """Parse from ComfyUI workflow JSON."""
        # Handle nodes (convert list to dict)
        if isinstance(data.get('nodes'), list):
            nodes = {str(node['id']): WorkflowNode.from_dict(node) for node in data['nodes']}
        else:
            nodes = {k: WorkflowNode.from_dict(v) for k, v in data.get('nodes', {}).items()}

        # Parse links from arrays
        links = [Link.from_array(link) for link in data.get('links', [])]

        # Parse groups (if present)
        groups = [Group(**group) for group in data.get('groups', [])]

        return cls(
            nodes=nodes,
            links=links,
            groups=groups,
            id=data.get('id'),
            revision=data.get('revision', 0),
            last_node_id=data.get('last_node_id'),
            last_link_id=data.get('last_link_id'),
            version=data.get('version'),
            config=data.get('config', {}),
            extra=data.get('extra', {})
        )

    def to_json(self) -> dict:
        """Convert back to ComfyUI workflow format."""
        return {
            'id': self.id,
            'revision': self.revision,
            'last_node_id': self.last_node_id,
            'last_link_id': self.last_link_id,
            'nodes': [node.to_dict() for node in self.nodes.values()],
            'links': [link.to_array() for link in self.links],
            'groups': [asdict(group) for group in self.groups],
            'config': self.config,
            'extra': self.extra,
            'version': self.version
        }

@dataclass
class NodeInput:
    """Represents a node input definition."""
    name: str
    type: str
    link: int | None = None
    localized_name: str | None = None
    widget: dict[str, Any] | None = None
    shape: int | None = None
    slot_index: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict format."""
        result: dict = {
            'name': self.name,
            'type': self.type
        }
        if self.link is not None:
            result['link'] = self.link
        if self.localized_name is not None:
            result['localized_name'] = self.localized_name
        if self.widget is not None:
            result['widget'] = self.widget
        if self.shape is not None:
            result['shape'] = self.shape
        if self.slot_index is not None:
            result['slot_index'] = self.slot_index
        return result


@dataclass
class NodeOutput:
    """Represents a node output definition."""
    name: str
    type: str
    links: list[int] | None = None
    localized_name: str | None = None
    slot_index: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict format."""
        result: dict = {
            'name': self.name,
            'type': self.type
        }
        if self.links is not None:
            result['links'] = self.links
        if self.localized_name is not None:
            result['localized_name'] = self.localized_name
        if self.slot_index is not None:
            result['slot_index'] = self.slot_index
        return result


@dataclass
class WorkflowNode:
    """Complete workflow node with all available data."""
    id: str
    type: str

    # Core data - dual naming for compatibility
    api_widget_values: dict[str, Any] = field(default_factory=dict)  # For convenience/internal use
    widgets_values: list[Any] = field(default_factory=list)  # Frontend format

    # UI positioning
    pos: tuple[float, float] | None = None
    size: tuple[float, float] | None = None

    # UI state
    flags: dict[str, Any] = field(default_factory=dict)
    order: int | None = None
    mode: int | None = None
    title: str | None = None
    color: str | None = None
    bgcolor: str | None = None

    # Connections
    inputs: list[NodeInput] = field(default_factory=list)
    outputs: list[NodeOutput] = field(default_factory=list)

    # Extended properties
    properties: dict[str, Any] = field(default_factory=dict)

    @property
    def class_type(self) -> str:
        """Alias for API format compatibility."""
        return self.type

    def to_api_format(self) -> dict:
        """Convert to ComfyUI API format."""
        inputs = {}

        # Handle connections and widget values
        widget_idx = 0
        for inp in self.inputs:
            if inp.link is not None:
                # Connected input: [source_node_id, output_slot]
                inputs[inp.name] = [str(inp.link), inp.slot_index or 0]
            elif inp.widget and widget_idx < len(self.widgets_values):
                # Widget input: use value from widgets_values array
                inputs[inp.name] = self.widgets_values[widget_idx]
                widget_idx += 1

        return {
            "class_type": self.type,
            "inputs": inputs
        }

    @classmethod
    def from_dict(cls, data: dict) -> WorkflowNode:
        """Parse from workflow node dict."""
        # Parse inputs
        inputs = []
        raw_inputs = data.get('inputs', [])
        if isinstance(raw_inputs, list):
            for idx, input_data in enumerate(raw_inputs):
                if isinstance(input_data, dict):
                    inputs.append(NodeInput(
                        name=input_data.get('name', ''),
                        type=input_data.get('type', ''),
                        link=input_data.get('link'),
                        localized_name=input_data.get('localized_name'),
                        widget=input_data.get('widget'),
                        shape=input_data.get('shape'),
                        slot_index=input_data.get('slot_index', idx)
                    ))

        # Parse outputs
        outputs = []
        raw_outputs = data.get('outputs', [])
        if isinstance(raw_outputs, list):
            for idx, output_data in enumerate(raw_outputs):
                if isinstance(output_data, dict):
                    outputs.append(NodeOutput(
                        name=output_data.get('name', ''),
                        type=output_data.get('type', ''),
                        links=output_data.get('links'),
                        localized_name=output_data.get('localized_name'),
                        slot_index=output_data.get('slot_index', idx)
                    ))

        # Parse position and size
        pos = None
        if 'pos' in data and isinstance(data['pos'], list) and len(data['pos']) >= 2:
            pos = (float(data['pos'][0]), float(data['pos'][1]))

        size = None
        if 'size' in data and isinstance(data['size'], list) and len(data['size']) >= 2:
            size = (float(data['size'][0]), float(data['size'][1]))

        # Handle dual naming convention for widget values
        widgets_values = data.get('widgets_values', [])
        widget_values = data.get('widget_values', widgets_values)

        return cls(
            id=str(data.get('id', 'unknown')),
            type=data.get('type') or data.get('class_type') or '',
            api_widget_values=widget_values,
            widgets_values=widgets_values,
            pos=pos,
            size=size,
            flags=data.get('flags', {}),
            order=data.get('order'),
            mode=data.get('mode'),
            title=data.get('title'),
            color=data.get('color'),
            bgcolor=data.get('bgcolor'),
            inputs=inputs,
            outputs=outputs,
            properties=data.get('properties', {})
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict format."""
        result = {
            'id': int(self.id) if self.id.isdigit() else self.id,
            'type': self.type,
            'widgets_values': self.widgets_values,
            'inputs': [inp.to_dict() for inp in self.inputs],
            'outputs': [out.to_dict() for out in self.outputs],
            'properties': self.properties,
            'flags': self.flags
        }

        # Add optional fields only if they have values
        if self.pos is not None:
            result['pos'] = list(self.pos)
        if self.size is not None:
            result['size'] = list(self.size)
        if self.order is not None:
            result['order'] = self.order
        if self.mode is not None:
            result['mode'] = self.mode
        if self.title is not None:
            result['title'] = self.title
        if self.color is not None:
            result['color'] = self.color
        if self.bgcolor is not None:
            result['bgcolor'] = self.bgcolor

        return result


@dataclass
class InstalledPackageInfo:
    """Information about an already-installed package."""

    package_id: str
    display_name: Optional[str]
    installed_version: str
    suggested_version: Optional[str] = None

    @property
    def version_mismatch(self) -> bool:
        """Check if installed version differs from suggested."""
        return bool(self.suggested_version and
                   self.installed_version != self.suggested_version)

@dataclass
class WorkflowNodeWidgetRef:
    """Reference to a widget value in a workflow node."""
    node_id: str
    node_type: str
    widget_index: int
    widget_value: str  # Original value from workflow

@dataclass
class WorkflowDependencies:
    """Complete workflow dependency analysis results."""
    workflow_name: str
    found_models: list[WorkflowNodeWidgetRef] = field(default_factory=list)
    builtin_nodes: list[WorkflowNode] = field(default_factory=list)
    missing_nodes: list[WorkflowNode] = field(default_factory=list)

    @property
    def total_models(self) -> int:
        """Total number of model references found."""
        return len(self.found_models) + len(self.found_models)
    
@dataclass
class ResolvedNodePackage:
    """A potential match for an unknown node."""

    package_id: str
    package_data: GlobalNodePackage
    versions: list[str]
    match_type: str  # "exact", "type_only", "fuzzy"
    match_confidence: float = 1.0

@dataclass
class NodeResolutionResult:
    """Result of resolving unknown nodes."""

    resolved: dict[str, ResolvedNodePackage] = field(default_factory=dict)  # node_type -> match
    ambiguous: dict[str, List[ResolvedNodePackage]] = field(default_factory=dict)
    unresolved: list[str] = field(default_factory=list)

@dataclass
class ModelResolutionResult:
    """Result of attempting to resolve a model reference"""
    reference: WorkflowNodeWidgetRef
    candidates: List["ModelWithLocation"]  # All possible matches
    resolution_type: str  # "exact", "case_insensitive", "filename", "ambiguous", "not_found"
    resolved_model: "ModelWithLocation | None" = None
    resolution_confidence: float = 0.0  # 1.0 = exact, 0.5 = fuzzy

    @property
    def is_resolved(self) -> bool:
        return self.resolved_model is not None

@dataclass
class WorkflowAnalysisResult:
    """Result of analyzing workflow dependencies - pure analysis, no decisions."""
    workflow_name: str
    workflow_path: Path

    # Node analysis
    custom_nodes_installed: Dict[str, Any] = field(default_factory=dict)  # Already in environment
    custom_nodes_missing: List[str] = field(default_factory=list)  # Not installed
    node_suggestions: Dict[str, List[dict]] = field(default_factory=dict)  # Registry matches

    # Model analysis (categorized by resolution status)
    models_resolved: List[ModelResolutionResult] = field(default_factory=list)  # Auto-resolved
    models_ambiguous: List[ModelResolutionResult] = field(default_factory=list)  # Multiple matches
    models_missing: List[ModelResolutionResult] = field(default_factory=list)  # No matches

    # Raw data for strategies
    model_resolution_results: List[ModelResolutionResult] = field(default_factory=list)
    builtin_nodes: List[str] = field(default_factory=list)
    custom_nodes_found: List[str] = field(default_factory=list)

    # Status flags
    already_tracked: bool = False

    @property
    def has_issues(self) -> bool:
        """Check if workflow has any missing dependencies."""
        return bool(
            self.custom_nodes_missing or
            self.models_ambiguous or
            self.models_missing
        )

    @property
    def needs_node_resolution(self) -> bool:
        """Check if workflow needs node resolution."""
        return bool(self.custom_nodes_missing)

    @property
    def needs_model_resolution(self) -> bool:
        """Check if workflow needs model resolution."""
        return bool(self.models_ambiguous or self.models_missing)


@dataclass
class ResolutionResult:
    """Result of applying resolution strategies."""
    nodes_added: List[ResolvedNodePackage] = field(default_factory=list)  # Package IDs added
    models_resolved: List["ModelWithLocation"] = field(default_factory=list)  # Models resolved
    models_unresolved: List["WorkflowNodeWidgetRef"] = field(default_factory=list)  # Models unresolved
    external_models_added: List[str] = field(default_factory=list)  # URLs added as external
    changes_made: bool = False

    @property
    def summary(self) -> str:
        """Generate summary of changes."""
        parts = []
        if self.nodes_added:
            parts.append(f"{len(self.nodes_added)} nodes")
        if self.models_resolved:
            parts.append(f"{len(self.models_resolved)} models")
        if self.external_models_added:
            parts.append(f"{len(self.external_models_added)} external models")

        if not parts:
            return "No changes"
        return f"Added: {', '.join(parts)}"


@dataclass
class CommitAnalysis:
    """Analysis of all workflows for commit."""
    workflows_copied: Dict[str, str] = field(default_factory=dict)  # name -> status
    analyses: List[WorkflowDependencies] = field(default_factory=list)
    has_git_changes: bool = False  # Whether there are actual git changes to commit

    @property
    def summary(self) -> str:
        """Generate commit summary."""
        copied_count = len([s for s in self.workflows_copied.values() if s == "copied"])
        if copied_count:
            return f"Update {copied_count} workflow(s)"
        return "Update workflows"
