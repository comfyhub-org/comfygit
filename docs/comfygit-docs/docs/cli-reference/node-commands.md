# Node Commands

> Commands for managing custom nodes within an environment.


## `node`

**Usage:**

```bash
comfygit node [-h] {add,remove,prune,list,update} ...
```

### Subcommands


### `add`

**Usage:**

```bash
comfygit node add [-h] [--dev] [--no-test] [--force]
                         node_names [node_names ...]
```

**Arguments:**

- `node_names` - Node identifier(s): registry-id[@version], github-url[@ref], or directory name (multiple values allowed)

**Options:**

- `--dev` - Track existing local development node (default: `False`)
- `--no-test` - Don't test resolution (default: `False`)
- `--force` - Force overwrite existing directory (default: `False`)


### `remove`

**Usage:**

```bash
comfygit node remove [-h] [--dev] node_names [node_names ...]
```

**Arguments:**

- `node_names` - Node registry ID(s) or name(s) (multiple values allowed)

**Options:**

- `--dev` - Remove development node specifically (default: `False`)


### `prune`

**Usage:**

```bash
comfygit node prune [-h] [--exclude PACKAGE [PACKAGE ...]] [-y]
```

**Options:**

- `--exclude` - Package IDs to keep even if unused
- `-y, --yes` - Skip confirmation prompt (default: `False`)


### `list`

**Usage:**

```bash
comfygit node list [-h]
```


### `update`

**Usage:**

```bash
comfygit node update [-h] [-y] [--no-test] node_name
```

**Arguments:**

- `node_name` - Node identifier or name to update

**Options:**

- `-y, --yes` - Auto-confirm updates (skip prompts) (default: `False`)
- `--no-test` - Don't test resolution (default: `False`)
