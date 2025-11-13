# ComfyGit Documentation

Documentation site for ComfyGit v1.0+ - the package and environment manager for ComfyUI.

## Quick Start

### Install dependencies

```bash
uv sync
```

### Generate CLI reference

```bash
make generate-cli
```

This extracts command documentation from the argparse parser and generates markdown files in `docs/cli-reference/`.

### Local development

```bash
make serve
```

Visit `http://127.0.0.1:8000` to view the docs. CLI reference is regenerated automatically.

### Build static site

```bash
make build
```

Output will be in `site/` directory. CLI reference is regenerated automatically.

### Deploy to GitHub Pages

```bash
mkdocs gh-deploy
```

## Documentation Structure

```
docs/
├── index.md                          # Landing page
├── getting-started/                  # ✅ Phase 1 Complete
│   ├── installation.md
│   ├── quickstart.md
│   ├── concepts.md
│   └── migrating-from-v0.md
├── user-guide/                       # 🚧 Phase 2 TODO
│   ├── workspaces.md
│   ├── environments/
│   ├── custom-nodes/
│   ├── models/
│   ├── workflows/
│   ├── python-dependencies/
│   └── collaboration/
├── cli-reference/                    # ✅ Auto-generated from argparse
│   ├── global-commands.md
│   ├── environment-commands.md
│   ├── node-commands.md
│   ├── workflow-commands.md
│   └── shell-completion.md
├── troubleshooting/                  # 🚧 Phase 4 TODO
│   ├── common-issues.md
│   └── ...
└── legacy/                           # Old v0.x docs (Docker-based)
    └── ...
```

## Status

**Phase 1 (Complete)**: ✅ Getting Started section with 4 comprehensive guides

See `DOCUMENTATION_STATUS.md` for detailed roadmap and progress tracking.

## Writing Guidelines

### Tone

Follow Anthropic Claude Code documentation style:

- Friendly and conversational
- Practical, example-driven
- Progressive disclosure (beginner → advanced)
- Use "you" and "your"
- Clear, actionable instructions

### Structure

Each guide should include:

1. Title + one-line description
2. Prerequisites (if any)
3. Core content with examples
4. Common variations
5. Troubleshooting tips
6. Next steps with links

## CLI Reference

The CLI reference documentation is **automatically generated** from the argparse parser.

### How it works

- `scripts/generate_cli_reference.py` extracts command structure from `comfygit_cli.cli`
- Generates markdown for arguments, options, subcommands
- Runs automatically on `make build` and `make serve`

### When to regenerate

- After adding/modifying CLI commands
- After changing help text
- Run manually: `make generate-cli`

### Enhancing generated docs

Generated docs provide baseline coverage. To enhance:

1. **Edit generated files** - Add examples, tips (overwritten on regeneration)
2. **Modify generator** - Edit `scripts/generate_cli_reference.py` for persistent changes
3. **Switch to manual** - Stop using generator, maintain manually

See `scripts/README.md` for details.

## Contributing

1. Create new .md file in appropriate section
2. Follow tone and structure guidelines
3. Add to `mkdocs.yml` nav
4. Test locally with `make serve`
5. Submit PR

See `DOCUMENTATION_STATUS.md` for what needs writing.

## Files of Note

- `mkdocs.yml` - Site configuration and navigation
- `docs/index.md` - Landing page
- `docs/stylesheets/extra.css` - Custom CSS
- `DOCUMENTATION_STATUS.md` - Detailed status and roadmap

## Questions?

- GitHub Issues: https://github.com/comfyhub-org/comfygit/issues
- GitHub Discussions: https://github.com/comfyhub-org/comfygit/discussions

