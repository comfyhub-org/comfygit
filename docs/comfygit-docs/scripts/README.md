# Documentation Scripts

## generate_cli_reference.py

Automatically generates CLI reference documentation from the argparse parser.

### Usage

```bash
# From docs/comfygit-docs directory
make generate-cli

# Or run directly
python scripts/generate_cli_reference.py
```

### What it does

1. Imports the CLI parser from `comfygit_cli.cli`
2. Extracts command structure, arguments, options, and help text
3. Generates markdown files for each command category:
   - `global-commands.md` - Workspace-level commands
   - `environment-commands.md` - Environment management commands
   - `node-commands.md` - Custom node operations
   - `workflow-commands.md` - Workflow management
   - `shell-completion.md` - Shell completion setup (manual content)

### Output location

Generated files are written to: `docs/cli-reference/`

### When to run

- After adding new CLI commands
- After modifying command arguments or options
- After changing help text
- Before building documentation: `make build` runs this automatically

### Customization

The generator provides baseline documentation. To enhance:

1. Edit the generated markdown files directly
2. Add examples, tips, and cross-references
3. Improve descriptions beyond help text
4. Re-running the generator will overwrite changes

For persistent enhancements, modify the generator script itself or switch to manual documentation.

### Architecture

- **Command categorization**: Defined in `categorize_commands()`
- **Markdown formatting**: Handled by `format_option()`, `format_argument()`
- **Recursive parsing**: Handles nested subcommands (e.g., `model index find`)
- **Manual overrides**: Shell completion page uses manual content
