"""Interactive resolution strategies for CLI."""


from comfydock_core.models.protocols import (
    ModelResolutionStrategy,
    NodeResolutionStrategy,
)
from comfydock_core.models.shared import ModelWithLocation
from comfydock_core.models.workflow import ResolvedNodePackage, ScoredMatch, WorkflowNodeWidgetRef


class InteractiveNodeStrategy(NodeResolutionStrategy):
    """Interactive node resolution with unified search."""

    def __init__(self, search_fn=None, installed_packages=None):
        """Initialize with search function and installed packages.

        Args:
            search_fn: GlobalNodeResolver.search_packages function
            installed_packages: Dict of installed packages for prioritization
        """
        self.search_fn = search_fn
        self.installed_packages = installed_packages or {}
        self._last_choice = None  # Track last user choice for optional detection

    def _unified_choice_prompt(self, prompt_text: str, num_options: int, has_browse: bool = False) -> str:
        """Unified choice prompt with inline manual/skip/optional options.

        Args:
            prompt_text: The choice prompt like "Choice [1]/m/o/s: "
            num_options: Number of valid numeric options (1-based)
            has_browse: Whether option 0 (browse) is available

        Returns:
            User's choice as string (number, 'm', 'o', 's', or '0' for browse)
        """
        while True:
            choice = input(prompt_text).strip().lower()

            # Default to '1' if empty
            if not choice:
                return "1"

            # Check special options
            if choice in ('m', 's', 'o'):
                return choice

            # Check browse option
            if has_browse and choice == '0':
                return '0'

            # Check numeric range
            if choice.isdigit():
                idx = int(choice)
                if 1 <= idx <= num_options:
                    return choice

            print("  Invalid choice, try again")

    def _get_manual_package_id(self, node_type: str) -> ResolvedNodePackage | None:
        """Get package ID from manual user input."""
        pkg_id = input("Enter package ID: ").strip()
        if not pkg_id:
            return None

        print(f"  Note: Package '{pkg_id}' will be verified during install")
        return ResolvedNodePackage(
            node_type=node_type,
            match_type="manual",
            package_id=pkg_id
        )
        
    def _get_optional_package(self, node_type: str) -> ResolvedNodePackage:
        """Get package ID from manual user input."""
        return ResolvedNodePackage(
            node_type=node_type,
            match_type="optional"
        )

    def resolve_unknown_node(
        self, node_type: str, possible: list[ResolvedNodePackage]
    ) -> ResolvedNodePackage | None:
        """Prompt user to resolve unknown node."""

        # Case 1: Ambiguous from global table (multiple matches)
        if possible and len(possible) > 1:
            return self._resolve_ambiguous(node_type, possible)

        # Case 2: Single match from global table - confirm
        # NOTE: Shouldn't be called since automatic resolution should handle this
        if len(possible) == 1:
            pkg = possible[0]
            print(f"\n✓ Found in registry: {pkg.package_id}")
            print(f"  For node: {node_type}")

            choice = input("Accept? [Y/n]: ").strip().lower()
            if choice in ('', 'y', 'yes'):
                return pkg
            # User rejected - fall through to search

        # Case 3: No matches or user rejected single match - use unified search
        print(f"\n⚠️  Node not found in registry: {node_type}")

        if self.search_fn:
            print("🔍 Searching packages...")

            results = self.search_fn(
                node_type=node_type,
                installed_packages=self.installed_packages,
                include_registry=True,
                limit=10
            )

            if results:
                return self._show_search_results(node_type, results)
            else:
                print("  No matches found")

        # No matches - offer manual entry, optional, or skip
        print("\nNo packages found.")
        print("  [m] - Manually enter package ID")
        print("  [o] - Mark as optional (workflow works without it)")
        print("  [s] - Skip (leave unresolved)")
        choice = self._unified_choice_prompt("Choice [m]/o/s: ", num_options=0, has_browse=False)

        if choice == 'm':
            self._last_choice = 'manual'
            return self._get_manual_package_id(node_type)
        elif choice == 'o':
            self._last_choice = 'optional'
            print(f"  ✓ Marked '{node_type}' as optional")
            return self._get_optional_package(node_type)
        self._last_choice = 'skip'
        return None

    def _resolve_ambiguous(
        self,
        node_type: str,
        possible: list[ResolvedNodePackage]
    ) -> ResolvedNodePackage | None:
        """Handle ambiguous matches from global table."""
        print(f"\n🔍 Found {len(possible)} matches for '{node_type}':")
        display_count = min(5, len(possible))
        for i, pkg in enumerate(possible[:display_count], 1):
            display_name = pkg.package_data.display_name if pkg.package_data else pkg.package_id
            desc = pkg.package_data.description if pkg.package_data else "No description"
            print(f"  {i}. {display_name or pkg.package_id}")
            if desc and len(desc) > 60:
                desc = desc[:57] + "..."
            print(f"     {desc}")

        has_browse = len(possible) > 5
        if has_browse:
            print(f"  0. Browse all {len(possible)} matches")

        print("\n  [1-9] - Select package to install")
        print("  [o]   - Mark as optional (workflow works without it)")
        print("  [m]   - Manually enter package ID")
        print("  [s]   - Skip (leave unresolved)")

        choice = self._unified_choice_prompt(
            "Choice [1]/o/m/s: ",
            num_options=display_count,
            has_browse=has_browse
        )

        if choice == 's':
            self._last_choice = 'skip'
            return None
        elif choice == 'o':
            # Return None to skip - caller will check _last_choice for optional
            self._last_choice = 'optional'
            print(f"  ✓ Marked '{node_type}' as optional")
            return self._get_optional_package(node_type)
        elif choice == 'm':
            self._last_choice = 'manual'
            return self._get_manual_package_id(node_type)
        elif choice == '0':
            self._last_choice = 'browse'
            selected = self._browse_all_packages(possible)
            if selected and selected != "BACK":
                return selected
            return None
        else:
            self._last_choice = 'select'
            idx = int(choice) - 1
            selected = possible[idx]
            # Update match_type to ensure it's saved to node_mappings
            # User selected from ambiguous list, so this counts as user confirmation
            return self._create_resolved_from_match(node_type, selected)

    def _show_search_results(
        self,
        node_type: str,
        results: list
    ) -> ResolvedNodePackage | None:
        """Show unified search results to user."""
        print(f"\nFound {len(results)} potential matches:\n")

        display_count = min(5, len(results))
        for i, match in enumerate(results[:display_count], 1):
            pkg_id = match.package_id
            desc = (match.package_data.description or "No description")[:60] if match.package_data else ""
            installed_marker = " (installed)" if pkg_id in self.installed_packages else ""

            print(f"  {i}. {pkg_id}{installed_marker}")
            if desc:
                print(f"     {desc}")
            print()

        has_browse = len(results) > 5
        if has_browse:
            print(f"  0. Browse all {len(results)} matches\n")

        choice = self._unified_choice_prompt(
            "Choice [1]/o/m/s: ",
            num_options=display_count,
            has_browse=has_browse
        )

        if choice == 's':
            self._last_choice = 'skip'
            return None
        elif choice == 'o':
            # Return None to skip - caller will check _last_choice for optional
            self._last_choice = 'optional'
            print(f"  ✓ Marked '{node_type}' as optional")
            return None
        elif choice == 'm':
            self._last_choice = 'manual'
            return self._get_manual_package_id(node_type)
        elif choice == '0':
            self._last_choice = 'browse'
            selected = self._browse_all_packages(results)
            if selected and selected != "BACK":
                print(f"\n✓ Selected: {selected.package_id}")
                return self._create_resolved_from_match(node_type, selected)
            return None
        else:
            self._last_choice = 'select'
            idx = int(choice) - 1
            selected = results[idx]
            print(f"\n✓ Selected: {selected.package_id}")
            return self._create_resolved_from_match(node_type, selected)

    def _create_resolved_from_match(
        self,
        node_type: str,
        match
    ) -> ResolvedNodePackage:
        """Create ResolvedNodePackage from user-confirmed match.

        Args:
            node_type: The node type being resolved
            match: Either a search result (with .score) or ResolvedNodePackage (with .match_confidence)

        Returns:
            ResolvedNodePackage with match_type="user_confirmed"
        """
        # Handle both search results and existing ResolvedNodePackage
        confidence = getattr(match, 'score', None) or getattr(match, 'match_confidence', 1.0)
        versions = getattr(match, 'versions', [])

        return ResolvedNodePackage(
            package_id=match.package_id,
            package_data=match.package_data,
            node_type=node_type,
            versions=versions,
            match_type="user_confirmed",
            match_confidence=confidence
        )

    def _browse_all_packages(self, results: list):
        """Browse all matches with pagination."""
        page = 0
        page_size = 10
        total_pages = (len(results) + page_size - 1) // page_size

        while True:
            start = page * page_size
            end = min(start + page_size, len(results))

            print(f"\nAll matches (Page {page + 1}/{total_pages}):\n")

            for i, match in enumerate(results[start:end], start + 1):
                pkg_id = match.package_id
                installed_marker = " (installed)" if pkg_id in self.installed_packages else ""
                print(f"  {i}. {pkg_id}{installed_marker}")

            print("\n[N]ext, [P]rev, number, [B]ack, or [Q]uit:")

            choice = input("Choice: ").strip().lower()

            if choice == 'n':
                if page < total_pages - 1:
                    page += 1
                else:
                    print("  Already on last page")
            elif choice == 'p':
                if page > 0:
                    page -= 1
                else:
                    print("  Already on first page")
            elif choice == 'b':
                return "BACK"
            elif choice == 'q':
                return None
            elif choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(results):
                    return results[idx]
                else:
                    print("  Invalid number")
            else:
                print("  Invalid choice")


    def confirm_node_install(self, package: ResolvedNodePackage) -> bool:
        """Always confirm since user already made the choice."""
        return True


class InteractiveModelStrategy(ModelResolutionStrategy):
    """Interactive model resolution with user prompts."""

    def __init__(self, search_fn=None):
        """Initialize with optional fuzzy search function."""
        self.search_fn = search_fn

    def _unified_choice_prompt(self, prompt_text: str, num_options: int, has_browse: bool = False) -> str:
        """Unified choice prompt with inline manual/skip/optional options.

        Args:
            prompt_text: The choice prompt like "Choice [1]/m/o/s: "
            num_options: Number of valid numeric options (1-based)
            has_browse: Whether option 0 (browse) is available

        Returns:
            User's choice as string (number, 'm', 'o', 's', or '0' for browse)
        """
        while True:
            choice = input(prompt_text).strip().lower()

            # Default to '1' if empty
            if not choice:
                return "1"

            # Check special options
            if choice in ('m', 's', 'o'):
                return choice

            # Check browse option
            if has_browse and choice == '0':
                return '0'

            # Check numeric range
            if choice.isdigit():
                idx = int(choice)
                if 1 <= idx <= num_options:
                    return choice

            print("  Invalid choice, try again")

    def resolve_ambiguous_model(
        self, reference: WorkflowNodeWidgetRef, candidates: list[ModelWithLocation]
    ) -> ModelWithLocation | None:
        """Prompt user to resolve ambiguous model."""
        print(f"\n🔍 Multiple matches for model in node #{reference.node_id}:")
        print(f"  Looking for: {reference.widget_value}")
        print("  Found matches:")

        display_count = min(10, len(candidates))
        for i, model in enumerate(candidates[:display_count], 1):
            size_mb = model.file_size / (1024 * 1024)
            print(f"  {i}. {model.relative_path} ({size_mb:.1f} MB)")

        print("\n  [1-9] - Select model as required")
        print("  [o]   - Mark as optional nice-to-have (select from above)")
        print("  [m]   - Manually enter model path")
        print("  [s]   - Skip (leave unresolved)")

        choice = self._unified_choice_prompt(
            "Choice [1]/o/m/s: ",
            num_options=display_count,
            has_browse=False
        )

        if choice == 's':
            return None
        elif choice == 'm':
            path = input("Enter model path: ").strip()
            if path:
                # Create a ModelWithLocation from the manual path
                # Note: This is a simplified version, actual implementation may vary
                print(f"  ⚠️  Manual path entry: {path}")
                print("  Path will be validated during workflow execution")
            return None
        elif choice == 'o':
            # User wants to mark as optional - prompt for which model
            model_choice = input("  Which model? [1]: ").strip() or "1"
            idx = int(model_choice) - 1
            selected = candidates[idx]
            # Mark model as optional by setting attribute
            selected._mark_as_optional = True
            print(f"  ✓ Selected as optional: {selected.relative_path}")
            return selected
        else:
            idx = int(choice) - 1
            selected = candidates[idx]
            print(f"  ✓ Selected: {selected.relative_path}")
            return selected

    def handle_missing_model(self, reference: WorkflowNodeWidgetRef) -> tuple[str, str] | None:
        """Prompt user for missing model."""
        print(f"\n⚠️  Model not found: {reference.widget_value}")
        print(f"  in node #{reference.node_id} ({reference.node_type})")

        # If we have fuzzy search, try it first
        if self.search_fn:
            print("\n🔍 Searching model index...")

            similar: list[ScoredMatch] | None = self.search_fn(
                missing_ref=reference.widget_value,
                node_type=reference.node_type,
                limit=10
            )

            if similar:
                return self._show_fuzzy_results(reference, similar)
            else:
                print("  No similar models found in index")

        # No matches - offer manual entry, optional, or skip
        print("\nNo models found.")
        print("  [m] - Manually enter model path")
        print("  [o] - Mark as optional (workflow works without it)")
        print("  [s] - Skip (leave unresolved)")
        choice = self._unified_choice_prompt("Choice [m]/o/s: ", num_options=0, has_browse=False)

        if choice == 'm':
            path = input("Enter model path: ").strip()
            if path:
                return ("select", path)
        elif choice == 'o':
            return ("optional_unresolved", "")
        return ("skip", "")

    def _show_fuzzy_results(self, reference: WorkflowNodeWidgetRef, results: list[ScoredMatch]) -> tuple[str, str] | None:
        """Show fuzzy search results and get user selection."""
        print(f"\nFound {len(results)} potential matches:\n")

        display_count = min(5, len(results))
        for i, match in enumerate(results[:display_count], 1):
            model = match.model
            size_gb = model.file_size / (1024 * 1024 * 1024)
            confidence = match.confidence.capitalize()
            print(f"  {i}. {model.relative_path} ({size_gb:.2f} GB)")
            print(f"     Hash: {model.hash[:12]}... | {confidence} confidence match\n")

        has_browse = len(results) > 5
        if has_browse:
            print(f"  0. Browse all {len(results)} matches\n")

        choice = self._unified_choice_prompt(
            "Choice [1]/m/o/s: ",
            num_options=display_count,
            has_browse=has_browse
        )

        if choice == 's':
            return ("skip", "")
        elif choice == 'm':
            path = input("Enter model path: ").strip()
            if path:
                return ("select", path)
            return ("skip", "")
        elif choice == 'o':
            return ("optional_unresolved", "")
        elif choice == '0':
            selected = self._browse_all_models(results)
            if selected and selected != "BACK":
                return ("select", selected.relative_path)
            return ("skip", "")
        else:
            idx = int(choice) - 1
            selected = results[idx].model
            print(f"\n✓ Selected: {selected.relative_path}")
            print(f"  Hash: {selected.hash[:12]}... | Size: {selected.file_size / (1024 * 1024 * 1024):.2f} GB")
            return ("select", selected.relative_path)

    def _browse_all_models(self, results: list[ScoredMatch]) -> ModelWithLocation | None:
        """Browse all fuzzy search results with pagination."""
        page = 0
        page_size = 10
        total_pages = (len(results) + page_size - 1) // page_size

        while True:
            start = page * page_size
            end = min(start + page_size, len(results))

            print(f"\nAll matches (Page {page + 1}/{total_pages}):\n")

            for i, match in enumerate(results[start:end], start + 1):
                model = match.model
                size_gb = model.file_size / (1024 * 1024 * 1024)
                print(f"  {i}. {model.relative_path} ({size_gb:.2f} GB)")

            print("\n[N]ext, [P]rev, number, [B]ack, or [Q]uit:")

            choice = input("Choice: ").strip().lower()

            if choice == 'n':
                if page < total_pages - 1:
                    page += 1
                else:
                    print("  Already on last page")
            elif choice == 'p':
                if page > 0:
                    page -= 1
                else:
                    print("  Already on first page")
            elif choice == 'b':
                return "BACK"
            elif choice == 'q':
                return None
            elif choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(results):
                    return results[idx].model
                else:
                    print("  Invalid number")
            else:
                print("  Invalid choice")


