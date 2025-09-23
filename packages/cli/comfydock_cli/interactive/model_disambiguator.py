"""Model disambiguator for handling ambiguous model references."""
from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Tuple

if TYPE_CHECKING:
    from comfydock_core.models.workflow import ModelResolutionResult
    from comfydock_core.models.shared import ModelWithLocation


class ModelDisambiguator:
    """Handle user disambiguation for ambiguous models"""

    def resolve_ambiguous_models(
        self,
        results: List["ModelResolutionResult"]
    ) -> Dict[Tuple[str, int], "ModelWithLocation"]:
        """Prompt user to resolve ambiguous models"""
        resolutions = {}

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

            for i, model in enumerate(result.candidates[:10], 1):
                size_mb = model.file_size / (1024 * 1024)
                print(f"    {i}. {model.relative_path} ({size_mb:.1f} MB)")

            print("    s. Skip (leave unresolved)")

            while True:
                choice = input("  Choice [1-10/s]: ").strip().lower()

                if choice == 's':
                    print("  → Skipped\n")
                    break
                elif choice.isdigit():
                    idx = int(choice) - 1
                    if 0 <= idx < len(result.candidates):
                        chosen = result.candidates[idx]
                        resolutions[(ref.node_id, ref.widget_index)] = chosen
                        print(f"  → Selected: {chosen.relative_path}\n")
                        break

                print("  Invalid choice")

        return resolutions

    def show_resolution_summary(self, results: List["ModelResolutionResult"]) -> None:
        """Show summary of resolution results"""
        by_type = {}
        for result in results:
            type_key = result.resolution_type
            if type_key not in by_type:
                by_type[type_key] = []
            by_type[type_key].append(result)

        print("\nModel Resolution Summary:")
        if "metadata" in by_type:
            print(f"  ✅ {len(by_type['metadata'])} resolved from metadata (cached)")
        if "exact" in by_type:
            print(f"  ✅ {len(by_type['exact'])} exact matches")
        if "reconstructed" in by_type:
            print(f"  ✅ {len(by_type['reconstructed'])} reconstructed paths")
        if "case_insensitive" in by_type:
            print(f"  ✅ {len(by_type['case_insensitive'])} case-insensitive matches")
        if "filename" in by_type:
            print(f"  ✅ {len(by_type['filename'])} filename matches")
        if "ambiguous" in by_type:
            print(f"  ⚠️  {len(by_type['ambiguous'])} ambiguous (need selection)")
        if "not_found" in by_type:
            print(f"  ❌ {len(by_type['not_found'])} not found")

        # Show unresolved details
        if "not_found" in by_type:
            print("\nUnresolved models:")
            for result in by_type["not_found"][:5]:  # Show first 5
                ref = result.reference
                print(f"  - Node #{ref.node_id}: {ref.widget_value}")
            if len(by_type["not_found"]) > 5:
                print(f"  ... and {len(by_type['not_found']) - 5} more")