# Workflow Commands

> Commands for managing and resolving workflow dependencies.


## `workflow`

**Usage:**

```bash
comfygit workflow [-h] {list,resolve,model} ...
```

### Subcommands


### `list`

**Usage:**

```bash
comfygit workflow list [-h]
```


### `resolve`

**Usage:**

```bash
comfygit workflow resolve [-h] [--auto] [--install] [--no-install] name
```

**Arguments:**

- `name` - Workflow name to resolve

**Options:**

- `--auto` - Auto-resolve without interaction (default: `False`)
- `--install` - Auto-install missing nodes without prompting (default: `False`)
- `--no-install` - Skip node installation prompt (default: `False`)


### `model`

**Usage:**

```bash
comfygit workflow model [-h] {importance} ...
```

#### Subcommands


#### `importance`

**Usage:**

```bash
comfygit workflow model importance [-h]
                                          [workflow_name] [model_identifier]
                                          [{required,flexible,optional}]
```

**Arguments:**

- `workflow_name` - Workflow name (interactive if omitted) (optional)
- `model_identifier` - Model filename or hash (interactive if omitted) (optional)
- `importance` - Importance level (optional)
