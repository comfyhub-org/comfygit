"""Resolution strategy protocols for dependency injection."""
from typing import Protocol, Optional, List
from abc import abstractmethod

from .workflow import WorkflowModelRef
from .shared import ModelWithLocation


class NodeResolutionStrategy(Protocol):
    """Protocol for resolving unknown custom nodes."""
    
    @abstractmethod
    def resolve_unknown_node(self, 
                            node_type: str, 
                            suggestions: List[dict]) -> Optional[str]:
        """Given node type and suggestions, return package ID or None.
        
        Args:
            node_type: The unknown node type (e.g. "MyCustomNode")
            suggestions: List of registry suggestions with package_id, confidence
            
        Returns:
            Package ID to install or None to skip
        """
        ...
    
    @abstractmethod
    def confirm_node_install(self, package_id: str, node_type: str) -> bool:
        """Confirm whether to install a node package.
        
        Args:
            package_id: Registry package ID
            node_type: The node type being resolved
            
        Returns:
            True to install, False to skip
        """
        ...


class ModelResolutionStrategy(Protocol):
    """Protocol for resolving model references."""
    
    @abstractmethod
    def resolve_ambiguous_model(self,
                               reference: WorkflowModelRef,
                               candidates: List[ModelWithLocation]) -> Optional[ModelWithLocation]:
        """Choose from multiple model matches.
        
        Args:
            reference: The model reference from workflow
            candidates: List of possible model matches
            
        Returns:
            Chosen model or None to skip
        """
        ...
    
    @abstractmethod
    def handle_missing_model(self,
                            reference: WorkflowModelRef) -> Optional[str]:
        """Handle completely missing model.
        
        Args:
            reference: The model reference that couldn't be found
            
        Returns:
            Download URL or None to skip
        """
        ...
