# lvl3dev-todoist-cli

Simple command-line interface for Todoist using the official `todoist-api-python` SDK.

## Development setup (uv)

```bash
uv sync
```

Run commands through `uv`:

```bash
uv run todoist --help
```

## Build and install (uv + pipx)

Build a wheel with `uv`:

```bash
uv build
```

Install globally with `pipx` from the built wheel:

```bash
pipx install dist/lvl3dev_todoist_cli-*.whl
```

For local iteration, reinstall after changes with:

```bash
pipx install --force dist/lvl3dev_todoist_cli-*.whl
```

## Authentication

Set your API token:

```bash
export TODOIST_API_TOKEN="YOUR_API_TOKEN"
```

You can also pass `--token` per command.

## Usage

```bash
todoist --help
```

### Tasks

```bash
todoist tasks list
todoist tasks add "Pay rent" --due-string "tomorrow 9am" --priority 1
todoist tasks get <task_id>
todoist tasks update <task_id> --content "Pay rent and utilities"
todoist tasks complete <task_id>
todoist tasks delete <task_id>
```

Priority values are user-facing Todoist priorities: `p1` highest, `p4` lowest.

### Projects

```bash
todoist projects list
todoist projects add "Operations"
todoist projects update <project_id> "Ops"
```

### Comments

```bash
todoist comments list --task-id <task_id>
todoist comments add --task-id <task_id> "Started work"
```

### Labels

```bash
todoist labels list
```

### JSON Output

Use `--json` to get structured output:

```bash
todoist --json tasks list
```
