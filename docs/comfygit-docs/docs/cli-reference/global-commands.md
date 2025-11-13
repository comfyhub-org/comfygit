# Global Commands

> Workspace-level commands that operate on the entire ComfyDock workspace.


## `init`

**Usage:**

```bash
comfygit init [-h] [--models-dir MODELS_DIR] [--yes] [path]
```

**Arguments:**

- `path` - Workspace directory (default: ~/comfygit) (optional)

**Options:**

- `--models-dir` - Path to existing models directory to index
- `--yes, -y` - Use all defaults, no interactive prompts (default: `False`)


## `list`

**Usage:**

```bash
comfygit list [-h]
```


## `import`

**Usage:**

```bash
comfygit import [-h] [--name NAME] [--branch BRANCH]
                       [--torch-backend BACKEND] [--use]
                       [path]
```

**Arguments:**

- `path` - Path to .tar.gz file or git repository URL (use #subdirectory for subdirectory imports) (optional)

**Options:**

- `--name` - Name for imported environment (skip prompt)
- `--branch, -b` - Git branch, tag, or commit to import (git imports only)
- `--torch-backend` - PyTorch backend. Examples: auto (detect GPU), cpu, cu128 (CUDA 12.8), cu126, cu124, rocm6.3 (AMD), xpu (Intel). Default: auto (default: `auto`)
- `--use` - Set imported environment as active (default: `False`)


## `export`

**Usage:**

```bash
comfygit export [-h] [--allow-issues] [path]
```

**Arguments:**

- `path` - Path to output file (optional)

**Options:**

- `--allow-issues` - Skip confirmation if models are missing source URLs (default: `False`)


## `model`

**Usage:**

```bash
comfygit model [-h] {index,download,add-source} ...
```

### Subcommands


### `index`

**Usage:**

```bash
comfygit model index [-h] {find,list,show,status,sync,dir} ...
```

#### Subcommands


#### `find`

**Usage:**

```bash
comfygit model index find [-h] query
```

**Arguments:**

- `query` - Search query (hash prefix or filename)


#### `list`

**Usage:**

```bash
comfygit model index list [-h]
```


#### `show`

**Usage:**

```bash
comfygit model index show [-h] identifier
```

**Arguments:**

- `identifier` - Model hash, hash prefix, filename, or path


#### `status`

**Usage:**

```bash
comfygit model index status [-h]
```


#### `sync`

**Usage:**

```bash
comfygit model index sync [-h]
```


#### `dir`

**Usage:**

```bash
comfygit model index dir [-h] path
```

**Arguments:**

- `path` - Path to models directory


### `download`

**Usage:**

```bash
comfygit model download [-h] [--path PATH] [-c CATEGORY] [-y] url
```

**Arguments:**

- `url` - Model download URL (Civitai, HuggingFace, or direct)

**Options:**

- `--path` - Target path relative to models directory (e.g., checkpoints/model.safetensors)
- `-c, --category` - Model category for auto-path (e.g., checkpoints, loras, vae)
- `-y, --yes` - Skip path confirmation prompt (default: `False`)


### `add-source`

**Usage:**

```bash
comfygit model add-source [-h] [model] [url]
```

**Arguments:**

- `model` - Model filename or hash (omit for interactive mode) (optional)
- `url` - Download URL (optional)


## `registry`

**Usage:**

```bash
comfygit registry [-h] {status,update} ...
```

### Subcommands


### `status`

**Usage:**

```bash
comfygit registry status [-h]
```


### `update`

**Usage:**

```bash
comfygit registry update [-h]
```


## `config`

**Usage:**

```bash
comfygit config [-h] [--civitai-key CIVITAI_KEY] [--show]
```

**Options:**

- `--civitai-key` - Set Civitai API key (use empty string to clear)
- `--show` - Show current configuration (default: `False`)


## `completion`

**Usage:**

```bash
comfygit completion [-h] {install,uninstall,status} ...
```

### Subcommands


### `install`

**Usage:**

```bash
comfygit completion install [-h]
```


### `uninstall`

**Usage:**

```bash
comfygit completion uninstall [-h]
```


### `status`

**Usage:**

```bash
comfygit completion status [-h]
```
