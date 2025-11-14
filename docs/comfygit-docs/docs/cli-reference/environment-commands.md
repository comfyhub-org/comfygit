# Environment Commands

> Commands for managing and operating within ComfyUI environments.


## `create`

**Usage:**

```bash
cg create [-h] [--template TEMPLATE] [--python PYTHON]
                 [--comfyui COMFYUI] [--torch-backend BACKEND] [--use] [-y]
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
- `-y, --yes` - Skip confirmation prompts, use defaults for workspace initialization (default: `False`)


## `use`

**Usage:**

```bash
cg use [-h] name
```

**Arguments:**

- `name` - Environment name


## `delete`

**Usage:**

```bash
cg delete [-h] [-y] name
```

**Arguments:**

- `name` - Environment name

**Options:**

- `-y, --yes` - Skip confirmation (default: `False`)


## `run`

**Usage:**

```bash
cg run [-h] [--no-sync]
```

**Options:**

- `--no-sync` - Skip environment sync before running (default: `False`)


## `status`

**Usage:**

```bash
cg status [-h] [-v]
```

**Options:**

- `-v, --verbose` - Show full details (default: `False`)


## `manifest`

**Usage:**

```bash
cg manifest [-h] [--pretty] [--section SECTION]
```

**Options:**

- `--pretty` - Output as YAML instead of TOML (default: `False`)
- `--section` - Show specific section (e.g., tool.comfygit.nodes)


## `repair`

**Usage:**

```bash
cg repair [-h] [-y] [--models {all,required,skip}]
```

**Options:**

- `-y, --yes` - Skip confirmation (default: `False`)
- `--models` - Model download strategy: all (default), required only, or skip (choices: `all`, `required`, `skip`) (default: `all`)


## `log`

**Usage:**

```bash
cg log [-h] [-v]
```

**Options:**

- `-v, --verbose` - Show full details (default: `False`)


## `commit`

**Usage:**

```bash
cg commit [-h] [-m MESSAGE] [--auto] [--allow-issues]
```

**Options:**

- `-m, --message` - Commit message (auto-generated if not provided)
- `--auto` - Auto-resolve issues without interaction (default: `False`)
- `--allow-issues` - Allow committing workflows with unresolved issues (default: `False`)


## `rollback`

**Usage:**

```bash
cg rollback [-h] [-y] [--force] [target]
```

**Arguments:**

- `target` - Version to rollback to (e.g., 'v1', 'v2') - leave empty to discard uncommitted changes (optional)

**Options:**

- `-y, --yes` - Skip confirmation (default: `False`)
- `--force` - Force rollback, discarding uncommitted changes without error (default: `False`)


## `pull`

**Usage:**

```bash
cg pull [-h] [-r REMOTE] [--models {all,required,skip}] [--force]
```

**Options:**

- `-r, --remote` - Git remote name (default: origin) (default: `origin`)
- `--models` - Model download strategy (default: all) (choices: `all`, `required`, `skip`) (default: `all`)
- `--force` - Discard uncommitted changes and force pull (default: `False`)


## `push`

**Usage:**

```bash
cg push [-h] [-r REMOTE] [--force]
```

**Options:**

- `-r, --remote` - Git remote name (default: origin) (default: `origin`)
- `--force` - Force push using --force-with-lease (overwrite remote) (default: `False`)


## `remote`

**Usage:**

```bash
cg remote [-h] {add,remove,list} ...
```

### Subcommands


### `add`

**Usage:**

```bash
cg remote add [-h] name url
```

**Arguments:**

- `name` - Remote name (e.g., origin)
- `url` - Remote URL


### `remove`

**Usage:**

```bash
cg remote remove [-h] name
```

**Arguments:**

- `name` - Remote name to remove


### `list`

**Usage:**

```bash
cg remote list [-h]
```


## `py`

**Usage:**

```bash
cg py [-h] {add,remove,remove-group,list,uv} ...
```

### Subcommands


### `add`

**Usage:**

```bash
cg py add [-h] [-r REQUIREMENTS] [--upgrade] [--group GROUP] [--dev]
                 [--editable] [--bounds {lower,major,minor,exact}]
                 [packages ...]
```

**Arguments:**

- `packages` - Package specifications (e.g., requests>=2.0.0) (multiple values allowed)

**Options:**

- `-r, --requirements` - Add packages from requirements.txt file
- `--upgrade` - Upgrade existing packages (default: `False`)
- `--group` - Add to dependency group (e.g., optional-cuda)
- `--dev` - Add to dev dependencies (default: `False`)
- `--editable` - Install as editable (for local development) (default: `False`)
- `--bounds` - Version specifier style (choices: `lower`, `major`, `minor`, `exact`)


### `remove`

**Usage:**

```bash
cg py remove [-h] [--group GROUP] packages [packages ...]
```

**Arguments:**

- `packages` - Package names to remove (multiple values allowed)

**Options:**

- `--group` - Remove packages from dependency group instead of main dependencies


### `remove-group`

**Usage:**

```bash
cg py remove-group [-h] group
```

**Arguments:**

- `group` - Dependency group name to remove


### `list`

**Usage:**

```bash
cg py list [-h] [--all]
```

**Options:**

- `--all` - Show all dependencies including dependency groups (default: `False`)


### `uv`

**Usage:**

```bash
cg py uv ...
```

**Arguments:**

- `uv_args` - UV command and arguments (e.g., 'add --group optional-cuda sageattention')


## `constraint`

**Usage:**

```bash
cg constraint [-h] {add,list,remove} ...
```

### Subcommands


### `add`

**Usage:**

```bash
cg constraint add [-h] packages [packages ...]
```

**Arguments:**

- `packages` - Package specifications (e.g., torch==2.4.1) (multiple values allowed)


### `list`

**Usage:**

```bash
cg constraint list [-h]
```


### `remove`

**Usage:**

```bash
cg constraint remove [-h] packages [packages ...]
```

**Arguments:**

- `packages` - Package names to remove (multiple values allowed)
