"""Interactive model resolver for CLI."""
from __future__ import annotations

from typing import TYPE_CHECKING, List

from comfydock_core.models.sync import ModelResolutionMap, ModelResolutionStrategy

if TYPE_CHECKING:
    from comfydock_core.models.workflow import ModelResolutionResult


class InteractiveModelResolver(ModelResolutionStrategy):
    """Interactive CLI resolver that prompts user for ambiguous models."""

    def resolve_ambiguous(
        self,
        results: List[ModelResolutionResult]
    ) -> ModelResolutionMap:
        """Prompt user to resolve ambiguous models.

        Args:
            results: List of model resolution results

        Returns:
            ModelResolutionMap with user's choices
        """
        resolutions: ModelResolutionMap = {}

        # Filter to ambiguous cases only
        ambiguous = [r for r in results if r.resolution_type == "ambiguous"]

        if not ambiguous:
            return resolutions

        print(f"\n⚠️  Found {len(ambiguous)} ambiguous model reference(s)")
        print("Please select the correct model for each:\n")

        for result in ambiguous:
            ref = result.reference
            print(f"Node #{ref.node_id} ({ref.node_type})")
            print(f"  Looking for: {ref.widget_value}")
            print("  Found multiple matches:")

            # Show up to 10 candidates
            candidates = result.candidates[:10]
            for i, model in enumerate(candidates, 1):
                size_mb = model.file_size / (1024 * 1024)
                print(f"    {i}. {model.relative_path} ({size_mb:.1f} MB)")

            print("    s. Skip (leave unresolved)")

            # Get user choice
            while True:
                choice = input("  Choice [1-10/s]: ").strip().lower()

                if choice == 's':
                    print("  → Skipped\n")
                    break
                elif choice.isdigit():
                    idx = int(choice) - 1
                    if 0 <= idx < len(candidates):
                        chosen = candidates[idx]
                        resolutions[(ref.node_id, ref.widget_index)] = chosen
                        print(f"  → Selected: {chosen.relative_path}\n")
                        break

                print("  Invalid choice")

        return resolutions

    def show_summary(self, results: List[ModelResolutionResult]) -> None:
        """Show resolution summary to user.

        Args:
            results: Model resolution results to summarize
        """
        # Count different types
        resolved = [r for r in results if r.resolution_type not in ("ambiguous", "not_found")]
        ambiguous = [r for r in results if r.resolution_type == "ambiguous"]
        unresolved = [r for r in results if r.resolution_type == "not_found"]

        print("\n📊 Model Resolution Summary:")

        if resolved:
            print(f"  ✅ {len(resolved)} models resolved")

        if ambiguous:
            print(f"  ⚠️  {len(ambiguous)} models ambiguous (need selection)")

        if unresolved:
            print(f"  ❌ {len(unresolved)} models not found")
            # Show first few unresolved models
            for result in unresolved[:3]:
                ref = result.reference
                print(f"      • Node #{ref.node_id}: {ref.widget_value}")
            if len(unresolved) > 3:
                print(f"      • ... and {len(unresolved) - 3} more")

        print()  # Empty line for better formatting


class SilentResolver(ModelResolutionStrategy):
    """Silent resolver that auto-selects first candidate for ambiguous models."""

    def resolve_ambiguous(
        self,
        results: List[ModelResolutionResult]
    ) -> ModelResolutionMap:
        """Auto-select first candidate for each ambiguous model.

        Args:
            results: List of model resolution results

        Returns:
            ModelResolutionMap with auto-selected choices
        """
        resolutions: ModelResolutionMap = {}
        for result in results:
            if result.resolution_type == "ambiguous" and result.candidates:
                ref = result.reference
                resolutions[(ref.node_id, ref.widget_index)] = result.candidates[0]
        return resolutions