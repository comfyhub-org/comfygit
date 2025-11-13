# Environment Commands

> Commands for managing and operating within ComfyUI environments.


## `create`

**Usage:**

```bash
comfygit create [-h] [--template TEMPLATE] [--python PYTHON]
                       [--comfyui COMFYUI] [--torch-backend BACKEND] [--use]
                       name
```

**Arguments:**

- `name` - Environment name

**Options:**

- `--template` - Template manifest
- `--python` - Python version (default: `3.11`)
- `--comfyui` - ComfyUI version
- `--torch-backend` - PyTorch backend. Examples: auto (detect GPU), cpu, cu128 (CUDA 12.8), cu126, cu124, rocm6.3 (AMD), xpu (Intel). Default: auto (default: `auto`)
- `--use` - Set active environment after creation (default: `False`)


## `use`

**Usage:**

```bash
comfygit use [-h] name
```

**Arguments:**

- `name` - Environment name


## `delete`

**Usage:**

```bash
comfygit delete [-h] [-y] name
```

**Arguments:**

- `name` - Environment name

**Options:**

- `-y, --yes` - Skip confirmation (default: `False`)


## `run`

**Usage:**

```bash
comfygit run [-h] [--no-sync]
```

**Options:**

- `--no-sync` - Skip environment sync before running (default: `False`)


## `status`

**Usage:**

```bash
comfygit status [-h] [-v]
```

**Options:**

- `-v, --verbose` - Show full details (default: `False`)


## `manifest`

**Usage:**

```bash
comfygit manifest [-h] [--pretty] [--section SECTION]
```

**Options:**

- `--pretty` - Output as YAML instead of TOML (default: `False`)
- `--section` - Show specific section (e.g., tool.comfygit.nodes)


## `repair`

**Usage:**

```bash
comfygit repair [-h] [-y] [--models {all,required,skip}]
```

**Options:**

- `-y, --yes` - Skip confirmation (default: `False`)
- `--models` - Model download strategy: all (default), required only, or skip (choices: `all`, `required`, `skip`) (default: `all`)


## `commit`

**Usage:**

```bash
comfygit commit [-h] [-m MESSAGE] [--auto] [--allow-issues]
```

**Options:**

- `-m, --message` - Commit message (auto-generated if not provided)
- `--auto` - Auto-resolve issues without interaction (default: `False`)
- `--allow-issues` - Allow committing workflows with unresolved issues (default: `False`)


## `rollback`

**Usage:**

```bash
comfygit rollback [-h] [-y] [--force] [target]
```

**Arguments:**

- `target` - Version to rollback to (e.g., 'v1', 'v2') - leave empty to discard uncommitted changes (optional)

**Options:**

- `-y, --yes` - Skip confirmation (default: `False`)
- `--force` - Force rollback, discarding uncommitted changes without error (default: `False`)


## `pull`

**Usage:**

```bash
comfygit pull [-h] [-r REMOTE] [--models {all,required,skip}] [--force]
```

**Options:**

- `-r, --remote` - Git remote name (default: origin) (default: `origin`)
- `--models` - Model download strategy (default: all) (choices: `all`, `required`, `skip`) (default: `all`)
- `--force` - Discard uncommitted changes and force pull (default: `False`)


## `push`

**Usage:**

```bash
comfygit push [-h] [-r REMOTE] [--force]
```

**Options:**

- `-r, --remote` - Git remote name (default: origin) (default: `origin`)
- `--force` - Force push using --force-with-lease (overwrite remote) (default: `False`)


## `remote`

**Usage:**

```bash
comfygit remote [-h] {add,remove,list} ...
```

### Subcommands


### `add`

**Usage:**

```bash
comfygit remote add [-h] name url
```

**Arguments:**

- `name` - Remote name (e.g., origin)
- `url` - Remote URL


### `remove`

**Usage:**

```bash
comfygit remote remove [-h] name
```

**Arguments:**

- `name` - Remote name to remove


### `list`

**Usage:**

```bash
comfygit remote list [-h]
```
