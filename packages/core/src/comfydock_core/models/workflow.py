from __future__ import annotations

from dataclasses import asdict, dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..services.global_node_resolver import NodeMatch, PackageSuggestion
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
class WorkflowAnalysisResult:
    """Complete analysis of a workflow's dependencies and requirements.

    This is a pure data structure returned by WorkflowManager.analyze_workflow()
    to allow clients to make their own decisions about installation and tracking.
    """

    name: str
    workflow_path: Path

    # Node analysis
    resolved_nodes: Dict[str, "NodeMatch"] = field(default_factory=dict)  # node_type -> match
    unresolved_nodes: List[str] = field(default_factory=list)  # node types we couldn't resolve
    installed_packages: List[InstalledPackageInfo] = field(default_factory=list)  # already in pyproject
    missing_packages: List["PackageSuggestion"] = field(default_factory=list)  # need to install

    # Model analysis
    resolved_models: List[Any] = field(default_factory=list)  # Model objects or dicts
    missing_models: List[str] = field(default_factory=list)  # Model hashes not found
    model_hashes: List[str] = field(default_factory=list)  # All model hashes

    # Other dependencies
    python_dependencies: List[str] = field(default_factory=list)

    # Metadata
    total_custom_nodes: int = 0
    total_builtin_nodes: int = 0
    already_tracked: bool = False

    @property
    def has_missing_dependencies(self) -> bool:
        """Check if workflow has any missing dependencies."""
        return bool(self.missing_packages or self.missing_models or self.unresolved_nodes)

    @property
    def is_fully_resolvable(self) -> bool:
        """Check if all dependencies can be resolved."""
        return not self.unresolved_nodes

    @property
    def resolved_package_ids(self) -> List[str]:
        """Get list of resolved package IDs."""
        return [match.package_id for match in self.resolved_nodes.values()
                if match and match.package_id]

    def to_pyproject_requires(self) -> dict:
        """Convert analysis to pyproject.toml requires dict."""
        requires: dict = {
            "nodes": sorted(set(self.resolved_package_ids)),
            "models": self.model_hashes,
            "python": self.python_dependencies
        }

        # Store debug info if needed
        if self.unresolved_nodes:
            requires["_unknown_nodes"] = self.unresolved_nodes

        if self.missing_packages:
            # Store package suggestions for future reference
            requires["_missing_packages"] = [
                {"id": pkg.package_id, "version": pkg.suggested_version}
                for pkg in self.missing_packages
            ]

        return requires


@dataclass
class ModelReference:
    """Single model reference with full context"""
    node_id: str
    node_type: str
    widget_index: int
    widget_value: str  # Original value from workflow
    resolved_model: "ModelWithLocation | None" = None
    resolution_confidence: float = 0.0  # 1.0 = exact, 0.5 = fuzzy

    @property
    def is_resolved(self) -> bool:
        return self.resolved_model is not None


@dataclass
class ModelResolutionResult:
    """Result of attempting to resolve a model reference"""
    reference: ModelReference
    candidates: List["ModelWithLocation"]  # All possible matches
    resolution_type: str  # "exact", "case_insensitive", "filename", "ambiguous", "not_found"
