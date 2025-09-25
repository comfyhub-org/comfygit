"""Interactive resolution strategies for CLI."""
from typing import Optional, List

from comfydock_core.models.protocols import NodeResolutionStrategy, ModelResolutionStrategy
from comfydock_core.models.workflow import WorkflowModelRef
from comfydock_core.models.shared import ModelWithLocation


class InteractiveNodeStrategy:
    """Interactive node resolution with user prompts."""

    def resolve_unknown_node(self,
                             node_type: str,
                             suggestions: List[dict]) -> Optional[str]:
        """Prompt user to resolve unknown node."""
        if not suggestions:
            print(f"⚠️  No registry matches found for '{node_type}'")
            manual = input("Enter package ID manually (or press Enter to skip): ").strip()
            return manual if manual else None

        print(f"\n🔍 Found {len(suggestions)} matches for '{node_type}':")
        for i, suggestion in enumerate(suggestions[:5], 1):
            package_id = suggestion.get('package_id', 'unknown')
            confidence = suggestion.get('confidence', 0)
            print(f"  {i}. {package_id} (confidence: {confidence:.1f})")
        print("  s. Skip this node")

        while True:
            choice = input("Choice [1/s]: ").strip().lower()
            if choice == 's':
                return None
            elif choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(suggestions[:5]):
                    return suggestions[idx].get('package_id')
            print("  Invalid choice, try again")

    def confirm_node_install(self, package_id: str, node_type: str) -> bool:
        """Always confirm since user already made the choice."""
        return True


class InteractiveModelStrategy:
    """Interactive model resolution with user prompts."""

    def resolve_ambiguous_model(self,
                                reference: WorkflowModelRef,
                                candidates: List[ModelWithLocation]) -> Optional[ModelWithLocation]:
        """Prompt user to resolve ambiguous model."""
        print(f"\n🔍 Multiple matches for model in node #{reference.node_id}:")
        print(f"  Looking for: {reference.widget_value}")
        print("  Found matches:")

        for i, model in enumerate(candidates[:10], 1):
            size_mb = model.file_size / (1024 * 1024)
            print(f"  {i}. {model.relative_path} ({size_mb:.1f} MB)")
        print("  s. Skip")

        while True:
            choice = input("Choice [1/s]: ").strip().lower()
            if choice == 's':
                return None
            elif choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(candidates[:10]):
                    selected = candidates[idx]
                    print(f"  ✓ Selected: {selected.relative_path}")
                    return selected
            print("  Invalid choice, try again")

    def handle_missing_model(self, reference: WorkflowModelRef) -> Optional[str]:
        """Prompt user for missing model."""
        print(f"\n⚠️  Model not found: {reference.widget_value}")
        print("  in node #{} ({})".format(reference.node_id, reference.node_type))
        print("Options:")
        print("  1. Mark as external (skip for now)")
        print("  2. Provide download URL")
        print("  3. Search manually")

        while True:
            choice = input("Choice [1]: ").strip() or "1"

            if choice == "1":
                return None  # Skip
            elif choice == "2":
                url = input("Enter download URL: ").strip()
                if url:
                    return url
                print("  No URL provided, skipping")
                return None
            elif choice == "3":
                search_term = input("Enter search term: ").strip()
                if search_term:
                    print(f"  Search functionality not implemented yet")
                    print(f"  Would search for: {search_term}")
                return None
            else:
                print("  Invalid choice, try again")


class SilentStrategy:
    """Silent strategies that auto-resolve without user interaction."""

    def resolve_unknown_node(self,
                             node_type: str,
                             suggestions: List[dict]) -> Optional[str]:
        """Auto-resolve with highest confidence match."""
        if not suggestions:
            return None

        # Take the first suggestion if confidence is high enough
        best = suggestions[0]
        confidence = best.get('confidence', 0)
        if confidence > 0.8:  # High confidence threshold
            return best.get('package_id')
        return None

    def confirm_node_install(self, package_id: str, node_type: str) -> bool:
        """Always confirm in silent mode."""
        return True

    def resolve_ambiguous_model(self,
                                reference: WorkflowModelRef,
                                candidates: List[ModelWithLocation]) -> Optional[ModelWithLocation]:
        """Auto-select first candidate only if single match."""
        return candidates[0] if len(candidates) == 1 else None

    def handle_missing_model(self, reference: WorkflowModelRef) -> Optional[str]:
        """Skip missing models in silent mode."""
        return None