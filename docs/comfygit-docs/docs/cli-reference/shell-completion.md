# Shell Completion

> Enable tab completion for ComfyDock CLI commands in your shell.

## Overview

ComfyDock supports tab completion for bash, zsh, and fish shells. Tab completion helps you:

- Autocomplete command names
- Autocomplete environment names
- Autocomplete node names
- Autocomplete workflow names

## Installation

Install tab completion for your current shell:

```bash
cfd completion install
```

This will detect your shell automatically and install the appropriate completion script.

## Check Status

Check if tab completion is installed:

```bash
cfd completion status
```

## Uninstall

Remove tab completion:

```bash
cfd completion uninstall
```

## Supported Shells

- **Bash** - Requires bash-completion package
- **Zsh** - Works with default zsh completion system
- **Fish** - Works with fish's built-in completion

## Manual Setup

If automatic installation doesn't work, you can set up completion manually:

### Bash

Add to `~/.bashrc`:

```bash
eval "$(register-python-argcomplete cfd)"
```

### Zsh

Add to `~/.zshrc`:

```bash
eval "$(register-python-argcomplete cfd)"
```

### Fish

Run:

```bash
register-python-argcomplete --shell fish cfd > ~/.config/fish/completions/cfd.fish
```

## Troubleshooting

If tab completion isn't working:

1. Restart your shell or run `source ~/.bashrc` (or equivalent)
2. Verify argcomplete is installed: `pip show argcomplete`
3. Check completion status: `cfd completion status`
4. Try manual setup if automatic installation fails
