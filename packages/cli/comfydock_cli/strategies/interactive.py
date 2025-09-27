"""Interactive resolution strategies for CLI."""

from typing import Optional, List

from comfydock_core.models.protocols import (
    NodeResolutionStrategy,
    ModelResolutionStrategy,
)
from comfydock_core.models.workflow import ResolvedNodePackage, WorkflowNodeWidgetRef
from comfydock_core.models.shared import ModelWithLocation


class InteractiveNodeStrategy(NodeResolutionStrategy):
    """Interactive node resolution with user prompts."""

    def resolve_unknown_node(
        self, node_type: str, possible: List[ResolvedNodePackage]
    ) -> ResolvedNodePackage | None:
        """Prompt user to resolve unknown node."""
        if not possible:
            print(f"⚠️  No registry matches found for '{node_type}'")
            print("  Options:")
            print("    s. Skip this node")
            print("    m. Enter package ID manually")

            choice = input("Choice [s]: ").strip().lower() or "s"
            if choice == "m":
                manual = input("Enter package ID: ").strip()
                if manual:
                    # TODO: Create a manual ResolvedNodePackage
                    # Note: This would need actual package data in production
                    print(f"  Note: Manual package '{manual}' will need to be verified")
                return None
            return None

        print(f"\n🔍 Found {len(possible)} matches for '{node_type}':")
        for i, pkg in enumerate(possible[:5], 1):
            display_name = pkg.package_data.display_name or pkg.package_id
            desc = pkg.package_data.description or "No description"
            confidence = pkg.match_confidence
            print(f"  {i}. {display_name} (confidence: {confidence:.1f})")
            if desc and len(desc) > 60:
                desc = desc[:57] + "..."
            print(f"      {desc}")
        print("  s. Skip this node")

        while True:
            choice = input("Choice [1/s]: ").strip().lower()
            if choice == "s":
                return None
            elif choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(possible[:5]):
                    return possible[idx]
            print("  Invalid choice, try again")

    def confirm_node_install(self, package: ResolvedNodePackage) -> bool:
        """Always confirm since user already made the choice."""
        return True


class InteractiveModelStrategy(ModelResolutionStrategy):
    """Interactive model resolution with user prompts."""

    def resolve_ambiguous_model(
        self, reference: WorkflowNodeWidgetRef, candidates: List[ModelWithLocation]
    ) -> Optional[ModelWithLocation]:
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
            if choice == "s":
                return None
            elif choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(candidates[:10]):
                    selected = candidates[idx]
                    print(f"  ✓ Selected: {selected.relative_path}")
                    return selected
            print("  Invalid choice, try again")

    def handle_missing_model(self, reference: WorkflowNodeWidgetRef) -> Optional[str]:
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


